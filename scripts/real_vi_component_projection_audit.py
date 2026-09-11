from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections import Counter
from pathlib import Path
from statistics import median
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
from scripts.semantic_structure_frame_audit import (  # noqa: E402
    REAL_VIS,
    SOURCE_COMMIT,
    download,
)

PORT = int(os.getenv("VI_REAL_COMPONENT_PROJECTION_PORT", "8093"))
BASE_URL = f"http://127.0.0.1:{PORT}"
ARTIFACTS = Path(
    os.getenv(
        "BUILD_ARTIFACT_DIR",
        str(ROOT / "artifacts" / "real-component-projection"),
    )
)
VIEWPORTS = (
    {"width": 1365, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1920, "height": 1080},
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


def candidate_score(vi: dict[str, Any]) -> tuple[int, int, int, int]:
    objects = vi.get("objects") or []
    front = sum(
        item.get("surface") == "front-panel"
        and item.get("category") in {"control", "indicator"}
        for item in objects
    )
    nodes = sum(
        item.get("surface") == "block-diagram"
        and item.get("category") == "node"
        for item in objects
    )
    terminals = sum(
        item.get("surface") == "block-diagram"
        and item.get("category") == "terminal"
        for item in objects
    )
    wires = len(vi.get("wires") or [])
    return (min(front, 30) + min(nodes, 60), wires, terminals, len(objects))


def build_candidate() -> tuple[dict[str, Any], dict[str, Any]]:
    candidates: list[
        tuple[tuple[int, int, int, int], dict[str, Any], dict[str, Any]]
    ] = []
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="real-component-projection-") as directory:
        root = Path(directory)
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
                score = candidate_score(vi)
                if score[0] <= 0:
                    continue
                candidates.append(
                    (
                        score,
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
                            "score": score,
                        },
                    )
                )
            except Exception as error:
                errors.append(f"{name}: {type(error).__name__}: {error}")
    if not candidates:
        raise AssertionError("no real VI could be projected; " + "; ".join(errors))
    _, model, source = max(candidates, key=lambda value: value[0])
    source["candidate_errors"] = errors
    return model, source


def job() -> dict[str, Any]:
    return {
        "job_id": "real-component-projection",
        "status": "ready",
        "component_modified_at": "2026-09-11T09:55:00Z",
        "xml_modified_at": "2026-09-11T09:55:00Z",
        "files": [],
    }


def route_payload(page: Page, model: dict[str, Any]) -> None:
    def model_route(route: Route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(model, ensure_ascii=False),
        )

    page.route("**/api/jobs/real-component-projection/model*", model_route)


def require(condition: bool, message: str, diagnostics: dict[str, Any]) -> None:
    if not condition:
        diagnostics["failures"].append(message)


def median_or_none(values: list[float]) -> float | None:
    return median(values) if values else None


def browser_snapshot(page: Page) -> dict[str, Any]:
    return page.evaluate(
        """() => {
          const E = window.VISemanticEditor;
          const S = E.S;
          const P = window.VIComponentProjection;
          const rect = selector => {
            const element = document.querySelector(selector);
            if (!element) return null;
            const value = element.getBoundingClientRect();
            return {
              x: value.x,
              y: value.y,
              width: value.width,
              height: value.height,
              right: value.right,
              bottom: value.bottom,
            };
          };
          const bodyFor = group => group?.querySelector([
            '.vi-front-panel-body',
            '.vi-block-node-body',
            '.vi-terminal-body',
            '.vi-cluster-frame',
            '.vi-structure-frame',
          ].join(','));
          const matrix = S.el.modelGraphSvg.getScreenCTM();
          const records = [...document.querySelectorAll(
            '#model-graph-svg [data-object-id]'
          )].map(group => {
            const item = S.objects.get(group.dataset.objectId);
            const logical = item ? E.effectiveBounds(item) : null;
            const projected = item ? P.projectBounds(item, logical) : null;
            const body = bodyFor(group);
            const bodyRect = body?.getBoundingClientRect() || null;
            return {
              id: item?.id || group.dataset.objectId,
              name: item?.name || '',
              surface: item?.surface || '',
              category: item?.category || '',
              kind: item?.kind || '',
              visualKind: item?.visual_kind || '',
              logical,
              projected,
              bodyScreen: bodyRect ? {
                width: bodyRect.width,
                height: bodyRect.height,
              } : null,
              projectionSource: group.dataset.projectionSource || null,
              scaleX: Number(group.dataset.componentScaleX || 1),
              scaleY: Number(group.dataset.componentScaleY || 1),
              labelInsideGeometry: Boolean(group.querySelector(
                '.vi-component-geometry .vi-object-label'
              )),
            };
          });
          const endpointErrors = [];
          if (S.surface === 'block-diagram') {
            for (const [id, wire] of S.wires) {
              const groups = [...document.querySelectorAll(
                `[data-wire-id="${CSS.escape(id)}"]`
              )];
              groups.forEach((group, branchIndex) => {
                const path = group.querySelector('.vi-wire');
                const targetTerminalId = group.dataset.targetTerminalId
                  || wire.target_terminal_ids?.[branchIndex]
                  || null;
                const source = P.projectedCenter(
                  wire.source_terminal_id || wire.source_object_id
                );
                const target = P.projectedCenter(
                  targetTerminalId || wire.target_object_ids?.[branchIndex]
                );
                if (!path?.getTotalLength || !source || !target) {
                  endpointErrors.push({id, branchIndex, reason: 'unresolved'});
                  return;
                }
                const start = path.getPointAtLength(0);
                const end = path.getPointAtLength(path.getTotalLength());
                const distance = (first, second) => Math.hypot(
                  first.x - second.x,
                  first.y - second.y,
                );
                const direct = distance(start, source) + distance(end, target);
                const reverse = distance(start, target) + distance(end, source);
                if (Math.min(direct, reverse) > 3) {
                  endpointErrors.push({id, branchIndex, direct, reverse});
                }
              });
            }
          }
          return {
            surface: S.surface,
            records,
            endpointErrors,
            matrix: matrix ? {
              scaleX: Math.hypot(matrix.a, matrix.b),
              scaleY: Math.hypot(matrix.c, matrix.d),
            } : null,
            viewBox: S.box ? {...S.box} : null,
            scale: window.VICanvasDensity.runtime.currentScale,
            mode: window.VICanvasDensity.runtime.currentMode,
            fitMetrics: window.VIComponentFit.representativeMetrics(),
            projectedBounds: window.VIComponentFit.projectedContentBounds({
              includeWires: true,
            }),
            metrics: P.projectedMetrics(),
            ui: {
              commandbar: rect('.azure-command-bar'),
              navigation: rect('.azure-navigation'),
              context: rect('.azure-context-pane'),
              objectPane: rect('.vi-object-pane'),
              canvas: rect('#model-graph-viewport'),
            },
            editableState: {
              local: S.local.size,
              dirty: S.dirty.size,
            },
          };
        }"""
    )


def summarize(snapshot: dict[str, Any]) -> dict[str, Any]:
    records = snapshot["records"]
    projected = [
        record
        for record in records
        if record["projected"]
        and (
            record["projected"].get("factor_x", 1) < 0.999
            or record["projected"].get("factor_y", 1) < 0.999
        )
    ]
    containers = [
        record
        for record in records
        if record["projected"]
        and record["projected"].get("source") == "native-container"
    ]
    ratios = [
        float(record["projected"]["width"])
        / max(1.0, float(record["logical"]["width"]))
        for record in projected
        if record["logical"]
    ]
    screen_heights = [
        float(record["bodyScreen"]["height"])
        for record in projected
        if record["bodyScreen"]
        and float(record["bodyScreen"]["height"]) > 0
    ]
    sources = Counter(
        str(record["projected"].get("source"))
        for record in records
        if record["projected"]
    )
    body_errors = []
    matrix = snapshot.get("matrix") or {}
    for record in records:
        if not record["projected"] or not record["bodyScreen"]:
            continue
        expected_width = (
            float(record["projected"]["width"])
            * float(matrix.get("scaleX") or 0)
        )
        expected_height = (
            float(record["projected"]["height"])
            * float(matrix.get("scaleY") or 0)
        )
        body_errors.append(
            max(
                abs(float(record["bodyScreen"]["width"]) - expected_width),
                abs(float(record["bodyScreen"]["height"]) - expected_height),
            )
        )
    return {
        "object_count": len(records),
        "projected_count": len(projected),
        "container_count": len(containers),
        "median_projection_ratio": median_or_none(ratios),
        "median_projected_screen_height": median_or_none(screen_heights),
        "maximum_body_screen_error": max(body_errors) if body_errors else None,
        "projection_sources": dict(sources),
        "endpoint_error_count": len(snapshot["endpointErrors"]),
    }


def audit_viewport(
    browser,
    viewport: dict[str, int],
    model: dict[str, Any],
    diagnostics: dict[str, Any],
) -> None:
    key = f"{viewport['width']}x{viewport['height']}"
    context = browser.new_context(viewport=viewport)
    page = context.new_page()
    page.set_default_timeout(15_000)
    page.on(
        "console",
        lambda message: diagnostics["console_errors"].append(f"{key}: {message.text}")
        if message.type == "error"
        else None,
    )
    page.on(
        "pageerror",
        lambda error: diagnostics["page_errors"].append(f"{key}: {error}"),
    )
    route_payload(page, model)
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_function("() => Boolean(window.viPages && window.viModelGraph)")
    value = job()
    page.evaluate("job => window.viPages.setJob(job, {openModel: true})", value)
    page.evaluate("async job => { await window.viModelGraph.setJob(job); }", value)
    page.wait_for_function(
        """() => Boolean(
          window.VIComponentProjection?.ready
          && window.VIComponentFit?.ready
          && window.VISemanticEditor?.S?.vi
        )"""
    )
    page.wait_for_timeout(350)

    front = browser_snapshot(page)
    front_summary = summarize(front)
    page.screenshot(
        path=str(ARTIFACTS / f"real-component-projection-front-{key}.png"),
        full_page=False,
    )
    page.locator('[data-vi-surface="block-diagram"]').click()
    page.wait_for_timeout(350)
    block = browser_snapshot(page)
    block_summary = summarize(block)
    page.screenshot(
        path=str(ARTIFACTS / f"real-component-projection-block-{key}.png"),
        full_page=False,
    )

    require(47 <= front["ui"]["commandbar"]["height"] <= 49, f"{key}: command bar was compacted", diagnostics)
    require(214 <= front["ui"]["navigation"]["width"] <= 218, f"{key}: navigation was compacted", diagnostics)
    require(290 <= front["ui"]["context"]["width"] <= 294, f"{key}: context pane was compacted", diagnostics)
    require(222 <= front["ui"]["objectPane"]["width"] <= 226, f"{key}: object pane was compacted", diagnostics)
    require(front["editableState"] == {"local": 0, "dirty": 0}, f"{key}: front render modified editable state", diagnostics)
    require(block["editableState"] == {"local": 0, "dirty": 0}, f"{key}: block render modified editable state", diagnostics)
    require(front_summary["object_count"] > 0, f"{key}: real front panel rendered no objects", diagnostics)
    require(block_summary["object_count"] > 0, f"{key}: real block diagram rendered no objects", diagnostics)
    require(front_summary["projected_count"] > 0, f"{key}: real front panel projected no component bodies", diagnostics)
    require(block_summary["projected_count"] > 0, f"{key}: real block diagram projected no component bodies", diagnostics)
    require(
        front_summary["median_projection_ratio"] is not None
        and front_summary["median_projection_ratio"] < 0.85,
        f"{key}: front component bodies remain close to oversized logical bounds",
        diagnostics,
    )
    require(
        block_summary["median_projection_ratio"] is not None
        and block_summary["median_projection_ratio"] < 0.80,
        f"{key}: block component bodies remain close to oversized logical bounds",
        diagnostics,
    )
    for label, summary in (("front", front_summary), ("block", block_summary)):
        height = summary["median_projected_screen_height"]
        require(
            height is not None and 8 <= height <= 96,
            f"{key}: {label} projected screen body height is implausible ({height})",
            diagnostics,
        )
        error = summary["maximum_body_screen_error"]
        require(
            error is None or error <= 4.5,
            f"{key}: {label} body screen geometry diverges from projection ({error})",
            diagnostics,
        )
    require(not block["endpointErrors"], f"{key}: projected wire endpoints miss terminals", diagnostics)

    diagnostics["viewports"][key] = {
        "front_panel": {
            "summary": front_summary,
            "scale": front["scale"],
            "mode": front["mode"],
            "fit_metrics": front["fitMetrics"],
            "projected_bounds": front["projectedBounds"],
            "ui": front["ui"],
        },
        "block_diagram": {
            "summary": block_summary,
            "scale": block["scale"],
            "mode": block["mode"],
            "fit_metrics": block["fitMetrics"],
            "projected_bounds": block["projectedBounds"],
            "endpoint_errors": block["endpointErrors"],
        },
    }
    context.close()


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    model, source = build_candidate()
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".sandbox-real-component-projection-jobs"),
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
        "semantic_summary": model["vi"].get("summary"),
        "failures": [],
        "console_errors": [],
        "page_errors": [],
        "viewports": {},
    }
    try:
        wait_for_server(process)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            for viewport in VIEWPORTS:
                audit_viewport(browser, viewport, model, diagnostics)
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
                print("REAL_COMPONENT_PROJECTION_APP_LOG=" + output[-4000:].replace("\n", "\\n"))

    (ARTIFACTS / "real-component-projection.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "REAL_COMPONENT_PROJECTION_JSON="
        + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
    )
    failed = bool(
        diagnostics["failures"]
        or diagnostics["console_errors"]
        or diagnostics["page_errors"]
    )
    print(
        "REAL_COMPONENT_PROJECTION_AUDIT_FAILED"
        if failed
        else "REAL_COMPONENT_PROJECTION_AUDIT_OK"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
