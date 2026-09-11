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

PORT = int(os.getenv("VI_MULTI_SELECTION_PORT", "8097"))
BASE_URL = f"http://127.0.0.1:{PORT}"
ARTIFACTS = Path(
    os.getenv(
        "BUILD_ARTIFACT_DIR",
        str(ROOT / "artifacts" / "semantic-multi-selection"),
    )
)
VIEWPORTS = (
    {"width": 1365, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1920, "height": 1080},
)


def _template(
    objects: list[dict[str, Any]],
    *,
    surface: str,
    category: str,
) -> dict[str, Any]:
    return copy.deepcopy(
        next(
            item
            for item in objects
            if item.get("surface") == surface and item.get("category") == category
        )
    )


def _clone_object(
    template: dict[str, Any],
    object_id: str,
    name: str,
    bounds: dict[str, Any],
    *,
    surface: str | None = None,
) -> dict[str, Any]:
    item = copy.deepcopy(template)
    item["id"] = object_id
    item["component_id"] = object_id
    item["uid"] = object_id
    item["name"] = name
    item["bounds"] = {
        **(item.get("bounds") or {}),
        **bounds,
        "source_property_id": None,
    }
    if surface is not None:
        item["surface"] = surface
    item["wire_ids"] = []
    item["terminal_ids"] = []
    item["linked_terminal_ids"] = []
    item["linked_object_ids"] = []
    item["properties"] = []
    item["movable"] = True
    item["resizable"] = True
    return item


def fixture() -> dict[str, Any]:
    value = copy.deepcopy(make_payload())
    vi = value["vi"]
    objects: list[dict[str, Any]] = vi["objects"]
    node_template = _template(
        objects,
        surface="block-diagram",
        category="node",
    )
    control_template = _template(
        objects,
        surface="front-panel",
        category="control",
    )
    terminal_template = _template(
        objects,
        surface="block-diagram",
        category="terminal",
    )

    node_a = _clone_object(
        node_template,
        "multi-node-a",
        "Multi A",
        {"x": 220, "y": 235, "width": 78, "height": 58},
    )
    node_b = _clone_object(
        node_template,
        "multi-node-b",
        "Multi B",
        {"x": 365, "y": 290, "width": 82, "height": 62},
    )
    node_c = _clone_object(
        node_template,
        "multi-node-c",
        "Multi C",
        {"x": 520, "y": 245, "width": 86, "height": 64},
    )
    parent = _clone_object(
        node_template,
        "multi-parent",
        "Parent Container",
        {"x": 260, "y": 480, "width": 190, "height": 130},
    )
    parent["is_container"] = True
    parent["child_object_ids"] = ["multi-child"]
    child = _clone_object(
        node_template,
        "multi-child",
        "Relative Child",
        {
            "x": 38,
            "y": 42,
            "width": 66,
            "height": 46,
            "relative_to_object_id": "multi-parent",
            "source_coordinate_space": "parent-relative",
        },
    )
    child["owner_object_id"] = "multi-parent"
    child["parent_object_id"] = "multi-parent"

    hidden = _clone_object(
        node_template,
        "multi-hidden",
        "Inactive Frame Object",
        {"x": 280, "y": 250, "width": 70, "height": 50},
        surface="block-diagram-inactive",
    )
    hidden["hidden_by_structure_frame"] = True
    hidden["movable"] = False

    source_terminal = _clone_object(
        terminal_template,
        "multi-source-terminal",
        "A output",
        {
            "x": node_a["bounds"]["x"] + node_a["bounds"]["width"] - 8,
            "y": node_a["bounds"]["y"] + 18,
            "width": 16,
            "height": 16,
            "relative_to_object_id": "multi-node-a",
            "source_coordinate_space": "absolute-owner-anchored",
            "anchor_x": 1.0,
            "anchor_y": 0.5,
        },
    )
    source_terminal["category"] = "terminal"
    source_terminal["direction"] = "source"
    source_terminal["owner_object_id"] = "multi-node-a"
    source_terminal["linked_object_id"] = "multi-node-a"
    source_terminal["movable"] = False
    source_terminal["resizable"] = False

    target_terminal = _clone_object(
        terminal_template,
        "multi-target-terminal",
        "B input",
        {
            "x": node_b["bounds"]["x"] - 8,
            "y": node_b["bounds"]["y"] + 20,
            "width": 16,
            "height": 16,
            "relative_to_object_id": "multi-node-b",
            "source_coordinate_space": "absolute-owner-anchored",
            "anchor_x": 0.0,
            "anchor_y": 0.5,
        },
    )
    target_terminal["category"] = "terminal"
    target_terminal["direction"] = "sink"
    target_terminal["owner_object_id"] = "multi-node-b"
    target_terminal["linked_object_id"] = "multi-node-b"
    target_terminal["movable"] = False
    target_terminal["resizable"] = False

    node_a["terminal_ids"] = [source_terminal["id"]]
    node_a["wire_ids"] = ["multi-wire"]
    node_b["terminal_ids"] = [target_terminal["id"]]
    node_b["wire_ids"] = ["multi-wire"]
    source_terminal["wire_ids"] = ["multi-wire"]
    target_terminal["wire_ids"] = ["multi-wire"]

    base_wire = copy.deepcopy((vi.get("wires") or [{}])[0])
    wire = {
        **base_wire,
        "id": "multi-wire",
        "component_id": "multi-wire",
        "uid": "multi-wire",
        "name": "Multi wire",
        "surface": "block-diagram",
        "source_terminal_id": source_terminal["id"],
        "source_object_id": node_a["id"],
        "target_terminal_ids": [target_terminal["id"]],
        "target_object_ids": [node_b["id"]],
        "terminal_ids": [source_terminal["id"], target_terminal["id"]],
        "endpoint_object_ids": [node_a["id"], node_b["id"]],
        "route_points": [
            {
                "x": node_a["bounds"]["x"] + node_a["bounds"]["width"],
                "y": node_a["bounds"]["y"] + node_a["bounds"]["height"] / 2,
            },
            {"x": 330, "y": 264},
            {"x": 330, "y": 321},
            {
                "x": node_b["bounds"]["x"],
                "y": node_b["bounds"]["y"] + node_b["bounds"]["height"] / 2,
            },
        ],
        "branch_count": 1,
        "target_terminal_count": 1,
        "net_id": "multi-net",
        "hidden_by_structure_frame": False,
    }

    additions = [
        node_a,
        node_b,
        node_c,
        parent,
        child,
        hidden,
        source_terminal,
        target_terminal,
    ]

    for index in range(150):
        row, column = divmod(index, 15)
        additions.append(
            _clone_object(
                control_template,
                f"multi-front-{index:03d}",
                f"Front filler {index + 1}",
                {
                    "x": 70 + column * 145,
                    "y": 70 + row * 105,
                    "width": 96,
                    "height": 42,
                },
            )
        )
        additions.append(
            _clone_object(
                node_template,
                f"multi-block-{index:03d}",
                f"Block filler {index + 1}",
                {
                    "x": 750 + column * 125,
                    "y": 75 + row * 95,
                    "width": 58,
                    "height": 44,
                },
            )
        )

    objects.extend(additions)
    vi.setdefault("wires", []).append(wire)
    vi.setdefault("nets", []).append(
        {
            "id": "multi-net",
            "wire_ids": ["multi-wire"],
            "source_terminal_id": source_terminal["id"],
            "target_terminal_ids": [target_terminal["id"]],
            "branch_count": 1,
            "data_type": wire.get("data_type") or "numeric",
        }
    )
    vi.setdefault("surfaces", {})["front-panel"] = [
        item["id"]
        for item in objects
        if item.get("surface") == "front-panel"
    ]
    vi["surfaces"]["block-diagram"] = [
        item["id"]
        for item in objects
        if item.get("surface") == "block-diagram"
    ]
    vi["surfaces"]["block-diagram-inactive"] = [hidden["id"]]
    summary = vi.setdefault("summary", {})
    summary["front_panel_objects"] = len(vi["surfaces"]["front-panel"])
    summary["block_diagram_nodes"] = sum(
        item.get("surface") == "block-diagram" and item.get("category") == "node"
        for item in objects
    )
    summary["terminals"] = sum(item.get("category") == "terminal" for item in objects)
    summary["wires"] = len(vi["wires"])
    summary["wire_nets"] = len(vi.get("nets") or [])
    return value


def job() -> dict[str, Any]:
    return {
        "job_id": "multi-selection",
        "status": "ready",
        "component_modified_at": "2026-09-11T17:45:00Z",
        "xml_modified_at": "2026-09-11T17:45:00Z",
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

    page.route("**/api/jobs/multi-selection/model*", model_route)


def require(condition: bool, message: str, diagnostics: dict[str, Any]) -> None:
    if not condition:
        diagnostics["failures"].append(message)


def close_point(
    first: dict[str, float] | None,
    second: dict[str, float] | None,
    tolerance: float = 1.0,
) -> bool:
    if not first or not second:
        return False
    return (
        abs(float(first["x"]) - float(second["x"])) <= tolerance
        and abs(float(first["y"]) - float(second["y"])) <= tolerance
    )


def editor_state(page: Page) -> dict[str, Any]:
    return page.evaluate(
        """() => {
          const E = window.VISemanticEditor;
          const S = E.S;
          const M = window.VIMultiSelection;
          const P = window.VIComponentProjection;
          const bounds = id => {
            const item = S.objects.get(id);
            const value = item && E.effectiveBounds(item);
            return value ? {...value} : null;
          };
          const group = id => document.querySelector(
            `[data-object-id="${CSS.escape(id)}"]`
          );
          const wirePath = document.querySelector(
            '[data-wire-id="multi-wire"] .vi-wire'
          );
          const length = wirePath?.getTotalLength?.() || 0;
          const pointAt = offset => {
            const value = wirePath?.getPointAtLength?.(offset);
            return value ? {x: value.x, y: value.y} : null;
          };
          const history = window.VISemanticEnhancements?.history;
          return {
            selectedIds: [...M.runtime.selectedIds].sort(),
            primaryId: M.runtime.primaryId,
            selected: S.selected,
            localKeys: [...S.local.keys()].sort(),
            dirtyKeys: [...S.dirty].sort(),
            bounds: {
              a: bounds('multi-node-a'),
              b: bounds('multi-node-b'),
              c: bounds('multi-node-c'),
              parent: bounds('multi-parent'),
              child: bounds('multi-child'),
            },
            roots: M.movementRoots().map(item => item.id).sort(),
            selectionBounds: M.selectionBounds(),
            historyLength: history?.history?.length || 0,
            futureLength: history?.future?.length || 0,
            historyTop: history?.history?.at(-1) || null,
            summary: M.selectionSummary(),
            summaryText: M.summaryText(),
            classes: {
              a: group('multi-node-a')?.classList.contains('is-multi-selected'),
              b: group('multi-node-b')?.classList.contains('is-multi-selected'),
              c: group('multi-node-c')?.classList.contains('is-multi-selected'),
              primaryA: group('multi-node-a')?.classList.contains('is-multi-primary'),
              primaryB: group('multi-node-b')?.classList.contains('is-multi-primary'),
            },
            resizeVisible: [...document.querySelectorAll(
              '.is-multi-selected .vi-resize-handle'
            )].some(element => getComputedStyle(element).display !== 'none'),
            aggregateInspectorHidden: document.querySelector(
              '#vi-multi-selection-inspector'
            )?.hidden,
            aggregateStatus: document.querySelector(
              '#vi-multi-selection-status'
            )?.textContent || '',
            wire: {
              start: length ? pointAt(0) : null,
              end: length ? pointAt(length) : null,
              source: P?.projectedCenter?.('multi-source-terminal') || null,
              target: P?.projectedCenter?.('multi-target-terminal') || null,
            },
          };
        }"""
    )


def click_object(page: Page, object_id: str, *, control: bool = False) -> None:
    modifier = ["Control"] if control else []
    page.locator(f'[data-object-id="{object_id}"]').click(modifiers=modifier)
    page.wait_for_timeout(120)


def assert_shared_delta(
    before: dict[str, Any],
    after: dict[str, Any],
    diagnostics: dict[str, Any],
    key: str,
) -> tuple[float, float]:
    delta_a = (
        after["bounds"]["a"]["x"] - before["bounds"]["a"]["x"],
        after["bounds"]["a"]["y"] - before["bounds"]["a"]["y"],
    )
    delta_b = (
        after["bounds"]["b"]["x"] - before["bounds"]["b"]["x"],
        after["bounds"]["b"]["y"] - before["bounds"]["b"]["y"],
    )
    require(
        abs(delta_a[0] - delta_b[0]) < 0.05
        and abs(delta_a[1] - delta_b[1]) < 0.05,
        f"{key}: selected objects did not receive one shared movement delta",
        diagnostics,
    )
    return delta_a


def run_viewport(
    browser,
    viewport: dict[str, int],
    value: dict[str, Any],
    diagnostics: dict[str, Any],
) -> None:
    key = f"{viewport['width']}x{viewport['height']}"
    context = browser.new_context(viewport=viewport)
    page = context.new_page()
    page.set_default_timeout(20_000)
    page.add_init_script(
        """() => {
          window.__copiedSelectionSummary = null;
          Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: {
              writeText: async value => {
                window.__copiedSelectionSummary = value;
              },
            },
          });
        }"""
    )
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
    route_payload(page, value)
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_function("() => Boolean(window.viPages && window.viModelGraph)")
    active_job = job()
    page.evaluate("value => window.viPages.setJob(value, {openModel: true})", active_job)
    page.evaluate("async value => { await window.viModelGraph.setJob(value); }", active_job)
    page.wait_for_function(
        """() => Boolean(
          window.VIRuntimeFixes?.ready
          && window.VINavigationHistoryStability?.ready
          && window.VIMultiSelection?.ready
          && window.VIComponentFit?.ready
          && window.VISemanticEditor?.S?.vi
        )"""
    )
    page.locator('[data-vi-surface="block-diagram"]').click()
    page.wait_for_timeout(300)

    initial = editor_state(page)
    require(
        len(value["vi"]["objects"]) >= 300,
        f"{key}: fixture does not contain at least 300 objects",
        diagnostics,
    )
    require(
        initial["localKeys"] == [] and initial["dirtyKeys"] == [],
        f"{key}: model loaded with unexpected local or dirty geometry",
        diagnostics,
    )

    click_object(page, "multi-node-a")
    click_object(page, "multi-node-b", control=True)
    selected = editor_state(page)
    require(
        selected["selectedIds"] == ["multi-node-a", "multi-node-b"],
        f"{key}: Ctrl-click did not create the expected two-object selection",
        diagnostics,
    )
    require(
        selected["primaryId"] == "multi-node-b"
        and selected["selected"] == "multi-node-b",
        f"{key}: primary selection is not compatible with S.selected",
        diagnostics,
    )
    require(
        selected["classes"]["a"] and selected["classes"]["b"],
        f"{key}: multi-selection classes are missing",
        diagnostics,
    )
    require(
        not selected["resizeVisible"]
        and selected["aggregateInspectorHidden"] is False,
        f"{key}: group resize was not disabled or inspector was hidden",
        diagnostics,
    )
    require(
        selected["localKeys"] == [] and selected["dirtyKeys"] == [],
        f"{key}: selection alone modified geometry state",
        diagnostics,
    )

    page.locator('[data-list-id="multi-node-a"]').click()
    page.wait_for_timeout(100)
    page.locator('[data-list-id="multi-node-c"]').click(modifiers=["Shift"])
    page.wait_for_timeout(150)
    ranged = editor_state(page)
    require(
        "multi-node-a" in ranged["selectedIds"]
        and "multi-node-c" in ranged["selectedIds"]
        and len(ranged["selectedIds"]) >= 2,
        f"{key}: Shift list range selection failed",
        diagnostics,
    )

    page.evaluate(
        "() => window.VIMultiSelection.setSelection(['multi-node-a','multi-node-b'], 'multi-node-b')"
    )
    page.wait_for_timeout(100)
    before_drag = editor_state(page)
    box = page.locator('[data-object-id="multi-node-a"]').bounding_box()
    require(bool(box), f"{key}: group drag source is not rendered", diagnostics)
    if box:
        start_x = box["x"] + box["width"] / 2
        start_y = box["y"] + box["height"] / 2
        page.mouse.move(start_x, start_y)
        page.mouse.down()
        page.mouse.move(start_x + 34, start_y + 23, steps=6)
        page.mouse.up()
        page.wait_for_timeout(220)
    after_drag = editor_state(page)
    drag_delta = assert_shared_delta(
        before_drag,
        after_drag,
        diagnostics,
        key,
    )
    require(
        abs(drag_delta[0]) > 5 or abs(drag_delta[1]) > 5,
        f"{key}: group drag did not move the selected objects",
        diagnostics,
    )
    require(
        after_drag["historyTop"]
        and after_drag["historyTop"].get("multi_selection") is True
        and len(after_drag["historyTop"].get("entries") or []) == 2,
        f"{key}: group drag was not recorded as one two-object history action",
        diagnostics,
    )
    require(
        close_point(after_drag["wire"]["start"], after_drag["wire"]["source"])
        and close_point(after_drag["wire"]["end"], after_drag["wire"]["target"]),
        f"{key}: wire endpoints detached after group drag",
        diagnostics,
    )

    page.locator("#vi-undo-layout").click()
    page.wait_for_timeout(200)
    undone = editor_state(page)
    require(
        abs(undone["bounds"]["a"]["x"] - before_drag["bounds"]["a"]["x"]) < 0.05
        and abs(undone["bounds"]["b"]["y"] - before_drag["bounds"]["b"]["y"]) < 0.05,
        f"{key}: one Undo did not restore the whole group",
        diagnostics,
    )
    page.locator("#vi-redo-layout").click()
    page.wait_for_timeout(200)
    redone = editor_state(page)
    require(
        abs(redone["bounds"]["a"]["x"] - after_drag["bounds"]["a"]["x"]) < 0.05
        and abs(redone["bounds"]["b"]["y"] - after_drag["bounds"]["b"]["y"]) < 0.05,
        f"{key}: one Redo did not restore the whole group movement",
        diagnostics,
    )

    history_before_keys = redone["historyLength"]
    page.keyboard.press("ArrowRight")
    page.keyboard.press("Shift+ArrowDown")
    page.wait_for_timeout(220)
    keyed = editor_state(page)
    require(
        abs(keyed["bounds"]["a"]["x"] - redone["bounds"]["a"]["x"] - 1) < 0.05
        and abs(keyed["bounds"]["a"]["y"] - redone["bounds"]["a"]["y"] - 10) < 0.05,
        f"{key}: arrow-key group movement used the wrong step",
        diagnostics,
    )
    require(
        keyed["historyLength"] == history_before_keys + 2,
        f"{key}: arrow movements were not recorded as separate batch actions",
        diagnostics,
    )

    page.evaluate(
        "() => window.VIMultiSelection.setSelection(['multi-parent','multi-child'], 'multi-child')"
    )
    page.wait_for_timeout(100)
    parent_before = editor_state(page)
    require(
        parent_before["roots"] == ["multi-parent"],
        f"{key}: selected child was not removed from movement roots",
        diagnostics,
    )
    page.evaluate("() => window.VIMultiSelection.moveSelectionBy(12, 7, '親子移動')")
    page.wait_for_timeout(180)
    parent_after = editor_state(page)
    require(
        abs(parent_after["bounds"]["parent"]["x"] - parent_before["bounds"]["parent"]["x"] - 12) < 0.05
        and abs(parent_after["bounds"]["child"]["x"] - parent_before["bounds"]["child"]["x"] - 12) < 0.05,
        f"{key}: parent-relative child did not follow its selected parent",
        diagnostics,
    )
    require(
        "multi-child" not in parent_after["localKeys"],
        f"{key}: parent-relative child received redundant local geometry",
        diagnostics,
    )

    page.evaluate(
        "() => window.VIMultiSelection.setSelection(['multi-node-a','multi-node-b','multi-hidden'], 'multi-hidden')"
    )
    page.wait_for_timeout(100)
    filtered = editor_state(page)
    require(
        "multi-hidden" not in filtered["selectedIds"],
        f"{key}: inactive Structure-frame object entered the visible selection",
        diagnostics,
    )

    page.evaluate(
        "() => window.VIMultiSelection.setSelection(['multi-node-a','multi-node-b','multi-node-c'], 'multi-node-c')"
    )
    page.wait_for_timeout(100)
    page.locator("#vi-copy-selection-summary").click()
    page.wait_for_timeout(100)
    copied = page.evaluate("() => window.__copiedSelectionSummary")
    require(
        isinstance(copied, str)
        and "選択: 3件" in copied
        and "Multi A" in copied
        and "Multi C" in copied,
        f"{key}: aggregate selection summary was not copied",
        diagnostics,
    )

    if viewport["width"] == 1440:
        page.evaluate("() => window.VIMultiSelection.clearSelection()")
        page.wait_for_timeout(100)
        boxes = [
            page.locator(f'[data-object-id="multi-node-{name}"]').bounding_box()
            for name in ("a", "b", "c")
        ]
        if all(boxes):
            left = min(box["x"] for box in boxes if box) - 10
            top = min(box["y"] for box in boxes if box) - 10
            right = max(box["x"] + box["width"] for box in boxes if box) + 10
            bottom = max(box["y"] + box["height"] for box in boxes if box) + 10
            page.mouse.move(left, top)
            page.mouse.down()
            page.mouse.move(right, bottom, steps=8)
            page.mouse.up()
            page.wait_for_timeout(200)
            marquee = editor_state(page)
            require(
                all(
                    object_id in marquee["selectedIds"]
                    for object_id in ("multi-node-a", "multi-node-b", "multi-node-c")
                ),
                f"{key}: blank-canvas marquee did not select the enclosed objects",
                diagnostics,
            )
        else:
            require(False, f"{key}: marquee targets were not rendered", diagnostics)

    page.keyboard.press("Escape")
    page.wait_for_timeout(120)
    cleared = editor_state(page)
    require(
        cleared["selectedIds"] == [] and cleared["selected"] is None,
        f"{key}: Escape did not clear multi-selection",
        diagnostics,
    )

    diagnostics["viewports"][key] = {
        "initial": initial,
        "selected": selected,
        "range": ranged,
        "before_drag": before_drag,
        "after_drag": after_drag,
        "undone": undone,
        "redone": redone,
        "keyed": keyed,
        "parent_before": parent_before,
        "parent_after": parent_after,
        "filtered": filtered,
        "cleared": cleared,
    }
    page.screenshot(
        path=str(ARTIFACTS / f"multi-selection-{key}.png"),
        full_page=False,
    )
    context.close()


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    value = fixture()
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".semantic-multi-selection-jobs"),
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
        "fixture_object_count": len(value["vi"]["objects"]),
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

    output = ARTIFACTS / "semantic-multi-selection.json"
    output.write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "SEMANTIC_MULTI_SELECTION_JSON="
        + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
    )
    failed = bool(
        diagnostics["failures"]
        or diagnostics["console_errors"]
        or diagnostics["page_errors"]
    )
    print(
        "SEMANTIC_MULTI_SELECTION_TEST_FAILED"
        if failed
        else "SEMANTIC_MULTI_SELECTION_TEST_OK"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
