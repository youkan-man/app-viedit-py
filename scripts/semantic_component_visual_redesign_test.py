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

from semantic_component_projection_test import (  # noqa: E402
    object_record,
    payload as projection_payload,
)

PORT = int(os.getenv("VI_COMPONENT_VISUAL_PORT", "8098"))
BASE_URL = f"http://127.0.0.1:{PORT}"
ARTIFACTS = Path(
    os.getenv(
        "BUILD_ARTIFACT_DIR",
        str(ROOT / "artifacts" / "semantic-component-visuals"),
    )
)
VIEWPORTS = (
    {"width": 1365, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1920, "height": 1080},
)


def front_object(
    object_id: str,
    *,
    name: str,
    category: str,
    visual_kind: str,
    data_type: str,
    x: float,
    y: float,
    width: float,
    height: float,
    **extra: Any,
) -> dict[str, Any]:
    return object_record(
        object_id,
        surface="front-panel",
        category=category,
        kind=f"{visual_kind}-{category}",
        visual_kind=visual_kind,
        name=name,
        bounds={"x": x, "y": y, "width": width, "height": height},
        data_type=data_type,
        symbol="",
        **extra,
    )


def block_object(
    object_id: str,
    *,
    name: str,
    kind: str,
    visual_kind: str,
    data_type: str,
    symbol: str,
    x: float,
    y: float,
    width: float = 66,
    height: float = 58,
    **extra: Any,
) -> dict[str, Any]:
    return object_record(
        object_id,
        surface="block-diagram",
        category="node",
        kind=kind,
        visual_kind=visual_kind,
        name=name,
        bounds={"x": x, "y": y, "width": width, "height": height},
        data_type=data_type,
        symbol=symbol,
        **extra,
    )


def model() -> dict[str, Any]:
    value = copy.deepcopy(projection_payload())
    vi = value["vi"]
    objects = vi["objects"]
    by_id = {item["id"]: item for item in objects}

    # Reuse the projection fixture's connected objects, but classify the
    # arithmetic target precisely for the visual system.
    by_id["projection-target"].update(
        {
            "kind": "add",
            "visual_kind": "arithmetic",
            "symbol": "+",
            "data_type": "numeric",
        }
    )
    by_id["projection-front-cluster"]["bounds"] = {
        "x": 700,
        "y": 355,
        "width": 300,
        "height": 185,
    }
    by_id["projection-structure"]["bounds"] = {
        "x": 690,
        "y": 340,
        "width": 330,
        "height": 225,
    }

    front = [
        front_object(
            "visual-front-numeric-indicator",
            name="Actual value",
            category="indicator",
            visual_kind="numeric",
            data_type="numeric",
            x=430,
            y=105,
            width=170,
            height=54,
            display_value="12.50",
        ),
        front_object(
            "visual-front-boolean-indicator",
            name="Ready",
            category="indicator",
            visual_kind="boolean",
            data_type="boolean",
            x=160,
            y=210,
            width=64,
            height=58,
            display_value="TRUE",
        ),
        front_object(
            "visual-front-string-control",
            name="Command",
            category="control",
            visual_kind="string",
            data_type="string",
            x=300,
            y=210,
            width=210,
            height=52,
            display_value="START",
        ),
        front_object(
            "visual-front-string-indicator",
            name="Status text",
            category="indicator",
            visual_kind="string",
            data_type="string",
            x=560,
            y=210,
            width=210,
            height=52,
            display_value="Running",
        ),
        front_object(
            "visual-front-path-control",
            name="Input path",
            category="control",
            visual_kind="path",
            data_type="path",
            x=80,
            y=305,
            width=250,
            height=54,
            display_value="/input/data",
        ),
        front_object(
            "visual-front-path-indicator",
            name="Output path",
            category="indicator",
            visual_kind="path",
            data_type="path",
            x=365,
            y=305,
            width=250,
            height=54,
            display_value="/output/result",
        ),
        front_object(
            "visual-front-ring-control",
            name="Mode",
            category="control",
            visual_kind="ring",
            data_type="ring",
            x=650,
            y=305,
            width=180,
            height=54,
            display_value="Automatic",
        ),
        front_object(
            "visual-front-table",
            name="Samples",
            category="indicator",
            visual_kind="table",
            data_type="table",
            x=80,
            y=410,
            width=270,
            height=150,
        ),
        front_object(
            "visual-front-array",
            name="Measurements",
            category="indicator",
            visual_kind="array",
            data_type="array",
            x=390,
            y=395,
            width=245,
            height=165,
            child_object_ids=["visual-array-child"],
            is_container=True,
        ),
        front_object(
            "visual-array-child",
            name="Element",
            category="indicator",
            visual_kind="numeric",
            data_type="numeric",
            x=445,
            y=455,
            width=120,
            height=46,
            parent_object_id="visual-front-array",
            nesting_depth=1,
        ),
        front_object(
            "visual-cluster-child",
            name="Threshold",
            category="control",
            visual_kind="numeric",
            data_type="numeric",
            x=760,
            y=430,
            width=145,
            height=48,
            parent_object_id="projection-front-cluster",
            nesting_depth=1,
        ),
    ]
    by_id["projection-front-cluster"]["child_object_ids"] = [
        "visual-cluster-child"
    ]

    block = [
        block_object(
            "visual-block-compare",
            name="Greater?",
            kind="greater",
            visual_kind="primitive",
            data_type="boolean",
            symbol=">",
            x=260,
            y=190,
        ),
        block_object(
            "visual-block-logic",
            name="AND",
            kind="and",
            visual_kind="primitive",
            data_type="boolean",
            symbol="∧",
            x=390,
            y=190,
        ),
        block_object(
            "visual-block-select",
            name="Select",
            kind="select",
            visual_kind="primitive",
            data_type="numeric",
            symbol="?",
            x=520,
            y=190,
        ),
        block_object(
            "visual-block-string-constant",
            name="Message constant",
            kind="string-constant",
            visual_kind="constant",
            data_type="string",
            symbol="abc",
            x=180,
            y=470,
            width=150,
            height=54,
            display_value="Complete",
        ),
        block_object(
            "visual-block-generic",
            name="Scale and offset",
            kind="formula-node",
            visual_kind="node",
            data_type="numeric",
            symbol="ƒ",
            x=430,
            y=475,
            width=105,
            height=72,
        ),
    ]

    objects.extend(front + block)
    front_ids = [
        item["id"] for item in objects if item["surface"] == "front-panel"
    ]
    block_ids = [
        item["id"] for item in objects if item["surface"] == "block-diagram"
    ]
    vi["surfaces"]["front-panel"] = front_ids
    vi["surfaces"]["block-diagram"] = block_ids
    vi["summary"].update(
        {
            "controls": sum(
                item["surface"] == "front-panel"
                and item["category"] == "control"
                for item in objects
            ),
            "indicators": sum(
                item["surface"] == "front-panel"
                and item["category"] == "indicator"
                for item in objects
            ),
            "front_panel_objects": len(front_ids),
            "block_diagram_nodes": sum(
                item["surface"] == "block-diagram"
                and item["category"] == "node"
                for item in objects
            ),
            "terminals": sum(item["category"] == "terminal" for item in objects),
        }
    )
    vi["hierarchy"] = {
        "roots": [
            item["id"]
            for item in objects
            if not item.get("parent_object_id")
        ],
        "containers": [
            "visual-front-array",
            "projection-front-cluster",
            "projection-structure",
        ],
        "children_by_parent": {
            "visual-front-array": ["visual-array-child"],
            "projection-front-cluster": ["visual-cluster-child"],
        },
    }
    return value


def job() -> dict[str, Any]:
    return {
        "job_id": "component-visuals",
        "status": "ready",
        "component_modified_at": "2026-09-12T05:30:00Z",
        "xml_modified_at": "2026-09-12T05:30:00Z",
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

    page.route("**/api/jobs/component-visuals/model*", model_route)


def require(condition: bool, message: str, diagnostics: dict[str, Any]) -> None:
    if not condition:
        diagnostics["failures"].append(message)


def component_snapshot(page: Page, ids: list[str]) -> dict[str, Any]:
    return page.evaluate(
        """ids => {
          const E = window.VISemanticEditor;
          const S = E.S;
          const root = S.el.modelGraphSvg;
          const record = id => {
            const group = document.querySelector(
              `[data-object-id="${CSS.escape(id)}"]`
            );
            const skin = group?.querySelector('.vi-component-skin');
            const anchor = group?.querySelector(
              '.vi-front-panel-body,.vi-block-node-body,.vi-terminal-body'
            );
            const label = group?.querySelector(':scope > .vi-object-label');
            const rect = group?.getBoundingClientRect();
            const hit = group?.querySelector(
              ':scope > .vi-component-hit-target,' +
              ':scope > .vi-resize-hit-target'
            );
            return {
              exists: Boolean(group),
              signature: group?.dataset.componentVisualSignature || null,
              visual: group?.dataset.componentVisual || null,
              role: group?.dataset.componentRole || null,
              type: group?.dataset.componentDataType || null,
              skinCount: group?.querySelectorAll('.vi-component-skin').length || 0,
              legacyCount: group?.querySelectorAll(
                '.vi-cluster-interior,.vi-array-index,.vi-boolean-led,' +
                '.vi-numeric-spinner,.vi-primitive-body,.vi-structure-titlebar,' +
                '.vi-subvi-icon'
              ).length || 0,
              shapeClasses: skin
                ? [...skin.querySelectorAll('*')]
                    .flatMap(element => [...element.classList])
                    .filter((value, index, values) => values.indexOf(value) === index)
                : [],
              skinPointerEvents: skin ? getComputedStyle(skin).pointerEvents : null,
              anchorFill: anchor ? getComputedStyle(anchor).fill : null,
              anchorStroke: anchor ? getComputedStyle(anchor).stroke : null,
              labelOutsideSkin: Boolean(label && skin && !skin.contains(label)),
              hasHitTarget: Boolean(hit),
              screenRect: rect ? {
                x: rect.x,
                y: rect.y,
                width: rect.width,
                height: rect.height,
              } : null,
            };
          };
          const order = [...root.children]
            .filter(element => element.dataset?.objectId)
            .map(element => element.dataset.objectId);
          return {
            surface: S.surface,
            lod: document.querySelector('#vi-editor-shell')?.dataset.viLod,
            mode: document.querySelector('#vi-editor-shell')?.dataset.viViewMode,
            localKeys: [...S.local.keys()].sort(),
            dirtyKeys: [...S.dirty].sort(),
            records: Object.fromEntries(ids.map(id => [id, record(id)])),
            order,
            visualReady: window.VIComponentVisuals?.ready === true,
            visualRootMarker: root.dataset.componentVisualSystem || null,
            runtimeModules: window.VIRuntimeFixes?.modules || [],
          };
        }""",
        ids,
    )


def detail_state(page: Page, object_id: str) -> dict[str, Any]:
    return page.evaluate(
        """id => {
          const group = document.querySelector(
            `[data-object-id="${CSS.escape(id)}"]`
          );
          const detail = group?.querySelector('.vi-skin-detail');
          const value = group?.querySelector('.vi-skin-value');
          const frame = group?.querySelector(
            '.vi-skin-frame,.vi-skin-primitive-body,.vi-skin-structure-frame'
          );
          return {
            lod: document.querySelector('#vi-editor-shell')?.dataset.viLod,
            detail: detail ? getComputedStyle(detail).display : null,
            value: value ? getComputedStyle(value).display : null,
            frame: frame ? getComputedStyle(frame).display : null,
          };
        }""",
        object_id,
    )


def terminal_hit(page: Page, terminal_id: str) -> str | None:
    return page.evaluate(
        """id => {
          const group = document.querySelector(
            `[data-object-id="${CSS.escape(id)}"]`
          );
          const rect = group?.getBoundingClientRect();
          if (!rect) return null;
          const element = document.elementFromPoint(
            rect.left + rect.width / 2,
            rect.top + rect.height / 2,
          );
          return element?.closest?.('[data-object-id]')?.dataset.objectId || null;
        }""",
        terminal_id,
    )


def audit_viewport(
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
    current_job = job()
    page.evaluate(
        "value => window.viPages.setJob(value, {openModel: true})",
        current_job,
    )
    page.evaluate(
        "async value => { await window.viModelGraph.setJob(value); }",
        current_job,
    )
    page.wait_for_function(
        """() => Boolean(
          window.VIRuntimeFixes?.ready
          && window.VIComponentVisuals?.ready
          && window.VIComponentPrimer?.ready
          && window.VIComponentProjection?.ready
          && window.VIComponentFit?.ready
          && window.VIWireStability?.ready
          && window.VISemanticEditor?.S?.vi
        )"""
    )
    page.wait_for_timeout(350)

    front_ids = [
        "projection-front-boolean",
        "visual-front-boolean-indicator",
        "projection-front-numeric",
        "visual-front-numeric-indicator",
        "visual-front-string-control",
        "visual-front-string-indicator",
        "visual-front-path-control",
        "visual-front-path-indicator",
        "visual-front-ring-control",
        "visual-front-table",
        "visual-front-array",
        "visual-array-child",
        "projection-front-cluster",
        "visual-cluster-child",
    ]
    front = component_snapshot(page, front_ids)
    diagnostics["viewports"].setdefault(key, {})["front"] = front
    require(front["visualReady"], f"{key}: visual runtime is not ready", diagnostics)
    require(
        "vi-editor-component-visuals" in front["runtimeModules"],
        f"{key}: visual runtime is absent from the module manifest",
        diagnostics,
    )
    require(
        front["visualRootMarker"] == "semantic-v1",
        f"{key}: SVG root has no semantic visual marker",
        diagnostics,
    )
    for object_id in front_ids:
        record = front["records"][object_id]
        require(record["exists"], f"{key}: {object_id} is missing", diagnostics)
        require(
            record["skinCount"] == 1,
            f"{key}: {object_id} does not have exactly one semantic skin",
            diagnostics,
        )
        require(
            record["legacyCount"] == 0,
            f"{key}: {object_id} still contains legacy decoration",
            diagnostics,
        )
        require(
            record["skinPointerEvents"] == "none",
            f"{key}: {object_id} skin intercepts pointer input",
            diagnostics,
        )
        require(
            record["labelOutsideSkin"],
            f"{key}: {object_id} label is inside scaled visual geometry",
            diagnostics,
        )
        require(
            record["signature"],
            f"{key}: {object_id} has no visual signature",
            diagnostics,
        )

    numeric_control = front["records"]["projection-front-numeric"]
    numeric_indicator = front["records"]["visual-front-numeric-indicator"]
    require(
        numeric_control["signature"] != numeric_indicator["signature"],
        f"{key}: numeric control and indicator share one visual signature",
        diagnostics,
    )
    require(
        "vi-skin-spinner" in numeric_control["shapeClasses"]
        and "vi-skin-indicator-dot" not in numeric_control["shapeClasses"],
        f"{key}: numeric control has the wrong visual affordance",
        diagnostics,
    )
    require(
        "vi-skin-indicator-dot" in numeric_indicator["shapeClasses"]
        and "vi-skin-spinner" not in numeric_indicator["shapeClasses"],
        f"{key}: numeric indicator has the wrong visual affordance",
        diagnostics,
    )
    boolean_control = front["records"]["projection-front-boolean"]
    boolean_indicator = front["records"]["visual-front-boolean-indicator"]
    require(
        "vi-skin-boolean-track" in boolean_control["shapeClasses"],
        f"{key}: Boolean control is not rendered as a switch",
        diagnostics,
    )
    require(
        "vi-skin-boolean-led" in boolean_indicator["shapeClasses"],
        f"{key}: Boolean indicator is not rendered as an LED",
        diagnostics,
    )
    require(
        "vi-skin-path-folder" in front["records"]["visual-front-path-control"]["shapeClasses"],
        f"{key}: path control has no path-specific body",
        diagnostics,
    )
    require(
        "vi-skin-table-grid" in front["records"]["visual-front-table"]["shapeClasses"],
        f"{key}: table has no table grid",
        diagnostics,
    )
    require(
        "vi-skin-array-viewport" in front["records"]["visual-front-array"]["shapeClasses"],
        f"{key}: array has no array viewport",
        diagnostics,
    )
    require(
        "vi-skin-cluster-interior" in front["records"]["projection-front-cluster"]["shapeClasses"],
        f"{key}: cluster has no semantic interior",
        diagnostics,
    )
    require(
        front["order"].index("visual-front-array")
        < front["order"].index("visual-array-child")
        and front["order"].index("projection-front-cluster")
        < front["order"].index("visual-cluster-child"),
        f"{key}: container layers obscure their children",
        diagnostics,
    )
    require(
        not front["localKeys"] and not front["dirtyKeys"],
        f"{key}: front visual decoration changed edit state",
        diagnostics,
    )

    page.screenshot(
        path=str(ARTIFACTS / f"component-visuals-front-{key}.png"),
        full_page=False,
    )

    page.locator('[data-vi-surface="block-diagram"]').click()
    page.wait_for_function(
        "() => window.VISemanticEditor.S.surface === 'block-diagram'"
    )
    page.wait_for_timeout(320)
    block_ids = [
        "projection-source",
        "projection-target",
        "projection-constant",
        "projection-structure",
        "visual-block-compare",
        "visual-block-logic",
        "visual-block-select",
        "visual-block-string-constant",
        "visual-block-generic",
        "projection-source-terminal",
        "projection-target-terminal",
    ]
    block = component_snapshot(page, block_ids)
    diagnostics["viewports"][key]["block"] = block
    expected = {
        "projection-source": ("subvi", "vi-skin-subvi-wave"),
        "projection-target": ("arithmetic", "vi-skin-primitive-body"),
        "projection-constant": ("constant", "vi-skin-constant-fold"),
        "projection-structure": ("structure", "vi-skin-structure-selector"),
        "visual-block-compare": ("compare", "vi-skin-primitive-body"),
        "visual-block-logic": ("logic", "vi-skin-primitive-body"),
        "visual-block-select": ("select", "vi-skin-primitive-body"),
        "visual-block-string-constant": ("constant", "vi-skin-constant-fold"),
        "visual-block-generic": ("node", "vi-skin-node-header"),
        "projection-source-terminal": ("terminal", "vi-skin-terminal-direction"),
        "projection-target-terminal": ("terminal", "vi-skin-terminal-direction"),
    }
    for object_id, (visual, shape) in expected.items():
        record = block["records"][object_id]
        require(
            record["visual"] == visual,
            f"{key}: {object_id} was classified as {record['visual']} instead of {visual}",
            diagnostics,
        )
        require(
            shape in record["shapeClasses"],
            f"{key}: {object_id} lacks its type-specific shape {shape}",
            diagnostics,
        )
        require(
            record["skinCount"] == 1 and record["legacyCount"] == 0,
            f"{key}: {object_id} has mixed visual systems",
            diagnostics,
        )
    terminal_indices = [
        block["order"].index("projection-source-terminal"),
        block["order"].index("projection-target-terminal"),
    ]
    node_indices = [
        block["order"].index(object_id)
        for object_id in block_ids
        if "terminal" not in object_id
    ]
    require(
        min(terminal_indices) > max(node_indices),
        f"{key}: terminals are not the top object layer",
        diagnostics,
    )
    require(
        terminal_hit(page, "projection-source-terminal")
        == "projection-source-terminal",
        f"{key}: source terminal is not directly selectable above the wire",
        diagnostics,
    )
    require(
        terminal_hit(page, "projection-target-terminal")
        == "projection-target-terminal",
        f"{key}: target terminal is not directly selectable above the wire",
        diagnostics,
    )
    require(
        not block["localKeys"] and not block["dirtyKeys"],
        f"{key}: block visual decoration changed edit state",
        diagnostics,
    )

    page.locator("#model-graph-overview").click()
    page.wait_for_timeout(220)
    overview = detail_state(page, "projection-target")
    diagnostics["viewports"][key]["overview"] = overview
    require(
        overview["lod"] in {"overview", "compact"},
        f"{key}: overview did not enter a reduced LOD",
        diagnostics,
    )
    if overview["lod"] == "overview":
        require(
            overview["detail"] in {None, "none"},
            f"{key}: overview still shows secondary component detail",
            diagnostics,
        )
    require(
        overview["frame"] != "none",
        f"{key}: overview removed the component silhouette",
        diagnostics,
    )

    page.locator("#model-graph-fit").click()
    page.wait_for_timeout(180)
    page.screenshot(
        path=str(ARTIFACTS / f"component-visuals-block-{key}.png"),
        full_page=False,
    )
    context.close()


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    value = model()
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".component-visual-jobs"),
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
                audit_viewport(browser, viewport, value, diagnostics)
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

    (ARTIFACTS / "semantic-component-visual-redesign.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "SEMANTIC_COMPONENT_VISUALS_JSON="
        + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
    )
    failed = bool(
        diagnostics["failures"]
        or diagnostics["console_errors"]
        or diagnostics["page_errors"]
    )
    print(
        "SEMANTIC_COMPONENT_VISUALS_TEST_FAILED"
        if failed
        else "SEMANTIC_COMPONENT_VISUALS_TEST_OK"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
