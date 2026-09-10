from __future__ import annotations

from pathlib import Path

from app.lvkit_semantic_runtime import _discover_primary_document
from app.semantic_integrity_v2 import finalize_semantic_vi


def _terminal(
    object_id: str,
    direction: str,
    *,
    type_payload: dict | None = None,
    definition_id: str | None = None,
) -> dict:
    return {
        "id": object_id,
        "surface": "block-diagram",
        "category": "terminal",
        "kind": "terminal",
        "direction": direction,
        "bounds": {"x": 0, "y": 0, "width": 8, "height": 8},
        "owner_object_id": None,
        "linked_object_id": None,
        "terminal_ids": [],
        "linked_terminal_ids": [],
        "wire_ids": [],
        "child_object_ids": [],
        "data_type": "unknown",
        "type": type_payload,
        "type_definition_id": definition_id,
    }


def test_tunnel_used_on_both_sides_is_bidirectional_not_mismatched() -> None:
    vi = {
        "version": 3,
        "objects": [
            _terminal("outside-source", "source"),
            _terminal("tunnel", "source"),
            _terminal("inside-sink", "sink"),
        ],
        "wires": [
            {
                "id": "outside-wire",
                "native_uid": "100",
                "source_terminal_id": "outside-source",
                "target_terminal_ids": ["tunnel"],
                "resolved": True,
            },
            {
                "id": "inside-wire",
                "native_uid": "101",
                "source_terminal_id": "tunnel",
                "target_terminal_ids": ["inside-sink"],
                "resolved": True,
            },
        ],
        "type_definitions": [],
        "summary": {"unresolved_wires": 0},
        "warnings": [],
    }

    result = finalize_semantic_vi(vi)
    objects = {item["id"]: item for item in result["objects"]}

    assert objects["outside-source"]["wire_roles"] == ["source"]
    assert objects["inside-sink"]["wire_roles"] == ["sink"]
    assert set(objects["tunnel"]["wire_roles"]) == {"source", "sink"}
    assert objects["tunnel"]["direction"] == "bidirectional"
    assert objects["tunnel"]["direction_source"] == "signal-term-list-mixed"
    assert result["summary"]["bidirectional_terminals"] == 1
    assert result["integrity"]["bidirectional_terminals"] == 1
    assert len(result["wires"]) == 2


def test_same_typedef_basename_in_different_directories_stays_distinct() -> None:
    type_a = {
        "kind": "typedef_ref",
        "name": "Cluster",
        "typedef_name": "Settings.ctl",
        "typedef_path": "alpha/Settings.ctl",
        "fields": [{"name": "A", "type": {"kind": "primitive", "name": "NumInt32"}}],
    }
    type_b = {
        "kind": "typedef_ref",
        "name": "Cluster",
        "typedef_name": "Settings.ctl",
        "typedef_path": "beta/Settings.ctl",
        "fields": [{"name": "B", "type": {"kind": "primitive", "name": "String"}}],
    }
    vi = {
        "objects": [
            _terminal("terminal-a", "source", type_payload=type_a),
            _terminal("terminal-b", "source", type_payload=type_b),
        ],
        "wires": [],
        "type_definitions": [],
        "summary": {"unresolved_wires": 0},
        "warnings": [],
    }

    result = finalize_semantic_vi(vi)
    objects = {item["id"]: item for item in result["objects"]}
    definitions = result["type_definitions"]

    assert len(definitions) == 2
    assert {item["recorded_path"] for item in definitions} == {
        "alpha/Settings.ctl",
        "beta/Settings.ctl",
    }
    assert objects["terminal-a"]["type_definition_id"] != objects["terminal-b"]["type_definition_id"]
    assert result["integrity"]["ambiguous_type_definition_names"] == 1


def test_dangling_relationship_is_not_counted_as_unresolved_wire() -> None:
    vi = {
        "objects": [
            {
                **_terminal("remaining", "sink"),
                "owner_object_id": "missing-owner",
            }
        ],
        "wires": [],
        "type_definitions": [],
        "summary": {"unresolved_wires": 2},
        "warnings": [],
    }

    result = finalize_semantic_vi(vi)

    assert result["summary"]["unresolved_wires"] == 2
    assert result["integrity"]["dangling_relationships_cleared"] == 1
    assert result["integrity"]["dangling_wires_removed"] == 0


def test_repeated_finalization_does_not_inflate_or_drop_unresolved_count() -> None:
    vi = {
        "objects": [_terminal("remaining", "sink")],
        "wires": [
            {
                "id": "dangling-wire",
                "source_terminal_id": "missing-source",
                "target_terminal_ids": ["remaining"],
            }
        ],
        "type_definitions": [],
        "summary": {"unresolved_wires": 2},
        "warnings": [],
    }

    first = finalize_semantic_vi(vi)
    second = finalize_semantic_vi(first)

    assert first["summary"]["unresolved_wires"] == 3
    assert second["summary"]["unresolved_wires"] == 3
    assert first["integrity"]["dangling_wires_removed"] == 1
    assert second["integrity"]["dangling_wires_removed"] == 1


def test_primary_document_prefers_selected_main_xml_sibling(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    for directory in (first, second):
        (directory / "Shared.xml").write_text("<RSRC/>", encoding="utf-8")
        (directory / "Shared_BDHb.xml").write_text("<SL__rootObject/>", encoding="utf-8")
        (directory / "Shared_FPHb.xml").write_text("<SL__rootObject/>", encoding="utf-8")

    selected = second / "Shared.xml"
    document = _discover_primary_document(tmp_path, selected)

    assert document is not None
    block_diagram, front_panel, main_xml = document
    assert block_diagram == second / "Shared_BDHb.xml"
    assert front_panel == second / "Shared_FPHb.xml"
    assert main_xml == selected.resolve()
