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


def node(
    object_id: str,
    name: str,
    x: float,
    y: float,
    *,
    kind: str = "subvi",
    parent: str | None = None,
    terminals: list[str] | None = None,
    visual_kind: str = "subvi",
) -> dict[str, Any]:
    return {
        "id": object_id,
        "component_id": object_id,
        "surface": "block-diagram",
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
        "terminal_ids": terminals or [],
        "linked_terminal_ids": [],
        "wire_ids": [],
        "parent_object_id": parent,
        "child_object_ids": [],
        "data_type": "numeric",
        "visual_kind": visual_kind,
        "source": {"file": "fixture_BDHb.xml", "xml_path": f"/{object_id}"},
    }


def terminal(
    object_id: str,
    name: str,
    x: float,
    y: float,
    direction: str,
    owner: str,
) -> dict[str, Any]:
    return {
        "id": object_id,
        "component_id": object_id,
        "surface": "block-diagram",
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
        "source": {"file": "fixture_BDHb.xml", "xml_path": f"/{object_id}"},
    }


def wire(
    wire_id: str,
    net_id: str,
    source_terminal: str,
    source_object: str,
    target_terminal: str,
    target_object: str,
    points: list[tuple[float, float]],
) -> dict[str, Any]:
    return {
        "id": wire_id,
        "name": f"{source_object} → {target_object}",
        "surface": "block-diagram",
        "source_terminal_id": source_terminal,
        "target_terminal_ids": [target_terminal],
        "terminal_ids": [source_terminal, target_terminal],
        "source_object_id": source_object,
        "target_object_ids": [target_object],
        "endpoint_object_ids": [source_object, target_object],
        "route_points": [{"x": x, "y": y} for x, y in points],
        "resolved": True,
        "direction_confidence": "signal-term-list",
        "native_uid": wire_id,
        "native_signal_uid": net_id,
        "net_id": net_id,
        "branch_count": 1,
        "data_type": "numeric",
        "semantic_source": "fixture",
    }


def payload() -> dict[str, Any]:
    case = node(
        "case",
        "Case Structure",
        160,
        100,
        kind="structure-case",
        terminals=[],
        visual_kind="structure",
    )
    case["bounds"] = {"x": 160, "y": 100, "width": 500, "height": 300}
    case["structure_frames"] = [
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
    case["active_frame_index"] = 0
    case["active_frame_label"] = "False"
    case["structure"] = {
        "displayed_frame": 0,
        "frames": [
            {"selector_value": "False", "inner_node_uids": ["node-false"]},
            {
                "selector_value": "True",
                "inner_node_uids": ["node-true-a", "node-true-b"],
            },
        ],
    }

    source = node("source", "Input", 40, 210, kind="constant", terminals=["source-term"], visual_kind="constant")
    false_node = node(
        "node-false",
        "False Handler",
        420,
        170,
        parent="case",
        terminals=["false-term"],
    )
    true_a = node(
        "node-true-a",
        "True Handler A",
        360,
        145,
        parent="case",
        terminals=["true-a-term"],
    )
    true_a["surface"] = "block-diagram-inactive"
    true_a["native_surface"] = "block-diagram"
    true_a["hidden_by_structure_frame"] = True
    true_b = node(
        "node-true-b",
        "True Handler B",
        470,
        285,
        parent="case",
        terminals=["true-b-term"],
    )
    true_b["surface"] = "block-diagram-inactive"
    true_b["native_surface"] = "block-diagram"
    true_b["hidden_by_structure_frame"] = True

    source_term = terminal("source-term", "value", 116, 229, "source", "source")
    false_term = terminal("false-term", "value", 415, 189, "sink", "node-false")
    true_a_term = terminal("true-a-term", "value", 355, 164, "sink", "node-true-a")
    true_b_term = terminal("true-b-term", "value", 465, 304, "sink", "node-true-b")
    for item in (true_a_term, true_b_term):
        item["surface"] = "block-diagram-inactive"
        item["native_surface"] = "block-diagram"
        item["hidden_by_structure_frame"] = True

    false_wire = wire(
        "wire-false",
        "net-false",
        "source-term",
        "source",
        "false-term",
        "node-false",
        [(121, 234), (250, 234), (250, 194), (420, 194)],
    )
    true_wire_a = wire(
        "wire-true-a",
        "net-true",
        "source-term",
        "source",
        "true-a-term",
        "node-true-a",
        [(121, 234), (235, 234), (235, 169), (360, 169)],
    )
    true_wire_b = wire(
        "wire-true-b",
        "net-true",
        "source-term",
        "source",
        "true-b-term",
        "node-true-b",
        [(121, 234), (275, 234), (275, 309), (470, 309)],
    )
    for item in (true_wire_a, true_wire_b):
        item["hidden_by_structure_frame"] = True
        item["branch_count"] = 2

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
        case,
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
                "hidden_structure_frame_objects": 4,
                "hidden_structure_frame_wires": 2,
            },
            "warnings": [],
            "type_definitions": [],
            "hierarchy": {
                "roots": ["front-input", "case", "source", "source-term"],
                "containers": ["case"],
                "children_by_parent": {"case": ["node-false"]},
            },
            "parser": {"name": "lvkit", "mode": "authoritative"},
            "integrity": {
                "version": 3,
                "wire_nets": 1,
                "structure_frames": {
                    "active_frame_only": True,
                    "inactive_object_count": 4,
                    "inactive_wire_count": 2,
                },
            },
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


def box_close(first: dict[str, float], second: dict[str, float], tolerance: float = 1.0) -> bool:
    return all(abs(float(first[key]) - float(second[key])) <= tolerance for key in first)


def audit(page: Page, model: dict[str, Any], diagnostics: dict[str, Any]) -> None:
    job = {
        "job_id": "structure-net",
        "status": "ready",
        "component_modified_at": "2026-09-10T11:58:00Z",
        "xml_modified_at": "2026-09-10T11:58:00Z",
        "files": [],
    }

    def model_route(route: Route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(model, ensure_ascii=False),
        )

    page.route("**/api/jobs/structure-net/model*", model_route)
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_function("() => Boolean(window.viPages && window.viModelGraph)")
    page.evaluate("job => window.viPages.setJob(job, {openModel: true})", job)
    page.evaluate("async job => { await window.viModelGraph.setJob(job); }", job)
    page.wait_for_function(
        "() => Boolean(window.VIStructureNetWorkflow?.ready && window.VICanvasDensity?.ready)"
    )
    page.wait_for_timeout(300)

    page.locator('[data-vi-surface="block-diagram"]').click()
    page.wait_for_timeout(180)
    page.evaluate("() => window.VISemanticEditor.select('case', true)")
    page.wait_for_selector("#vi-structure-frame-section:not([hidden])")

    initial = page.evaluate(
        """() => ({
          frame: document.querySelector('#vi-structure-frame-select').value,
          options: document.querySelector('#vi-structure-frame-select').options.length,
          visibleFalse: Boolean(document.querySelector('[data-object-id="node-false"]')),
          visibleTrueA: Boolean(document.querySelector('[data-object-id="node-true-a"]')),
          wireCount: window.VISemanticEditor.S.wires.size,
          netCount: window.VISemanticEditor.S.vi.nets.length,
          box: {...window.VISemanticEditor.S.box},
          title: document.querySelector('[data-object-id="case"] .vi-structure-title')?.textContent,
        })"""
    )
    diagnostics["initial"] = initial
    require(initial["frame"] == "0", "initial Structure frame is not False", diagnostics)
    require(initial["options"] == 2, "Structure frame selector does not list both frames", diagnostics)
    require(initial["visibleFalse"], "False frame node is missing", diagnostics)
    require(not initial["visibleTrueA"], "inactive True frame node is visible", diagnostics)
    require(initial["wireCount"] == 1, "initial frame has stale wires", diagnostics)
    require(initial["netCount"] == 1, "initial frame has stale nets", diagnostics)
    require("False" in (initial["title"] or ""), "Structure title does not show active frame", diagnostics)

    page.evaluate(
        """() => {
          const S = window.VISemanticEditor.S;
          S.local.set('node-false', {x: 438, y: 182, width: 84, height: 48});
          S.dirty.add('node-false');
        }"""
    )
    page.locator("#vi-structure-frame-select").select_option("1")
    page.wait_for_function(
        "() => Boolean(document.querySelector('[data-object-id="node-true-a"]')) && window.VISemanticEditor.S.wires.size === 2"
    )
    page.wait_for_timeout(180)

    true_frame = page.evaluate(
        """() => ({
          frame: document.querySelector('#vi-structure-frame-select').value,
          visibleFalse: Boolean(document.querySelector('[data-object-id="node-false"]')),
          visibleTrueA: Boolean(document.querySelector('[data-object-id="node-true-a"]')),
          visibleTrueB: Boolean(document.querySelector('[data-object-id="node-true-b"]')),
          wireCount: window.VISemanticEditor.S.wires.size,
          netCount: window.VISemanticEditor.S.vi.nets.length,
          branchCount: window.VISemanticEditor.S.vi.nets[0]?.branch_ids?.length,
          dirtyPreserved: window.VISemanticEditor.S.dirty.has('node-false'),
          localPreserved: window.VISemanticEditor.S.local.has('node-false'),
          box: {...window.VISemanticEditor.S.box},
          selected: window.VISemanticEditor.S.selected,
        })"""
    )
    diagnostics["true_frame"] = true_frame
    require(true_frame["frame"] == "1", "True frame was not selected", diagnostics)
    require(not true_frame["visibleFalse"], "False frame node remained visible", diagnostics)
    require(true_frame["visibleTrueA"] and true_frame["visibleTrueB"], "True frame nodes are incomplete", diagnostics)
    require(true_frame["wireCount"] == 2, "True frame does not expose both branches", diagnostics)
    require(true_frame["netCount"] == 1 and true_frame["branchCount"] == 2, "True branches were not grouped into one net", diagnostics)
    require(true_frame["dirtyPreserved"] and true_frame["localPreserved"], "inactive frame local edit was discarded", diagnostics)
    require(box_close(initial["box"], true_frame["box"]), "frame switch reset pan/zoom", diagnostics)
    require(true_frame["selected"] == "case", "Structure selection was not preserved", diagnostics)

    page.evaluate("() => window.VISemanticEditor.select('wire-true-a', true)")
    page.wait_for_selector("#vi-net-inspector-section:not([hidden])")
    page.wait_for_function(
        "() => document.querySelectorAll('#model-graph-svg .vi-wire-group.is-net-selected').length === 2"
    )
    net = page.evaluate(
        """() => ({
          title: document.querySelector('#vi-net-title').textContent,
          branchCount: document.querySelector('#vi-net-branch-count').textContent,
          targetCount: document.querySelector('#vi-net-target-count').textContent,
          branchButtons: document.querySelectorAll('#vi-net-branch-list .vi-net-branch').length,
          endpointButtons: document.querySelectorAll('#vi-net-endpoints .vi-net-endpoint').length,
          selectedBranches: document.querySelectorAll('#model-graph-svg .vi-wire-group.is-net-selected').length,
          sourceMarks: document.querySelectorAll('#model-graph-svg .is-net-source').length,
          sinkMarks: document.querySelectorAll('#model-graph-svg .is-net-sink').length,
          netId: window.VIStructureNetWorkflow.selectedNet()?.id,
        })"""
    )
    diagnostics["net"] = net
    require(net["netId"] == "net-true", "wrong net selected", diagnostics)
    require(net["branchCount"] == "2", "net branch count is wrong", diagnostics)
    require(net["targetCount"] == "2", "net sink count is wrong", diagnostics)
    require(net["branchButtons"] == 2, "net branch list is incomplete", diagnostics)
    require(net["endpointButtons"] == 3, "net endpoint list is incomplete", diagnostics)
    require(net["selectedBranches"] == 2, "complete net is not highlighted", diagnostics)
    require(net["sourceMarks"] >= 1 and net["sinkMarks"] >= 2, "net endpoints are not marked", diagnostics)

    page.locator("#vi-net-next-endpoint").click()
    page.wait_for_function("() => window.VISemanticEditor.S.selected !== 'wire-true-a'")
    cycled = page.evaluate("() => window.VISemanticEditor.S.selected")
    diagnostics["cycled_endpoint"] = cycled
    require(cycled in {"node-true-a", "node-true-b", "source"}, "endpoint navigation selected an unrelated object", diagnostics)

    page.locator("#vi-net-focus").click()
    page.wait_for_timeout(120)
    focus_mode = page.evaluate("() => window.VICanvasDensity.runtime.currentMode")
    diagnostics["focus_mode"] = focus_mode
    require(focus_mode == "focus", "net focus did not use focus view", diagnostics)

    page.evaluate("() => window.VISemanticEditor.select('case', true)")
    page.locator("#vi-structure-frame-select").select_option("0")
    page.wait_for_function(
        "() => Boolean(document.querySelector('[data-object-id="node-false"]')) && window.VISemanticEditor.S.wires.size === 1"
    )
    page.wait_for_timeout(140)
    restored = page.evaluate(
        """() => ({
          frame: document.querySelector('#vi-structure-frame-select').value,
          local: window.VISemanticEditor.S.local.get('node-false'),
          dirty: window.VISemanticEditor.S.dirty.has('node-false'),
          wireIds: [...window.VISemanticEditor.S.wires.keys()],
          inactiveWireIds: window.VISemanticEditor.S.vi.inactive_structure_frame_wires.map(wire => wire.id).sort(),
          visibleFalse: Boolean(document.querySelector('[data-object-id="node-false"]')),
          visibleTrueA: Boolean(document.querySelector('[data-object-id="node-true-a"]')),
        })"""
    )
    diagnostics["restored"] = restored
    require(restored["frame"] == "0", "False frame did not restore", diagnostics)
    require(restored["local"] == {"x": 438, "y": 182, "width": 84, "height": 48}, "False frame local bounds were lost", diagnostics)
    require(restored["dirty"], "False frame dirty state was lost", diagnostics)
    require(restored["wireIds"] == ["wire-false"], "restored frame wire set is wrong", diagnostics)
    require(restored["inactiveWireIds"] == ["wire-true-a", "wire-true-b"], "inactive wire catalog is wrong", diagnostics)
    require(restored["visibleFalse"] and not restored["visibleTrueA"], "restored frame visibility is wrong", diagnostics)

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
    require(front["surface"] == "front-panel" and front["visible"], "front panel was damaged by frame workflow", diagnostics)
    require(front["dirty"], "surface switch discarded inactive frame edit", diagnostics)


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    model = payload()
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
            audit(page, model, diagnostics)
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
