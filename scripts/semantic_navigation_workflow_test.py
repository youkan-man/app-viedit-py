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

from semantic_ui_browser_test import make_payload  # noqa: E402

PORT = int(os.getenv("VI_NAVIGATION_WORKFLOW_PORT", "8096"))
BASE_URL = f"http://127.0.0.1:{PORT}"
ARTIFACTS = Path(
    os.getenv(
        "BUILD_ARTIFACT_DIR",
        str(ROOT / "artifacts" / "semantic-navigation-workflow"),
    )
)
VIEWPORTS = (
    {"width": 1365, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1920, "height": 1080},
)


def large_payload() -> dict[str, Any]:
    value = copy.deepcopy(make_payload())
    vi = value["vi"]
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
    for index in range(160):
        front = copy.deepcopy(front_template)
        front["id"] = f"navigation-front-{index:03d}"
        front["component_id"] = front["id"]
        front["uid"] = f"nav-fp-{index:03d}"
        front["name"] = f"Panel Input {index:03d}"
        front["class_name"] = "NumericControl.NavigationFixture"
        front["data_type"] = "numeric"
        front["terminal_ids"] = []
        front["linked_terminal_ids"] = []
        front["wire_ids"] = []
        front["bounds"] = {
            **(front.get("bounds") or {}),
            "x": 60 + (index % 16) * 150,
            "y": 60 + (index // 16) * 82,
            "width": 112,
            "height": 44,
            "source_property_id": None,
        }
        front["movable"] = False
        front["resizable"] = False
        additions.append(front)

        block = copy.deepcopy(block_template)
        block["id"] = f"navigation-block-{index:03d}"
        block["component_id"] = block["id"]
        block["uid"] = f"nav-bd-{index:03d}"
        block["name"] = f"Processing Node {index:03d}"
        block["class_name"] = "Primitive.NavigationFixture"
        block["data_type"] = "numeric"
        block["terminal_ids"] = []
        block["linked_terminal_ids"] = []
        block["wire_ids"] = []
        block["bounds"] = {
            **(block.get("bounds") or {}),
            "x": 80 + (index % 16) * 165,
            "y": 80 + (index // 16) * 96,
            "width": 46,
            "height": 42,
            "source_property_id": None,
        }
        block["movable"] = False
        block["resizable"] = False
        additions.append(block)

    by_id = {item["id"]: item for item in additions}
    by_id["navigation-block-042"]["name"] = "N42 Target Processor"
    by_id["navigation-block-042"]["class_name"] = "UniqueNavigationTarget"
    by_id["navigation-front-011"]["name"] = "History Front A"
    by_id["navigation-block-012"]["name"] = "History Block B"
    by_id["navigation-front-013"]["name"] = "History Front C"

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
    return value


def job() -> dict[str, Any]:
    return {
        "job_id": "navigation-workflow",
        "status": "ready",
        "component_modified_at": "2026-09-11T16:30:00Z",
        "xml_modified_at": "2026-09-11T16:30:00Z",
        "files": [],
    }


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


def route_payload(page: Page, value: dict[str, Any]) -> None:
    def model_route(route: Route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(value, ensure_ascii=False),
        )

    page.route("**/api/jobs/navigation-workflow/model*", model_route)


def require(condition: bool, message: str, diagnostics: dict[str, Any]) -> None:
    if not condition:
        diagnostics["failures"].append(message)


def close_number(first: float, second: float, tolerance: float = 1.2) -> bool:
    return abs(float(first) - float(second)) <= tolerance


def close_box(
    first: dict[str, float] | None,
    second: dict[str, float],
    tolerance: float = 1.2,
) -> bool:
    return bool(first) and all(
        close_number(float(first[key]), float(second[key]), tolerance)
        for key in ("x", "y", "width", "height")
    )


def editor_snapshot(page: Page) -> dict[str, Any]:
    return page.evaluate(
        """() => {
          const S = window.VISemanticEditor.S;
          const R = window.VINavigationWorkflow.runtime;
          const dialog = document.querySelector('#vi-navigation-dialog');
          const overlay = document.querySelector('#vi-navigation-overlay');
          const rect = dialog?.getBoundingClientRect();
          return {
            selected: S.selected,
            surface: S.surface,
            box: S.box ? {...S.box} : null,
            localKeys: [...S.local.keys()].sort(),
            dirtyKeys: [...S.dirty].sort(),
            history: R.history.map(item => ({
              id: item.id,
              surface: item.surface,
              box: item.box ? {...item.box} : null,
              mode: item.mode,
              jobKey: item.jobKey,
            })),
            cursor: R.cursor,
            recent: [...R.recent],
            activeIndex: R.activeIndex,
            guardHandled: window.VINavigationKeyboardGuard.runtime.handled,
            open: R.open,
            overlayHidden: overlay?.hidden,
            backgroundInert: Boolean(document.querySelector('.azure-application-shell')?.inert),
            dialog: rect ? {
              x: rect.x,
              y: rect.y,
              width: rect.width,
              height: rect.height,
              right: rect.right,
              bottom: rect.bottom,
            } : null,
            activeElement: document.activeElement?.id || null,
            resultIds: [...document.querySelectorAll('[data-navigation-result]')]
              .map(element => element.dataset.navigationResult),
            groups: [...document.querySelectorAll('.vi-navigation-group')]
              .map(element => element.textContent),
            historyStatus: document.querySelector('#vi-selection-history-status')?.textContent,
            backDisabled: document.querySelector('#vi-selection-back')?.disabled,
            forwardDisabled: document.querySelector('#vi-selection-forward')?.disabled,
          };
        }"""
    )


def assert_selected(page: Page, object_id: str, diagnostics: dict[str, Any], key: str) -> None:
    selected = page.evaluate(
        """id => ({
          state: window.VISemanticEditor.S.selected,
          surface: window.VISemanticEditor.S.surface,
          list: Boolean(document.querySelector(
            `[data-list-id="${CSS.escape(id)}"].is-selected`
          )),
          canvas: Boolean(document.querySelector(
            `[data-object-id="${CSS.escape(id)}"].is-selected`
          )),
        })""",
        object_id,
    )
    require(selected["state"] == object_id, f"{key}: selected state is wrong", diagnostics)
    require(selected["list"], f"{key}: object list did not select the target", diagnostics)
    require(selected["canvas"], f"{key}: canvas did not select the target", diagnostics)


def set_view_and_select(
    page: Page,
    object_id: str,
    box: dict[str, float],
) -> None:
    page.evaluate(
        """({id, box}) => {
          window.VISemanticEditor.select(id, true);
          window.setTimeout(() => {
            window.VICanvasDensity.applyBox(box, 'manual');
          }, 120);
        }""",
        {"id": object_id, "box": box},
    )
    page.wait_for_timeout(320)


def run_viewport(
    browser,
    viewport: dict[str, int],
    value: dict[str, Any],
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
    route_payload(page, value)
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_function("() => Boolean(window.viPages && window.viModelGraph)")
    page.evaluate("value => window.viPages.setJob(value, {openModel: true})", job())
    page.evaluate("async value => { await window.viModelGraph.setJob(value); }", job())
    page.wait_for_function(
        """() => Boolean(
          window.VIRuntimeFixes?.ready
          && window.VINavigationWorkflow?.ready
          && window.VINavigationKeyboardGuard?.ready
          && window.VIComponentFit?.ready
          && window.VISemanticEditor?.S?.vi
        )"""
    )
    page.wait_for_timeout(300)

    total_records = page.evaluate(
        "() => window.VISemanticEditor.S.objects.size + window.VISemanticEditor.S.wires.size"
    )
    require(total_records >= 300, f"{key}: fixture has fewer than 300 records", diagnostics)
    baseline = editor_snapshot(page)

    page.locator("#model-graph-query").fill("hidden-filter")
    page.locator("#model-graph-kind").select_option(
        page.locator("#model-graph-kind option").nth(1).get_attribute("value") or ""
    )
    page.keyboard.press("Control+K")
    page.wait_for_timeout(120)
    opened = editor_snapshot(page)
    require(opened["open"], f"{key}: Ctrl+K did not open the navigator", diagnostics)
    require(opened["backgroundInert"], f"{key}: background is not inert", diagnostics)
    require(
        opened["dialog"]["x"] >= -1
        and opened["dialog"]["y"] >= -1
        and opened["dialog"]["right"] <= viewport["width"] + 1
        and opened["dialog"]["bottom"] <= viewport["height"] + 1,
        f"{key}: navigation dialog is outside the viewport",
        diagnostics,
    )
    require(
        opened["activeElement"] == "vi-navigation-query",
        f"{key}: search input did not receive focus",
        diagnostics,
    )

    page.locator("#vi-navigation-query").fill("n42")
    page.wait_for_timeout(80)
    results = editor_snapshot(page)
    require(
        results["resultIds"] and results["resultIds"][0] == "navigation-block-042",
        f"{key}: five-character cross-surface search did not rank the target first",
        diagnostics,
    )
    page.keyboard.press("Enter")
    page.wait_for_timeout(360)
    navigated = editor_snapshot(page)
    require(not navigated["open"], f"{key}: Enter did not close the navigator", diagnostics)
    require(
        navigated["surface"] == "block-diagram",
        f"{key}: target surface was not revealed",
        diagnostics,
    )
    assert_selected(page, "navigation-block-042", diagnostics, key)
    require(
        page.locator("#model-graph-query").input_value() == "",
        f"{key}: list search filter was not cleared for reveal",
        diagnostics,
    )
    require(
        page.locator("#model-graph-kind").input_value() == "",
        f"{key}: kind filter was not cleared for reveal",
        diagnostics,
    )

    page.keyboard.press("Control+K")
    page.wait_for_timeout(100)
    before_key = editor_snapshot(page)
    page.keyboard.press("ArrowDown")
    page.wait_for_timeout(80)
    after_key = editor_snapshot(page)
    require(
        after_key["activeIndex"] == min(1, len(after_key["resultIds"]) - 1),
        f"{key}: ArrowDown was processed more than once",
        diagnostics,
    )
    require(
        after_key["guardHandled"] == before_key["guardHandled"] + 1,
        f"{key}: keyboard guard did not handle exactly one event",
        diagnostics,
    )
    page.locator("#vi-navigation-query").focus()
    page.keyboard.press("Shift+Tab")
    page.wait_for_timeout(50)
    trapped = editor_snapshot(page)
    require(
        trapped["activeElement"] == "vi-navigation-close",
        f"{key}: Shift+Tab escaped the modal focus cycle",
        diagnostics,
    )
    page.keyboard.press("Escape")
    page.wait_for_timeout(80)
    closed = editor_snapshot(page)
    require(not closed["open"], f"{key}: Escape did not close the navigator", diagnostics)
    require(
        not closed["backgroundInert"],
        f"{key}: background remained inert after closing",
        diagnostics,
    )

    box_a = {"x": 25, "y": 35, "width": 520, "height": 360}
    box_b = {"x": 180, "y": 140, "width": 620, "height": 410}
    box_c = {"x": 410, "y": 260, "width": 560, "height": 390}
    set_view_and_select(page, "navigation-front-011", box_a)
    set_view_and_select(page, "navigation-block-012", box_b)
    set_view_and_select(page, "navigation-front-013", box_c)
    history_before = editor_snapshot(page)
    require(
        history_before["historyStatus"].endswith(f"/{len(history_before['history'])}"),
        f"{key}: history status is not synchronized",
        diagnostics,
    )

    page.keyboard.press("Alt+ArrowLeft")
    page.wait_for_timeout(360)
    back_b = editor_snapshot(page)
    require(back_b["selected"] == "navigation-block-012", f"{key}: back did not restore B", diagnostics)
    require(back_b["surface"] == "block-diagram", f"{key}: back did not restore B surface", diagnostics)
    require(close_box(back_b["box"], box_b), f"{key}: back did not restore B view", diagnostics)

    page.keyboard.press("Alt+ArrowLeft")
    page.wait_for_timeout(360)
    back_a = editor_snapshot(page)
    require(back_a["selected"] == "navigation-front-011", f"{key}: second back did not restore A", diagnostics)
    require(back_a["surface"] == "front-panel", f"{key}: second back did not restore A surface", diagnostics)
    require(close_box(back_a["box"], box_a), f"{key}: second back did not restore A view", diagnostics)

    page.keyboard.press("Alt+ArrowRight")
    page.wait_for_timeout(360)
    forward_b = editor_snapshot(page)
    require(forward_b["selected"] == "navigation-block-012", f"{key}: forward did not restore B", diagnostics)
    require(forward_b["surface"] == "block-diagram", f"{key}: forward did not restore B surface", diagnostics)
    require(close_box(forward_b["box"], box_b), f"{key}: forward did not restore B view", diagnostics)

    page.keyboard.press("Control+K")
    page.wait_for_timeout(100)
    empty_results = editor_snapshot(page)
    require(
        "最近の選択" in empty_results["groups"]
        or "現在の選択に接続" in empty_results["groups"],
        f"{key}: empty query did not show contextual navigation results",
        diagnostics,
    )
    page.keyboard.press("Escape")
    page.wait_for_timeout(60)

    final = editor_snapshot(page)
    require(
        final["localKeys"] == baseline["localKeys"],
        f"{key}: navigation changed local geometry",
        diagnostics,
    )
    require(
        final["dirtyKeys"] == baseline["dirtyKeys"],
        f"{key}: navigation dirtied VI geometry",
        diagnostics,
    )
    diagnostics["viewports"][key] = {
        "record_count": total_records,
        "opened": opened,
        "navigated": navigated,
        "single_key": {"before": before_key, "after": after_key},
        "history_before": history_before,
        "back_b": back_b,
        "back_a": back_a,
        "forward_b": forward_b,
        "final": final,
    }
    page.screenshot(
        path=str(ARTIFACTS / f"navigation-workflow-{key}.png"),
        full_page=False,
    )
    context.close()


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    value = large_payload()
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".navigation-workflow-jobs"),
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
                run_viewport(browser, viewport, value, diagnostics)
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
                diagnostics["application_log_tail"] = output[-4000:]

    (ARTIFACTS / "semantic-navigation-workflow.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "SEMANTIC_NAVIGATION_WORKFLOW_JSON="
        + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
    )
    failed = bool(
        diagnostics["failures"]
        or diagnostics["console_errors"]
        or diagnostics["page_errors"]
    )
    print(
        "SEMANTIC_NAVIGATION_WORKFLOW_TEST_FAILED"
        if failed
        else "SEMANTIC_NAVIGATION_WORKFLOW_TEST_OK"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
