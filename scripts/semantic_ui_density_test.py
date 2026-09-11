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

PORT = int(os.getenv("VI_UI_DENSITY_PORT", "8086"))
BASE_URL = f"http://127.0.0.1:{PORT}"
ARTIFACTS = Path(
    os.getenv("BUILD_ARTIFACT_DIR", str(ROOT / "artifacts" / "semantic-density"))
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


def large_payload() -> dict[str, Any]:
    payload = copy.deepcopy(make_payload())
    vi = payload["vi"]
    front_template = next(
        item
        for item in vi["objects"]
        if item["surface"] == "front-panel" and item["category"] == "control"
    )
    block_template = next(
        item
        for item in vi["objects"]
        if item["surface"] == "block-diagram" and item["category"] == "node"
    )
    additions: list[dict[str, Any]] = []
    for row in range(4):
        for column in range(6):
            front = copy.deepcopy(front_template)
            front["id"] = f"density-front-{row}-{column}"
            front["component_id"] = front["id"]
            front["uid"] = f"f-{row}-{column}"
            front["name"] = f"Panel {row + 1}-{column + 1}"
            front["linked_terminal_ids"] = []
            front["terminal_ids"] = []
            front["wire_ids"] = []
            front["bounds"] = {
                **(front.get("bounds") or {}),
                "x": 60 + column * 390,
                "y": 60 + row * 290,
                "width": 116,
                "height": 48,
                "source_property_id": None,
            }
            front["movable"] = False
            front["resizable"] = False
            additions.append(front)

            node = copy.deepcopy(block_template)
            node["id"] = f"density-node-{row}-{column}"
            node["component_id"] = node["id"]
            node["uid"] = f"n-{row}-{column}"
            node["name"] = f"Operation {row + 1}-{column + 1}"
            node["terminal_ids"] = []
            node["linked_terminal_ids"] = []
            node["wire_ids"] = []
            node["bounds"] = {
                **(node.get("bounds") or {}),
                "x": 80 + column * 430,
                "y": 80 + row * 330,
                "width": 42,
                "height": 42,
                "source_property_id": None,
            }
            node["movable"] = False
            node["resizable"] = False
            additions.append(node)

    vi["objects"].extend(additions)
    vi["surfaces"]["front-panel"] = [
        item["id"] for item in vi["objects"] if item["surface"] == "front-panel"
    ]
    vi["surfaces"]["block-diagram"] = [
        item["id"] for item in vi["objects"] if item["surface"] == "block-diagram"
    ]
    vi["summary"]["front_panel_objects"] = len(vi["surfaces"]["front-panel"])
    vi["summary"]["block_diagram_nodes"] = sum(
        item["surface"] == "block-diagram" and item["category"] == "node"
        for item in vi["objects"]
    )
    return payload


def route_payload(page: Page, job_id: str, payload: dict[str, Any]) -> None:
    def route_model(route: Route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload, ensure_ascii=False),
        )

    page.route(f"**/api/jobs/{job_id}/model*", route_model)


def job(job_id: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "status": "ready",
        "component_modified_at": "2026-09-11T04:00:00Z",
        "xml_modified_at": "2026-09-11T04:00:00Z",
        "files": [],
    }


def load_job(page: Page, value: dict[str, Any]) -> None:
    page.evaluate("job => window.viPages.setJob(job, {openModel: true})", value)
    page.evaluate("async job => { await window.viModelGraph.setJob(job); }", value)
    page.wait_for_function(
        "() => Boolean(window.VICanvasDensity?.ready && window.VISemanticEditor?.S?.vi)"
    )
    page.wait_for_timeout(300)


def snapshot(page: Page) -> dict[str, Any]:
    return page.evaluate(
        """() => {
          const rect = selector => {
            const element = document.querySelector(selector);
            if (!element) return null;
            const box = element.getBoundingClientRect();
            return {x: box.x, y: box.y, width: box.width, height: box.height,
                    right: box.right, bottom: box.bottom};
          };
          const fontSize = selector => {
            const element = document.querySelector(selector);
            return element ? parseFloat(getComputedStyle(element).fontSize) : null;
          };
          const median = values => {
            const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
            if (!sorted.length) return null;
            const middle = Math.floor(sorted.length / 2);
            return sorted.length % 2
              ? sorted[middle]
              : (sorted[middle - 1] + sorted[middle]) / 2;
          };
          const S = window.VISemanticEditor.S;
          const canvas = rect('#model-graph-viewport');
          const box = S.box;
          const scale = canvas && box
            ? Math.min(canvas.width / box.width, canvas.height / box.height)
            : null;
          const components = [...document.querySelectorAll(
            '#model-graph-svg [data-object-id]'
          )].flatMap(group => {
            const item = S.objects.get(group.dataset.objectId);
            if (!item || item.category === 'terminal') return [];
            const body = group.querySelector(
              '.vi-front-panel-body,.vi-block-node-body'
            );
            if (!body) return [];
            const bounds = body.getBoundingClientRect();
            if (bounds.width < 1 || bounds.height < 1) return [];
            return [{
              id: item.id,
              width: bounds.width,
              height: bounds.height,
              shortSide: Math.min(bounds.width, bounds.height),
              longSide: Math.max(bounds.width, bounds.height),
              category: item.category,
            }];
          });
          return {
            viewport: {width: innerWidth, height: innerHeight},
            commandbar: rect('.azure-command-bar'),
            navigation: rect('.azure-navigation'),
            context: rect('.azure-context-pane'),
            objectPane: rect('.vi-object-pane'),
            canvas,
            shell: rect('#vi-editor-shell'),
            box: box ? {...box} : null,
            fitBox: S.fitBox ? {...S.fitBox} : null,
            scale,
            mode: document.querySelector('#vi-editor-shell')?.dataset.viViewMode,
            lod: document.querySelector('#vi-editor-shell')?.dataset.viLod,
            zoomText: document.querySelector('#vi-canvas-zoom-status')?.textContent,
            zoomStatusCount: document.querySelectorAll(
              '#vi-canvas-zoom-status,#vi-zoom-status'
            ).length,
            surface: S.surface,
            selected: S.selected,
            componentMetrics: window.VICanvasDensity.componentMetrics(),
            componentScale: window.VICanvasDensity.componentScale(),
            componentScreenMetrics:
              window.VICanvasDensity.componentScreenMetrics(scale),
            renderedComponents: {
              count: components.length,
              medianWidth: median(components.map(item => item.width)),
              medianHeight: median(components.map(item => item.height)),
              medianShortSide: median(components.map(item => item.shortSide)),
              medianLongSide: median(components.map(item => item.longSide)),
            },
            fonts: {
              brand: fontSize('.azure-command-bar .brand-copy strong'),
              navigation: fontSize('.navigation-item strong'),
              objectList: fontSize('.vi-list-copy strong'),
              toolbar: fontSize('.vi-canvas-toolbar > div:first-child strong'),
              inspector: fontSize('.model-inspector h2'),
            },
            objectPaneCollapsed: document.querySelector('#vi-editor-shell')
              ?.classList.contains('is-object-pane-collapsed'),
            contextPaneCollapsed: document.body.classList.contains(
              'vi-context-pane-collapsed'
            ),
            page: {
              scrollWidth: document.documentElement.scrollWidth,
              scrollHeight: document.documentElement.scrollHeight,
            },
          };
        }"""
    )


def require(condition: bool, message: str, diagnostics: dict[str, Any]) -> None:
    if not condition:
        diagnostics["failures"].append(message)


def content_bounds(page: Page) -> dict[str, float] | None:
    return page.evaluate("() => window.VICanvasDensity.contentBounds()")


def box_contains(
    box: dict[str, float],
    bounds: dict[str, float],
    tolerance: float = 2,
) -> bool:
    return (
        box["x"] <= bounds["x"] + tolerance
        and box["y"] <= bounds["y"] + tolerance
        and box["x"] + box["width"]
        >= bounds["x"] + bounds["width"] - tolerance
        and box["y"] + box["height"]
        >= bounds["y"] + bounds["height"] - tolerance
    )


def assert_normal_chrome(
    snapshot_value: dict[str, Any],
    key: str,
    diagnostics: dict[str, Any],
) -> None:
    require(
        47 <= snapshot_value["commandbar"]["height"] <= 49,
        f"{key}: command bar was compacted",
        diagnostics,
    )
    require(
        214 <= snapshot_value["navigation"]["width"] <= 218,
        f"{key}: navigation was compacted",
        diagnostics,
    )
    require(
        290 <= snapshot_value["context"]["width"] <= 294,
        f"{key}: context pane was compacted",
        diagnostics,
    )
    require(
        222 <= snapshot_value["objectPane"]["width"] <= 226,
        f"{key}: object pane was compacted",
        diagnostics,
    )
    for name, minimum in {
        "brand": 11,
        "navigation": 11,
        "objectList": 9,
        "toolbar": 10,
        "inspector": 14,
    }.items():
        require(
            snapshot_value["fonts"][name] is not None
            and snapshot_value["fonts"][name] >= minimum,
            f"{key}: {name} UI font was compacted",
            diagnostics,
        )


def assert_component_size(
    snapshot_value: dict[str, Any],
    key: str,
    target_short_side: float,
    diagnostics: dict[str, Any],
) -> None:
    rendered = snapshot_value["renderedComponents"]
    screen = snapshot_value["componentScreenMetrics"]
    require(rendered["count"] > 0, f"{key}: no rendered components", diagnostics)
    require(
        screen["medianScreenShortSide"] is not None
        and abs(screen["medianScreenShortSide"] - target_short_side) <= 1.5,
        f"{key}: component-derived screen size missed its target",
        diagnostics,
    )
    require(
        rendered["medianShortSide"] is not None
        and target_short_side - 2 <= rendered["medianShortSide"]
        <= target_short_side + 3,
        f"{key}: rendered component size is not reduced to the target band",
        diagnostics,
    )
    require(
        snapshot_value["scale"] < 0.90,
        f"{key}: readable mode still forces components to 100% or larger",
        diagnostics,
    )
    require(
        snapshot_value["zoomStatusCount"] == 1,
        f"{key}: duplicate and contradictory zoom indicators remain",
        diagnostics,
    )


def audit_viewport(
    browser,
    viewport_size: dict[str, int],
    small: dict[str, Any],
    large: dict[str, Any],
    diagnostics: dict[str, Any],
) -> None:
    context = browser.new_context(viewport=viewport_size)
    page = context.new_page()
    page.on(
        "console",
        lambda message: diagnostics["console_errors"].append(
            f"{viewport_size}: {message.text}"
        )
        if message.type == "error"
        else None,
    )
    page.on(
        "pageerror",
        lambda error: diagnostics["page_errors"].append(
            f"{viewport_size}: {error}"
        ),
    )
    route_payload(page, "density-small", small)
    route_payload(page, "density-large", large)
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_function("() => Boolean(window.viPages && window.viModelGraph)")
    page.wait_for_function("() => window.VICanvasDensity?.ready === true")

    load_job(page, job("density-small"))
    small_front = snapshot(page)
    key = f"{viewport_size['width']}x{viewport_size['height']}"
    diagnostics["viewports"][key] = {"small_front": small_front}
    assert_normal_chrome(small_front, key, diagnostics)
    assert_component_size(
        small_front,
        f"{key} front panel",
        28,
        diagnostics,
    )
    require(
        0.24 <= small_front["scale"] <= 0.86,
        f"{key}: small front-panel component scale is outside policy",
        diagnostics,
    )
    require(
        small_front["mode"] == "readable",
        f"{key}: initial front-panel mode is not readable",
        diagnostics,
    )
    require(
        small_front["page"]["scrollWidth"] <= viewport_size["width"] + 2,
        f"{key}: horizontal page overflow",
        diagnostics,
    )
    page.screenshot(
        path=str(ARTIFACTS / f"density-{key}-front-readable.png"),
        full_page=False,
    )

    page.locator('[data-vi-surface="block-diagram"]').click()
    page.wait_for_timeout(220)
    small_block = snapshot(page)
    diagnostics["viewports"][key]["small_block"] = small_block
    assert_component_size(
        small_block,
        f"{key} block diagram",
        24,
        diagnostics,
    )
    require(
        0.20 <= small_block["scale"] <= 0.78,
        f"{key}: small block-diagram component scale is outside policy",
        diagnostics,
    )
    page.screenshot(
        path=str(ARTIFACTS / f"density-{key}-block-readable.png"),
        full_page=False,
    )

    load_job(page, job("density-large"))
    page.locator('[data-vi-surface="block-diagram"]').click()
    page.wait_for_timeout(260)
    large_readable = snapshot(page)
    large_bounds = content_bounds(page)
    diagnostics["viewports"][key]["large_readable"] = large_readable
    diagnostics["viewports"][key]["large_content"] = large_bounds
    assert_component_size(
        large_readable,
        f"{key} large block diagram",
        24,
        diagnostics,
    )
    require(
        large_readable["mode"] == "readable",
        f"{key}: large diagram initial mode is not readable",
        diagnostics,
    )
    require(
        bool(large_bounds)
        and (
            large_bounds["width"] > large_readable["box"]["width"]
            or large_bounds["height"] > large_readable["box"]["height"]
        ),
        f"{key}: readable mode still forces the entire large diagram into one view",
        diagnostics,
    )

    page.locator("#model-graph-overview").click()
    page.wait_for_timeout(180)
    overview = snapshot(page)
    diagnostics["viewports"][key]["large_overview"] = overview
    require(
        overview["scale"] < large_readable["scale"],
        f"{key}: overview did not zoom out from component-sized view",
        diagnostics,
    )
    require(
        overview["mode"] == "overview",
        f"{key}: overview mode not recorded",
        diagnostics,
    )
    require(
        overview["lod"] in {"overview", "compact"},
        f"{key}: overview did not reduce label detail",
        diagnostics,
    )
    require(
        bool(large_bounds) and box_contains(overview["box"], large_bounds),
        f"{key}: overview does not contain the full diagram",
        diagnostics,
    )
    page.screenshot(
        path=str(ARTIFACTS / f"density-{key}-large-overview.png"),
        full_page=False,
    )

    selectable = next(
        item["id"]
        for item in large["vi"]["objects"]
        if item["surface"] == "block-diagram"
        and item["category"] == "node"
    )
    page.evaluate("id => window.VISemanticEditor.select(id, false)", selectable)
    page.wait_for_timeout(100)
    page.locator("#model-graph-focus").click()
    page.wait_for_timeout(180)
    focus = snapshot(page)
    diagnostics["viewports"][key]["focus"] = focus
    require(
        focus["scale"] > large_readable["scale"],
        f"{key}: focus did not enlarge the selected component",
        diagnostics,
    )
    require(
        focus["scale"] <= 1.26,
        f"{key}: focus enlarged components excessively",
        diagnostics,
    )
    require(
        focus["mode"] == "focus",
        f"{key}: focus mode not recorded",
        diagnostics,
    )

    before_panes = snapshot(page)
    page.locator("#vi-toggle-object-pane").click()
    page.wait_for_timeout(180)
    object_collapsed = snapshot(page)
    require(
        object_collapsed["objectPaneCollapsed"],
        f"{key}: object pane did not collapse",
        diagnostics,
    )
    require(
        object_collapsed["canvas"]["width"]
        > before_panes["canvas"]["width"] + 150,
        f"{key}: collapsing object pane did not reclaim canvas width",
        diagnostics,
    )
    require(
        abs(object_collapsed["scale"] - before_panes["scale"]) < 0.04,
        f"{key}: object pane collapse changed visual scale",
        diagnostics,
    )

    page.locator("#vi-toggle-context-pane").click()
    page.wait_for_timeout(180)
    context_collapsed = snapshot(page)
    diagnostics["viewports"][key]["panes_collapsed"] = context_collapsed
    require(
        context_collapsed["contextPaneCollapsed"],
        f"{key}: context pane did not collapse",
        diagnostics,
    )
    require(
        context_collapsed["canvas"]["width"]
        > object_collapsed["canvas"]["width"] + 230,
        f"{key}: collapsing context pane did not reclaim canvas width",
        diagnostics,
    )
    require(
        abs(context_collapsed["scale"] - object_collapsed["scale"]) < 0.04,
        f"{key}: context pane collapse changed visual scale",
        diagnostics,
    )

    page.set_viewport_size(
        {
            "width": viewport_size["width"] + 120,
            "height": viewport_size["height"] + 40,
        }
    )
    page.wait_for_timeout(240)
    resized = snapshot(page)
    diagnostics["viewports"][key]["resized"] = resized
    require(
        abs(resized["scale"] - context_collapsed["scale"]) < 0.04,
        f"{key}: viewport resize reset zoom",
        diagnostics,
    )

    page.screenshot(
        path=str(ARTIFACTS / f"density-{key}-panes-collapsed.png"),
        full_page=False,
    )
    context.close()


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    small = make_payload()
    large = large_payload()
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".sandbox-density-jobs"),
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
            for viewport_size in VIEWPORTS:
                audit_viewport(browser, viewport_size, small, large, diagnostics)
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
                print("DENSITY_APPLICATION_LOG=" + output[-4000:].replace("\n", "\\n"))

    output = ARTIFACTS / "semantic-ui-density.json"
    output.write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "SEMANTIC_UI_DENSITY_JSON="
        + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
    )
    if diagnostics["failures"] or diagnostics["console_errors"] or diagnostics["page_errors"]:
        print("SEMANTIC_UI_DENSITY_TEST_FAILED")
        return 1
    print("SEMANTIC_UI_DENSITY_TEST_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
