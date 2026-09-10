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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PORT = int(os.getenv("VI_STRUCTURE_NET_PORT", "8088"))
BASE_URL = f"http://127.0.0.1:{PORT}"
ARTIFACTS = Path(
    os.getenv(
        "BUILD_ARTIFACT_DIR",
        str(ROOT / "artifacts" / "semantic-structure-net"),
    )
)


def _node(
    object_id: str,
    name: str,
    x: float,
    y: float,
    *,
    kind: str = "subvi",
    parent: str | None = None,
    terminal_ids: list[str] | None = None,
    surface: str = "block-diagram",
    visual_kind: str = "subvi",
) -> dict[str, Any]:
    return {
        "id": object_id,
        "component_id": object_id,
        "surface": surface,
        "native_surface": "block-diagram" if surface == "block-diagram-inactive" else surface,
        "kind": kind,
        "category": "node",
        "name": name,
        "symbol": "VI" if kind == "subvi" else "▣",
        "class_name": kind,
        "uid": object_id,
        "bounds": {"x": x, "y": y, "width": 84, "height": 48},
        "positioned": True,
        "movable": True,
        "resizable": True,
        "terminal_ids": terminal_ids or [],
        "linked_terminal_ids": [],
        "wire_ids": [],
        "parent_object_id": parent,
        "child_object_ids": [],
        "data_type": "numeric",
        "visual_kind": visual_kind,
        "hidden_by_structure_frame": surface == "block-diagram-inactive",
        "source": {"file": "fixture_BDHb.xml", "xml_path": f"/{object_id}"},
    }


def _terminal(
    object_id: str,
    name: str,
    x: float,
    y: float,
    direction: str,
    owner: str,
    *,
    surface: str = "block-diagram",
) -> dict[str, Any]:
    return {
        "id": object_id,
        "component_id": object_id,
        "surface": surface,
        "native_surface": "block-diagram" if surface == "block-diagram-inactive" else surface,
        "kind": "terminal",
        "category": "terminal",
        "name": name,
        "symbol": "",
        "class_name": "term",
        "uid": object_id,
        "bounds": {"x": x, "y": y, "width": 10, "height": 10},
        "positioned": True,
        "movable": False,
        "resizable": False,
        "direction": direction,
        "owner_object_id": owner,
        "linked_object_id": None,
        "terminal_ids": [],
        "linked_terminal_ids": [],
        "wire_ids": [],
        "parent_object_id": None,
        "child_object_ids": [],
        "data_type": "numeric",
        "visual_kind": "terminal",
        "hidden_by_structure_frame": surface == "block-diagram-inactive",
        "source": {"file": "fixture_BDHb.xml", "xml_path": f"/{object_id}"},
    }


def _wire(
    wire_id: str,
    net_id: str,
    source_terminal_id: str,
    source_object_id: str,
    target_terminal_id: str,
    target_object_id: str,
    points: list[tuple[float, float]],
    *,
    hidden: bool = False,
) -> dict[str, Any]:
    return {
        "id": wire_id,
        "name": f"{source_object_id} → {target_object_id}",
        "surface": "block-diagram",
        "source_terminal_id": source_terminal_id,
        "target_terminal_ids": [target_terminal_id],
        "terminal_ids": [source_terminal_id, target_terminal_id],
        "source_object_id": source_object_id,
        "target_object_ids": [target_object_id],
        "endpoint_object_ids": [source_object_id, target_object_id],
        "route_points": [{"x": x, "y": y} for x, y in points],
        "resolved": True,
        "direction_confidence": "signal-term-list",
        "native_uid": wire_id,
        "native_signal_uid": net_id,
        "net_id": net_id,
        "branch_count": 1,
        "data_type": "numeric",
        "semantic_source": "fixture",
        "hidden_by_structure_frame": hidden,
    }


def make_payload() -> dict[str, Any]:
    structure = _node(
        "case",
        "Case Structure",
        160,
        100,
        kind="structure-case",
        visual_kind="structure",
    )
    structure["bounds"] = {"x": 160, "y": 100, "width": 500, "height": 300}
    structure["structure_frames"] = [
        {
            "index": 0,
            "label": "False",
            "is_active": True,
            "object_ids": ["node-false"],
            "node_uids": ["node-false"],
        },
        {
            "index": 1,
            "label": "True",
            "is_active": False,
            "object_ids": ["node-true-a", "node-true-b"],
            "node_uids": ["node-true-a", "node-true-b"],
        },
    ]
    structure["active_frame_index"] = 0
    structure["active_frame_label"] = "False"

    source = _node(
        "source",
        "Input",
        40,
        210,
        kind="constant",
        terminal_ids=["source-term"],
        visual_kind="constant",
    )
    false_node = _node(
        "node-false",
        "False Handler",
        420,
        170,
        parent="case",
        terminal_ids=["false-term"],
    )
    true_a = _node(
        "node-true-a",
        "True Handler A",
        360,
        145,
        parent="case",
        terminal_ids=["true-a-term"],
        surface="block-diagram-inactive",
    )
    true_b = _node(
        "node-true-b",
        "True Handler B",
        470,
        285,
        parent="case",
        terminal_ids=["true-b-term"],
        surface="block-diagram-inactive",
    )

    source_term = _terminal("source-term", "value", 116, 229, "source", "source")
    false_term = _terminal("false-term", "value", 415, 189, "sink", "node-false")
    true_a_term = _terminal(
        "true-a-term",
        "value",
        355,
        164,
        "sink",
        "node-true-a",
        surface="block-diagram-inactive",
    )
    true_b_term = _terminal(
        "true-b-term",
        "value",
        465,
        304,
        "sink",
        "node-true-b",
        surface="block-diagram-inactive",
    )

    false_wire = _wire(
        "wire-false",
        "net-false",
        "source-term",
        "source",
        "false-term",
        "node-false",
        [(121, 234), (250, 234), (250, 194), (420, 194)],
    )
    true_wire_a = _wire(
        "wire-true-a",
        "net-true",
        "source-term",
        "source",
        "true-a-term",
        "node-true-a",
        [(121, 234), (235, 234), (235, 169), (360, 169)],
        hidden=True,
    )
    true_wire_b = _wire(
        "wire-true-b",
        "net-true",
        "source-term",
        "source",
        "true-b-term",
        "node-true-b",
        [(121, 234), (275, 234), (275, 309), (470, 309)],
        hidden=True,
    )

    front_control = {
        "id": "front-input",
        "component_id": "front-input",
        "surface": "front-panel",
        "kind": "numeric-control",
        "category": "control",
        "name": "Input",
        "symbol": "IN",
        "class_name": "fPDCO",
        "uid": "front-input",
        "bounds": {"x": 40, "y": 40, "width": 110, "height": 46},
        "positioned": True,
        "movable": True,
        "resizable": True,
        "terminal_ids": [],
        "linked_terminal_ids": [],
        "wire_ids": [],
        "parent_object_id": None,
        "child_object_ids": [],
        "data_type": "numeric",
        "visual_kind": "numeric",
        "source": {"file": "fixture_FPHb.xml", "xml_path": "/front-input"},
    }
    objects = [
        front_control,
        structure,
        source,
        false_node,
        true_a,
        true_b,
        source_term,
        false_term,
        true_a_term,
        true_b_term,
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
            "wires": [false_wire],
            "inactive_structure_frame_wires": [true_wire_a, true_wire_b],
            "nets": [
                {
                    "id": "net-false",
                    "source_terminal_id": "source-term",
                    "source_object_id": "source",
                    "target_terminal_ids": ["false-term"],
                    "target_object_ids": ["node-false"],
                    "branch_ids": ["wire-false"],
                    "branch_count": 1,
                    "data_type": "numeric",
                }
            ],
            "surfaces": {
                "front-panel": ["front-input"],
                "block-diagram": [
                    "case",
                    "source",
                    "node-false",
                    "source-term",
                    "false-term",
                ],
            },
            "summary": {
                "controls": 1,
                "indicators": 0,
                "front_panel_objects": 1,
                "block_diagram_nodes": 3,
                "terminals": 2,
                "wires": 1,
                "resolved_wires": 1,
                "wire_nets": 1,
            },
            "warnings": [],
            "type_definitions": [],
            "hierarchy": {
                "roots": ["front-input", "case", "source", "source-term"],
                "containers": ["case"],
                "children_by_parent": {"case": ["node-false"]},
            },
            "parser": {"name": "lvkit", "mode": "authoritative"},
            "integrity": {"version": 3, "wire_nets": 1},
            "debug": {"generic_graph_used_for_block_diagram": False},
        },
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


def boxes_close(
    first: dict[str, float],
    second: dict[str, float],
    tolerance: float = 1.0,
) -> bool:
    return all(
        abs(float(first[key]) - float(second[key])) <= tolerance
        for key in ("x", "y", "width", "height")
    )


def install_route(page: Page, model: dict[str, Any]) -> None:
    def model_route(route: Route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(model, ensure_ascii=False),
        )

    page.route("**/api/jobs/structure-net/model*", model_route)


def open_editor(page: Page) -> None:
    job = {
        "job_id": "structure-net",
        "status": "ready",
        "component_modified_at": "2026-09-10T11:58:00Z",
        "xml_modified_at": "2026-09-10T11:58:00Z",
        "files": [],
    }
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_function("() => Boolean(window.viPages && window.viModelGraph)")
    page.evaluate("job => window.viPages.setJob(job, {openModel: true})", job)
    page.evaluate("async job => { await window.viModelGraph.setJob(job); }", job)
    page.wait_for_function(
        "() => Boolean(window.VIStructureNetWorkflow?.ready && window.VICanvasDensity?.ready)"
    )
    page.wait_for_timeout(250)
    page.locator('[data-vi-surface="block-diagram"]').click()
    page.wait_for_timeout(150)


def snapshot(page: Page) -> dict[str, Any]:
    return page.evaluate(
        """() => ({
          frame: document.querySelector('#vi-structure-frame-select')?.value,
          visibleFalse: Boolean(document.querySelector('[data-object-id="node-false"]')),
          visibleTrueA: Boolean(document.querySelector('[data-object-id="node-true-a"]')),
          visibleTrueB: Boolean(document.querySelector('[data-object-id="node-true-b"]')),
          wires: [...window.VISemanticEditor.S.wires.keys()].sort(),
          netIds: window.VISemanticEditor.S.vi.nets.map(net => net.id).sort(),
          branchCounts: window.VISemanticEditor.S.vi.nets.map(net => net.branch_ids.length),
          selected: window.VISemanticEditor.S.selected,
          box: {...window.VISemanticEditor.S.box},
          dirtyFalse: window.VISemanticEditor.S.dirty.has('node-false'),
          localFalse: window.VISemanticEditor.S.local.get('node-false') || null,
        })"""
    )


def audit(page: Page, diagnostics: dict[str, Any]) -> None:
    page.evaluate("() => window.VISemanticEditor.select('case', true)")
    page.wait_for_selector("#vi-structure-frame-section:not([hidden])")

    initial = snapshot(page)
    diagnostics["initial"] = initial
    require(initial["frame"] == "0", "initial frame is not False", diagnostics)
    require(initial["visibleFalse"], "False frame node is missing", diagnostics)
    require(not initial["visibleTrueA"], "inactive True frame is visible", diagnostics)
    require(initial["wires"] == ["wire-false"], "initial wire set is stale", diagnostics)
    require(initial["netIds"] == ["net-false"], "initial net set is stale", diagnostics)

    page.evaluate(
        """() => {
          const S = window.VISemanticEditor.S;
          S.local.set('node-false', {x: 438, y: 182, width: 84, height: 48});
          S.dirty.add('node-false');
        }"""
    )
    page.locator("#vi-structure-frame-select").select_option("1")
    page.wait_for_function(
        """() => Boolean(
          document.querySelector('[data-object-id="node-true-a"]')
          && document.querySelector('[data-object-id="node-true-b"]')
          && window.VISemanticEditor.S.wires.size === 2
        )"""
    )
    true_frame = snapshot(page)
    diagnostics["true_frame"] = true_frame
    require(true_frame["frame"] == "1", "True frame was not selected", diagnostics)
    require(not true_frame["visibleFalse"], "False node remains visible", diagnostics)
    require(true_frame["visibleTrueA"] and true_frame["visibleTrueB"], "True nodes are incomplete", diagnostics)
    require(true_frame["wires"] == ["wire-true-a", "wire-true-b"], "True wire set is incomplete", diagnostics)
    require(true_frame["netIds"] == ["net-true"], "True branches are not one net", diagnostics)
    require(true_frame["branchCounts"] == [2], "True net branch count is wrong", diagnostics)
    require(true_frame["dirtyFalse"] and true_frame["localFalse"] is not None, "inactive-frame edit was discarded", diagnostics)
    require(boxes_close(initial["box"], true_frame["box"]), "frame switch reset pan/zoom", diagnostics)
    require(true_frame["selected"] == "case", "Structure selection was lost", diagnostics)

    page.evaluate("() => window.VISemanticEditor.select('wire-true-a', true)")
    page.wait_for_selector("#vi-net-inspector-section:not([hidden])")
    page.wait_for_function(
        """() => document.querySelectorAll(
          '#model-graph-svg .vi-wire-group.is-net-selected'
        ).length === 2"""
    )
    net = page.evaluate(
        """() => ({
          id: window.VIStructureNetWorkflow.selectedNet()?.id,
          branchCount: document.querySelector('#vi-net-branch-count')?.textContent,
          targetCount: document.querySelector('#vi-net-target-count')?.textContent,
          branchButtons: document.querySelectorAll('#vi-net-branch-list .vi-net-branch').length,
          endpointButtons: document.querySelectorAll('#vi-net-endpoints .vi-net-endpoint').length,
          selectedBranches: document.querySelectorAll('#model-graph-svg .vi-wire-group.is-net-selected').length,
          sourceMarks: document.querySelectorAll('#model-graph-svg .is-net-source').length,
          sinkMarks: document.querySelectorAll('#model-graph-svg .is-net-sink').length,
        })"""
    )
    diagnostics["net"] = net
    require(net["id"] == "net-true", "wrong net selected", diagnostics)
    require(net["branchCount"] == "2", "net branch count is wrong", diagnostics)
    require(net["targetCount"] == "2", "net sink count is wrong", diagnostics)
    require(net["branchButtons"] == 2, "branch list is incomplete", diagnostics)
    require(net["endpointButtons"] == 3, "endpoint list is incomplete", diagnostics)
    require(net["selectedBranches"] == 2, "complete net is not highlighted", diagnostics)
    require(net["sourceMarks"] >= 1 and net["sinkMarks"] >= 2, "net endpoints are not marked", diagnostics)

    page.locator("#vi-net-next-endpoint").click()
    page.wait_for_function("() => window.VISemanticEditor.S.selected !== 'wire-true-a'")
    diagnostics["cycled_endpoint"] = page.evaluate(
        "() => window.VISemanticEditor.S.selected"
    )
    require(
        diagnostics["cycled_endpoint"] in {"source", "node-true-a", "node-true-b"},
        "endpoint navigation selected an unrelated object",
        diagnostics,
    )

    page.locator("#vi-net-focus").click()
    page.wait_for_timeout(100)
    diagnostics["focus_mode"] = page.evaluate(
        "() => window.VICanvasDensity.runtime.currentMode"
    )
    require(diagnostics["focus_mode"] == "focus", "net focus did not use focus mode", diagnostics)

    page.evaluate("() => window.VISemanticEditor.select('case', true)")
    page.locator("#vi-structure-frame-select").select_option("0")
    page.wait_for_function(
        """() => Boolean(
          document.querySelector('[data-object-id="node-false"]')
          && window.VISemanticEditor.S.wires.size === 1
        )"""
    )
    restored = snapshot(page)
    diagnostics["restored"] = restored
    require(restored["frame"] == "0", "False frame did not restore", diagnostics)
    require(restored["wires"] == ["wire-false"], "restored wire set is wrong", diagnostics)
    require(restored["dirtyFalse"], "dirty state was lost", diagnostics)
    require(
        restored["localFalse"] == {"x": 438, "y": 182, "width": 84, "height": 48},
        "local bounds were lost",
        diagnostics,
    )

    page.locator('[data-vi-surface="front-panel"]').click()
    page.wait_for_timeout(100)
    front = page.evaluate(
        """() => ({
          surface: window.VISemanticEditor.S.surface,
          visible: Boolean(document.querySelector('[data-object-id="front-input"]')),
          dirty: window.VISemanticEditor.S.dirty.has('node-false'),
        })"""
    )
    diagnostics["front_panel"] = front
    require(front["surface"] == "front-panel" and front["visible"], "front panel was damaged", diagnostics)
    require(front["dirty"], "surface switch discarded frame edit", diagnostics)


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    model = make_payload()
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".sandbox-structure-net-jobs"),
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
    }
    try:
        wait_for_server(process)
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
            install_route(page, model)
            open_editor(page)
            audit(page, diagnostics)
            page.screenshot(
                path=str(ARTIFACTS / "structure-frame-and-net.png"),
                full_page=False,
            )
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
                print("STRUCTURE_NET_APP_LOG=" + output[-4000:].replace("\n", "\\n"))

    (ARTIFACTS / "semantic-structure-net.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "SEMANTIC_STRUCTURE_NET_JSON="
        + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
    )
    if diagnostics["failures"] or diagnostics["console_errors"] or diagnostics["page_errors"]:
        print("SEMANTIC_STRUCTURE_NET_TEST_FAILED")
        return 1
    print("SEMANTIC_STRUCTURE_NET_TEST_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
