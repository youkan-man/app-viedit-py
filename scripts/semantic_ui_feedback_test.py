from __future__ import annotations

import hashlib
import json
import os
import runpy
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image
from playwright.sync_api import Page, Request, Route, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.component_model import DatasetComponentModel  # noqa: E402
from app.model_graph import build_model_graph  # noqa: E402
from app.semantic_enrichment import enrich_semantic_vi  # noqa: E402
from app.semantic_vi import build_semantic_vi  # noqa: E402

ARTIFACTS = Path(
    os.getenv("BUILD_ARTIFACT_DIR", str(ROOT / "artifacts" / "semantic-feedback"))
)
PORT = int(os.getenv("VI_UI_FEEDBACK_PORT", "8084"))
BASE_URL = f"http://127.0.0.1:{PORT}"


def make_payload() -> dict[str, Any]:
    sum_fixture = runpy.run_path(str(ROOT / "tests" / "test_semantic_vi.py"))
    cluster_fixture = runpy.run_path(
        str(ROOT / "tests" / "test_semantic_hierarchy.py")
    )
    with tempfile.TemporaryDirectory(prefix="semantic-feedback-") as directory:
        dataset = Path(directory)
        sum_fixture["_write_sum_vi"](dataset)
        cluster_fixture["_write_cluster_vi"](dataset)
        model = DatasetComponentModel.analyze(dataset, max_bytes=8 * 1024 * 1024)
        graph = build_model_graph(model)
        semantic = build_semantic_vi(model, graph)
        vi = enrich_semantic_vi(model, graph, semantic)
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


def parse_rectangle(value: str) -> list[float]:
    return [float(item.strip()) for item in value.strip().strip("()").split(",")]


def serialize_object_bounds(item: dict[str, Any]) -> str:
    bounds = item["bounds"]
    left = bounds["x"]
    top = bounds["y"]
    right = left + bounds["width"]
    bottom = top + bounds["height"]
    if bounds.get("storage_order") == "top,left,bottom,right":
        return f"({top}, {left}, {bottom}, {right})"
    return f"({left}, {top}, {right}, {bottom})"


def update_object_bounds(item: dict[str, Any], value: str) -> None:
    first, second, third, fourth = parse_rectangle(value)
    if item["bounds"].get("storage_order") == "top,left,bottom,right":
        top, left, bottom, right = first, second, third, fourth
    else:
        left, top, right, bottom = first, second, third, fourth
    item["bounds"].update(
        {
            "x": left,
            "y": top,
            "width": right - left,
            "height": bottom - top,
        }
    )


def property_id(component_id: str, name: str) -> str:
    return hashlib.sha256(f"{component_id}:{name}".encode()).hexdigest()[:24]


def detail_for(payload: dict[str, Any], component_id: str) -> dict[str, Any]:
    item = next(
        record
        for record in payload["vi"]["objects"]
        if record.get("component_id") == component_id
    )
    bounds_id = item.get("bounds", {}).get("source_property_id") or property_id(
        component_id, "bounds"
    )
    label_id = property_id(component_id, "label")
    uid_id = property_id(component_id, "uid")
    properties = [
        {
            "id": bounds_id,
            "name": item.get("bounds", {}).get("source_property") or "bounds",
            "field_name": item.get("bounds", {}).get("source_property") or "bounds",
            "path": f"{item.get('source', {}).get('xml_path', '')}/bounds",
            "value_type": "rect",
            "value": serialize_object_bounds(item),
            "preview": serialize_object_bounds(item),
            "editable": True,
            "structural": False,
            "reference_like": False,
            "binary": False,
        },
        {
            "id": label_id,
            "name": "name",
            "field_name": "name",
            "path": f"{item.get('source', {}).get('xml_path', '')}/name",
            "value_type": "string",
            "value": item["name"],
            "preview": item["name"],
            "editable": True,
            "structural": False,
            "reference_like": False,
            "binary": False,
        },
        {
            "id": uid_id,
            "name": "SL__uid",
            "field_name": "uid",
            "path": f"{item.get('source', {}).get('xml_path', '')}/SL__uid",
            "value_type": "int",
            "value": item.get("uid") or "0",
            "preview": item.get("uid") or "0",
            "editable": False,
            "structural": True,
            "reference_like": False,
            "binary": False,
        },
    ]
    return {
        "id": component_id,
        "name": item["name"],
        "kind": item["kind"],
        "role": item["category"],
        "class_name": item.get("class_name") or "",
        "uid": item.get("uid") or "",
        "file": item.get("source", {}).get("file") or "fixture.xml",
        "path": item.get("source", {}).get("xml_path") or "/fixture",
        "file_sha256": "a" * 64,
        "bounds": {"property_id": bounds_id, **item.get("bounds", {})},
        "properties": properties,
        "children_detail": [],
        "relationships": {"outbound": [], "inbound": []},
        "breadcrumb": [],
    }


def install_routes(
    page: Page,
    payload: dict[str, Any],
    job: dict[str, Any],
    calls: dict[str, Any],
) -> None:
    def model_route(route: Route) -> None:
        calls["model"] += 1
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload, ensure_ascii=False),
        )

    def components_route(route: Route, request: Request) -> None:
        parsed = urllib.parse.urlparse(request.url)
        marker = "/components"
        suffix = parsed.path.split(marker, 1)[1].strip("/")
        if not suffix:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "job_id": job["job_id"],
                        "total": 0,
                        "offset": 0,
                        "limit": 200,
                        "items": [],
                    }
                ),
            )
            return
        component_id = urllib.parse.unquote(suffix)
        detail = detail_for(payload, component_id)
        if request.method == "GET":
            calls["component_get"] += 1
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(detail, ensure_ascii=False),
            )
            return
        if request.method != "PATCH":
            route.fulfill(status=405, body="unsupported")
            return
        body = request.post_data_json
        calls["patches"].append(body)
        item = next(
            record
            for record in payload["vi"]["objects"]
            if record.get("component_id") == component_id
        )
        updated_ids = []
        for update in body.get("updates", []):
            updated_ids.append(update["property_id"])
            if update["property_id"] == detail["bounds"]["property_id"]:
                update_object_bounds(item, update["value"])
            elif update["property_id"] == property_id(component_id, "label"):
                item["name"] = update["value"]
        calls["revision"] += 1
        job["component_modified_at"] = f"2026-09-10T02:00:{calls['revision']:02d}Z"
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "job": job,
                    "component": detail_for(payload, component_id),
                    "updated_properties": updated_ids,
                },
                ensure_ascii=False,
            ),
        )

    def rebuild_route(route: Route, request: Request) -> None:
        calls["rebuild"] += 1
        calls["rebuild_body"] = request.post_data_json
        job["reconstructed"] = {
            "path": "output/reconstructed.vi",
            "stale": False,
        }
        job["status"] = "completed"
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(job, ensure_ascii=False),
        )

    page.route("**/api/jobs/ui-feedback/model*", model_route)
    page.route("**/api/jobs/ui-feedback/components*", components_route)
    page.route("**/api/jobs/ui-feedback/rebuild", rebuild_route)


def open_editor(page: Page, payload: dict[str, Any], job: dict[str, Any]) -> None:
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_function("() => Boolean(window.viPages && window.viModelGraph)")
    page.evaluate("job => window.viPages.setJob(job, {openModel: true})", job)
    page.evaluate("async job => { await window.viModelGraph.setJob(job); }", job)
    page.wait_for_function(
        "expected => document.querySelectorAll('#model-graph-svg .vi-object').length === expected",
        arg=payload["vi"]["summary"]["front_panel_objects"],
    )
    page.wait_for_function(
        """() => Boolean(
          window.VIRuntimeFixes?.ready
          && window.VIRealism?.ready
          && window.VIPersistence?.ready
          && window.VIInPlaceActions?.ready
          && window.VIInlineProperties?.ready
        )"""
    )
    page.wait_for_timeout(300)


def audit_cluster(
    page: Page,
    payload: dict[str, Any],
    diagnostics: dict[str, Any],
) -> None:
    objects = payload["vi"]["objects"]
    cluster = next(item for item in objects if item.get("data_type") == "cluster")
    children = [
        next(item for item in objects if item["id"] == child_id)
        for child_id in cluster["child_object_ids"]
    ]
    cluster_selector = f'[data-object-id="{cluster["id"]}"]'
    cluster_group = page.locator(cluster_selector)
    cluster_box = cluster_group.bounding_box()
    child_boxes = [
        page.locator(f'[data-object-id="{child["id"]}"]').bounding_box()
        for child in children
    ]
    cluster_index = page.locator("#model-graph-svg > .vi-object").evaluate_all(
        "(nodes, id) => nodes.findIndex(node => node.dataset.objectId === id)",
        cluster["id"],
    )
    child_indexes = [
        page.locator("#model-graph-svg > .vi-object").evaluate_all(
            "(nodes, id) => nodes.findIndex(node => node.dataset.objectId === id)",
            child["id"],
        )
        for child in children
    ]
    require(cluster_group.count() == 1, "cluster container is not rendered", diagnostics)
    require(
        cluster_group.locator(".vi-cluster-interior").count() == 1,
        "cluster interior is missing",
        diagnostics,
    )
    require(len(children) == 2, "cluster members are missing from semantic payload", diagnostics)
    require(all(box is not None for box in child_boxes), "cluster child is not rendered", diagnostics)
    require(
        all(index > cluster_index for index in child_indexes),
        "cluster children are painted below the cluster frame",
        diagnostics,
    )
    if cluster_box and all(child_boxes):
        require(
            all(
                box["x"] >= cluster_box["x"] - 2
                and box["y"] >= cluster_box["y"] - 2
                and box["x"] + box["width"] <= cluster_box["x"] + cluster_box["width"] + 2
                and box["y"] + box["height"] <= cluster_box["y"] + cluster_box["height"] + 2
                for box in child_boxes
                if box
            ),
            "cluster members are not positioned inside the cluster",
            diagnostics,
        )
    diagnostics["cluster"] = {
        "id": cluster["id"],
        "children": [child["name"] for child in children],
        "cluster_box": cluster_box,
        "child_boxes": child_boxes,
        "cluster_index": cluster_index,
        "child_indexes": child_indexes,
    }
    page.screenshot(path=str(ARTIFACTS / "feedback-cluster.png"))


def audit_drag_and_save(
    page: Page,
    payload: dict[str, Any],
    calls: dict[str, Any],
    diagnostics: dict[str, Any],
) -> None:
    input_a = next(item for item in payload["vi"]["objects"] if item["name"] == "Input A")
    selector = f'[data-object-id="{input_a["id"]}"]'
    page.locator("#model-graph-zoom-out").click()
    page.locator("#model-graph-zoom-out").click()
    page.wait_for_timeout(100)
    box = page.locator(selector).bounding_box()
    require(box is not None, "Input A has no browser bounds", diagnostics)
    if box is None:
        return
    fraction_x = 0.31
    fraction_y = 0.43
    start_x = box["x"] + box["width"] * fraction_x
    start_y = box["y"] + box["height"] * fraction_y
    errors = []
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    for dx, dy in ((70, 30), (145, 65), (225, 105)):
        pointer_x = start_x + dx
        pointer_y = start_y + dy
        page.mouse.move(pointer_x, pointer_y, steps=5)
        page.wait_for_timeout(60)
        moved_box = page.locator(selector).bounding_box()
        if moved_box:
            grabbed_x = moved_box["x"] + moved_box["width"] * fraction_x
            grabbed_y = moved_box["y"] + moved_box["height"] * fraction_y
            errors.append(
                {
                    "x": abs(grabbed_x - pointer_x),
                    "y": abs(grabbed_y - pointer_y),
                }
            )
    page.mouse.up()
    page.wait_for_timeout(160)
    require(errors and max(max(item.values()) for item in errors) <= 3.0, "dragged object drifts away from pointer", diagnostics)

    moved_transform = page.locator(selector).get_attribute("transform")
    model_calls_before = calls["model"]
    page.locator("#vi-save-layout").click()
    page.wait_for_function("() => window.VISemanticEditor.S.dirty.size === 0")
    page.wait_for_timeout(180)
    persisted_transform = page.locator(selector).get_attribute("transform")
    require(len(calls["patches"]) == 1, "position save did not issue one PATCH", diagnostics)
    require(calls["model"] > model_calls_before, "position save did not reload semantic model", diagnostics)
    require(
        persisted_transform == moved_transform,
        "saved object returned to its old position after model reload",
        diagnostics,
    )
    diagnostics["drag_and_save"] = {
        "pointer_errors": errors,
        "moved_transform": moved_transform,
        "persisted_transform": persisted_transform,
        "model_calls_before": model_calls_before,
        "model_calls_after": calls["model"],
        "patch": calls["patches"][0] if calls["patches"] else None,
    }


def audit_inline_properties_and_actions(
    page: Page,
    payload: dict[str, Any],
    calls: dict[str, Any],
    diagnostics: dict[str, Any],
) -> None:
    input_b = next(item for item in payload["vi"]["objects"] if item["name"] == "Input B")
    page.locator(f'[data-object-id="{input_b["id"]}"]').click()
    page.wait_for_timeout(260)
    active_before = page.evaluate("() => window.viPages.activePage")
    page.locator("#model-open-properties").click()
    page.wait_for_selector("#vi-inline-properties:not([hidden])")
    page.wait_for_function(
        "() => document.querySelector('#vi-inline-properties-state')?.textContent?.includes('項目')"
    )
    active_after = page.evaluate("() => window.viPages.activePage")
    raw_open = page.locator("#vi-inline-properties-raw").evaluate("element => element.open")
    require(active_before == "model" and active_after == "model", "property details changed pages", diagnostics)
    require(not raw_open, "RAW property data is expanded by default", diagnostics)
    require(
        page.locator("#vi-inline-properties-meaningful .vi-inline-property-row").count() >= 1,
        "semantic property details are empty",
        diagnostics,
    )
    require(
        page.locator("#vi-inline-properties-raw summary").inner_text() == "RAWデータ",
        "XML metadata is not labelled as RAW data",
        diagnostics,
    )
    page.screenshot(path=str(ARTIFACTS / "feedback-inline-properties.png"))

    page.locator("#vi-inline-properties-close").click()
    rebuild_page_before = page.evaluate("() => window.viPages.activePage")
    page.locator("#header-rebuild").click()
    page.wait_for_function("() => window.VIInPlaceActions.runtime.rebuilding === false")
    page.wait_for_timeout(120)
    rebuild_page_after = page.evaluate("() => window.viPages.activePage")
    require(calls["rebuild"] == 1, "rebuild button did not execute rebuild", diagnostics)
    require(
        rebuild_page_before == rebuild_page_after == "model",
        "rebuild button navigated to another page",
        diagnostics,
    )
    require(
        page.locator('[data-app-page="xml"] strong').inner_text() == "RAWデータ",
        "XML view is not identified as RAW data",
        diagnostics,
    )
    require(
        page.locator('[data-app-page="build"] strong').inner_text() == "成果物",
        "build log view still looks like an action button",
        diagnostics,
    )
    diagnostics["inline_and_actions"] = {
        "active_before": active_before,
        "active_after": active_after,
        "raw_open": raw_open,
        "rebuild_calls": calls["rebuild"],
        "rebuild_page_before": rebuild_page_before,
        "rebuild_page_after": rebuild_page_after,
    }


def audit_block_diagram(
    page: Page,
    payload: dict[str, Any],
    diagnostics: dict[str, Any],
) -> None:
    add = next(item for item in payload["vi"]["objects"] if item["kind"] == "add")
    page.locator('[data-vi-surface="block-diagram"]').click()
    page.wait_for_function(
        "expected => document.querySelectorAll('#model-graph-svg .vi-wire-group').length === expected",
        arg=payload["vi"]["summary"]["wires"],
    )
    page.wait_for_timeout(250)
    selector = f'[data-object-id="{add["id"]}"]'
    require(
        page.locator(f"{selector} .vi-primitive-body").count() == 1,
        "arithmetic node is still rendered as a generic rectangle",
        diagnostics,
    )
    require(
        page.locator(selector).get_attribute("data-visual-kind") == "arithmetic",
        "arithmetic visual metadata is missing",
        diagnostics,
    )
    paths = page.locator("#model-graph-svg .vi-wire").evaluate_all(
        "nodes => nodes.map(node => node.getAttribute('d') || '')"
    )
    require(
        all("H" in path or "V" in path for path in paths),
        "diagram wires are not routed orthogonally",
        diagnostics,
    )
    require(
        page.locator("#model-graph-svg .vi-object.is-native-terminal").count()
        == payload["vi"]["summary"]["terminals"],
        "native-style terminals are missing",
        diagnostics,
    )
    diagnostics["block_diagram"] = {
        "add_id": add["id"],
        "wire_paths": paths,
        "terminal_count": page.locator(
            "#model-graph-svg .vi-object.is-native-terminal"
        ).count(),
    }
    page.locator(selector).click()
    page.wait_for_timeout(120)
    page.screenshot(path=str(ARTIFACTS / "feedback-block-diagram.png"))


def build_contact_sheet() -> Path:
    names = (
        "feedback-cluster.png",
        "feedback-inline-properties.png",
        "feedback-block-diagram.png",
    )
    images = [Image.open(ARTIFACTS / name).convert("RGB") for name in names]
    for image in images:
        image.thumbnail((980, 600))
    sheet = Image.new("RGB", (980, sum(image.height for image in images)), "white")
    offset = 0
    for image in images:
        sheet.paste(image, ((980 - image.width) // 2, offset))
        offset += image.height
    output = ARTIFACTS / "feedback-contact-sheet.jpg"
    sheet.save(output, quality=58, optimize=True)
    return output


def run_audit(payload: dict[str, Any]) -> dict[str, Any]:
    job = {
        "job_id": "ui-feedback",
        "kind": "vi_to_xml",
        "status": "completed",
        "component_modified_at": "2026-09-10T02:00:00Z",
        "xml_modified_at": "2026-09-10T02:00:00Z",
        "main_xml": None,
        "xml_editable": False,
        "rebuild_url": "/api/jobs/ui-feedback/rebuild",
        "text_encoding": "shift_jis",
        "source": {"name": "feedback.vi"},
        "files": [],
        "urls": {},
    }
    calls: dict[str, Any] = {
        "model": 0,
        "component_get": 0,
        "patches": [],
        "rebuild": 0,
        "rebuild_body": None,
        "revision": 0,
    }
    diagnostics: dict[str, Any] = {
        "failures": [],
        "console_errors": [],
        "page_errors": [],
        "summary": payload["vi"]["summary"],
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page.on(
            "console",
            lambda message: diagnostics["console_errors"].append(message.text)
            if message.type == "error"
            else None,
        )
        page.on("pageerror", lambda error: diagnostics["page_errors"].append(str(error)))
        install_routes(page, payload, job, calls)
        open_editor(page, payload, job)
        audit_cluster(page, payload, diagnostics)
        audit_drag_and_save(page, payload, calls, diagnostics)
        audit_inline_properties_and_actions(page, payload, calls, diagnostics)
        audit_block_diagram(page, payload, diagnostics)
        browser.close()
    diagnostics["calls"] = calls
    return diagnostics


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    payload = make_payload()
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".sandbox-ui-feedback-jobs"),
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
        print("SEMANTIC_UI_FEEDBACK_JSON=" + compact)
        contact_sheet = build_contact_sheet()
        print(f"SEMANTIC_UI_FEEDBACK_CONTACT_SHEET={contact_sheet}")
        if diagnostics["console_errors"] or diagnostics["page_errors"] or diagnostics["failures"]:
            print("SEMANTIC_UI_FEEDBACK_TEST_FAILED")
            return 1
        print("SEMANTIC_UI_FEEDBACK_TEST_OK")
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
                print("FEEDBACK_APPLICATION_LOG_TAIL=" + output[-4000:].replace("\n", "\\n"))
        if diagnostics is not None:
            print(
                "SEMANTIC_UI_FEEDBACK_FINAL_JSON="
                + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
            )


if __name__ == "__main__":
    raise SystemExit(main())
