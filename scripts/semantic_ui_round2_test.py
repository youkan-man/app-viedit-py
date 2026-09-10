from __future__ import annotations

import base64
import hashlib
import json
import os
import runpy
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image
from playwright.sync_api import Page, Route, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.component_model import DatasetComponentModel  # noqa: E402
from app.model_graph import build_model_graph  # noqa: E402
from app.semantic_vi import build_semantic_vi  # noqa: E402

ARTIFACTS = Path(
    os.getenv("BUILD_ARTIFACT_DIR", str(ROOT / "artifacts" / "semantic-ui-round2"))
)
PORT = int(os.getenv("VI_UI_ROUND2_PORT", "8082"))
BASE_URL = f"http://127.0.0.1:{PORT}"


def make_payload() -> dict[str, Any]:
    fixture = runpy.run_path(str(ROOT / "tests" / "test_semantic_vi.py"))
    with tempfile.TemporaryDirectory(prefix="semantic-ui-round2-") as directory:
        dataset = Path(directory)
        fixture["_write_sum_vi"](dataset)
        model = DatasetComponentModel.analyze(dataset, max_bytes=4 * 1024 * 1024)
        graph = build_model_graph(model)
        vi = build_semantic_vi(model, graph)
    return {
        "summary": {"failed_files": 0},
        "warnings": [],
        "graph": graph,
        "vi": vi,
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


def require(condition: bool, message: str, diagnostics: dict[str, Any]) -> None:
    if not condition:
        diagnostics["failures"].append(message)


def drag(page: Page, selector: str, dx: float, dy: float) -> None:
    box = page.locator(selector).bounding_box()
    if box is None:
        raise AssertionError(f"no browser bounds for {selector}")
    start_x = box["x"] + box["width"] / 2
    start_y = box["y"] + box["height"] / 2
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(start_x + dx, start_y + dy, steps=8)
    page.mouse.up()
    page.wait_for_timeout(180)


def rect(page: Page, selector: str) -> dict[str, float]:
    return page.locator(selector).evaluate(
        """element => {
          const box = element.getBoundingClientRect();
          return {x: box.x, y: box.y, width: box.width, height: box.height,
                  right: box.right, bottom: box.bottom};
        }"""
    )


def emit_image(path: Path) -> None:
    data = path.read_bytes()
    encoded = base64.b64encode(data).decode("ascii")
    print(f"ROUND2_CONTACT_SHEET_SHA256={hashlib.sha256(data).hexdigest()}")
    print(f"ROUND2_CONTACT_SHEET_BYTES={len(data)}")
    for offset in range(0, len(encoded), 3000):
        print(
            f"ROUND2_CONTACT_SHEET_B64_{offset // 3000:03d}="
            + encoded[offset : offset + 3000]
        )


def semantic_records(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    objects = payload["vi"]["objects"]
    return {
        "input_a": next(item for item in objects if item["name"] == "Input A"),
        "input_b": next(item for item in objects if item["name"] == "Input B"),
        "add": next(item for item in objects if item["kind"] == "add"),
        "result": next(item for item in objects if item["name"] == "Result"),
    }


def install_model_route(page: Page, payload: dict[str, Any]) -> None:
    def model_route(route: Route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload, ensure_ascii=False),
        )

    page.route("**/api/jobs/ui-round2/model*", model_route)


def open_editor(page: Page, payload: dict[str, Any]) -> None:
    job = {
        "job_id": "ui-round2",
        "status": "ready",
        "component_modified_at": "2026-09-09T23:30:00Z",
        "xml_modified_at": "2026-09-09T23:30:00Z",
        "files": [
            {"path": "sum_FPHb.xml", "size": 1024},
            {"path": "sum_BDHb.xml", "size": 2048},
        ],
    }
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_function("() => Boolean(window.viPages && window.viModelGraph)")
    page.evaluate("job => window.viPages.setJob(job, {openModel: true})", job)
    page.evaluate("async job => { await window.viModelGraph.setJob(job); }", job)
    page.wait_for_function(
        "expected => document.querySelectorAll('#model-graph-svg .vi-object').length === expected",
        arg=payload["vi"]["summary"]["front_panel_objects"],
    )
    page.wait_for_function("() => window.VISemanticEnhancements?.ready === true")
    page.wait_for_timeout(260)


def audit_front_panel(
    page: Page,
    records: dict[str, dict[str, Any]],
    diagnostics: dict[str, Any],
) -> None:
    input_a = records["input_a"]
    selector = f'[data-object-id="{input_a["id"]}"]'
    page.locator(selector).click()
    page.wait_for_timeout(280)

    semantic = {
        "kind": page.locator("#vi-inspector-kind").inner_text(),
        "surface": page.locator("#vi-inspector-surface").inner_text(),
        "role": page.locator("#vi-inspector-role").inner_text(),
        "data_type": page.locator("#vi-inspector-data-type").inner_text(),
        "connections": page.locator("#vi-inspector-connections-summary").inner_text(),
        "source_details_open": page.locator("#vi-inspector-source-details").evaluate(
            "element => element.open"
        ),
        "counterpart_visible": page.locator("#vi-jump-counterpart").is_visible(),
    }
    require(semantic["kind"] == "数値入力", "semantic kind is not numeric control", diagnostics)
    require(
        semantic["surface"] == "フロントパネル",
        "semantic surface is not front panel",
        diagnostics,
    )
    require("入力コントロール" in semantic["role"], "semantic role is missing", diagnostics)
    require(semantic["data_type"] == "数値", "numeric data type is not shown", diagnostics)
    require(not semantic["source_details_open"], "raw XML metadata is expanded by default", diagnostics)
    require(semantic["counterpart_visible"], "counterpart navigation is hidden", diagnostics)

    selected_list = page.locator(f'#vi-object-list [data-list-id="{input_a["id"]}"]')
    selected_list.focus()
    selected_list.press("ArrowDown")
    page.wait_for_timeout(160)
    selected_after_arrow = page.evaluate("() => window.VISemanticEditor.S.selected")
    focused_after_arrow = page.locator("#vi-object-list [data-list-id]:focus").count()
    require(
        selected_after_arrow != input_a["id"],
        "ArrowDown did not move object-list selection",
        diagnostics,
    )
    require(focused_after_arrow == 1, "object-list keyboard focus was lost", diagnostics)

    page.locator(selector).click()
    page.wait_for_timeout(280)
    page.locator("#vi-jump-counterpart").click()
    page.wait_for_function("() => window.VISemanticEditor.S.surface === 'block-diagram'")
    counterpart_selected = page.evaluate("() => window.VISemanticEditor.S.selected")
    require(
        counterpart_selected in input_a["linked_terminal_ids"],
        "counterpart command did not select the linked terminal",
        diagnostics,
    )

    diagnostics["front_panel"] = {
        "semantic_inspector": semantic,
        "selected_after_arrow": selected_after_arrow,
        "focused_after_arrow": focused_after_arrow,
        "counterpart_selected": counterpart_selected,
        "canvas": rect(page, "#model-graph-viewport"),
    }
    page.locator('[data-vi-surface="front-panel"]').click()
    page.locator(selector).click()
    page.wait_for_timeout(280)
    page.screenshot(path=str(ARTIFACTS / "round2-front-panel.png"))


def audit_block_diagram(
    page: Page,
    payload: dict[str, Any],
    records: dict[str, dict[str, Any]],
    diagnostics: dict[str, Any],
) -> None:
    add = records["add"]
    page.locator('[data-vi-surface="block-diagram"]').click()
    page.wait_for_function(
        "expected => document.querySelectorAll('#model-graph-svg .vi-wire-group').length === expected",
        arg=payload["vi"]["summary"]["wires"],
    )
    page.wait_for_timeout(180)

    wire_types = page.locator("#model-graph-svg .vi-wire-group").evaluate_all(
        "groups => groups.map(group => group.dataset.dataType)"
    )
    require(
        wire_types and all(value == "numeric" for value in wire_types),
        "numeric wires were not decorated as numeric",
        diagnostics,
    )

    add_selector = f'[data-object-id="{add["id"]}"]'
    page.locator(add_selector).click()
    page.wait_for_timeout(160)
    terminal_caption_count = page.locator("#model-graph-svg .vi-terminal-caption").count()
    terminal_dot_count = page.locator(
        "#model-graph-svg .vi-terminal-type-dot.is-type-numeric"
    ).count()
    require(terminal_caption_count >= 3, "selected node terminal captions are missing", diagnostics)
    require(terminal_dot_count >= 6, "terminal type markers are missing", diagnostics)
    require(
        page.locator("#vi-inspector-kind").inner_text() == "加算",
        "add node semantic kind is wrong",
        diagnostics,
    )
    require(
        page.locator("#vi-inspector-data-type").inner_text() == "数値",
        "add node data type is wrong",
        diagnostics,
    )
    require(
        "入力" in page.locator("#vi-inspector-connections-summary").inner_text(),
        "add node connection summary is missing",
        diagnostics,
    )

    page.locator("#model-graph-zoom-out").click()
    page.locator("#model-graph-zoom-out").click()
    view_before_focus = page.locator("#model-graph-svg").get_attribute("viewBox")
    page.locator("#vi-focus-selection").click()
    page.wait_for_timeout(100)
    view_after_focus = page.locator("#model-graph-svg").get_attribute("viewBox")
    require(
        view_before_focus != view_after_focus,
        "focus-selection command did not change the viewport",
        diagnostics,
    )

    transform_before = page.locator(add_selector).get_attribute("transform")
    drag(page, f"{add_selector} .vi-block-node-body", 84, 44)
    transform_after_move = page.locator(add_selector).get_attribute("transform")
    require(
        transform_before != transform_after_move,
        "dragging did not move the add node",
        diagnostics,
    )
    require(
        page.locator("#vi-undo-layout").is_enabled(),
        "undo did not become enabled after moving a node",
        diagnostics,
    )

    paths_after_move = page.locator("#model-graph-svg .vi-wire").evaluate_all(
        "paths => paths.map(path => path.getAttribute('d') || '')"
    )
    require(
        all(" L " not in f" {path} " for path in paths_after_move),
        "a moved endpoint left a diagonal wire segment",
        diagnostics,
    )

    page.locator("#vi-undo-layout").click()
    page.wait_for_timeout(120)
    transform_after_undo = page.locator(add_selector).get_attribute("transform")
    require(
        transform_after_undo == transform_before,
        "undo did not restore the original add-node position",
        diagnostics,
    )
    require(
        page.locator("#vi-redo-layout").is_enabled(),
        "redo did not become enabled after undo",
        diagnostics,
    )

    page.locator("#vi-redo-layout").click()
    page.wait_for_timeout(120)
    transform_after_redo = page.locator(add_selector).get_attribute("transform")
    require(
        transform_after_redo == transform_after_move,
        "redo did not restore the moved add-node position",
        diagnostics,
    )

    # Selecting the add node relates the complete three-wire graph, so there is
    # no unrelated object to dim. Select an offscreen input terminal through the
    # object list, which is also the intended user path after focusing a node.
    terminal_id = records["input_a"]["linked_terminal_ids"][0]
    terminal_list = page.locator(f'#vi-object-list [data-list-id="{terminal_id}"]')
    terminal_list.click()
    page.wait_for_timeout(180)
    unrelated = page.locator(
        "#model-graph-svg .vi-object:not(.is-related):not(.is-selected)"
    )
    unrelated_count = unrelated.count()
    require(unrelated_count > 0, "terminal selection has no unrelated context", diagnostics)
    unrelated_opacity = (
        unrelated.first.evaluate("element => getComputedStyle(element).opacity")
        if unrelated_count
        else "1"
    )
    require(
        float(unrelated_opacity) < 0.8,
        "unrelated diagram objects are not visually de-emphasized",
        diagnostics,
    )

    page.keyboard.press("Escape")
    page.wait_for_timeout(100)
    require(
        page.evaluate("() => window.VISemanticEditor.S.selected") is None,
        "Escape did not clear the selection",
        diagnostics,
    )

    diagnostics["block_diagram"] = {
        "wire_types": wire_types,
        "terminal_caption_count": terminal_caption_count,
        "terminal_dot_count": terminal_dot_count,
        "view_before_focus": view_before_focus,
        "view_after_focus": view_after_focus,
        "transform_before": transform_before,
        "transform_after_move": transform_after_move,
        "transform_after_undo": transform_after_undo,
        "transform_after_redo": transform_after_redo,
        "wire_paths_after_move": paths_after_move,
        "unrelated_count": unrelated_count,
        "unrelated_opacity": unrelated_opacity,
        "canvas": rect(page, "#model-graph-viewport"),
    }
    page.locator(add_selector).click()
    page.wait_for_timeout(100)
    page.screenshot(path=str(ARTIFACTS / "round2-block-diagram.png"))


def audit_responsive(page: Page, diagnostics: dict[str, Any]) -> None:
    page.set_viewport_size({"width": 920, "height": 720})
    page.wait_for_timeout(220)
    require(
        page.locator("#vi-object-drawer-toggle").is_visible(),
        "responsive object drawer toggle is hidden",
        diagnostics,
    )
    page.locator("#vi-object-drawer-toggle").click()
    page.wait_for_timeout(220)
    drawer = rect(page, ".vi-object-pane")
    canvas = rect(page, "#model-graph-viewport")
    page_size = page.evaluate(
        "() => ({width: innerWidth, height: innerHeight, scrollWidth: document.documentElement.scrollWidth, scrollHeight: document.documentElement.scrollHeight})"
    )
    require(drawer["right"] > 150, "responsive object drawer did not open", diagnostics)
    require(canvas["height"] >= 360, "responsive canvas is too short", diagnostics)
    require(
        page_size["scrollWidth"] <= page_size["width"] + 2,
        "responsive page has horizontal overflow",
        diagnostics,
    )
    require(
        page_size["scrollHeight"] <= page_size["height"] + 2,
        "responsive page has vertical overflow",
        diagnostics,
    )
    diagnostics["responsive"] = {
        "drawer": drawer,
        "canvas": canvas,
        "page": page_size,
    }
    page.screenshot(path=str(ARTIFACTS / "round2-responsive.png"))


def build_contact_sheet() -> Path:
    images = [
        Image.open(ARTIFACTS / name).convert("RGB")
        for name in (
            "round2-front-panel.png",
            "round2-block-diagram.png",
            "round2-responsive.png",
        )
    ]
    for image in images:
        image.thumbnail((980, 600))
    sheet = Image.new("RGB", (980, sum(image.height for image in images)), "white")
    offset = 0
    for image in images:
        sheet.paste(image, ((980 - image.width) // 2, offset))
        offset += image.height
    path = ARTIFACTS / "round2-contact-sheet.jpg"
    sheet.save(path, quality=54, optimize=True)
    return path


def run_audit(payload: dict[str, Any]) -> dict[str, Any]:
    records = semantic_records(payload)
    diagnostics: dict[str, Any] = {
        "failures": [],
        "console_errors": [],
        "page_errors": [],
        "semantic_summary": payload["vi"]["summary"],
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1365, "height": 860})
        page = context.new_page()
        page.on(
            "console",
            lambda message: diagnostics["console_errors"].append(message.text)
            if message.type == "error"
            else None,
        )
        page.on("pageerror", lambda error: diagnostics["page_errors"].append(str(error)))
        install_model_route(page, payload)
        open_editor(page, payload)
        audit_front_panel(page, records, diagnostics)
        audit_block_diagram(page, payload, records, diagnostics)
        audit_responsive(page, diagnostics)
        browser.close()
    return diagnostics


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    payload = make_payload()
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".sandbox-ui-round2-jobs"),
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
    diagnostics: dict[str, Any] | None = None
    try:
        wait_for_server(process)
        diagnostics = run_audit(payload)
        compact = json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
        print("SEMANTIC_UI_ROUND2_JSON=" + compact)
        contact_sheet = build_contact_sheet()
        emit_image(contact_sheet)
        if diagnostics["console_errors"] or diagnostics["page_errors"] or diagnostics["failures"]:
            print("SEMANTIC_UI_ROUND2_TEST_FAILED")
            return 1
        print("SEMANTIC_UI_ROUND2_TEST_OK")
        return 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
        if process.stdout:
            output = process.stdout.read()
            if output:
                print("ROUND2_APPLICATION_LOG_TAIL=" + output[-4000:].replace("\n", "\\n"))
        if diagnostics is not None:
            print(
                "SEMANTIC_UI_ROUND2_FINAL_JSON="
                + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
            )


if __name__ == "__main__":
    raise SystemExit(main())
