from __future__ import annotations

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
PORT = int(os.getenv("VI_COMPONENT_PROJECTION_PORT", "8092"))
BASE_URL = f"http://127.0.0.1:{PORT}"
ARTIFACTS = Path(
    os.getenv(
        "BUILD_ARTIFACT_DIR",
        str(ROOT / "artifacts" / "semantic-component-projection"),
    )
)
VIEWPORTS = (
    {"width": 1365, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1920, "height": 1080},
)


def object_record(
    object_id: str,
    *,
    surface: str,
    category: str,
    kind: str,
    visual_kind: str,
    name: str,
    bounds: dict[str, float],
    data_type: str = "numeric",
    symbol: str = "VI",
    owner_object_id: str | None = None,
    parent_object_id: str | None = None,
    terminal_ids: list[str] | None = None,
    wire_ids: list[str] | None = None,
    movable: bool = True,
    resizable: bool = True,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "id": object_id,
        "component_id": object_id,
        "uid": object_id,
        "surface": surface,
        "category": category,
        "kind": kind,
        "visual_kind": visual_kind,
        "name": name,
        "symbol": symbol,
        "class_name": kind,
        "bounds": bounds,
        "positioned": True,
        "movable": movable,
        "resizable": resizable,
        "terminal_ids": terminal_ids or [],
        "linked_terminal_ids": [],
        "wire_ids": wire_ids or [],
        "parent_object_id": parent_object_id,
        "owner_object_id": owner_object_id,
        "linked_object_id": None,
        "child_object_ids": [],
        "data_type": data_type,
        "semantic_source": "component-projection-browser-fixture",
        "source": {
            "file": "component-projection-fixture.xml",
            "xml_path": f"/{object_id}",
        },
        **extra,
    }


def payload() -> dict[str, Any]:
    front_boolean = object_record(
        "projection-front-boolean",
        surface="front-panel",
        category="control",
        kind="boolean-control",
        visual_kind="boolean",
        name="Enable",
        bounds={"x": 80, "y": 100, "width": 56, "height": 56},
        data_type="boolean",
        symbol="ON",
    )
    front_numeric = object_record(
        "projection-front-numeric",
        surface="front-panel",
        category="control",
        kind="numeric-control",
        visual_kind="numeric",
        name="Set point",
        bounds={"x": 210, "y": 105, "width": 160, "height": 52},
        symbol="0.00",
    )
    front_explicit = object_record(
        "projection-front-explicit",
        surface="front-panel",
        category="control",
        kind="string-control",
        visual_kind="string",
        name="VISA resource name",
        bounds={"x": 430, "y": 100, "width": 220, "height": 70},
        data_type="string",
        symbol="abc",
        visual_bounds={"x": 12, "y": 10, "width": 110, "height": 30},
    )
    front_cluster = object_record(
        "projection-front-cluster",
        surface="front-panel",
        category="control",
        kind="cluster-control",
        visual_kind="cluster",
        name="Configuration",
        bounds={"x": 1360, "y": 330, "width": 280, "height": 180},
        data_type="cluster",
        child_object_ids=[],
    )

    source = object_record(
        "projection-source",
        surface="block-diagram",
        category="node",
        kind="subvi",
        visual_kind="subvi",
        name="Source VI",
        bounds={"x": 120, "y": 320, "width": 72, "height": 72},
        terminal_ids=["projection-source-terminal"],
        wire_ids=["projection-wire"],
    )
    target = object_record(
        "projection-target",
        surface="block-diagram",
        category="node",
        kind="primitive-add",
        visual_kind="primitive",
        name="Add",
        bounds={"x": 390, "y": 325, "width": 60, "height": 60},
        symbol="+",
        terminal_ids=["projection-target-terminal"],
        wire_ids=["projection-wire"],
    )
    constant = object_record(
        "projection-constant",
        surface="block-diagram",
        category="node",
        kind="numeric-constant",
        visual_kind="constant",
        name="Constant",
        bounds={"x": 250, "y": 500, "width": 120, "height": 50},
        symbol="1.00",
    )
    structure = object_record(
        "projection-structure",
        surface="block-diagram",
        category="node",
        kind="structure-case",
        visual_kind="structure",
        name="Case Structure",
        bounds={"x": 1280, "y": 260, "width": 320, "height": 220},
        symbol="▣",
        structure_frames=[
            {
                "index": 0,
                "label": "True",
                "is_active": True,
                "object_ids": [],
                "node_uids": [],
            }
        ],
        active_frame_index=0,
        active_frame_label="True",
    )
    source_terminal = object_record(
        "projection-source-terminal",
        surface="block-diagram",
        category="terminal",
        kind="terminal",
        visual_kind="terminal",
        name="result",
        bounds={"x": 168, "y": 344, "width": 24, "height": 24},
        owner_object_id=source["id"],
        wire_ids=["projection-wire"],
        direction="source",
        wire_roles=["source"],
        movable=False,
        resizable=False,
        symbol="",
    )
    target_terminal = object_record(
        "projection-target-terminal",
        surface="block-diagram",
        category="terminal",
        kind="terminal",
        visual_kind="terminal",
        name="input",
        bounds={"x": 378, "y": 343, "width": 24, "height": 24},
        owner_object_id=target["id"],
        wire_ids=["projection-wire"],
        direction="sink",
        wire_roles=["sink"],
        movable=False,
        resizable=False,
        symbol="",
    )
    wire = {
        "id": "projection-wire",
        "name": "Source VI → Add",
        "surface": "block-diagram",
        "source_terminal_id": source_terminal["id"],
        "target_terminal_ids": [target_terminal["id"]],
        "terminal_ids": [source_terminal["id"], target_terminal["id"]],
        "source_object_id": source["id"],
        "target_object_ids": [target["id"]],
        "endpoint_object_ids": [source["id"], target["id"]],
        "route_points": [
            {"x": 180, "y": 356},
            {"x": 280, "y": 356},
            {"x": 280, "y": 355},
            {"x": 390, "y": 355},
        ],
        "resolved": True,
        "direction_confidence": "fixture",
        "native_uid": "projection-signal",
        "native_signal_uid": "projection-signal",
        "net_id": "projection-net",
        "branch_index": 0,
        "branch_count": 1,
        "data_type": "numeric",
        "semantic_source": "component-projection-browser-fixture",
    }

    objects = [
        front_boolean,
        front_numeric,
        front_explicit,
        front_cluster,
        source,
        target,
        constant,
        structure,
        source_terminal,
        target_terminal,
    ]
    return {
        "summary": {"failed_files": 0},
        "warnings": [],
        "graph": {
            "version": 1,
            "models": [],
            "connections": [],
            "nets": [],
            "unresolved": [],
            "documents": [],
        },
        "vi": {
            "version": 6,
            "objects": objects,
            "wires": [wire],
            "nets": [
                {
                    "id": "projection-net",
                    "source_terminal_id": source_terminal["id"],
                    "source_object_id": source["id"],
                    "target_terminal_ids": [target_terminal["id"]],
                    "target_object_ids": [target["id"]],
                    "branch_ids": [wire["id"]],
                    "branch_count": 1,
                    "data_type": "numeric",
                }
            ],
            "surfaces": {
                "front-panel": [
                    front_boolean["id"],
                    front_numeric["id"],
                    front_explicit["id"],
                    front_cluster["id"],
                ],
                "block-diagram": [
                    source["id"],
                    target["id"],
                    constant["id"],
                    structure["id"],
                    source_terminal["id"],
                    target_terminal["id"],
                ],
            },
            "summary": {
                "controls": 4,
                "indicators": 0,
                "front_panel_objects": 4,
                "block_diagram_nodes": 4,
                "terminals": 2,
                "wires": 1,
                "resolved_wires": 1,
                "wire_nets": 1,
            },
            "warnings": [],
            "type_definitions": [],
            "hierarchy": {
                "roots": [item["id"] for item in objects],
                "containers": [front_cluster["id"], structure["id"]],
                "children_by_parent": {},
            },
            "parser": {"name": "lvkit", "mode": "authoritative"},
            "integrity": {"version": 3, "wire_nets": 1},
            "debug": {"generic_graph_used_for_block_diagram": False},
        },
    }


def job() -> dict[str, Any]:
    return {
        "job_id": "component-projection",
        "status": "ready",
        "component_modified_at": "2026-09-11T09:50:00Z",
        "xml_modified_at": "2026-09-11T09:50:00Z",
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


def route_payload(page: Page, model: dict[str, Any]) -> None:
    def model_route(route: Route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(model, ensure_ascii=False),
        )

    page.route("**/api/jobs/component-projection/model*", model_route)


def require(condition: bool, message: str, diagnostics: dict[str, Any]) -> None:
    if not condition:
        diagnostics["failures"].append(message)


def close(first: float, second: float, tolerance: float = 0.8) -> bool:
    return abs(float(first) - float(second)) <= tolerance


def projection_snapshot(page: Page, ids: list[str]) -> dict[str, Any]:
    return page.evaluate(
        """ids => {
          const E = window.VISemanticEditor;
          const S = E.S;
          const P = window.VIComponentProjection;
          const rect = selector => {
            const element = document.querySelector(selector);
            if (!element) return null;
            const value = element.getBoundingClientRect();
            return {
              x: value.x,
              y: value.y,
              width: value.width,
              height: value.height,
            };
          };
          const font = selector => {
            const element = document.querySelector(selector);
            return element
              ? Number.parseFloat(getComputedStyle(element).fontSize)
              : null;
          };
          const records = Object.fromEntries(ids.map(id => {
            const item = S.objects.get(id);
            const logical = item ? E.effectiveBounds(item) : null;
            const projected = item ? P.projectBounds(item, logical) : null;
            const group = document.querySelector(
              `[data-object-id="${CSS.escape(id)}"]`
            );
            return [id, {
              logical,
              projected,
              groupData: group ? {...group.dataset} : null,
              wrapperTransform: group?.querySelector(
                ':scope > .vi-component-geometry'
              )?.getAttribute('transform') || null,
              groupRect: rect(`[data-object-id="${CSS.escape(id)}"]`),
              bodyRect: rect(
                `[data-object-id="${CSS.escape(id)}"] ` +
                '.vi-front-panel-body,' +
                `[data-object-id="${CSS.escape(id)}"] ` +
                '.vi-block-node-body,' +
                `[data-object-id="${CSS.escape(id)}"] ` +
                '.vi-terminal-body'
              ),
              labelInsideGeometry: Boolean(group?.querySelector(
                '.vi-component-geometry .vi-object-label'
              )),
            }];
          }));
          const matrix = S.el.modelGraphSvg.getScreenCTM();
          return {
            surface: S.surface,
            records,
            metrics: P.projectedMetrics(),
            fitMetrics: window.VIComponentFit.representativeMetrics(),
            fitBounds: window.VIComponentFit.projectedContentBounds(),
            scale: window.VICanvasDensity.runtime.currentScale,
            mode: window.VICanvasDensity.runtime.currentMode,
            matrix: matrix ? {
              scaleX: Math.hypot(matrix.a, matrix.b),
              scaleY: Math.hypot(matrix.c, matrix.d),
            } : null,
            commandbar: rect('.azure-command-bar'),
            navigation: rect('.azure-navigation'),
            context: rect('.azure-context-pane'),
            objectPane: rect('.vi-object-pane'),
            fonts: {
              brand: font('.azure-command-bar .brand-copy strong'),
              navigation: font('.navigation-item strong'),
              objectList: font('.vi-list-copy strong'),
              inspector: font('.model-inspector-grid dd'),
              toolbar: font('.vi-canvas-actions .secondary-action'),
            },
            localCount: S.local.size,
            dirtyCount: S.dirty.size,
          };
        }""",
        ids,
    )


def wire_snapshot(page: Page) -> dict[str, Any]:
    return page.evaluate(
        """() => {
          const E = window.VISemanticEditor;
          const P = window.VIComponentProjection;
          const S = E.S;
          const wire = S.wires.get('projection-wire');
          const path = document.querySelector(
            '[data-wire-id="projection-wire"] .vi-wire'
          );
          const points = P.projectedWirePoints(
            wire,
            'projection-target-terminal',
            'projection-target',
          );
          const start = path?.getPointAtLength(0) || null;
          const end = path?.getPointAtLength(path.getTotalLength()) || null;
          return {
            points,
            start: start ? {x: start.x, y: start.y} : null,
            end: end ? {x: end.x, y: end.y} : null,
            source: P.projectedCenter('projection-source-terminal'),
            target: P.projectedCenter('projection-target-terminal'),
            path: path?.getAttribute('d') || null,
            projectedEndpoints: path?.closest('[data-wire-id]')
              ?.dataset.projectedEndpoints || null,
          };
        }"""
    )


def world_delta(page: Page, dx: float, dy: float, x: float, y: float) -> dict[str, float]:
    return page.evaluate(
        """([x, y, dx, dy]) => {
          const matrix = window.VISemanticEditor.S.el.modelGraphSvg
            .getScreenCTM().inverse();
          const first = new DOMPoint(x, y).matrixTransform(matrix);
          const second = new DOMPoint(x + dx, y + dy).matrixTransform(matrix);
          return {x: second.x - first.x, y: second.y - first.y};
        }""",
        [x, y, dx, dy],
    )


def audit_viewport(
    browser,
    viewport: dict[str, int],
    model: dict[str, Any],
    diagnostics: dict[str, Any],
) -> None:
    key = f"{viewport['width']}x{viewport['height']}"
    context = browser.new_context(viewport=viewport)
    page = context.new_page()
    page.set_default_timeout(10_000)
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
    route_payload(page, model)
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_function("() => Boolean(window.viPages && window.viModelGraph)")
    value = job()
    page.evaluate("job => window.viPages.setJob(job, {openModel: true})", value)
    page.evaluate("async job => { await window.viModelGraph.setJob(job); }", value)
    page.wait_for_function(
        """() => Boolean(
          window.VIComponentProjection?.ready
          && window.VIComponentFit?.ready
          && window.VICanvasDensity?.ready
          && window.VISemanticEditor?.S?.vi
        )"""
    )
    page.wait_for_timeout(300)

    front_ids = [
        "projection-front-boolean",
        "projection-front-numeric",
        "projection-front-explicit",
        "projection-front-cluster",
    ]
    front = projection_snapshot(page, front_ids)
    require(close(front["commandbar"]["height"], 48, 1), f"{key}: command bar was compacted", diagnostics)
    require(close(front["navigation"]["width"], 216, 2), f"{key}: navigation was compacted", diagnostics)
    require(close(front["context"]["width"], 292, 2), f"{key}: context pane was compacted", diagnostics)
    require(close(front["objectPane"]["width"], 224, 2), f"{key}: object pane was compacted", diagnostics)
    for name, size in front["fonts"].items():
        require(
            size is None or size >= 9,
            f"{key}: {name} UI font is still miniature ({size}px)",
            diagnostics,
        )
    require(front["localCount"] == 0 and front["dirtyCount"] == 0, f"{key}: initial projection modified edit state", diagnostics)

    expected_front = {
        "projection-front-boolean": (28.0, 28.0, "semantic-fallback"),
        "projection-front-numeric": (92.8, 30.16, "semantic-fallback"),
        "projection-front-explicit": (110.0, 30.0, "native-visual-bounds"),
        "projection-front-cluster": (280.0, 180.0, "native-container"),
    }
    for object_id, (width, height, source) in expected_front.items():
        record = front["records"][object_id]
        projected = record["projected"]
        require(close(projected["width"], width), f"{key}: {object_id} projected width is wrong", diagnostics)
        require(close(projected["height"], height), f"{key}: {object_id} projected height is wrong", diagnostics)
        require(projected["source"] == source, f"{key}: {object_id} projection source is wrong", diagnostics)
        require(not record["labelInsideGeometry"], f"{key}: {object_id} label was scaled with its body", diagnostics)
        if record["bodyRect"] and front["matrix"]:
            require(
                close(
                    record["bodyRect"]["width"],
                    projected["width"] * front["matrix"]["scaleX"],
                    2.2,
                ),
                f"{key}: {object_id} body screen width does not match projection",
                diagnostics,
            )

    page.locator('[data-vi-surface="block-diagram"]').click()
    page.wait_for_function("() => window.VISemanticEditor.S.surface === 'block-diagram'")
    page.wait_for_timeout(260)
    block_ids = [
        "projection-source",
        "projection-target",
        "projection-constant",
        "projection-structure",
        "projection-source-terminal",
        "projection-target-terminal",
    ]
    block = projection_snapshot(page, block_ids)
    expected_block = {
        "projection-source": (36.0, 36.0, 0.50),
        "projection-target": (27.6, 27.6, 0.46),
        "projection-constant": (57.6, 24.0, 0.48),
        "projection-structure": (320.0, 220.0, 1.0),
    }
    for object_id, (width, height, factor) in expected_block.items():
        projected = block["records"][object_id]["projected"]
        require(close(projected["width"], width), f"{key}: {object_id} projected width is wrong", diagnostics)
        require(close(projected["height"], height), f"{key}: {object_id} projected height is wrong", diagnostics)
        require(close(projected["factor_x"], factor, 0.02), f"{key}: {object_id} factor is wrong", diagnostics)

    source_body = block["records"]["projection-source"]["projected"]
    target_body = block["records"]["projection-target"]["projected"]
    source_terminal = block["records"]["projection-source-terminal"]["projected"]
    target_terminal = block["records"]["projection-target-terminal"]["projected"]
    require(close(source_terminal["width"], 7.68, 0.2), f"{key}: source terminal was not reduced", diagnostics)
    require(close(target_terminal["width"], 7.68, 0.2), f"{key}: target terminal was not reduced", diagnostics)
    require(
        close(
            source_terminal["x"] + source_terminal["width"] / 2,
            source_body["x"] + source_body["width"],
            0.3,
        ),
        f"{key}: source terminal is not on the projected owner edge",
        diagnostics,
    )
    require(
        close(
            target_terminal["x"] + target_terminal["width"] / 2,
            target_body["x"],
            0.3,
        ),
        f"{key}: target terminal is not on the projected owner edge",
        diagnostics,
    )

    wire_before = wire_snapshot(page)
    require(wire_before["projectedEndpoints"] == "true", f"{key}: wire was not projected", diagnostics)
    require(
        wire_before["start"] and wire_before["source"]
        and close(wire_before["start"]["x"], wire_before["source"]["x"], 0.5)
        and close(wire_before["start"]["y"], wire_before["source"]["y"], 0.5),
        f"{key}: wire source is not at the projected terminal center",
        diagnostics,
    )
    require(
        wire_before["end"] and wire_before["target"]
        and close(wire_before["end"]["x"], wire_before["target"]["x"], 0.5)
        and close(wire_before["end"]["y"], wire_before["target"]["y"], 0.5),
        f"{key}: wire target is not at the projected terminal center",
        diagnostics,
    )

    body = page.locator(
        '[data-object-id="projection-source"] .vi-component-hit-target'
    ).bounding_box()
    before_drag = page.evaluate(
        """() => ({
          bounds: {...window.VISemanticEditor.effectiveBounds(
            window.VISemanticEditor.S.objects.get('projection-source')
          )},
          terminal: window.VIComponentProjection.projectedCenter(
            'projection-source-terminal'
          ),
        })"""
    )
    require(body is not None, f"{key}: source component has no hit target", diagnostics)
    if body:
        center_x = body["x"] + body["width"] / 2
        center_y = body["y"] + body["height"] / 2
        delta = world_delta(page, 72, 36, center_x, center_y)
        page.mouse.move(center_x, center_y)
        page.mouse.down()
        page.mouse.move(center_x + 72, center_y + 36, steps=6)
        page.mouse.up()
        page.wait_for_timeout(180)
        after_drag = page.evaluate(
            """() => ({
              bounds: {...window.VISemanticEditor.effectiveBounds(
                window.VISemanticEditor.S.objects.get('projection-source')
              )},
              terminal: window.VIComponentProjection.projectedCenter(
                'projection-source-terminal'
              ),
              dirty: window.VISemanticEditor.S.dirty.has('projection-source'),
            })"""
        )
        require(
            close(
                after_drag["bounds"]["x"] - before_drag["bounds"]["x"],
                delta["x"],
                1.5,
            )
            and close(
                after_drag["bounds"]["y"] - before_drag["bounds"]["y"],
                delta["y"],
                1.5,
            ),
            f"{key}: drag delta drifted from the pointer",
            diagnostics,
        )
        require(after_drag["dirty"], f"{key}: drag did not mark the component dirty", diagnostics)
        require(
            close(
                after_drag["terminal"]["x"] - before_drag["terminal"]["x"],
                delta["x"],
                1.5,
            )
            and close(
                after_drag["terminal"]["y"] - before_drag["terminal"]["y"],
                delta["y"],
                1.5,
            ),
            f"{key}: terminal did not follow the dragged projected body",
            diagnostics,
        )
        wire_after = wire_snapshot(page)
        require(wire_after["path"] != wire_before["path"], f"{key}: wire did not follow the dragged component", diagnostics)

    page.evaluate("() => window.VIComponentFit.fit('overview')")
    page.wait_for_timeout(140)
    overview = page.evaluate(
        """() => ({
          scale: window.VICanvasDensity.runtime.currentScale,
          mode: window.VICanvasDensity.runtime.currentMode,
          bounds: window.VIComponentFit.projectedContentBounds({
            includeWires: true,
          }),
        })"""
    )
    require(overview["mode"] == "overview", f"{key}: overview mode was not applied", diagnostics)
    require(overview["scale"] < 1, f"{key}: overview was incorrectly forced to 100%", diagnostics)
    page.evaluate("() => window.VIComponentFit.fit('readable')")
    page.wait_for_timeout(140)
    readable = page.evaluate(
        """() => ({
          scale: window.VICanvasDensity.runtime.currentScale,
          mode: window.VICanvasDensity.runtime.currentMode,
          metrics: window.VIComponentFit.representativeMetrics(),
        })"""
    )
    require(readable["mode"] == "readable", f"{key}: readable mode was not restored", diagnostics)
    require(0.50 <= readable["scale"] <= 1.45, f"{key}: readable scale left projected policy bounds", diagnostics)

    diagnostics["viewports"][key] = {
        "front": front,
        "block": block,
        "wire_before": wire_before,
        "overview": overview,
        "readable": readable,
    }
    page.screenshot(
        path=str(ARTIFACTS / f"component-projection-{key}.png"),
        full_page=False,
    )
    context.close()


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    model = payload()
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".sandbox-component-projection-jobs"),
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
                audit_viewport(browser, viewport, model, diagnostics)
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
                print("COMPONENT_PROJECTION_APP_LOG=" + output[-4000:].replace("\n", "\\n"))

    (ARTIFACTS / "semantic-component-projection.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "SEMANTIC_COMPONENT_PROJECTION_JSON="
        + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
    )
    failed = bool(
        diagnostics["failures"]
        or diagnostics["console_errors"]
        or diagnostics["page_errors"]
    )
    print(
        "SEMANTIC_COMPONENT_PROJECTION_TEST_FAILED"
        if failed
        else "SEMANTIC_COMPONENT_PROJECTION_TEST_OK"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
