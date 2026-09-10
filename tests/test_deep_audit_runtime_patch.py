from __future__ import annotations

from app.deep_audit_runtime_patch import (
    canonicalize_type_definitions,
    select_displayed_structure_frames,
)


def test_reference_and_resolved_typedef_are_one_definition() -> None:
    vi = {
        "objects": [
            {"id": "control", "type_definition_id": "ref"},
            {"id": "terminal", "type_definition_id": "body"},
        ],
        "wires": [{"id": "wire", "type_definition_id": "body"}],
        "summary": {},
        "type_definitions": [
            {
                "id": "ref",
                "name": "Settings.ctl",
                "kind": "typedef_ref",
                "definition": {
                    "kind": "typedef_ref",
                    "name": "Settings.ctl",
                    "typedef_name": "Settings.ctl",
                },
                "source_object_ids": ["control"],
                "available": False,
            },
            {
                "id": "body",
                "name": "Settings.ctl",
                "kind": "cluster",
                "definition": {
                    "kind": "cluster",
                    "name": "Settings.ctl",
                    "typedef_name": "Settings.ctl",
                    "fields": [
                        {
                            "name": "Gain",
                            "type": {"kind": "primitive", "name": "NumFloat64"},
                        }
                    ],
                },
                "source_object_ids": ["terminal"],
                "available": True,
            },
        ],
    }

    result = canonicalize_type_definitions(vi)

    assert len(result["type_definitions"]) == 1
    definition = result["type_definitions"][0]
    assert definition["definition"]["fields"][0]["name"] == "Gain"
    assert definition["recorded_path"] == "unresolved://settings.ctl"
    assert definition["source_object_ids"] == ["control", "terminal"]
    assert result["objects"][0]["type_definition_id"] == definition["id"]
    assert result["objects"][1]["type_definition_id"] == definition["id"]
    assert result["wires"][0]["type_definition_id"] == definition["id"]
    assert result["integrity"]["type_definition_remap_count"] == 1


def test_distinct_embedded_types_keep_distinct_scoped_paths() -> None:
    vi = {
        "objects": [],
        "wires": [],
        "summary": {},
        "type_definitions": [
            {
                "id": "first",
                "name": "Cluster",
                "definition": {
                    "kind": "cluster",
                    "name": "Cluster",
                    "fields": [
                        {"name": "A", "type": {"kind": "primitive", "name": "I32"}}
                    ],
                },
            },
            {
                "id": "second",
                "name": "Cluster",
                "definition": {
                    "kind": "cluster",
                    "name": "Cluster",
                    "fields": [
                        {"name": "B", "type": {"kind": "primitive", "name": "String"}}
                    ],
                },
            },
        ],
    }

    result = canonicalize_type_definitions(vi)

    assert len(result["type_definitions"]) == 2
    paths = {item["recorded_path"] for item in result["type_definitions"]}
    assert len(paths) == 2
    assert all(path.startswith("embedded://cluster/") for path in paths)


def test_only_displayed_structure_frame_remains_on_diagram() -> None:
    vi = {
        "objects": [
            {
                "id": "case",
                "uid": "100",
                "surface": "block-diagram",
                "category": "node",
                "kind": "structure-case",
                "terminal_ids": [],
                "linked_terminal_ids": [],
                "wire_ids": [],
                "structure": {
                    "displayed_frame": 1,
                    "frames": [
                        {"selector_value": "False", "inner_node_uids": ["200"]},
                        {"selector_value": "True", "inner_node_uids": ["201"]},
                    ],
                },
            },
            {
                "id": "inactive-node",
                "uid": "200",
                "surface": "block-diagram",
                "category": "node",
                "kind": "subvi",
                "parent_object_id": "case",
                "terminal_ids": ["inactive-terminal"],
                "linked_terminal_ids": [],
                "wire_ids": ["inactive-wire"],
            },
            {
                "id": "active-node",
                "uid": "201",
                "surface": "block-diagram",
                "category": "node",
                "kind": "subvi",
                "parent_object_id": "case",
                "terminal_ids": ["active-terminal"],
                "linked_terminal_ids": [],
                "wire_ids": ["active-wire"],
            },
            {
                "id": "inactive-terminal",
                "uid": "210",
                "surface": "block-diagram",
                "category": "terminal",
                "owner_object_id": "inactive-node",
                "terminal_ids": [],
                "linked_terminal_ids": [],
                "wire_ids": ["inactive-wire"],
            },
            {
                "id": "active-terminal",
                "uid": "211",
                "surface": "block-diagram",
                "category": "terminal",
                "owner_object_id": "active-node",
                "terminal_ids": [],
                "linked_terminal_ids": [],
                "wire_ids": ["active-wire"],
            },
            {
                "id": "external-terminal",
                "uid": "300",
                "surface": "block-diagram",
                "category": "terminal",
                "owner_object_id": None,
                "terminal_ids": [],
                "linked_terminal_ids": [],
                "wire_ids": ["inactive-wire", "active-wire"],
            },
        ],
        "wires": [
            {
                "id": "inactive-wire",
                "source_terminal_id": "external-terminal",
                "target_terminal_ids": ["inactive-terminal"],
                "source_object_id": None,
                "target_object_ids": ["inactive-node"],
                "resolved": True,
            },
            {
                "id": "active-wire",
                "source_terminal_id": "external-terminal",
                "target_terminal_ids": ["active-terminal"],
                "source_object_id": None,
                "target_object_ids": ["active-node"],
                "resolved": True,
            },
        ],
        "surfaces": {"block-diagram": []},
        "summary": {},
    }

    result = select_displayed_structure_frames(vi)
    by_id = {item["id"]: item for item in result["objects"]}

    assert by_id["case"]["active_frame_index"] == 1
    assert by_id["case"]["active_frame_label"] == "True"
    assert by_id["inactive-node"]["surface"] == "block-diagram-inactive"
    assert by_id["inactive-terminal"]["surface"] == "block-diagram-inactive"
    assert by_id["active-node"]["surface"] == "block-diagram"
    assert [wire["id"] for wire in result["wires"]] == ["active-wire"]
    assert [wire["id"] for wire in result["inactive_structure_frame_wires"]] == [
        "inactive-wire"
    ]
    assert result["summary"]["block_diagram_nodes"] == 2
    assert result["summary"]["terminals"] == 2
    assert result["summary"]["wires"] == 1
    assert result["summary"]["hidden_structure_frame_objects"] == 2
    assert result["integrity"]["structure_frames"]["active_frame_only"] is True


def test_inactive_outer_frame_hides_nested_structure_descendants() -> None:
    vi = {
        "objects": [
            {
                "id": "outer",
                "uid": "10",
                "surface": "block-diagram",
                "category": "node",
                "structure": {
                    "displayed_frame": 0,
                    "frames": [
                        {"inner_node_uids": ["11"]},
                        {"inner_node_uids": ["12"]},
                    ],
                },
                "terminal_ids": [],
                "linked_terminal_ids": [],
                "wire_ids": [],
            },
            {
                "id": "active",
                "uid": "11",
                "surface": "block-diagram",
                "category": "node",
                "parent_object_id": "outer",
                "terminal_ids": [],
                "linked_terminal_ids": [],
                "wire_ids": [],
            },
            {
                "id": "nested",
                "uid": "12",
                "surface": "block-diagram",
                "category": "node",
                "parent_object_id": "outer",
                "terminal_ids": [],
                "linked_terminal_ids": [],
                "wire_ids": [],
            },
            {
                "id": "nested-child",
                "uid": "13",
                "surface": "block-diagram",
                "category": "node",
                "parent_object_id": "nested",
                "terminal_ids": [],
                "linked_terminal_ids": [],
                "wire_ids": [],
            },
        ],
        "wires": [],
        "surfaces": {"block-diagram": []},
        "summary": {},
    }

    result = select_displayed_structure_frames(vi)
    by_id = {item["id"]: item for item in result["objects"]}

    assert by_id["active"]["surface"] == "block-diagram"
    assert by_id["nested"]["surface"] == "block-diagram-inactive"
    assert by_id["nested-child"]["surface"] == "block-diagram-inactive"
