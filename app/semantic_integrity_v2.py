from __future__ import annotations

import copy
import json
from collections import defaultdict
from typing import Any

from . import semantic_integrity as base


def _definition_path(definition: dict[str, Any]) -> str:
    payload = definition.get("definition") or {}
    return base._definition_path(
        definition.get("recorded_path")
        or payload.get("typedef_path")
        or definition.get("target_file")
    )


def _definition_name(definition: dict[str, Any]) -> str:
    payload = definition.get("definition") or {}
    return base._definition_name(
        definition.get("name")
        or payload.get("typedef_name")
        or definition.get("recorded_path")
        or definition.get("target_file")
    )


def _definition_signature(definition: dict[str, Any]) -> str:
    payload = definition.get("definition")
    if not payload:
        return ""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _merge_record(
    current: dict[str, Any],
    incoming: dict[str, Any],
    canonical_id: str,
) -> dict[str, Any]:
    def strength(definition: dict[str, Any]) -> tuple[int, int, int, int]:
        return (
            int(bool(definition.get("definition"))),
            int(bool(definition.get("target_file"))),
            len(definition.get("source_object_ids") or []),
            int(definition.get("source") == "parsed-type"),
        )

    primary, secondary = (
        (copy.deepcopy(incoming), current)
        if strength(incoming) > strength(current)
        else (copy.deepcopy(current), incoming)
    )
    primary["id"] = canonical_id
    for key in (
        "definition",
        "target_file",
        "recorded_path",
        "name",
        "kind",
        "source",
    ):
        if not primary.get(key) and secondary.get(key):
            primary[key] = copy.deepcopy(secondary[key])
    sources = list(dict.fromkeys([
        *(primary.get("source_object_ids") or []),
        *(secondary.get("source_object_ids") or []),
    ]))
    primary["source_object_ids"] = sources
    primary["available"] = bool(primary.get("definition") or primary.get("target_file"))
    return primary


def _merge_type_definitions(
    result: dict[str, Any],
    object_index: dict[str, dict[str, Any]],
) -> tuple[int, int, int]:
    definitions = [copy.deepcopy(item) for item in result.get("type_definitions", [])]
    by_id = {str(item.get("id")): item for item in definitions if item.get("id")}

    for item in object_index.values():
        payload = item.get("type")
        requested = base._payload_definition(payload)
        if not requested:
            continue
        name, recorded_path = requested
        existing_id = item.get("type_definition_id")
        if existing_id in by_id:
            sources = by_id[existing_id].setdefault("source_object_ids", [])
            if item["id"] not in sources:
                sources.append(item["id"])
            continue
        signature = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        definition_id = base._stable_id(
            "semantic-type",
            name,
            recorded_path,
            signature,
        )
        definition = by_id.setdefault(
            definition_id,
            {
                "id": definition_id,
                "name": name,
                "kind": payload.get("kind") or "unknown",
                "recorded_path": recorded_path,
                "target_file": None,
                "available": True,
                "definition": payload,
                "source_object_ids": [],
                "source": "semantic-integrity-v2",
            },
        )
        if item["id"] not in definition["source_object_ids"]:
            definition["source_object_ids"].append(item["id"])
        item["type_definition_id"] = definition_id

    paths_by_name: dict[str, set[str]] = defaultdict(set)
    signatures_by_name: dict[str, set[str]] = defaultdict(set)
    for definition in by_id.values():
        name = _definition_name(definition)
        path = _definition_path(definition)
        signature = _definition_signature(definition)
        if name and path:
            paths_by_name[name].add(path)
        if name and signature:
            signatures_by_name[name].add(signature)

    ambiguous_names = {
        name
        for name in set(paths_by_name) | set(signatures_by_name)
        if len(paths_by_name.get(name, set())) > 1
        or len(signatures_by_name.get(name, set())) > 1
    }

    def canonical_key(definition: dict[str, Any]) -> tuple[str, ...]:
        definition_id = str(definition["id"])
        name = _definition_name(definition)
        path = _definition_path(definition)
        signature = _definition_signature(definition)
        if path:
            return ("path", path)
        if not name:
            return ("id", definition_id)
        known_paths = paths_by_name.get(name, set())
        if len(known_paths) == 1:
            return ("path", next(iter(known_paths)))
        known_signatures = signatures_by_name.get(name, set())
        if len(known_paths) > 1:
            return (
                "ambiguous-payload",
                name,
                signature or definition_id,
            )
        if len(known_signatures) == 1:
            return ("name-payload", name, next(iter(known_signatures)))
        if signature:
            return ("name-payload", name, signature)
        return ("name", name)

    canonical_by_key: dict[tuple[str, ...], str] = {}
    canonical: dict[str, dict[str, Any]] = {}
    remap: dict[str, str] = {}
    merged_count = 0
    for definition in by_id.values():
        definition_id = str(definition["id"])
        key = canonical_key(definition)
        canonical_id = canonical_by_key.get(key)
        if canonical_id is None:
            canonical_id = definition_id
            canonical_by_key[key] = canonical_id
            canonical[canonical_id] = copy.deepcopy(definition)
            canonical[canonical_id]["id"] = canonical_id
        else:
            canonical[canonical_id] = _merge_record(
                canonical[canonical_id],
                definition,
                canonical_id,
            )
            merged_count += 1
        remap[definition_id] = canonical_id

    for item in object_index.values():
        definition_id = item.get("type_definition_id")
        if definition_id in remap:
            item["type_definition_id"] = remap[definition_id]

    result["type_definitions"] = sorted(
        canonical.values(),
        key=lambda item: (
            str(item.get("name") or "").casefold(),
            _definition_path(item),
            str(item["id"]),
        ),
    )
    unattached = sum(
        not definition.get("source_object_ids")
        for definition in result["type_definitions"]
    )
    return merged_count, unattached, len(ambiguous_names)


def _sanitize_and_rebuild_relationships(
    result: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    unique_objects: list[dict[str, Any]] = []
    object_index: dict[str, dict[str, Any]] = {}
    duplicate_objects = 0
    for item in result.get("objects", []):
        object_id = str(item.get("id") or "")
        if not object_id:
            continue
        if object_id in object_index:
            duplicate_objects += 1
            continue
        object_index[object_id] = item
        unique_objects.append(item)

    valid_wires: list[dict[str, Any]] = []
    seen_wire_ids: set[str] = set()
    removed_wires = 0
    duplicate_wires = 0
    removed_endpoints = 0
    for wire in result.get("wires", []):
        wire_id = str(wire.get("id") or "")
        if not wire_id or wire_id in seen_wire_ids:
            duplicate_wires += 1
            continue
        seen_wire_ids.add(wire_id)
        source = wire.get("source_terminal_id")
        original_targets = list(wire.get("target_terminal_ids") or [])
        targets = list(dict.fromkeys(
            target for target in original_targets if target in object_index
        ))
        removed_endpoints += len(original_targets) - len(targets)
        if source not in object_index or not targets:
            removed_wires += 1
            continue
        wire["target_terminal_ids"] = targets
        wire["terminal_ids"] = [source, *targets]
        wire["resolved"] = True
        valid_wires.append(wire)

    cleared_relationships = 0
    for item in unique_objects:
        for key in ("owner_object_id", "linked_object_id", "parent_object_id"):
            value = item.get(key)
            if value and value not in object_index:
                item[key] = None
                cleared_relationships += 1
        item["terminal_ids"] = []
        item["linked_terminal_ids"] = []
        item["wire_ids"] = []
        item["child_object_ids"] = []
        if item.get("category") == "terminal":
            item["wire_roles"] = []

    for item in unique_objects:
        parent_id = item.get("parent_object_id")
        if parent_id:
            object_index[parent_id]["child_object_ids"].append(item["id"])
        if item.get("category") != "terminal":
            continue
        owner_id = item.get("owner_object_id")
        linked_id = item.get("linked_object_id")
        if owner_id:
            object_index[owner_id]["terminal_ids"].append(item["id"])
        if linked_id:
            object_index[linked_id]["linked_terminal_ids"].append(item["id"])

    for item in unique_objects:
        item["terminal_ids"].sort(
            key=lambda terminal_id: object_index[terminal_id].get(
                "port_index",
                10**9,
            )
        )
        item["child_object_ids"].sort(
            key=lambda child_id: (
                int(object_index[child_id].get("nesting_depth", 0)),
                float((object_index[child_id].get("bounds") or {}).get("y", 10**9)),
                float((object_index[child_id].get("bounds") or {}).get("x", 10**9)),
            )
        )

    for wire in valid_wires:
        source_terminal = object_index[wire["source_terminal_id"]]
        target_terminals = [
            object_index[target_id]
            for target_id in wire["target_terminal_ids"]
        ]
        if "source" not in source_terminal["wire_roles"]:
            source_terminal["wire_roles"].append("source")
        for terminal in target_terminals:
            if "sink" not in terminal["wire_roles"]:
                terminal["wire_roles"].append("sink")

        source_object_id = (
            source_terminal.get("linked_object_id")
            or source_terminal.get("owner_object_id")
        )
        target_object_ids = list(dict.fromkeys(
            terminal.get("linked_object_id") or terminal.get("owner_object_id")
            for terminal in target_terminals
            if terminal.get("linked_object_id") or terminal.get("owner_object_id")
        ))
        target_object_ids = [
            object_id
            for object_id in target_object_ids
            if object_id in object_index
        ]
        wire["source_object_id"] = source_object_id
        wire["target_object_ids"] = target_object_ids
        wire["endpoint_object_ids"] = list(dict.fromkeys(
            object_id
            for object_id in [source_object_id, *target_object_ids]
            if object_id in object_index
        ))
        wire["endpoint_roles"] = {
            "source": wire["source_terminal_id"],
            "targets": list(wire["target_terminal_ids"]),
        }
        for terminal_id in wire["terminal_ids"]:
            terminal = object_index[terminal_id]
            if wire["id"] not in terminal["wire_ids"]:
                terminal["wire_ids"].append(wire["id"])
        for object_id in wire["endpoint_object_ids"]:
            endpoint = object_index[object_id]
            if wire["id"] not in endpoint["wire_ids"]:
                endpoint["wire_ids"].append(wire["id"])

    bidirectional = 0
    for item in unique_objects:
        if item.get("category") != "terminal":
            continue
        roles = list(dict.fromkeys(item.get("wire_roles") or []))
        item["wire_roles"] = roles
        role_set = set(roles)
        if role_set == {"source", "sink"}:
            item["direction"] = "bidirectional"
            item["direction_source"] = "signal-term-list-mixed"
            item["is_bidirectional"] = True
            bidirectional += 1
        elif role_set == {"source"}:
            item["direction"] = "source"
            item["direction_source"] = "signal-term-list"
            item["is_bidirectional"] = False
        elif role_set == {"sink"}:
            item["direction"] = "sink"
            item["direction_source"] = "signal-term-list"
            item["is_bidirectional"] = False
        else:
            item["is_bidirectional"] = item.get("direction") == "bidirectional"

    result["objects"] = unique_objects
    result["wires"] = valid_wires
    return object_index, {
        "duplicate_objects_removed": duplicate_objects,
        "duplicate_wires_removed": duplicate_wires,
        "dangling_wires_removed": removed_wires,
        "dangling_wire_endpoints_removed": removed_endpoints,
        "dangling_relationships_cleared": cleared_relationships,
        "bidirectional_terminals": bidirectional,
    }


def _input_unresolved_wires(result: dict[str, Any]) -> int:
    integrity = result.get("integrity") or {}
    if "input_unresolved_wires" in integrity:
        return max(0, int(integrity.get("input_unresolved_wires") or 0))
    summary = result.get("summary") or {}
    unresolved = max(0, int(summary.get("unresolved_wires") or 0))
    previous_removed = max(0, int(integrity.get("dangling_wires_removed") or 0))
    return max(0, unresolved - previous_removed)


def _recompute_summary(
    result: dict[str, Any],
    object_index: dict[str, dict[str, Any]],
    *,
    input_unresolved_wires: int,
    removed_wires: int,
) -> None:
    objects = list(object_index.values())
    controls = [item for item in objects if item.get("category") == "control"]
    indicators = [item for item in objects if item.get("category") == "indicator"]
    nodes = [
        item
        for item in objects
        if item.get("surface") == "block-diagram"
        and item.get("category") == "node"
    ]
    terminals = [item for item in objects if item.get("category") == "terminal"]
    wires = result.get("wires", [])
    definitions = result.get("type_definitions", [])
    summary = result.setdefault("summary", {})
    summary.update(
        {
            "front_panel_objects": len(controls) + len(indicators),
            "block_diagram_nodes": len(nodes),
            "controls": len(controls),
            "indicators": len(indicators),
            "terminals": len(terminals),
            "bidirectional_terminals": sum(
                item.get("direction") == "bidirectional"
                for item in terminals
            ),
            "wires": len(wires),
            "wire_nets": len(result.get("nets", [])),
            "resolved_wires": sum(bool(item.get("resolved", True)) for item in wires),
            "unresolved_wires": input_unresolved_wires + removed_wires,
            "numeric_controls": sum(
                item.get("data_type") == "numeric"
                for item in controls
            ),
            "numeric_indicators": sum(
                item.get("data_type") == "numeric"
                for item in indicators
            ),
            "add_nodes": sum(item.get("kind") == "add" for item in nodes),
            "clusters": sum(item.get("data_type") == "cluster" for item in objects),
            "cluster_members": sum(
                bool(item.get("parent_object_id"))
                and object_index.get(item.get("parent_object_id"), {}).get("data_type")
                == "cluster"
                for item in objects
            ),
            "type_definitions": len(definitions),
            "positioned_nodes": sum(bool(item.get("bounds")) for item in nodes),
            "editable_nodes": sum(bool(item.get("movable")) for item in nodes),
        }
    )
    result["surfaces"] = {
        "front-panel": [
            item["id"]
            for item in objects
            if item.get("surface") == "front-panel"
        ],
        "block-diagram": [
            item["id"]
            for item in objects
            if item.get("surface") == "block-diagram"
        ],
    }
    result["hierarchy"] = {
        "roots": [
            item["id"]
            for item in objects
            if not item.get("parent_object_id")
        ],
        "containers": [
            item["id"]
            for item in objects
            if item.get("child_object_ids")
        ],
        "children_by_parent": {
            item["id"]: list(item.get("child_object_ids") or [])
            for item in objects
            if item.get("child_object_ids")
        },
    }


def finalize_semantic_vi(
    vi: dict[str, Any],
    *,
    parsed: object | None = None,
) -> dict[str, Any]:
    result = copy.deepcopy(vi)
    result.setdefault("objects", [])
    result.setdefault("wires", [])
    result.setdefault("warnings", [])
    input_unresolved = _input_unresolved_wires(result)

    constants_typed = base._resolve_constant_types(result, parsed)
    structure_owners = base._resolve_structure_terminal_owners(result, parsed)
    for item in result["objects"]:
        base._normalize_node_identity(item)
        item["data_type"] = base.type_family(
            item.get("type"),
            item.get("data_type"),
        )

    object_index, cleanup = _sanitize_and_rebuild_relationships(result)

    owner_anchors = 0
    hierarchy_anchors = 0
    for item in object_index.values():
        owner_id = item.get("owner_object_id")
        if owner_id and owner_id in object_index:
            owner_anchors += int(base._anchor_bounds(
                item,
                object_index[owner_id],
                source_space="absolute-owner-anchored",
            ))
        parent_id = item.get("parent_object_id")
        if parent_id and parent_id in object_index:
            hierarchy_anchors += int(base._anchor_bounds(
                item,
                object_index[parent_id],
                source_space="absolute-parent-anchored",
            ))

    merged, unattached, ambiguous_names = _merge_type_definitions(
        result,
        object_index,
    )
    nets, type_conflicts = base._wire_integrity(result, object_index)
    propagated = base._propagate_object_types(result, object_index)
    merged_again, unattached, ambiguous_again = _merge_type_definitions(
        result,
        object_index,
    )
    merged += merged_again
    ambiguous_names = max(ambiguous_names, ambiguous_again)
    # The second registry pass may remap endpoint definition IDs. Rebuild wire
    # and net metadata once more so wires never retain stale definition IDs.
    nets, type_conflicts = base._wire_integrity(result, object_index)

    warnings: list[str] = []
    for warning in result.get("warnings", []):
        text = str(warning).strip()
        if text and text not in warnings:
            warnings.append(text)
    result["warnings"] = warnings
    _recompute_summary(
        result,
        object_index,
        input_unresolved_wires=input_unresolved,
        removed_wires=cleanup["dangling_wires_removed"],
    )
    result["integrity"] = {
        "version": 2,
        "input_unresolved_wires": input_unresolved,
        **cleanup,
        "structure_terminal_owners_resolved": structure_owners,
        "owner_anchors_added": owner_anchors,
        "hierarchy_anchors_added": hierarchy_anchors,
        "constant_types_resolved": constants_typed,
        "types_propagated": propagated,
        "type_conflicts": type_conflicts,
        "type_definitions_merged": merged,
        "ambiguous_type_definition_names": ambiguous_names,
        "unattached_type_definitions": unattached,
        "wire_nets": len(nets),
    }
    result["version"] = max(5, int(result.get("version") or 1))
    return result


__all__ = ["finalize_semantic_vi"]
