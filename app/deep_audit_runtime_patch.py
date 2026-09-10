from __future__ import annotations

import copy
import hashlib
import json
import posixpath
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

_INSTALLED = False
_ORIGINALS: dict[str, Callable[..., dict[str, Any]]] = {}


def _text(value: object) -> str:
    return str(value or "").strip()


def _normalize_name(value: object) -> str:
    text = _text(value).replace("\\", "/")
    return Path(text).name.casefold()


def _normalize_path(value: object) -> str:
    text = _text(value).replace("\\", "/")
    if not text:
        return ""
    if "://" in text:
        scheme, rest = text.split("://", 1)
        return f"{scheme.casefold()}://{posixpath.normpath('/' + rest).lstrip('/').casefold()}"
    return posixpath.normpath("/" + text).lstrip("/").casefold()


def _definition_payload(definition: dict[str, Any]) -> dict[str, Any]:
    payload = definition.get("definition")
    return payload if isinstance(payload, dict) else {}


def _definition_name(definition: dict[str, Any]) -> str:
    payload = _definition_payload(definition)
    return _text(
        definition.get("name")
        or payload.get("typedef_name")
        or definition.get("recorded_path")
        or definition.get("target_file")
        or payload.get("name")
        or payload.get("kind")
        or "Type Definition"
    )


def _definition_path(definition: dict[str, Any]) -> str:
    payload = _definition_payload(definition)
    return _normalize_path(
        definition.get("target_file")
        or definition.get("recorded_path")
        or payload.get("typedef_path")
    )


def _payload_signature(definition: dict[str, Any]) -> str:
    payload = _definition_payload(definition)
    if not payload:
        return "reference"
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _richness(definition: dict[str, Any]) -> tuple[int, int, int, int]:
    payload = _definition_payload(definition)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return (
        int(bool(payload.get("fields"))),
        int(bool(payload.get("element_type") or payload.get("values"))),
        int(bool(payload)),
        len(encoded),
    )


def _compatible_payloads(first: dict[str, Any], second: dict[str, Any]) -> bool:
    first_payload = _definition_payload(first)
    second_payload = _definition_payload(second)
    if not first_payload or not second_payload:
        return True
    if first_payload == second_payload:
        return True
    first_kind = _text(first_payload.get("kind")).casefold()
    second_kind = _text(second_payload.get("kind")).casefold()
    if first_kind and second_kind and first_kind != second_kind:
        # A typedef reference and its resolved cluster/enum/array body are the
        # same type at different decoding depths, not two definitions.
        compatible_pairs = {
            frozenset(("typedef_ref", "cluster")),
            frozenset(("typedef_ref", "array")),
            frozenset(("typedef_ref", "enum")),
            frozenset(("typedef_ref", "ring")),
            frozenset(("typedef_ref", "class")),
        }
        if frozenset((first_kind, second_kind)) not in compatible_pairs:
            return False
    first_name = _normalize_name(
        first_payload.get("typedef_name") or first_payload.get("name")
    )
    second_name = _normalize_name(
        second_payload.get("typedef_name") or second_payload.get("name")
    )
    return not first_name or not second_name or first_name == second_name


def _canonical_type_keys(
    definitions: list[dict[str, Any]],
) -> dict[str, tuple[str, ...]]:
    paths_by_name: dict[str, set[str]] = defaultdict(set)
    for definition in definitions:
        name = _normalize_name(_definition_name(definition))
        path = _definition_path(definition)
        if name and path and not path.startswith(("embedded://", "unresolved://")):
            paths_by_name[name].add(path)

    keys: dict[str, tuple[str, ...]] = {}
    for definition in definitions:
        definition_id = _text(definition.get("id"))
        name = _normalize_name(_definition_name(definition)) or "type-definition"
        path = _definition_path(definition)
        signature = _payload_signature(definition)
        if path:
            keys[definition_id] = ("path", path)
            continue
        known_paths = paths_by_name.get(name, set())
        if len(known_paths) == 1:
            keys[definition_id] = ("path", next(iter(known_paths)))
        elif name.endswith((".ctl", ".ctt")) and len(known_paths) == 0:
            keys[definition_id] = ("unresolved-typedef", name)
        else:
            keys[definition_id] = ("embedded", name, signature)
    return keys


def _merge_definition(
    canonical: dict[str, Any],
    candidate: dict[str, Any],
) -> None:
    canonical.setdefault("source_object_ids", [])
    for object_id in candidate.get("source_object_ids") or []:
        if object_id not in canonical["source_object_ids"]:
            canonical["source_object_ids"].append(object_id)
    canonical["available"] = bool(
        canonical.get("available") or candidate.get("available")
    )
    for key in ("target_file", "recorded_path", "source"):
        if not canonical.get(key) and candidate.get(key):
            canonical[key] = candidate[key]
    if _richness(candidate) > _richness(canonical):
        canonical["definition"] = copy.deepcopy(candidate.get("definition"))
        if candidate.get("kind"):
            canonical["kind"] = candidate["kind"]
    if not _compatible_payloads(canonical, candidate):
        variants = canonical.setdefault("definition_variants", [])
        for definition in (canonical, candidate):
            payload = _definition_payload(definition)
            signature = _payload_signature(definition)
            if payload and all(item.get("signature") != signature for item in variants):
                variants.append(
                    {
                        "signature": signature,
                        "definition": copy.deepcopy(payload),
                    }
                )
        canonical["definition_conflict"] = True


def canonicalize_type_definitions(vi: dict[str, Any]) -> dict[str, Any]:
    definitions = [
        copy.deepcopy(item)
        for item in vi.get("type_definitions", [])
        if isinstance(item, dict) and item.get("id")
    ]
    if not definitions:
        return vi

    keys = _canonical_type_keys(definitions)
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for definition in definitions:
        grouped[keys[_text(definition.get("id"))]].append(definition)

    merged: list[dict[str, Any]] = []
    remap: dict[str, str] = {}
    for key in sorted(grouped):
        candidates = sorted(
            grouped[key],
            key=lambda item: (_richness(item), _text(item.get("id"))),
            reverse=True,
        )
        canonical = copy.deepcopy(candidates[0])
        canonical_id = _text(canonical.get("id"))
        if key[0] == "path":
            if not canonical.get("recorded_path") and not canonical.get("target_file"):
                canonical["recorded_path"] = key[1]
        elif key[0] == "unresolved-typedef":
            canonical["recorded_path"] = f"unresolved://{key[1]}"
        else:
            canonical["recorded_path"] = f"embedded://{key[1]}/{key[2]}"
        for candidate in candidates:
            candidate_id = _text(candidate.get("id"))
            remap[candidate_id] = canonical_id
            if candidate_id != canonical_id:
                _merge_definition(canonical, candidate)
        canonical["source_object_ids"] = sorted(
            set(canonical.get("source_object_ids") or [])
        )
        merged.append(canonical)

    for collection_name in ("objects", "wires"):
        for item in vi.get(collection_name, []) or []:
            definition_id = _text(item.get("type_definition_id"))
            if definition_id in remap:
                item["type_definition_id"] = remap[definition_id]
            definition_ids = item.get("type_definition_ids")
            if isinstance(definition_ids, list):
                item["type_definition_ids"] = sorted(
                    {
                        remap.get(_text(value), _text(value))
                        for value in definition_ids
                        if value
                    }
                )

    vi["type_definitions"] = sorted(
        merged,
        key=lambda item: (
            _normalize_name(_definition_name(item)),
            _definition_path(item),
            _text(item.get("id")),
        ),
    )
    vi.setdefault("summary", {})["type_definitions"] = len(merged)
    vi.setdefault("integrity", {})["canonical_type_definitions"] = True
    vi["integrity"]["type_definition_remap_count"] = sum(
        old_id != new_id for old_id, new_id in remap.items()
    )
    vi["integrity"]["type_definition_conflicts"] = sum(
        bool(item.get("definition_conflict")) for item in merged
    )
    return vi


def _frames_from_structure(structure: dict[str, Any]) -> list[dict[str, Any]]:
    for key in (
        "frames",
        "cases",
        "subdiagrams",
        "event_frames",
        "diagram_frames",
    ):
        value = structure.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _frame_node_uids(frame: dict[str, Any]) -> list[str]:
    result: list[str] = []
    stack: list[object] = [frame]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            for key, item in value.items():
                if key.endswith("node_uids") and isinstance(item, list):
                    result.extend(_text(uid) for uid in item if _text(uid))
                elif key not in {"frames", "cases", "subdiagrams"}:
                    stack.append(item)
        elif isinstance(value, list):
            stack.extend(value)
    return list(dict.fromkeys(result))


def _displayed_frame_index(structure: dict[str, Any], frames: list[dict[str, Any]]) -> int:
    raw = structure.get("displayed_frame")
    if raw is None:
        raw = structure.get("active_frame")
    if raw is None:
        raw = structure.get("current_frame")
    try:
        index = int(raw)
    except (TypeError, ValueError):
        index = 0
    return max(0, min(index, max(0, len(frames) - 1)))


def _frame_label(frame: dict[str, Any], index: int) -> str:
    for key in ("name", "label", "selector_value", "event_name", "condition"):
        value = frame.get(key)
        if value not in (None, ""):
            return _text(value)
    if frame.get("is_default"):
        return "Default"
    return f"Frame {index}"


def select_displayed_structure_frames(vi: dict[str, Any]) -> dict[str, Any]:
    objects = vi.get("objects", []) or []
    object_by_id = {item.get("id"): item for item in objects if item.get("id")}
    ids_by_uid: dict[str, list[str]] = defaultdict(list)
    for item in objects:
        uid = _text(item.get("uid"))
        if uid:
            ids_by_uid[uid].append(_text(item.get("id")))

    inactive_ids: set[str] = set()
    active_ids: set[str] = set()
    structure_reports: list[dict[str, Any]] = []
    for structure_object in objects:
        structure = structure_object.get("structure")
        if not isinstance(structure, dict):
            continue
        frames = _frames_from_structure(structure)
        if len(frames) < 2:
            continue
        active_index = _displayed_frame_index(structure, frames)
        public_frames: list[dict[str, Any]] = []
        for index, frame in enumerate(frames):
            node_uids = _frame_node_uids(frame)
            object_ids = [
                object_id
                for uid in node_uids
                for object_id in ids_by_uid.get(uid, [])
                if object_id != structure_object.get("id")
            ]
            public_frames.append(
                {
                    "index": index,
                    "label": _frame_label(frame, index),
                    "is_active": index == active_index,
                    "node_uids": node_uids,
                    "object_ids": object_ids,
                }
            )
            if index == active_index:
                active_ids.update(object_ids)
            else:
                inactive_ids.update(object_ids)
        structure_object["structure_frames"] = public_frames
        structure_object["active_frame_index"] = active_index
        structure_object["active_frame_label"] = public_frames[active_index]["label"]
        structure_reports.append(
            {
                "object_id": structure_object.get("id"),
                "uid": structure_object.get("uid"),
                "active_frame_index": active_index,
                "frame_count": len(public_frames),
                "inactive_object_count": sum(
                    len(item["object_ids"])
                    for item in public_frames
                    if not item["is_active"]
                ),
            }
        )

    inactive_ids.difference_update(active_ids)
    changed = True
    while changed:
        changed = False
        for item in objects:
            item_id = _text(item.get("id"))
            owner_id = _text(item.get("owner_object_id"))
            parent_id = _text(item.get("parent_object_id"))
            if item_id in inactive_ids:
                continue
            if owner_id in inactive_ids or parent_id in inactive_ids:
                inactive_ids.add(item_id)
                changed = True

    for item in objects:
        item_id = _text(item.get("id"))
        if item_id not in inactive_ids:
            continue
        item["native_surface"] = item.get("surface")
        item["surface"] = "block-diagram-inactive"
        item["hidden_by_structure_frame"] = True

    visible_wires: list[dict[str, Any]] = []
    inactive_wires: list[dict[str, Any]] = []
    for wire in vi.get("wires", []) or []:
        terminal_ids = {
            _text(wire.get("source_terminal_id")),
            *(_text(value) for value in wire.get("target_terminal_ids") or []),
        }
        endpoint_ids = {
            _text(wire.get("source_object_id")),
            *(_text(value) for value in wire.get("target_object_ids") or []),
        }
        if (terminal_ids | endpoint_ids) & inactive_ids:
            wire["hidden_by_structure_frame"] = True
            inactive_wires.append(wire)
        else:
            visible_wires.append(wire)
    vi["wires"] = visible_wires
    if inactive_wires:
        vi["inactive_structure_frame_wires"] = inactive_wires

    visible_ids = {
        _text(item.get("id"))
        for item in objects
        if item.get("surface") != "block-diagram-inactive"
    }
    visible_wire_ids = {_text(wire.get("id")) for wire in visible_wires}
    for item in objects:
        item["terminal_ids"] = [
            value for value in item.get("terminal_ids") or [] if _text(value) in visible_ids
        ]
        item["linked_terminal_ids"] = [
            value
            for value in item.get("linked_terminal_ids") or []
            if _text(value) in visible_ids
        ]
        item["wire_ids"] = [
            value for value in item.get("wire_ids") or [] if _text(value) in visible_wire_ids
        ]

    vi.setdefault("surfaces", {})["block-diagram"] = [
        item.get("id")
        for item in objects
        if item.get("surface") == "block-diagram"
    ]
    block_nodes = [
        item
        for item in objects
        if item.get("surface") == "block-diagram" and item.get("category") == "node"
    ]
    terminals = [
        item
        for item in objects
        if item.get("surface") == "block-diagram" and item.get("category") == "terminal"
    ]
    summary = vi.setdefault("summary", {})
    summary["block_diagram_nodes"] = len(block_nodes)
    summary["terminals"] = len(terminals)
    summary["wires"] = len(visible_wires)
    summary["resolved_wires"] = sum(bool(wire.get("resolved")) for wire in visible_wires)
    summary["hidden_structure_frame_objects"] = len(inactive_ids)
    summary["hidden_structure_frame_wires"] = len(inactive_wires)
    vi.setdefault("integrity", {})["structure_frames"] = {
        "structures": structure_reports,
        "inactive_object_count": len(inactive_ids),
        "inactive_wire_count": len(inactive_wires),
        "active_frame_only": True,
    }
    return vi


def _postprocess(vi: dict[str, Any]) -> dict[str, Any]:
    vi = canonicalize_type_definitions(vi)
    vi = select_displayed_structure_frames(vi)
    try:
        from .semantic_integrity_v2 import finalize_semantic_vi

        vi = finalize_semantic_vi(vi)
    except (ImportError, TypeError, ValueError, KeyError):
        # The projection remains internally consistent without a second pass;
        # older deployments may not expose the v2 finalizer as a public API.
        pass
    return vi


def _patch_module(module_name: str) -> None:
    module = __import__(module_name, fromlist=["build_authoritative_semantic_vi"])
    original = getattr(module, "build_authoritative_semantic_vi", None)
    if not callable(original) or getattr(original, "_deep_audit_patch", False):
        return
    _ORIGINALS[module_name] = original

    def wrapped(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = original(*args, **kwargs)
        return _postprocess(result)

    wrapped._deep_audit_patch = True  # type: ignore[attr-defined]
    wrapped.__name__ = getattr(original, "__name__", "build_authoritative_semantic_vi")
    wrapped.__doc__ = getattr(original, "__doc__", None)
    setattr(module, "build_authoritative_semantic_vi", wrapped)


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    for module_name in (
        "app.semantic_integrity_runtime",
        "app.lvkit_semantic_runtime",
    ):
        try:
            _patch_module(module_name)
        except ImportError:
            continue
    service_graph = sys.modules.get("app.service_graph")
    if service_graph is not None:
        patched = sys.modules.get("app.semantic_integrity_runtime")
        function = getattr(patched, "build_authoritative_semantic_vi", None)
        if callable(function):
            setattr(service_graph, "build_authoritative_semantic_vi", function)


__all__ = [
    "canonicalize_type_definitions",
    "install",
    "select_displayed_structure_frames",
]
