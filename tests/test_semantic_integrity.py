from __future__ import annotations

from types import SimpleNamespace

from app.semantic_integrity import finalize_semantic_vi, type_family


def _bounds(x: float, y: float, width: float = 10, height: float = 10):
    return {"x": x, "y": y, "width": width, "height": height}


def test_scalar_typedef_reference_is_not_fabricated_as_cluster() -> None:
    assert type_family(
        {
            "kind": "typedef_ref",
            "name": "NumInt32",
            "typedef_name": "Counter.ctl",
        },
        "cluster",
    ) == "numeric"
    assert type_family(
        {
            "kind": "typedef_ref",
            "name": "Path",
            "typedef_name": "Output Path.ctl",
        },
        "cluster",
    ) == "path"
    assert type_family(
        {
            "kind": "typedef_ref",
            "name": "OpaqueNamedType",
            "typedef_name": "Opaque.ctl",
        },
        "cluster",
    ) == "unknown"
    assert type_family(
        {
            "kind": "typedef_ref",
            "name": "Cluster",
            "typedef_name": "Settings.ctl",
            "fields": [{"name": "Gain", "type": {"kind": "primitive", "name": "NumFloat64"}}],
        }
    ) == "cluster"


def test_structure_srn_terminal_is_owned_anchored_and_wired() -> None:
    vi = {
        "version": 3,
        "objects": [
            {
                "id": "structure",
                "uid": "400",
                "surface": "block-diagram",
                "category": "node",
                "kind": "structure-case",
                "class_name": "caseStruct",
                "bounds": _bounds(100, 80, 220, 160),
                "terminal_ids": [],
                "linked_terminal_ids": [],
                "wire_ids": [],
                "child_object_ids": [],
                "data_type": "unknown",
            },
            {
                "id": "source-terminal",
                "uid": "410",
                "surface": "block-diagram",
                "category": "terminal",
                "kind": "terminal",
                "direction": "source",
                "bounds": _bounds(310, 130, 8, 8),
                "owner_object_id": None,
                "linked_object_id": None,
                "semantic": {"parent_uid": "sRN-1"},
                "terminal_ids": [],
                "linked_terminal_ids": [],
                "wire_ids": [],
                "child_object_ids": [],
                "data_type": "unknown",
            },
            {
                "id": "target-node",
                "uid": "500",
                "surface": "block-diagram",
                "category": "node",
                "kind": "node-propnode",
                "class_name": "propNode",
                "name": "propNode",
                "bounds": _bounds(380, 105, 70, 45),
                "terminal_ids": [],
                "linked_terminal_ids": [],
                "wire_ids": [],
                "child_object_ids": [],
                "data_type": "unknown",
            },
            {
                "id": "target-terminal",
                "uid": "510",
                "surface": "block-diagram",
                "category": "terminal",
                "kind": "terminal",
                "direction": "sink",
                "bounds": _bounds(380, 120, 8, 8),
                "owner_object_id": "target-node",
                "linked_object_id": None,
                "terminal_ids": [],
                "linked_terminal_ids": [],
                "wire_ids": [],
                "child_object_ids": [],
                "data_type": "numeric",
                "type": {"kind": "typedef_ref", "name": "NumInt32", "typedef_name": "Counter.ctl"},
            },
        ],
        "wires": [
            {
                "id": "branch-a",
                "native_uid": "900",
                "source_terminal_id": "source-terminal",
                "target_terminal_ids": ["target-terminal"],
                "terminal_ids": ["source-terminal", "target-terminal"],
                "route_points": [],
                "resolved": True,
            }
        ],
        "type_definitions": [],
        "summary": {"wires": 99, "unresolved_wires": 0},
        "warnings": [],
    }
    parsed = SimpleNamespace(
        block_diagram=SimpleNamespace(
            srn_to_structure={"sRN-1": "400"},
            constants=[],
        ),
        metadata=SimpleNamespace(type_map={}),
    )

    result = finalize_semantic_vi(vi, parsed=parsed)
    objects = {item["id"]: item for item in result["objects"]}
    terminal = objects["source-terminal"]
    wire = result["wires"][0]

    assert terminal["owner_object_id"] == "structure"
    assert terminal["owner_resolution"] == "srn_to_structure"
    assert terminal["bounds"]["relative_to_object_id"] == "structure"
    assert terminal["bounds"]["raw_x"] == 210
    assert terminal["bounds"]["raw_y"] == 50
    assert "source-terminal" in objects["structure"]["terminal_ids"]
    assert objects["target-node"]["kind"] == "property-node"
    assert objects["target-node"]["name"] == "Property Node"
    assert wire["data_type"] == "numeric"
    assert wire["source_object_id"] == "structure"
    assert wire["target_object_ids"] == ["target-node"]
    assert result["integrity"]["structure_terminal_owners_resolved"] == 1
    assert result["integrity"]["owner_anchors_added"] == 2


def test_branch_wires_share_one_net_and_type_definition() -> None:
    type_payload = {
        "kind": "typedef_ref",
        "name": "Cluster",
        "typedef_name": "Settings.ctl",
        "typedef_path": "types/Settings.ctl",
        "fields": [{"name": "Gain", "type": {"kind": "primitive", "name": "NumFloat64"}}],
    }
    objects = [
        {
            "id": "source",
            "surface": "block-diagram",
            "category": "terminal",
            "kind": "terminal",
            "direction": "source",
            "bounds": _bounds(10, 10),
            "data_type": "cluster",
            "type": type_payload,
            "type_definition_id": "parsed-definition",
        },
        {
            "id": "sink-a",
            "surface": "block-diagram",
            "category": "terminal",
            "kind": "terminal",
            "direction": "sink",
            "bounds": _bounds(100, 10),
            "data_type": "cluster",
            "type": type_payload,
            "type_definition_id": "parsed-definition",
        },
        {
            "id": "sink-b",
            "surface": "block-diagram",
            "category": "terminal",
            "kind": "terminal",
            "direction": "sink",
            "bounds": _bounds(100, 60),
            "data_type": "cluster",
            "type": type_payload,
            "type_definition_id": "parsed-definition",
        },
    ]
    vi = {
        "objects": objects,
        "wires": [
            {
                "id": "wire-a",
                "native_uid": "700",
                "source_terminal_id": "source",
                "target_terminal_ids": ["sink-a"],
                "resolved": True,
            },
            {
                "id": "wire-b",
                "native_uid": "700_1",
                "source_terminal_id": "source",
                "target_terminal_ids": ["sink-b"],
                "resolved": True,
            },
        ],
        "type_definitions": [
            {
                "id": "parsed-definition",
                "name": "Settings.ctl",
                "kind": "typedef_ref",
                "recorded_path": "types/Settings.ctl",
                "target_file": None,
                "available": True,
                "definition": type_payload,
                "source_object_ids": ["source"],
                "source": "parsed-type",
            },
            {
                "id": "dependency-definition",
                "name": "Settings.ctl",
                "kind": "typedef_ref",
                "recorded_path": "/types/Settings.ctl",
                "target_file": "types/Settings.ctl",
                "available": True,
                "definition": None,
                "source_object_ids": [],
                "source": "link-table",
            },
        ],
        "summary": {},
        "warnings": [],
    }

    result = finalize_semantic_vi(vi)
    wires = result["wires"]

    assert len(result["nets"]) == 1
    assert result["nets"][0]["branch_count"] == 2
    assert wires[0]["net_id"] == wires[1]["net_id"]
    assert wires[0]["native_signal_uid"] == "700"
    assert wires[1]["native_signal_uid"] == "700"
    assert wires[1]["branch_index"] == 1
    assert len(result["type_definitions"]) == 1
    definition = result["type_definitions"][0]
    assert definition["target_file"] == "types/Settings.ctl"
    assert definition["definition"] == type_payload
    assert result["summary"]["wire_nets"] == 1
    assert result["summary"]["wires"] == 2


def test_dangling_fallback_links_are_removed_and_summary_is_recomputed() -> None:
    vi = {
        "version": 3,
        "objects": [
            {
                "id": "front-control",
                "surface": "front-panel",
                "category": "control",
                "kind": "numeric-control",
                "bounds": _bounds(20, 20, 100, 40),
                "linked_terminal_ids": ["removed-terminal"],
                "wire_ids": ["removed-wire"],
                "terminal_ids": [],
                "child_object_ids": [],
                "data_type": "numeric",
            }
        ],
        "wires": [
            {
                "id": "removed-wire",
                "source_terminal_id": "removed-terminal",
                "target_terminal_ids": ["also-removed"],
            }
        ],
        "summary": {
            "block_diagram_nodes": 42,
            "terminals": 99,
            "wires": 99,
            "resolved_wires": 99,
            "unresolved_wires": 0,
        },
        "surfaces": {"block-diagram": ["removed-terminal"]},
        "hierarchy": {"roots": ["removed-terminal"]},
        "type_definitions": [],
        "warnings": ["parser unavailable"],
    }

    result = finalize_semantic_vi(vi)
    control = result["objects"][0]

    assert result["wires"] == []
    assert control["linked_terminal_ids"] == []
    assert control["wire_ids"] == []
    assert result["summary"]["block_diagram_nodes"] == 0
    assert result["summary"]["terminals"] == 0
    assert result["summary"]["wires"] == 0
    assert result["summary"]["resolved_wires"] == 0
    assert result["summary"]["unresolved_wires"] == 1
    assert result["surfaces"]["block-diagram"] == []
    assert result["hierarchy"]["roots"] == ["front-control"]
    assert result["integrity"]["dangling_wires_removed"] == 1
