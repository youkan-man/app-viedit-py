from __future__ import annotations

from types import SimpleNamespace

from app.lvkit_semantic_runtime import _NullableBoundsSafeIndex
from app.semantic_integrity_runtime import finalize_semantic_vi


def _component(
    component_id: str,
    *,
    uid: str,
    file: str,
    kind: str,
    class_name: str,
) -> dict:
    return {
        "id": component_id,
        "uid": uid,
        "file": file,
        "kind": kind,
        "class_name": class_name,
        "role": "component",
        "bounds": None,
    }


def test_connector_lookup_rejects_globally_unique_nonterminal_uid() -> None:
    model = SimpleNamespace(
        components={
            "control": _component(
                "control",
                uid="10",
                file="panel_FPHb.xml",
                kind="control",
                class_name="fPDCO",
            )
        }
    )
    index = _NullableBoundsSafeIndex(model)

    assert (
        index.find(
            "10",
            "diagram_BDHb.xml",
            class_hint="term",
            kind_hint="connector",
        )
        is None
    )


def test_connector_lookup_keeps_same_file_connector_and_normalizes_bounds() -> None:
    model = SimpleNamespace(
        components={
            "control": _component(
                "control",
                uid="10",
                file="panel_FPHb.xml",
                kind="control",
                class_name="fPDCO",
            ),
            "terminal": _component(
                "terminal",
                uid="10",
                file="diagram_BDHb.xml",
                kind="connector",
                class_name="term",
            ),
        }
    )
    index = _NullableBoundsSafeIndex(model)

    result = index.find(
        "10",
        "diagram_BDHb.xml",
        class_hint="term",
        kind_hint="connector",
    )

    assert result is not None
    assert result["id"] == "terminal"
    assert result["bounds"] == {}


def test_duplicate_endpoint_identity_is_reported_without_crashing() -> None:
    duplicate_node = {
        "id": "duplicate",
        "surface": "block-diagram",
        "category": "node",
        "kind": "subvi",
        "terminal_ids": [],
        "linked_terminal_ids": [],
        "wire_ids": [],
        "child_object_ids": [],
        "data_type": "unknown",
    }
    duplicate_terminal = {
        "id": "duplicate",
        "surface": "block-diagram",
        "category": "terminal",
        "kind": "terminal",
        "direction": "source",
        "terminal_ids": [],
        "linked_terminal_ids": [],
        "wire_ids": [],
        "child_object_ids": [],
        "data_type": "unknown",
    }
    sink = {
        "id": "sink",
        "surface": "block-diagram",
        "category": "terminal",
        "kind": "terminal",
        "direction": "sink",
        "terminal_ids": [],
        "linked_terminal_ids": [],
        "wire_ids": [],
        "child_object_ids": [],
        "data_type": "unknown",
    }
    vi = {
        "objects": [duplicate_node, duplicate_terminal, sink],
        "wires": [
            {
                "id": "wire",
                "source_terminal_id": "duplicate",
                "target_terminal_ids": ["sink"],
                "native_uid": "1",
            }
        ],
        "type_definitions": [],
        "summary": {"unresolved_wires": 0},
        "warnings": [],
    }

    result = finalize_semantic_vi(vi)

    assert result["integrity"]["duplicate_objects_removed"] == 1
    assert result["integrity"]["nonterminal_wire_endpoints"] == 1
    assert result["integrity"]["nonterminal_wire_endpoint_ids"] == ["duplicate"]
