from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, Route, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.semantic_ui_browser_test import make_payload  # noqa: E402

PORT = int(os.getenv("VI_COMPONENT_SCALE_PORT", "8092"))
BASE_URL = f"http://127.0.0.1:{PORT}"
ARTIFACTS = Path(
    os.getenv(
        "BUILD_ARTIFACT_DIR",
        str(ROOT / "artifacts" / "component-visual-scale"),
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


def clone_outlier(
    template: dict[str, Any],
    object_id: str,
    surface: str,
    x: float,
    y: float,
) -> dict[str, Any]:
    item = copy.deepcopy(template)
    item.update(
        {
            "id": object_id,
            "component_id": object_id,
            "uid": object_id,
            "surface": surface,
            "native_surface": surface,
            "name": f"Far layout object {object_id}",
            "bounds": {
                "x": x,
                "y": y,
                "width": 54 if surface == "block-diagram" else 104,
                "height": 38 if surface == "block-diagram" else 42,
            },
            "positioned": True,
            "movable": True,
            "resizable": True,
            "terminal_ids": [],
            "linked_terminal_ids": [],
            "wire_ids": [],
            "parent_object_id": None,
            "child_object_ids": [],
            "hidden_by_structure_frame": False,
            "source": {
                "file": "component-scale-fixture.xml",
                "xml_path": f"/{object_id}",
            },
        }
    )
    return item


def scale_payload() -> dict[str, Any]:
    payload = copy.deepcopy(make_payload())
    vi = payload["vi"]
    objects = vi["objects"]
    front_template = next(
        item
        for item in objects
        if item.get("surface") == "front-panel"
        and item.get("category") in {"control", "indicator"}
    )
    diagram_template = next(
        item
        for item in objects
        if item.get("surface") == "block-diagram"
        and item.get("category") == "node"
    )
    front_outlier = clone_outlier(
        front_template,
        "component-scale-front-outlier",
        "front-panel",
        5200,
        3800,
    )
    diagram_outlier = clone_outlier(
        diagram_template,
        "component-scale-diagram-outlier",
        "block-diagram",
        6400,
        4600,
    )
    objects.extend([front_outlier, diagram_outlier])
    vi["surfaces"]["front-panel"] = [
        item["id"]
        for item in objects
        if item.get("surface") == "front-panel"
    ]
    vi["surfaces"]["block-diagram"] = [
        item["id"]
        for item in objects
        if item.get("surface") == "block-diagram"
    ]
    vi["summary"]["front_panel_objects"] = len(vi["surfaces"]["front-panel"])
    vi["summary"]["block_diagram_nodes"] = sum(
        item.get("surface") == "block-diagram"
        and item.get("category") == "node"
        for item in objects
    )
    return payload


def job() -> dict[str, Any]:
    return {
        "job_id": "component-scale",
        "status": "ready",
        "component_modified_at": "2026-09-11T06:50:00Z",
        "xml_modified_at": "2026-09-11T06:50:00Z",
        "files": [],
    }


def route_payload(page: Page, payload: dict[str, Any]) -> None:
    def model_route(route: Route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload, ensure_ascii=False),
        )

    page.route("**/api/jobs/component-scale/model*", model_route)


def require(condition: bool, message: str, diagnostics: dict[str, Any]) -> None:
    if not condition:
        diagnostics["failures"].append(message)


def open_editor(page: Page) -> None:
    value = job()
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_function("() => Boolean(window.viPages && window.viModelGraph)")
    page.evaluate("value => window.viPages.setJob(value, {openModel: true})", value)
    page.evaluate("async value => { await window.viModelGraph.setJob(value); }", value)
    page.wait_for_function(
        """() => Boolean(
          window.VISemanticComponentScale?.ready
          && window.VICanvasDensity?.ready
          && window.VISemanticEditor?.S?.vi
        )"""
    )
    page.wait_for_timeout(260)


def surface_metrics(page: Page, surface: str) -> dict[str, Any]:
    page.locator(f'[data-vi-surface="{surface}"]').click()
    page.wait_for_function(
        "surface => window.VISemanticEditor.S.surface === surface",
        arg=surface,
    )
    page.evaluate(
        "surface => window.VISemanticComponentScale.fitReadable(surface)",
        surface,
    )
    page.wait_for_timeout(160)
    return page.evaluate(
        """surface => {
          const scale = window.VICanvasDensity.runtime.currentScale;
          const measurement = window.VISemanticComponentScale.measure(surface);
          const records = window.VISemanticComponentScale
            .representativeItems(surface);
          const values = records.map(record => {
            const node = document.querySelector(
              `[data-object-id="${CSS.escape(record.item.id)}"]`
            );
            const rect = node?.getBoundingClientRect();
            return rect ? {
              id: record.item.id,
              width: rect.width,
              height: rect.height,
              worldWidth: Number(record.bounds.width || 0),
              worldHeight: Number(record.bounds.height || 0),
            } : null;
          }).filter(Boolean);
          const median = array => {
            const sorted = [...array].sort((a, b) => a - b);
            if (!sorted.length) return 0;
            const middle = Math.floor(sorted.length / 2);
            return sorted.length % 2
              ? sorted[middle]
              : (sorted[middle - 1] + sorted[middle]) / 2;
          };
          return {
            surface,
            scale,
            mode: window.VICanvasDensity.runtime.currentMode,
            measurement,
            renderedCount: values.length,
            medianScreenWidth: median(values.map(value => value.width)),
            medianScreenHeight: median(values.map(value => value.height)),
            medianWorldWidth: median(values.map(value => value.worldWidth)),
            medianWorldHeight: median(values.map(value => value.worldHeight)),
            screenScaleFromHeight: median(
              values
                .filter(value => value.worldHeight > 0)
                .map(value => value.height / value.worldHeight)
            ),
            shellPolicy: document.querySelector('#vi-editor-shell')
              ?.dataset.viComponentScalePolicy,
            viewBox: {...window.VISemanticEditor.S.box},
          };
        }""",
        surface,
    )


def overview_metrics(page: Page) -> dict[str, Any]:
    page.evaluate("() => window.VICanvasDensity.fit('overview')")
    page.wait_for_timeout(160)
    return page.evaluate(
        """() => ({
          scale: window.VICanvasDensity.runtime.currentScale,
          mode: window.VICanvasDensity.runtime.currentMode,
          viewBox: {...window.VISemanticEditor.S.box},
        })"""
    )


def chrome_metrics(page: Page) -> dict[str, Any]:
    return page.evaluate(
        """() => {
          const rect = selector => {
            const node = document.querySelector(selector);
            if (!node) return null;
            const box = node.getBoundingClientRect();
            return {width: box.width, height: box.height};
          };
          return {
            commandbar: rect('.azure-commandbar'),
            navigation: rect('.azure-navigation'),
            context: rect('.azure-context-pane'),
            objectPane: rect('.vi-object-pane'),
            editorHeader: rect('.vi-editor-header'),
            canvasToolbar: rect('.vi-canvas-toolbar'),
            canvasStatus: rect(
              '.vi-canvas-status, .vi-canvas-footer, .vi-canvas-pane > footer'
            ),
          };
        }"""
    )


def audit_viewport(
    browser,
    size: dict[str, int],
    payload: dict[str, Any],
    diagnostics: dict[str, Any],
) -> None:
    key = f"{size['width']}x{size['height']}"
    context = browser.new_context(viewport=size)
    page = context.new_page()
    page.set_default_timeout(10_000)
    page.on(
        "console",
        lambda message: diagnostics["console_errors"].append(
            f"{key}: {message.text}"
        )
        if message.type == "error"
        else None,
    )
    page.on(
        "pageerror",
        lambda error: diagnostics["page_errors"].append(f"{key}: {error}"),
    )
    route_payload(page, payload)
    open_editor(page)

    chrome = chrome_metrics(page)
    require(
        chrome["commandbar"]
        and 47 <= chrome["commandbar"]["height"] <= 49,
        f"{key}: command bar is still compacted",
        diagnostics,
    )
    require(
        chrome["navigation"] and chrome["navigation"]["width"] >= 195,
        f"{key}: navigation is still compacted",
        diagnostics,
    )
    require(
        chrome["context"] and chrome["context"]["width"] >= 268,
        f"{key}: context pane is still compacted",
        diagnostics,
    )
    require(
        chrome["objectPane"] and chrome["objectPane"]["width"] >= 206,
        f"{key}: object pane is still compacted",
        diagnostics,
    )
    require(
        chrome["editorHeader"] and chrome["editorHeader"]["height"] >= 50,
        f"{key}: VI header is still compacted",
        diagnostics,
    )
    require(
        chrome["canvasToolbar"] and chrome["canvasToolbar"]["height"] >= 38,
        f"{key}: canvas toolbar is still compacted",
        diagnostics,
    )

    front = surface_metrics(page, "front-panel")
    require(front["scale"] >= 0.99, f"{key}: front panel was auto-shrunk", diagnostics)
    require(front["mode"] == "readable", f"{key}: front mode is not readable", diagnostics)
    require(front["renderedCount"] >= 1, f"{key}: no front component rendered", diagnostics)
    require(
        front["screenScaleFromHeight"] >= 0.94,
        f"{key}: front components render below native scale",
        diagnostics,
    )
    require(
        front["medianScreenHeight"] >= 26,
        f"{key}: front components remain too small on screen",
        diagnostics,
    )
    front_overview = overview_metrics(page)
    require(
        front_overview["scale"] < front["scale"],
        f"{key}: overview is not distinct from readable front fit",
        diagnostics,
    )
    front_restored = surface_metrics(page, "front-panel")
    require(
        front_restored["scale"] >= 0.99,
        f"{key}: readable front fit did not restore native size",
        diagnostics,
    )

    block = surface_metrics(page, "block-diagram")
    require(block["scale"] >= 0.99, f"{key}: block diagram was auto-shrunk", diagnostics)
    require(block["mode"] == "readable", f"{key}: block mode is not readable", diagnostics)
    require(block["renderedCount"] >= 1, f"{key}: no diagram node rendered", diagnostics)
    require(
        block["screenScaleFromHeight"] >= 0.94,
        f"{key}: diagram nodes render below native scale",
        diagnostics,
    )
    require(
        block["medianScreenHeight"] >= 25,
        f"{key}: diagram nodes remain too small on screen",
        diagnostics,
    )
    block_overview = overview_metrics(page)
    require(
        block_overview["scale"] < block["scale"],
        f"{key}: overview is not distinct from readable diagram fit",
        diagnostics,
    )
    block_restored = surface_metrics(page, "block-diagram")
    require(
        block_restored["scale"] >= 0.99,
        f"{key}: readable diagram fit did not restore native size",
        diagnostics,
    )

    diagnostics["viewports"][key] = {
        "chrome": chrome,
        "front": front,
        "front_overview": front_overview,
        "front_restored": front_restored,
        "block": block,
        "block_overview": block_overview,
        "block_restored": block_restored,
    }
    page.screenshot(
        path=str(ARTIFACTS / f"component-scale-{key}.png"),
        full_page=False,
    )
    context.close()


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    payload = scale_payload()
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".sandbox-component-scale-jobs"),
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
        "failures": [],
        "console_errors": [],
        "page_errors": [],
        "viewports": {},
    }
    try:
        wait_for_server(process)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            for size in VIEWPORTS:
                audit_viewport(browser, size, payload, diagnostics)
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
                print("COMPONENT_SCALE_APPLICATION_LOG=" + output[-4000:].replace("\n", "\\n"))

    (ARTIFACTS / "semantic-component-scale.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "SEMANTIC_COMPONENT_SCALE_JSON="
        + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
    )
    failed = bool(
        diagnostics["failures"]
        or diagnostics["console_errors"]
        or diagnostics["page_errors"]
    )
    print(
        "SEMANTIC_COMPONENT_SCALE_TEST_FAILED"
        if failed
        else "SEMANTIC_COMPONENT_SCALE_TEST_OK"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
