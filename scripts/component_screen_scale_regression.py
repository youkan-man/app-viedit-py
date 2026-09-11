from __future__ import annotations

import json
import os
import statistics
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

PORT = int(os.getenv("VI_COMPONENT_SCALE_PORT", "8094"))
BASE_URL = f"http://127.0.0.1:{PORT}"
ARTIFACTS = Path(
    os.getenv(
        "BUILD_ARTIFACT_DIR",
        str(ROOT / "artifacts" / "component-screen-scale"),
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


def job() -> dict[str, Any]:
    return {
        "job_id": "component-screen-scale",
        "status": "ready",
        "component_modified_at": "2026-09-11T04:20:00Z",
        "xml_modified_at": "2026-09-11T04:20:00Z",
        "files": [],
    }


def route_model(page: Page, payload: dict[str, Any]) -> None:
    def model_route(route: Route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload, ensure_ascii=False),
        )

    page.route("**/api/jobs/component-screen-scale/model*", model_route)


def median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def snapshot(page: Page) -> dict[str, Any]:
    value = page.evaluate(
        """() => {
          const rect = selector => {
            const element = document.querySelector(selector);
            if (!element) return null;
            const box = element.getBoundingClientRect();
            return {
              x: box.x,
              y: box.y,
              width: box.width,
              height: box.height,
              right: box.right,
              bottom: box.bottom,
            };
          };
          const font = selector => {
            const element = document.querySelector(selector);
            return element ? Number.parseFloat(getComputedStyle(element).fontSize) : null;
          };
          const S = window.VISemanticEditor.S;
          const bodySelector = S.surface === 'front-panel'
            ? '.vi-object .vi-front-panel-body'
            : '.vi-object:not(.is-terminal) .vi-block-node-body';
          const components = [...document.querySelectorAll(bodySelector)].map(body => {
            const group = body.closest('[data-object-id]');
            const id = group?.dataset.objectId || null;
            const item = id ? S.objects.get(id) : null;
            const screen = body.getBoundingClientRect();
            const logical = item ? window.VISemanticEditor.effectiveBounds(item) : null;
            return {
              id,
              category: item?.category || null,
              positioned: item?.positioned !== false,
              generated: Boolean(logical?.generated),
              screenWidth: screen.width,
              screenHeight: screen.height,
              logicalWidth: logical?.width || null,
              logicalHeight: logical?.height || null,
              widthRatio: logical?.width ? screen.width / logical.width : null,
              heightRatio: logical?.height ? screen.height / logical.height : null,
            };
          }).filter(component => (
            component.positioned
            && !component.generated
            && component.screenWidth > 0
            && component.screenHeight > 0
          ));
          const canvas = rect('#model-graph-viewport');
          const box = S.box ? {...S.box} : null;
          const measuredScale = canvas && box
            ? Math.min(canvas.width / box.width, canvas.height / box.height)
            : null;
          return {
            viewport: {width: innerWidth, height: innerHeight},
            surface: S.surface,
            mode: document.querySelector('#vi-editor-shell')?.dataset.viViewMode,
            lod: document.querySelector('#vi-editor-shell')?.dataset.viLod,
            scale: window.VICanvasDensity.runtime.currentScale,
            measuredScale,
            zoomText: document.querySelector('#vi-canvas-zoom-status')?.textContent,
            commandbar: rect('.azure-command-bar'),
            navigation: rect('.azure-navigation'),
            context: rect('.azure-context-pane'),
            objectPane: rect('.vi-object-pane'),
            canvas,
            components,
            fonts: {
              brand: font('.azure-command-bar .brand-copy strong'),
              command: font('.header-command'),
              navigation: font('.navigation-item strong'),
              objectName: font('.vi-list-copy strong'),
              toolbar: font('.vi-canvas-actions .secondary-action'),
              inspector: font('.model-inspector-grid dd'),
            },
            page: {
              scrollWidth: document.documentElement.scrollWidth,
              scrollHeight: document.documentElement.scrollHeight,
            },
          };
        }"""
    )
    components = value["components"]
    value["component_medians"] = {
        "screen_width": median([item["screenWidth"] for item in components]),
        "screen_height": median([item["screenHeight"] for item in components]),
        "width_ratio": median(
            [item["widthRatio"] for item in components if item["widthRatio"]]
        ),
        "height_ratio": median(
            [item["heightRatio"] for item in components if item["heightRatio"]]
        ),
    }
    return value


def require(condition: bool, message: str, diagnostics: dict[str, Any]) -> None:
    if not condition:
        diagnostics["failures"].append(message)


def check_normal_chrome(
    snap: dict[str, Any],
    key: str,
    diagnostics: dict[str, Any],
) -> None:
    require(
        47 <= snap["commandbar"]["height"] <= 49,
        f"{key}: command bar was compacted",
        diagnostics,
    )
    require(
        214 <= snap["navigation"]["width"] <= 218,
        f"{key}: navigation was compacted",
        diagnostics,
    )
    require(
        290 <= snap["context"]["width"] <= 294,
        f"{key}: context pane was compacted",
        diagnostics,
    )
    require(
        222 <= snap["objectPane"]["width"] <= 226,
        f"{key}: object list was compacted",
        diagnostics,
    )
    for name, size in snap["fonts"].items():
        if size is not None:
            require(size >= 9, f"{key}: {name} font is too small ({size}px)", diagnostics)


def check_readable_components(
    snap: dict[str, Any],
    key: str,
    diagnostics: dict[str, Any],
) -> None:
    medians = snap["component_medians"]
    require(snap["mode"] == "readable", f"{key}: not in readable mode", diagnostics)
    require(snap["scale"] >= 0.99, f"{key}: readable scale fell below 100%", diagnostics)
    require(
        snap["measuredScale"] >= 0.99,
        f"{key}: actual SVG scale fell below 100%",
        diagnostics,
    )
    require(
        medians["height_ratio"] is not None and medians["height_ratio"] >= 0.98,
        f"{key}: component bodies are smaller than their VI bounds",
        diagnostics,
    )
    require(
        medians["screen_height"] is not None and medians["screen_height"] >= 30,
        f"{key}: representative components are still visually tiny",
        diagnostics,
    )
    require(
        snap["page"]["scrollWidth"] <= snap["viewport"]["width"] + 2,
        f"{key}: page has horizontal overflow",
        diagnostics,
    )


def run_viewport(
    browser,
    viewport: dict[str, int],
    payload: dict[str, Any],
    diagnostics: dict[str, Any],
) -> None:
    key = f"{viewport['width']}x{viewport['height']}"
    context = browser.new_context(viewport=viewport)
    page = context.new_page()
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
    route_model(page, payload)
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_function("() => Boolean(window.viPages && window.viModelGraph)")
    value = job()
    page.evaluate("job => window.viPages.setJob(job, {openModel: true})", value)
    page.evaluate("async job => { await window.viModelGraph.setJob(job); }", value)
    page.wait_for_function(
        "() => Boolean(window.VICanvasDensity?.ready && window.VISemanticEditor.S.vi)"
    )
    page.wait_for_timeout(300)

    front = snapshot(page)
    check_normal_chrome(front, f"{key}/front", diagnostics)
    check_readable_components(front, f"{key}/front", diagnostics)

    page.locator('[data-vi-surface="block-diagram"]').click()
    page.wait_for_timeout(250)
    block = snapshot(page)
    check_normal_chrome(block, f"{key}/block", diagnostics)
    check_readable_components(block, f"{key}/block", diagnostics)

    page.locator("#model-graph-overview").click()
    page.wait_for_timeout(180)
    overview = snapshot(page)
    require(overview["mode"] == "overview", f"{key}: overview mode missing", diagnostics)
    require(
        overview["scale"] < block["scale"],
        f"{key}: explicit overview did not zoom out",
        diagnostics,
    )

    diagnostics["viewports"][key] = {
        "front": front,
        "block": block,
        "overview": overview,
    }
    page.screenshot(
        path=str(ARTIFACTS / f"component-screen-scale-{key}.png"),
        full_page=False,
    )
    context.close()


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    payload = make_payload()
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".sandbox-component-screen-scale-jobs"),
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
            for viewport in VIEWPORTS:
                run_viewport(browser, viewport, payload, diagnostics)
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
                print(
                    "COMPONENT_SCALE_APPLICATION_LOG="
                    + output[-4000:].replace("\n", "\\n")
                )

    result = ARTIFACTS / "component-screen-scale.json"
    result.write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "COMPONENT_SCREEN_SCALE_JSON="
        + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
    )
    failed = bool(
        diagnostics["failures"]
        or diagnostics["console_errors"]
        or diagnostics["page_errors"]
    )
    print("COMPONENT_SCREEN_SCALE_FAILED" if failed else "COMPONENT_SCREEN_SCALE_OK")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
