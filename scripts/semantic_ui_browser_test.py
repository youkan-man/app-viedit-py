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

from app.component_model import DatasetComponentModel
from app.model_graph import build_model_graph
from app.semantic_vi import build_semantic_vi

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = Path(
    os.getenv("BUILD_ARTIFACT_DIR", str(ROOT / "artifacts" / "semantic-ui"))
)
PORT = int(os.getenv("VI_UI_TEST_PORT", "8080"))
BASE_URL = f"http://127.0.0.1:{PORT}"


def make_payload() -> dict[str, Any]:
    fixture = runpy.run_path(str(ROOT / "tests" / "test_semantic_vi.py"))
    with tempfile.TemporaryDirectory(prefix="semantic-ui-") as directory:
        dataset = Path(directory)
        fixture["_write_sum_vi"](dataset)
        model = DatasetComponentModel.analyze(dataset, max_bytes=4 * 1024 * 1024)
        graph = build_model_graph(model)
        vi = build_semantic_vi(model, graph)
    return {"summary": {"failed_files": 0}, "warnings": [], "graph": graph, "vi": vi}


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


def rect(page: Page, selector: str) -> dict[str, float]:
    return page.locator(selector).evaluate(
        """element => {
          const box = element.getBoundingClientRect();
          return {x: box.x, y: box.y, width: box.width, height: box.height,
                  right: box.right, bottom: box.bottom};
        }"""
    )


def require(condition: bool, message: str, diagnostics: dict[str, Any]) -> None:
    if not condition:
        diagnostics["failures"].append(message)


def emit_image(path: Path) -> None:
    data = path.read_bytes()
    encoded = base64.b64encode(data).decode("ascii")
    print(f"UI_CONTACT_SHEET_SHA256={hashlib.sha256(data).hexdigest()}")
    print(f"UI_CONTACT_SHEET_BYTES={len(data)}")
    for offset in range(0, len(encoded), 3000):
        print(f"UI_CONTACT_SHEET_B64_{offset // 3000:03d}={encoded[offset:offset + 3000]}")


def initial_render_state(page: Page) -> dict[str, Any]:
    return page.evaluate(
        """() => ({
          document_ready_state: document.readyState,
          state: window.VISemanticEditor?.S?.state || 'missing',
          graph_state: document.querySelector('#model-graph-state')?.textContent || '',
          surface: window.VISemanticEditor?.S?.surface || '',
          selected: window.VISemanticEditor?.S?.selected || null,
          has_vi: Boolean(window.VISemanticEditor?.S?.vi),
          object_map_size: window.VISemanticEditor?.S?.objects?.size || 0,
          semantic_summary: window.VISemanticEditor?.S?.vi?.summary || null,
          svg_object_count: document.querySelectorAll('#model-graph-svg .vi-object').length,
          svg_child_count: document.querySelector('#model-graph-svg')?.children.length || 0,
          editor_exists: Boolean(document.querySelector('#vi-editor-shell')),
          page_hidden: Boolean(document.querySelector('#page-model')?.hidden),
          stack_hidden: Boolean(document.querySelector('#page-stack')?.hidden),
          empty_message: document.querySelector('#model-graph-empty')?.textContent || '',
          render_function: typeof window.VISemanticEditor?.renderAll,
          interaction_function: typeof window.VISemanticEditor?.bindInteractions
        })"""
    )


def assert_initial_render(
    page: Page,
    vi: dict[str, Any],
    diagnostics: dict[str, Any],
) -> None:
    page.wait_for_timeout(250)
    state = initial_render_state(page)
    diagnostics["initial_render"] = state
    expected = vi["summary"]["front_panel_objects"]
    valid = (
        state["state"] in {"ready", "partial"}
        and state["has_vi"]
        and state["svg_object_count"] == expected
    )
    if valid:
        return
    page.screenshot(path=str(ARTIFACTS / "initial-render-failure.png"))
    raise AssertionError(
        "semantic editor initial render mismatch: "
        + json.dumps(
            {"expected_front_panel_objects": expected, **state},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )


def run_browser_audit(payload: dict[str, Any]) -> dict[str, Any]:
    vi = payload["vi"]
    add = next(item for item in vi["objects"] if item["kind"] == "add")
    owned_terminal = next(
        item for item in vi["objects"] if item.get("owner_object_id") == add["id"]
    )
    related_wire = next(
        wire for wire in vi["wires"] if add["id"] in wire["target_object_ids"]
    )
    job = {
        "job_id": "ui-sample",
        "status": "ready",
        "component_modified_at": "2026-09-09T00:00:00Z",
        "xml_modified_at": "2026-09-09T00:00:00Z",
        "files": [
            {"path": "sum_FPHb.xml", "size": 1024},
            {"path": "sum_BDHb.xml", "size": 2048},
        ],
    }
    diagnostics: dict[str, Any] = {
        "viewport": {"width": 1365, "height": 860},
        "semantic_summary": vi["summary"],
        "console_errors": [],
        "page_errors": [],
        "failures": [],
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

        def model_route(route: Route) -> None:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(payload, ensure_ascii=False),
            )

        page.route("**/api/jobs/ui-sample/model*", model_route)
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_function("() => Boolean(window.viPages && window.viModelGraph)")
        page.evaluate("job => window.viPages.setJob(job, {openModel: true})", job)
        page.evaluate("async job => { await window.viModelGraph.setJob(job); }", job)
        assert_initial_render(page, vi, diagnostics)

        page_size = page.evaluate(
            "() => ({innerWidth, innerHeight, scrollWidth: document.documentElement.scrollWidth, scrollHeight: document.documentElement.scrollHeight})"
        )
        shell = rect(page, "#vi-editor-shell")
        canvas = rect(page, "#model-graph-viewport")
        diagnostics["front_panel"] = {
            "object_count": page.locator("#model-graph-svg .vi-object").count(),
            "shell": shell,
            "canvas": canvas,
            "page": page_size,
        }
        require(canvas["height"] >= 360, "front-panel canvas is too short", diagnostics)
        require(
            page_size["scrollWidth"] <= page_size["innerWidth"] + 2,
            "page has horizontal overflow",
            diagnostics,
        )
        require(
            shell["bottom"] <= page_size["innerHeight"] + 2,
            "editor is clipped below viewport",
            diagnostics,
        )
        page.screenshot(path=str(ARTIFACTS / "front-panel.png"))

        page.locator('[data-vi-surface="block-diagram"]').click()
        page.wait_for_function(
            "expected => document.querySelectorAll('#model-graph-svg .vi-wire-group').length === expected",
            arg=vi["summary"]["wires"],
        )
        add_selector = f'[data-object-id="{add["id"]}"]'
        terminal_selector = f'[data-object-id="{owned_terminal["id"]}"]'
        wire_selector = f'[data-wire-id="{related_wire["id"]}"] .vi-wire'
        before = {
            "node": page.locator(add_selector).get_attribute("transform"),
            "terminal": page.locator(terminal_selector).get_attribute("transform"),
            "wire": page.locator(wire_selector).get_attribute("d"),
        }
        add_box = page.locator(add_selector).bounding_box()
        require(add_box is not None, "add node has no browser bounds", diagnostics)
        if add_box:
            page.mouse.move(
                add_box["x"] + add_box["width"] / 2,
                add_box["y"] + add_box["height"] / 2,
            )
            page.mouse.down()
            page.mouse.move(
                add_box["x"] + add_box["width"] / 2 + 96,
                add_box["y"] + add_box["height"] / 2 + 48,
                steps=6,
            )
            page.mouse.up()
            page.wait_for_timeout(120)
        after = {
            "node": page.locator(add_selector).get_attribute("transform"),
            "terminal": page.locator(terminal_selector).get_attribute("transform"),
            "wire": page.locator(wire_selector).get_attribute("d"),
        }
        diagnostics["block_diagram"] = {
            "object_count": page.locator("#model-graph-svg .vi-object").count(),
            "terminal_count": page.locator(
                "#model-graph-svg .vi-object.is-terminal"
            ).count(),
            "wire_count": page.locator("#model-graph-svg .vi-wire-group").count(),
            "before": before,
            "after": after,
            "canvas": rect(page, "#model-graph-viewport"),
            "object_pane": rect(page, ".vi-object-pane"),
            "inspector_visible": page.locator("#model-context-section").is_visible(),
            "save_enabled": page.locator("#vi-save-layout").is_enabled(),
        }
        require(before["node"] != after["node"], "drag did not move add node", diagnostics)
        require(
            before["terminal"] != after["terminal"],
            "owned terminal did not follow add node",
            diagnostics,
        )
        require(before["wire"] != after["wire"], "wire did not follow add node", diagnostics)
        require(
            diagnostics["block_diagram"]["save_enabled"],
            "layout save was not enabled",
            diagnostics,
        )
        require(
            diagnostics["block_diagram"]["inspector_visible"],
            "selection inspector is hidden",
            diagnostics,
        )
        page.screenshot(path=str(ARTIFACTS / "block-diagram.png"))
        browser.close()

    front = Image.open(ARTIFACTS / "front-panel.png").convert("RGB")
    block = Image.open(ARTIFACTS / "block-diagram.png").convert("RGB")
    front.thumbnail((720, 420))
    block.thumbnail((720, 420))
    sheet = Image.new("RGB", (720, front.height + block.height), "white")
    sheet.paste(front, ((720 - front.width) // 2, 0))
    sheet.paste(block, ((720 - block.width) // 2, front.height))
    sheet.save(ARTIFACTS / "contact-sheet.jpg", quality=38, optimize=True)
    return diagnostics


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    payload = make_payload()
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".sandbox-ui-jobs"),
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
        diagnostics = run_browser_audit(payload)
        compact = json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
        print("UI_AUDIT_JSON=" + compact)
        emit_image(ARTIFACTS / "contact-sheet.jpg")
        print("UI_AUDIT_RESULT_JSON=" + compact)
        if diagnostics["console_errors"] or diagnostics["page_errors"] or diagnostics["failures"]:
            print("SEMANTIC_UI_BROWSER_TEST_FAILED")
            return 1
        print("SEMANTIC_UI_BROWSER_TEST_OK")
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
                print("APPLICATION_LOG_TAIL=" + output[-4000:].replace("\n", "\\n"))
        if diagnostics is not None:
            print(
                "UI_AUDIT_FINAL_JSON="
                + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
            )


if __name__ == "__main__":
    raise SystemExit(main())
