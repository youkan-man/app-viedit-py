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

PORT = int(os.getenv("VI_REAL_COMPONENT_GEOMETRY_PORT", "8093"))
BASE_URL = f"http://127.0.0.1:{PORT}"
ARTIFACTS = Path(
    os.getenv(
        "BUILD_ARTIFACT_DIR",
        str(ROOT / "artifacts" / "real-component-geometry"),
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


def finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def dimension_summary(objects: list[dict[str, Any]]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for item in objects:
        bounds = item.get("bounds") or {}
        width = finite(bounds.get("width"))
        height = finite(bounds.get("height"))
        if width is None or height is None or width <= 0 or height <= 0:
            continue
        records.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "surface": item.get("surface"),
                "category": item.get("category"),
                "kind": item.get("kind"),
                "visual_kind": item.get("visual_kind"),
                "positioned": item.get("positioned") is not False,
                "width": width,
                "height": height,
                "area": width * height,
                "source_coordinate_space": bounds.get("source_coordinate_space"),
                "source_property_id": bounds.get("source_property_id"),
            }
        )
    by_surface: dict[str, Any] = {}
    for surface in ("front-panel", "block-diagram"):
        values = [record for record in records if record["surface"] == surface]
        widths = [record["width"] for record in values]
        heights = [record["height"] for record in values]
        areas = [record["area"] for record in values]
        by_surface[surface] = {
            "count": len(values),
            "median_width": median(widths) if widths else None,
            "median_height": median(heights) if heights else None,
            "median_area": median(areas) if areas else None,
            "categories": dict(Counter(str(record["category"]) for record in values)),
            "largest": sorted(values, key=lambda record: record["area"], reverse=True)[:20],
        }
    return {"by_surface": by_surface, "records": records}


def candidate_score(vi: dict[str, Any]) -> tuple[int, int, int]:
    objects = vi.get("objects") or []
    front = sum(item.get("surface") == "front-panel" for item in objects)
    block = sum(
        item.get("surface") == "block-diagram"
        and item.get("category") != "terminal"
        for item in objects
    )
    terminals = sum(
        item.get("surface") == "block-diagram"
        and item.get("category") == "terminal"
        for item in objects
    )
    return (min(front, 20) + min(block, 40), terminals, len(objects))


def build_candidate() -> tuple[dict[str, Any], dict[str, Any]]:
    candidates: list[tuple[tuple[int, int, int], dict[str, Any], dict[str, Any]]] = []
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="real-component-geometry-") as directory:
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
                payload = {
                    "summary": {"failed_files": 0},
                    "warnings": list(vi.get("warnings") or []),
                    "graph": copy.deepcopy(graph),
                    "vi": copy.deepcopy(vi),
                }
                source_record = {
                    "repository": "JKISoftware/JKI-EasyXML",
                    "commit": SOURCE_COMMIT,
                    "path": relative,
                    "name": name,
                    "score": score,
                }
                candidates.append((score, payload, source_record))
            except Exception as error:
                errors.append(f"{name}: {type(error).__name__}: {error}")
    if not candidates:
        raise AssertionError("no real VI could be projected; " + "; ".join(errors))
    _, payload, source = max(candidates, key=lambda value: value[0])
    source["candidate_errors"] = errors
    return payload, source


def job() -> dict[str, Any]:
    return {
        "job_id": "real-component-geometry",
        "status": "ready",
        "component_modified_at": "2026-09-11T05:10:00Z",
        "xml_modified_at": "2026-09-11T05:10:00Z",
        "files": [],
    }


def route_payload(page: Page, payload: dict[str, Any]) -> None:
    def model_route(route: Route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload, ensure_ascii=False),
        )

    page.route("**/api/jobs/real-component-geometry/model*", model_route)


def browser_snapshot(page: Page) -> dict[str, Any]:
    return page.evaluate(
        """() => {
          const rect = selector => {
            const element = document.querySelector(selector);
            if (!element) return null;
            const value = element.getBoundingClientRect();
            return {x: value.x, y: value.y, width: value.width,
                    height: value.height, right: value.right, bottom: value.bottom};
          };
          const S = window.VISemanticEditor.S;
          const report = window.VIComponentGeometry.report();
          const ranked = [...(report.records || [])]
            .sort((first, second) => (
              second.body_screen_width * second.body_screen_height
              - first.body_screen_width * first.body_screen_height
            ))
            .slice(0, 30);
          return {
            surface: S.surface,
            viewBox: S.box ? {...S.box} : null,
            scale: report.scale,
            geometry: {...report, records: ranked},
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


def require(condition: bool, message: str, diagnostics: dict[str, Any]) -> None:
    if not condition:
        diagnostics["failures"].append(message)


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    payload, source = build_candidate()
    diagnostics: dict[str, Any] = {
        "source": source,
        "semantic_bounds": dimension_summary(payload["vi"].get("objects") or []),
        "failures": [],
        "console_errors": [],
        "page_errors": [],
    }
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".sandbox-real-component-geometry-jobs"),
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
    try:
        wait_for_server(process)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()
            page.set_default_timeout(15_000)
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
                  window.VIComponentGeometry?.ready
                  && window.VICanvasDensity?.ready
                  && window.VISemanticEditor?.S?.vi
                )"""
            )
            page.wait_for_timeout(350)
            front = browser_snapshot(page)
            diagnostics["front_panel"] = front
            page.screenshot(
                path=str(ARTIFACTS / "real-component-geometry-front-1440x900.png"),
                full_page=False,
            )

            page.locator('[data-vi-surface="block-diagram"]').click()
            page.wait_for_timeout(350)
            block = browser_snapshot(page)
            diagnostics["block_diagram"] = block
            page.screenshot(
                path=str(ARTIFACTS / "real-component-geometry-block-1440x900.png"),
                full_page=False,
            )

            for label, snapshot in (("front", front), ("block", block)):
                require(
                    snapshot["geometry"]["object_count"] > 0,
                    f"{label}: no component geometry was measured",
                    diagnostics,
                )
                require(
                    snapshot["editableState"] == {"local": 0, "dirty": 0},
                    f"{label}: geometry audit modified editable state",
                    diagnostics,
                )
            require(
                47 <= front["ui"]["commandbar"]["height"] <= 49,
                "normal command bar height was not restored",
                diagnostics,
            )
            require(
                214 <= front["ui"]["navigation"]["width"] <= 218,
                "normal navigation width was not restored",
                diagnostics,
            )
            require(
                290 <= front["ui"]["context"]["width"] <= 294,
                "normal context width was not restored",
                diagnostics,
            )
            require(
                222 <= front["ui"]["objectPane"]["width"] <= 226,
                "normal object pane width was not restored",
                diagnostics,
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
                print("REAL_COMPONENT_GEOMETRY_APP_LOG=" + output[-4000:].replace("\n", "\\n"))

    output = ARTIFACTS / "real-component-geometry.json"
    output.write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "REAL_COMPONENT_GEOMETRY_JSON="
        + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
    )
    failed = bool(
        diagnostics["failures"]
        or diagnostics["console_errors"]
        or diagnostics["page_errors"]
    )
    print(
        "REAL_COMPONENT_GEOMETRY_AUDIT_FAILED"
        if failed
        else "REAL_COMPONENT_GEOMETRY_AUDIT_OK"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
