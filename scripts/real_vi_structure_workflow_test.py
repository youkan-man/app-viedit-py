from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, Route, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lvkit.extractor import extract_vi_xml  # noqa: E402

from app.component_model import DatasetComponentModel  # noqa: E402
from app.lvkit_semantic_runtime import build_authoritative_semantic_vi  # noqa: E402
from app.model_graph import build_model_graph  # noqa: E402
from app.semantic_enrichment import enrich_semantic_vi  # noqa: E402
from app.semantic_vi import build_semantic_vi  # noqa: E402
from semantic_structure_frame_audit import REAL_VIS, SOURCE_COMMIT, download  # noqa: E402

PORT = int(os.getenv("VI_REAL_STRUCTURE_WORKFLOW_PORT", "8091"))
BASE_URL = f"http://127.0.0.1:{PORT}"
ARTIFACTS = Path(
    os.getenv(
        "BUILD_ARTIFACT_DIR",
        str(ROOT / "artifacts" / "real-structure-workflow"),
    )
)


def wait_for_server(process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output, _ = process.communicate(timeout=3)
            raise RuntimeError(f"application exited before ready:\n{output}")
        try:
            with urllib.request.urlopen(f"{BASE_URL}/api/health", timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("application did not become ready")


def candidate_score(item: dict[str, Any]) -> tuple[int, int, int, str]:
    frames = item.get("structure_frames") or []
    populated = [frame for frame in frames if frame.get("object_ids")]
    distinct = len(
        {
            tuple(sorted(str(value) for value in frame.get("object_ids") or []))
            for frame in populated
        }
    )
    return (
        distinct,
        sum(len(frame.get("object_ids") or []) for frame in populated),
        len(frames),
        str(item.get("name") or ""),
    )


def build_candidate() -> tuple[dict[str, Any], dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="real-structure-workflow-") as directory:
        root = Path(directory)
        errors: list[str] = []
        for name, relative in REAL_VIS:
            source = root / name
            dataset = root / f"{source.stem}-dataset"
            dataset.mkdir()
            try:
                download(relative, source)
                _, _, main_xml = extract_vi_xml(
                    source,
                    output_dir=dataset,
                    force=True,
                )
                model = DatasetComponentModel.analyze(
                    dataset,
                    max_bytes=128 * 1024 * 1024,
                )
                graph = build_model_graph(model)
                fallback = enrich_semantic_vi(
                    model,
                    graph,
                    build_semantic_vi(model, graph),
                )
                vi = build_authoritative_semantic_vi(
                    dataset,
                    model,
                    fallback,
                    main_xml=main_xml,
                )
                candidates = [
                    item
                    for item in vi.get("objects", [])
                    if item.get("surface") == "block-diagram"
                    and len(item.get("structure_frames") or []) > 1
                    and len(
                        {
                            tuple(
                                sorted(
                                    str(value)
                                    for value in frame.get("object_ids") or []
                                )
                            )
                            for frame in item.get("structure_frames") or []
                            if frame.get("object_ids")
                        }
                    )
                    > 1
                ]
                if not candidates:
                    continue
                structure = max(candidates, key=candidate_score)
                return (
                    {
                        "summary": {"failed_files": 0},
                        "warnings": list(vi.get("warnings") or []),
                        "graph": copy.deepcopy(graph),
                        "vi": copy.deepcopy(vi),
                    },
                    {
                        "repository": "JKISoftware/JKI-EasyXML",
                        "commit": SOURCE_COMMIT,
                        "path": relative,
                        "name": name,
                        "structure_id": structure["id"],
                        "structure_name": structure.get("name"),
                        "frame_count": len(structure.get("structure_frames") or []),
                        "score": candidate_score(structure),
                    },
                )
            except Exception as error:
                errors.append(f"{name}: {type(error).__name__}: {error}")
        raise AssertionError(
            "no visible real-VI Structure with two populated frames; "
            + "; ".join(errors)
        )


def job() -> dict[str, Any]:
    return {
        "job_id": "real-structure-workflow",
        "status": "ready",
        "component_modified_at": "2026-09-11T02:20:00Z",
        "xml_modified_at": "2026-09-11T02:20:00Z",
        "files": [],
    }


def route_payload(page: Page, payload: dict[str, Any]) -> None:
    def model_route(route: Route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload, ensure_ascii=False),
        )

    page.route("**/api/jobs/real-structure-workflow/model*", model_route)


def require(condition: bool, message: str, diagnostics: dict[str, Any]) -> None:
    if not condition:
        diagnostics["failures"].append(message)


def box_close(
    first: dict[str, float] | None,
    second: dict[str, float] | None,
    tolerance: float = 1.0,
) -> bool:
    if not first or not second:
        return False
    return all(
        abs(float(first[key]) - float(second[key])) <= tolerance
        for key in ("x", "y", "width", "height")
    )


def frame_state(page: Page, structure_id: str) -> dict[str, Any]:
    return page.evaluate(
        """structureId => {
          const S = window.VISemanticEditor.S;
          const structure = S.objects.get(structureId);
          const frames = structure?.structure_frames || [];
          const index = Number(structure?.active_frame_index || 0);
          const activeIds = frames[index]?.object_ids || [];
          const inactiveIds = frames.flatMap((frame, frameIndex) => (
            frameIndex === index ? [] : (frame.object_ids || [])
          ));
          return {
            index,
            label: structure?.active_frame_label || null,
            activeIds,
            inactiveIds,
            activeVisible: activeIds.filter(id => Boolean(
              document.querySelector(`[data-object-id="${CSS.escape(id)}"]`)
            )),
            inactiveVisible: inactiveIds.filter(id => Boolean(
              document.querySelector(`[data-object-id="${CSS.escape(id)}"]`)
            )),
            selected: S.selected,
            box: S.box ? {...S.box} : null,
            wires: [...S.wires.keys()].sort(),
            nets: (S.vi.nets || []).map(net => net.id).sort(),
            hiddenObjects: S.vi.integrity?.structure_frame_runtime
              ?.inactive_object_count,
            hiddenWires: S.vi.integrity?.structure_frame_runtime
              ?.inactive_wire_count,
          };
        }""",
        structure_id,
    )


def visible_frame_pairs(page: Page, structure_id: str) -> list[dict[str, Any]]:
    return page.evaluate(
        """structureId => {
          const structure = window.VISemanticEditor.S.objects.get(structureId);
          const frames = structure?.structure_frames || [];
          const populated = frames
            .map((frame, index) => ({
              index,
              label: frame.label || frame.selector_value || frame.name || `Frame ${index}`,
              ids: [...(frame.object_ids || [])],
            }))
            .filter(frame => frame.ids.length);
          for (let first = 0; first < populated.length; first += 1) {
            for (let second = first + 1; second < populated.length; second += 1) {
              const left = new Set(populated[first].ids);
              const right = new Set(populated[second].ids);
              const leftOnly = populated[first].ids.filter(id => !right.has(id));
              const rightOnly = populated[second].ids.filter(id => !left.has(id));
              if (leftOnly.length && rightOnly.length) {
                return [{...populated[first], exclusive: leftOnly}, {
                  ...populated[second], exclusive: rightOnly,
                }];
              }
            }
          }
          return [];
        }""",
        structure_id,
    )


def stale_wire_endpoints(page: Page) -> list[dict[str, Any]]:
    return page.evaluate(
        """() => {
          const S = window.VISemanticEditor.S;
          const errors = [];
          for (const [id, wire] of S.wires) {
            const terminalIds = [
              wire.source_terminal_id,
              ...(wire.target_terminal_ids || []),
            ].filter(Boolean);
            const hidden = terminalIds.filter(terminalId => {
              const item = S.objects.get(terminalId);
              return !item || item.surface !== 'block-diagram';
            });
            if (hidden.length) errors.push({id, hidden});
          }
          return errors;
        }"""
    )


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    payload, source = build_candidate()
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".sandbox-real-structure-workflow-jobs"),
        }
    )
    process = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    diagnostics: dict[str, Any] = {
        "source": source,
        "failures": [],
        "console_errors": [],
        "page_errors": [],
    }
    try:
        wait_for_server(process)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()
            page.set_default_timeout(12_000)
            page.on(
                "console",
                lambda message: diagnostics["console_errors"].append(message.text)
                if message.type == "error"
                else None,
            )
            page.on(
                "pageerror",
                lambda error: diagnostics["page_errors"].append(str(error)),
            )
            route_payload(page, payload)
            value = job()
            page.goto(BASE_URL, wait_until="networkidle")
            page.wait_for_function("() => Boolean(window.viPages && window.viModelGraph)")
            page.evaluate("job => window.viPages.setJob(job, {openModel: true})", value)
            page.evaluate("async job => { await window.viModelGraph.setJob(job); }", value)
            page.wait_for_function(
                """() => Boolean(
                  window.VIStructureWorkflow?.ready
                  && window.VIReadability?.ready
                  && window.VICanvasDensity?.ready
                )"""
            )
            page.locator('[data-vi-surface="block-diagram"]').click()
            structure_id = str(source["structure_id"])
            page.evaluate(
                "id => window.VISemanticEditor.select(id, true)",
                structure_id,
            )
            page.wait_for_selector("#vi-structure-frame-workflow:not([hidden])")
            pairs = visible_frame_pairs(page, structure_id)
            diagnostics["frames"] = pairs
            require(len(pairs) == 2, "real Structure has no distinct populated frame pair", diagnostics)
            if len(pairs) == 2:
                first, second = pairs
                first_view = {"x": 20.0, "y": 20.0, "width": 920.0, "height": 620.0}
                second_view = {"x": 130.0, "y": 70.0, "width": 780.0, "height": 540.0}

                page.evaluate(
                    "([id, index]) => window.VIStructureWorkflow.switchFrame(id, index)",
                    [structure_id, first["index"]],
                )
                page.wait_for_function(
                    "([id, index]) => window.VISemanticEditor.S.objects.get(id)?.active_frame_index === index",
                    [structure_id, first["index"]],
                )
                page.evaluate(
                    "box => window.VICanvasDensity.applyBox(box, 'manual', {remember: true})",
                    first_view,
                )
                page.evaluate(
                    "id => window.VISemanticEditor.select(id, false)",
                    first["exclusive"][0],
                )
                first_state = frame_state(page, structure_id)
                diagnostics["first"] = first_state
                require(
                    first["exclusive"][0] in first_state["activeVisible"],
                    "first real frame did not render its exclusive object",
                    diagnostics,
                )
                require(
                    not set(second["exclusive"]) & set(first_state["inactiveVisible"]),
                    "inactive real-frame objects leaked into the first frame",
                    diagnostics,
                )
                require(
                    not stale_wire_endpoints(page),
                    "first real frame retained stale wire endpoints",
                    diagnostics,
                )

                page.evaluate(
                    "([id, index]) => window.VIStructureWorkflow.switchFrame(id, index)",
                    [structure_id, second["index"]],
                )
                page.wait_for_function(
                    "([id, index]) => window.VISemanticEditor.S.objects.get(id)?.active_frame_index === index",
                    [structure_id, second["index"]],
                )
                page.evaluate(
                    "box => window.VICanvasDensity.applyBox(box, 'manual', {remember: true})",
                    second_view,
                )
                page.evaluate(
                    "id => window.VISemanticEditor.select(id, false)",
                    second["exclusive"][0],
                )
                second_state = frame_state(page, structure_id)
                diagnostics["second"] = second_state
                require(
                    second["exclusive"][0] in second_state["activeVisible"],
                    "second real frame did not render its exclusive object",
                    diagnostics,
                )
                require(
                    not set(first["exclusive"]) & set(second_state["inactiveVisible"]),
                    "inactive real-frame objects leaked into the second frame",
                    diagnostics,
                )
                require(
                    not stale_wire_endpoints(page),
                    "second real frame retained stale wire endpoints",
                    diagnostics,
                )

                page.evaluate(
                    "([id, index]) => window.VIStructureWorkflow.switchFrame(id, index)",
                    [structure_id, first["index"]],
                )
                page.wait_for_timeout(150)
                first_restored = frame_state(page, structure_id)
                diagnostics["first_restored"] = first_restored
                require(
                    first_restored["selected"] == first["exclusive"][0],
                    "real first-frame selection was not restored",
                    diagnostics,
                )
                require(
                    box_close(first_restored["box"], first_view),
                    "real first-frame view was not restored",
                    diagnostics,
                )

                page.evaluate(
                    "([id, index]) => window.VIStructureWorkflow.switchFrame(id, index)",
                    [structure_id, second["index"]],
                )
                page.wait_for_timeout(150)
                second_restored = frame_state(page, structure_id)
                diagnostics["second_restored"] = second_restored
                require(
                    second_restored["selected"] == second["exclusive"][0],
                    "real second-frame selection was not restored",
                    diagnostics,
                )
                require(
                    box_close(second_restored["box"], second_view),
                    "real second-frame view was not restored",
                    diagnostics,
                )

            page.screenshot(
                path=str(ARTIFACTS / "real-structure-workflow-1440x900.png"),
                full_page=False,
            )
            context.close()
            browser.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
        if process.stdout:
            output = process.stdout.read()
            if output:
                print("REAL_STRUCTURE_WORKFLOW_APPLICATION_LOG=" + output[-4000:].replace("\n", "\\n"))

    (ARTIFACTS / "real-structure-workflow.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "REAL_STRUCTURE_WORKFLOW_JSON="
        + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
    )
    failed = bool(
        diagnostics["failures"]
        or diagnostics["console_errors"]
        or diagnostics["page_errors"]
    )
    print(
        "REAL_STRUCTURE_WORKFLOW_TEST_FAILED"
        if failed
        else "REAL_STRUCTURE_WORKFLOW_TEST_OK"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
