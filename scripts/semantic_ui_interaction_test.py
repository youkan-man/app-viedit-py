from __future__ import annotations

import json
import os
import re
import runpy
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, Request, Route, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.component_model import DatasetComponentModel  # noqa: E402
from app.model_graph import build_model_graph  # noqa: E402
from app.semantic_vi import build_semantic_vi  # noqa: E402

ARTIFACTS = Path(
    os.getenv("BUILD_ARTIFACT_DIR", str(ROOT / "artifacts" / "semantic-ui"))
)
PORT = int(os.getenv("VI_UI_INTERACTION_PORT", "8081"))
BASE_URL = f"http://127.0.0.1:{PORT}"
RECT_RE = re.compile(
    r"^\(\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*\)$"
)


def make_payload() -> dict[str, Any]:
    fixture = runpy.run_path(str(ROOT / "tests" / "test_semantic_vi.py"))
    with tempfile.TemporaryDirectory(prefix="semantic-ui-interaction-") as directory:
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


def require(condition: bool, message: str, diagnostics: dict[str, Any]) -> None:
    if not condition:
        diagnostics["failures"].append(message)


def drag(page: Page, selector: str, dx: float, dy: float) -> None:
    box = page.locator(selector).bounding_box()
    if box is None:
        raise AssertionError(f"no browser bounds for {selector}")
    x = box["x"] + box["width"] / 2
    y = box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + dx, y + dy, steps=8)
    page.mouse.up()
    page.wait_for_timeout(140)


def semantic_records(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    vi = payload["vi"]
    objects = vi["objects"]
    input_a = next(item for item in objects if item["name"] == "Input A")
    add = next(item for item in objects if item["kind"] == "add")
    linked_terminal = next(
        item for item in objects if item["id"] in input_a["linked_terminal_ids"]
    )
    native_wire = next(wire for wire in vi["wires"] if wire["route_points"])
    return {
        "input": input_a,
        "linked_terminal": linked_terminal,
        "add": add,
        "native_wire": native_wire,
    }


def apply_native_rectangle(
    payload: dict[str, Any],
    object_id: str,
    serialized: str,
) -> None:
    match = RECT_RE.fullmatch(serialized)
    if not match:
        raise AssertionError(f"invalid serialized rectangle: {serialized}")
    top, left, bottom, right = (int(value) for value in match.groups())
    item = next(item for item in payload["vi"]["objects"] if item["id"] == object_id)
    item["bounds"].update(
        {
            "x": left,
            "y": top,
            "width": right - left,
            "height": bottom - top,
        }
    )


def install_routes(
    page: Page,
    payload: dict[str, Any],
    job: dict[str, Any],
    records: dict[str, dict[str, Any]],
    patches: list[dict[str, Any]],
) -> None:
    def model_route(route: Route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload, ensure_ascii=False),
        )

    def component_route(route: Route, request: Request) -> None:
        property_id = "semantic-native-bounds"
        if request.method == "GET":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "file_sha256": "semantic-ui-fixture-sha256",
                        "bounds": {"property_id": property_id},
                        "properties": [{"id": property_id, "editable": True}],
                    }
                ),
            )
            return
        if request.method == "PATCH":
            patch = request.post_data_json
            patches.append(patch)
            serialized = patch["updates"][0]["value"]
            apply_native_rectangle(payload, records["add"]["id"], serialized)
            updated = {
                **job,
                "component_modified_at": "2026-09-09T14:55:00Z",
            }
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"job": updated}),
            )
            return
        route.fulfill(status=405, body="unsupported method")

    page.route("**/api/jobs/ui-interaction/model*", model_route)
    page.route("**/api/jobs/ui-interaction/components/**", component_route)


def run_audit(payload: dict[str, Any]) -> dict[str, Any]:
    records = semantic_records(payload)
    job = {
        "job_id": "ui-interaction",
        "status": "ready",
        "component_modified_at": "2026-09-09T14:50:00Z",
        "xml_modified_at": "2026-09-09T14:50:00Z",
        "files": [
            {"path": "sum_FPHb.xml", "size": 1024},
            {"path": "sum_BDHb.xml", "size": 2048},
        ],
    }
    diagnostics: dict[str, Any] = {
        "failures": [],
        "console_errors": [],
        "page_errors": [],
        "patches": [],
    }
    patches: list[dict[str, Any]] = diagnostics["patches"]

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
        install_routes(page, payload, job, records, patches)

        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_function("() => Boolean(window.viPages && window.viModelGraph)")
        page.evaluate("job => window.viPages.setJob(job, {openModel: true})", job)
        page.evaluate("async job => { await window.viModelGraph.setJob(job); }", job)
        page.wait_for_function(
            "() => document.querySelectorAll('#model-graph-svg .vi-object').length === 3"
        )
        page.wait_for_function("() => window.VIPersistence?.ready === true")

        input_selector = f'[data-object-id="{records["input"]["id"]}"]'
        terminal_selector = (
            f'[data-object-id="{records["linked_terminal"]["id"]}"]'
        )
        page.locator(input_selector).dblclick()
        page.wait_for_function(
            "expected => window.VISemanticEditor.S.surface === 'block-diagram' && window.VISemanticEditor.S.selected === expected",
            arg=records["linked_terminal"]["id"],
        )
        page.locator(terminal_selector).dblclick()
        page.wait_for_function(
            "expected => window.VISemanticEditor.S.surface === 'front-panel' && window.VISemanticEditor.S.selected === expected",
            arg=records["input"]["id"],
        )

        page.locator('[data-vi-surface="block-diagram"]').click()
        wire_selector = f'[data-wire-id="{records["native_wire"]["id"]}"]'
        page.wait_for_selector(wire_selector)
        route_source = page.locator(wire_selector).first.get_attribute(
            "data-route-source"
        )
        route_count = int(
            page.locator(wire_selector).first.get_attribute("data-route-point-count")
            or "0"
        )
        page.locator(wire_selector).first.click()
        bend_count = page.locator(f"{wire_selector} .vi-wire-bend").count()
        require(route_source == "native", "stored wire route was not used", diagnostics)
        require(route_count >= 4, "native route lost its bend points", diagnostics)
        require(bend_count >= 1, "selected native wire has no bend markers", diagnostics)

        add_selector = f'[data-object-id="{records["add"]["id"]}"]'
        page.locator(add_selector).click()
        page.locator("#model-graph-zoom-in").click()
        page.locator("#model-graph-zoom-in").click()
        view_before = page.locator("#model-graph-svg").get_attribute("viewBox")
        wire_path_before = page.locator(f"{wire_selector} .vi-wire").first.get_attribute(
            "d"
        )
        drag(page, f"{add_selector} .vi-block-node-body", 88, 48)
        wire_path_after = page.locator(f"{wire_selector} .vi-wire").first.get_attribute(
            "d"
        )
        require(
            wire_path_before != wire_path_after,
            "native route endpoint did not follow moved add node",
            diagnostics,
        )

        local_bounds = page.evaluate(
            "id => window.VISemanticEditor.S.local.get(id)", records["add"]["id"]
        )
        expected_value = (
            f"({round(local_bounds['y'])}, {round(local_bounds['x'])}, "
            f"{round(local_bounds['y'] + local_bounds['height'])}, "
            f"{round(local_bounds['x'] + local_bounds['width'])})"
        )
        direct_value = page.evaluate(
            """([id, bounds]) => window.VISemanticEditor.serializeBounds(
              window.VISemanticEditor.S.objects.get(id), bounds
            )""",
            [records["add"]["id"], local_bounds],
        )
        require(
            direct_value == expected_value,
            "native rectangle was not serialized as top,left,bottom,right",
            diagnostics,
        )

        page.evaluate(
            """() => {
              window.__semanticRenderCalls = 0;
              window.renderJob = async (job) => {
                await window.viModelGraph.setJob(job);
                window.__semanticRenderCalls += 1;
              };
            }"""
        )
        page.locator("#vi-save-layout").click()
        page.wait_for_function("() => window.__semanticRenderCalls >= 1")
        page.wait_for_function("() => window.VISemanticEditor.S.dirty.size === 0")
        page.wait_for_function(
            "expected => window.VISemanticEditor.S.selected === expected",
            arg=records["add"]["id"],
        )
        page.wait_for_timeout(160)

        render_calls = page.evaluate("() => window.__semanticRenderCalls")
        selected_after = page.evaluate(
            "() => window.VISemanticEditor.S.selected"
        )
        surface_after = page.evaluate("() => window.VISemanticEditor.S.surface")
        view_after = page.locator("#model-graph-svg").get_attribute("viewBox")
        saved_value = (
            patches[0]["updates"][0]["value"] if len(patches) == 1 else None
        )
        require(render_calls == 1, "save triggered duplicate semantic reloads", diagnostics)
        require(len(patches) == 1, "save did not issue one PATCH", diagnostics)
        require(saved_value == expected_value, "PATCH saved the wrong rectangle", diagnostics)
        require(
            selected_after == records["add"]["id"],
            "selection was lost after same-job reload",
            diagnostics,
        )
        require(
            surface_after == "block-diagram",
            "surface changed after same-job reload",
            diagnostics,
        )
        require(view_after == view_before, "zoom/pan view was lost after save", diagnostics)

        diagnostics.update(
            {
                "route_source": route_source,
                "route_point_count": route_count,
                "bend_count": bend_count,
                "wire_path_before": wire_path_before,
                "wire_path_after": wire_path_after,
                "expected_saved_rectangle": expected_value,
                "saved_rectangle": saved_value,
                "render_calls": render_calls,
                "selected_after_save": selected_after,
                "surface_after_save": surface_after,
                "view_before_save": view_before,
                "view_after_save": view_after,
            }
        )
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(ARTIFACTS / "semantic-interaction.png"))
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
            "WORK_ROOT": str(ROOT / ".sandbox-ui-interaction-jobs"),
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
        print("SEMANTIC_UI_INTERACTION_JSON=" + compact)
        if diagnostics["console_errors"] or diagnostics["page_errors"] or diagnostics["failures"]:
            print("SEMANTIC_UI_INTERACTION_TEST_FAILED")
            return 1
        print("SEMANTIC_UI_INTERACTION_TEST_OK")
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
                print("INTERACTION_APPLICATION_LOG_TAIL=" + output[-4000:].replace("\n", "\\n"))
        if diagnostics is not None:
            print(
                "SEMANTIC_UI_INTERACTION_FINAL_JSON="
                + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
            )


if __name__ == "__main__":
    raise SystemExit(main())
