from __future__ import annotations

import os
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PORT = int(os.getenv("VI_STRUCTURE_NET_PORT", "8088"))
BASE_URL = f"http://127.0.0.1:{PORT}"


def _node(
    object_id: str,
    name: str,
    x: float,
    y: float,
    *,
    kind: str = "subvi",
    parent_id: str | None = None,
    terminal_ids: list[str] | None = None,
    surface: str = "block-diagram",
    visual_kind: str = "subvi",
) -> dict[str, Any]:
    inactive = surface == "block-diagram-inactive"
    return {
        "id": object_id,
        "component_id": object_id,
        "surface": surface,
        "native_surface": "block-diagram" if inactive else surface,
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
        "parent_object_id": parent_id,
        "child_object_ids": [],
        "data_type": "numeric",
        "visual_kind": visual_kind,
        "hidden_by_structure_frame": inactive,
        "source": {
            "file": "fixture_BDHb.xml",
            "xml_path": f"/{object_id}",
        },
    }


def _terminal(
    object_id: str,
    x: float,
    y: float,
    direction: str,
    owner_id: str,
    *,
    surface: str = "block-diagram",
) -> dict[str, Any]:
    inactive = surface == "block-diagram-inactive"
    return {
        "id": object_id,
        "component_id": object_id,
        "surface": surface,
        "native_surface": "block-diagram" if inactive else surface,
        "kind": "terminal",
        "category": "terminal",
        "name": "value",
        "symbol": "",
        "class_name": "term",
        "uid": object_id,
        "bounds": {"x": x, "y": y, "width": 10, "height": 10},
        "positioned": True,
        "movable": False,
        "resizable": False,
        "direction": direction,
        "owner_object_id": owner_id,
        "linked_object_id": None,
        "terminal_ids": [],
        "linked_terminal_ids": [],
        "wire_ids": [],
        "parent_object_id": None,
        "child_object_ids": [],
        "data_type": "numeric",
        "visual_kind": "terminal",
        "hidden_by_structure_frame": inactive,
        "source": {
            "file": "fixture_BDHb.xml",
            "xml_path": f"/{object_id}",
        },
    }


def _wire(
    wire_id: str,
    net_id: str,
    target_terminal_id: str,
    target_object_id: str,
    points: list[tuple[float, float]],
    *,
    hidden: bool,
) -> dict[str, Any]:
    return {
        "id": wire_id,
        "name": f"Input → {target_object_id}",
        "surface": "block-diagram",
        "source_terminal_id": "source-term",
        "target_terminal_ids": [target_terminal_id],
        "terminal_ids": ["source-term", target_terminal_id],
        "source_object_id": "source",
        "target_object_ids": [target_object_id],
        "endpoint_object_ids": ["source", target_object_id],
        "route_points": [{"x": x, "y": y} for x, y in points],
        "resolved": True,
        "direction_confidence": "signal-term-list",
        "native_uid": wire_id,
        "native_signal_uid": net_id,
        "net_id": net_id,
        "branch_count": 1,
        "data_type": "numeric",
        "semantic_source": "structure-workflow-fixture",
        "hidden_by_structure_frame": hidden,
    }


def make_model() -> dict[str, Any]:
    structure = _node(
        "case",
        "Case Structure",
        160,
        100,
        kind="structure-case",
        visual_kind="structure",
    )
    structure["bounds"] = {
        "x": 160,
        "y": 100,
        "width": 500,
        "height": 300,
    }
    structure["active_frame_index"] = 0
    structure["active_frame_label"] = "False"
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
        parent_id="case",
        terminal_ids=["false-term"],
    )
    true_a = _node(
        "node-true-a",
        "True Handler A",
        360,
        145,
        parent_id="case",
        terminal_ids=["true-a-term"],
        surface="block-diagram-inactive",
    )
    true_b = _node(
        "node-true-b",
        "True Handler B",
        470,
        285,
        parent_id="case",
        terminal_ids=["true-b-term"],
        surface="block-diagram-inactive",
    )

    front_input = {
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
        "source": {
            "file": "fixture_FPHb.xml",
            "xml_path": "/front-input",
        },
    }

    objects = [
        front_input,
        structure,
        source,
        false_node,
        true_a,
        true_b,
        _terminal("source-term", 116, 229, "source", "source"),
        _terminal("false-term", 415, 189, "sink", "node-false"),
        _terminal(
            "true-a-term",
            355,
            164,
            "sink",
            "node-true-a",
            surface="block-diagram-inactive",
        ),
        _terminal(
            "true-b-term",
            465,
            304,
            "sink",
            "node-true-b",
            surface="block-diagram-inactive",
        ),
    ]

    false_wire = _wire(
        "wire-false",
        "net-false",
        "false-term",
        "node-false",
        [(121, 234), (250, 234), (250, 194), (420, 194)],
        hidden=False,
    )
    true_wire_a = _wire(
        "wire-true-a",
        "net-true",
        "true-a-term",
        "node-true-a",
        [(121, 234), (235, 234), (235, 169), (360, 169)],
        hidden=True,
    )
    true_wire_b = _wire(
        "wire-true-b",
        "net-true",
        "true-b-term",
        "node-true-b",
        [(121, 234), (275, 234), (275, 309), (470, 309)],
        hidden=True,
    )
    all_wires = [false_wire, true_wire_a, true_wire_b]

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
            "all_structure_frame_wires": all_wires,
            "nets": [
                {
                    "id": "net-false",
                    "source_terminal_id": "source-term",
                    "source_object_id": "source",
                    "target_terminal_ids": ["false-term"],
                    "target_object_ids": ["node-false"],
                    "branch_ids": ["wire-false"],
                    "branch_count": 1,
                    "wire_record_count": 1,
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
            "parser": {
                "name": "lvkit",
                "mode": "authoritative",
            },
            "integrity": {
                "version": 3,
                "wire_nets": 1,
                "structure_frames": {
                    "active_frame_only": True,
                    "inactive_object_count": 4,
                    "inactive_wire_count": 2,
                },
            },
            "debug": {
                "generic_graph_used_for_block_diagram": False,
            },
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
