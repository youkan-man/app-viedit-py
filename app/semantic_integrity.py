from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import re
from collections import defaultdict
from enum import Enum
from pathlib import Path
from typing import Any

_UNKNOWN_TYPES = {"", "unknown", "unresolved", "none", "null"}
_BRANCH_SUFFIX_RE = re.compile(r"^(?P<base>.+)_(?P<index>[1-9][0-9]*)$")

_NODE_CLASS_MAP: dict[str, tuple[str, str, str]] = {
    "fbox": ("formula", "Formula Node", "node"),
    "propnode": ("property-node", "Property Node", "node"),
    "invokenode": ("invoke-node", "Invoke Node", "node"),
    "eventregnode": ("register-events", "Register For Events", "node"),
    "eventdatanode": ("event-data-node", "Event Data Node", "node"),
    "abuild": ("build-array", "Build Array", "primitive"),
    "ainit": ("initialize-array", "Initialize Array", "primitive"),
    "aindx": ("index-array", "Index Array", "primitive"),
    "adelete": ("delete-array", "Delete From Array", "primitive"),
    "areplace": ("replace-array", "Replace Array Subset", "primitive"),
    "ainsert": ("insert-array", "Insert Into Array", "primitive"),
    "areshape": ("reshape-array", "Reshape Array", "primitive"),
    "printf": ("format-string", "Format Into String", "primitive"),
    "scanf": ("scan-string", "Scan From String", "primitive"),
    "concat": ("concatenate", "Concatenate", "primitive"),
    "subset": ("subset", "Array / String Subset", "primitive"),
    "mergeerrors": ("merge-errors", "Merge Errors", "primitive"),
    "nmux": ("bundle-by-name", "Bundle / Unbundle By Name", "node"),
    "mux": ("bundle", "Bundle", "node"),
    "demux": ("unbundle", "Unbundle", "node"),
    "ctlrefconst": ("control-reference", "Control Reference", "constant"),
    "gref": ("local-variable", "Local Variable", "node"),
    "statviref": ("static-vi-reference", "Static VI Reference", "constant"),
    "callbyrefnode": ("call-by-reference", "Call By Reference", "node"),
    "hiddenfbnode": ("feedback-node", "Feedback Node", "node"),
    "slavefbinputnode": ("feedback-node-input", "Feedback Node Input", "node"),
    "decomposeclusternode": ("decompose-cluster", "Decompose Cluster", "node"),
    "decomposearraynode": ("decompose-array", "Decompose Array", "node"),
    "decomposedatavalrefnode": ("decompose-data-value-reference", "Decompose Data Value Reference", "node"),
    "decomposematchnode": ("decompose-match", "Decompose / Recompose Match", "node"),
    "whileloop": ("structure-while-loop", "While Loop", "structure"),
    "forloop": ("structure-for-loop", "For Loop", "structure"),
    "casestruct": ("structure-case", "Case Structure", "structure"),
    "flatsequence": ("structure-flat-sequence", "Flat Sequence", "structure"),
    "seq": ("structure-sequence", "Sequence Structure", "structure"),
    "sequence": ("structure-sequence", "Sequence Structure", "structure"),
    "eventstruct": ("structure-event", "Event Structure", "structure"),
    "decomposerecomposestructure": (
        "structure-in-place",
        "In Place Element Structure",
        "structure",
    ),
}


def _key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _known_type(value: object) -> bool:
    return _key(value) not in _UNKNOWN_TYPES


def _stable_id(*parts: object) -> str:
    payload = "\x1f".join(str(part or "") for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _json_safe(value: object, depth: int = 0) -> Any:
    if depth > 14:
        return "…"
    if isinstance(value, Enum):
        return _json_safe(value.value, depth + 1)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return value.as_posix()
    if dataclasses.is_dataclass(value):
        return {
            field.name: _json_safe(getattr(value, field.name), depth + 1)
            for field in dataclasses.fields(value)
        }
    if isinstance(value, dict):
        return {
            str(key): _json_safe(item, depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item, depth + 1) for item in value]
    return str(value)


def type_payload(value: object | None, depth: int = 0) -> dict[str, Any] | None:
    """Convert either lvkit ParsedType or LVType into a JSON-safe type tree."""

    if value is None or depth > 12:
        return None
    kind_value = getattr(value, "kind", None)
    if isinstance(kind_value, Enum):
        kind_value = kind_value.value
    kind = str(kind_value or "unknown")
    name = (
        getattr(value, "type_name", None)
        or getattr(value, "underlying_type", None)
        or kind
    )
    payload: dict[str, Any] = {"kind": kind, "name": str(name or kind)}
    for attribute in (
        "typedef_name",
        "typedef_path",
        "ref_type",
        "classname",
        "description",
        "measure_flavor",
        "dimensions",
    ):
        item = getattr(value, attribute, None)
        if item is not None:
            payload[attribute] = _json_safe(item)

    fields = getattr(value, "fields", None) or []
    if fields:
        payload["fields"] = [
            {
                "name": str(getattr(field, "name", "field")),
                "type": type_payload(getattr(field, "type", None), depth + 1),
            }
            for field in fields
        ]
    element_type = getattr(value, "element_type", None)
    if element_type is not None:
        payload["element_type"] = type_payload(element_type, depth + 1)

    enum_values = getattr(value, "enum_values", None)
    if enum_values is None:
        enum_values = getattr(value, "values", None)
    if isinstance(enum_values, dict) and enum_values:
        payload["values"] = [
            {
                "name": str(name),
                "value": _json_safe(getattr(item, "value", item)),
                "description": _json_safe(getattr(item, "description", None)),
            }
            for name, item in enum_values.items()
        ]
    return payload


def _family_from_text(value: object) -> str:
    text = _key(value)
    if any(token in text for token in ("boolean", "bool")):
        return "boolean"
    if any(token in text for token in ("string", "char", "text")):
        return "string"
    if "path" in text:
        return "path"
    if any(token in text for token in ("refnum", "reference", "queue", "notifier", "semaphore")):
        return "refnum"
    if any(token in text for token in ("array",)):
        return "array"
    if any(token in text for token in ("cluster", "record", "waveform")):
        return "cluster"
    if any(token in text for token in ("enum", "ring")):
        return "ring"
    if any(
        token in text
        for token in (
            "numeric",
            "number",
            "num",
            "integer",
            "int",
            "uint",
            "float",
            "double",
            "single",
            "complex",
            "fixed",
            "dbl",
            "sgl",
            "i8",
            "i16",
            "i32",
            "i64",
            "u8",
            "u16",
            "u32",
            "u64",
        )
    ):
        return "numeric"
    return "unknown"


def type_family(payload: dict[str, Any] | None, fallback: object = "unknown") -> str:
    """Classify a type without treating every typedef reference as a cluster."""

    fallback_family = _family_from_text(fallback)
    if not payload:
        return fallback_family
    kind = _key(payload.get("kind"))
    if payload.get("fields"):
        return "cluster"
    if payload.get("element_type"):
        return "array"
    if payload.get("values"):
        return "ring"
    if kind == "cluster":
        return "cluster"
    if kind == "array":
        return "array"
    if kind in {"enum", "ring"}:
        return "ring"
    if kind in {"class", "refnum"}:
        return "refnum"

    textual = " ".join(
        str(payload.get(name) or "")
        for name in (
            "name",
            "display",
            "underlying_type",
            "ref_type",
            "classname",
            "typedef_name",
        )
    )
    inferred = _family_from_text(textual)
    if inferred != "unknown":
        return inferred

    # A typedef_ref only says that a named type exists. It may wrap a scalar,
    # enum, array, cluster, path, or refnum. Returning cluster here fabricated
    # cluster terminals and brown wires for scalar typedefs.
    if kind == "typedefref":
        return fallback_family if fallback_family != "cluster" else "unknown"
    return fallback_family


def _normalize_node_identity(item: dict[str, Any]) -> None:
    if item.get("surface") != "block-diagram" or item.get("category") != "node":
        return
    class_name = _key(
        item.get("class_name")
        or (item.get("semantic") or {}).get("node_type")
    )
    mapped = _NODE_CLASS_MAP.get(class_name)
    if not mapped:
        return
    kind, name, visual_kind = mapped
    previous_kind = str(item.get("kind") or "")
    previous_name = str(item.get("name") or "")
    item["kind"] = kind
    item["visual_kind"] = visual_kind
    if (
        not previous_name
        or _key(previous_name) in {class_name, _key(previous_kind), "primitive", "node"}
        or previous_kind.startswith("node-")
    ):
        item["name"] = name


def _resolve_constant_types(
    result: dict[str, Any],
    parsed: object | None,
) -> int:
    if parsed is None:
        return 0
    type_map = getattr(getattr(parsed, "metadata", None), "type_map", None) or {}
    if not type_map:
        return 0
    try:
        from lvkit.parser.type_mapping import resolve_type_rich
    except ImportError:
        return 0

    constants = {
        str(getattr(item, "uid", "") or ""): item
        for item in getattr(getattr(parsed, "block_diagram", None), "constants", ()) or ()
    }
    resolved = 0
    for item in result.get("objects", []):
        if item.get("kind") != "constant":
            continue
        constant = constants.get(str(item.get("uid") or ""))
        type_desc = getattr(constant, "type_desc", None) if constant else None
        if not type_desc:
            type_desc = (item.get("semantic") or {}).get("type_desc")
        if not type_desc:
            continue
        try:
            payload = type_payload(resolve_type_rich(str(type_desc), type_map))
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        if payload:
            item["type"] = payload
            item["data_type"] = type_family(payload, item.get("data_type"))
            resolved += 1
    return resolved


def _resolve_structure_terminal_owners(
    result: dict[str, Any],
    parsed: object | None,
) -> int:
    if parsed is None:
        return 0
    block = getattr(parsed, "block_diagram", None)
    srn_to_structure = getattr(block, "srn_to_structure", None) or {}
    if not srn_to_structure:
        return 0
    node_by_uid = {
        str(item.get("uid") or ""): item["id"]
        for item in result.get("objects", [])
        if item.get("surface") == "block-diagram"
        and item.get("category") == "node"
    }
    resolved = 0
    for item in result.get("objects", []):
        if item.get("category") != "terminal" or item.get("owner_object_id"):
            continue
        parent_uid = str((item.get("semantic") or {}).get("parent_uid") or "")
        structure_uid = str(srn_to_structure.get(parent_uid) or "")
        owner_id = node_by_uid.get(structure_uid)
        if owner_id:
            item["owner_object_id"] = owner_id
            item["owner_resolution"] = "srn_to_structure"
            resolved += 1
    return resolved


def _definition_path(value: object) -> str:
    text = str(value or "").replace("\\", "/").strip()
    text = re.sub(r"^/+", "", text)
    return text.casefold()


def _definition_name(value: object) -> str:
    text = str(value or "").replace("\\", "/").strip()
    return Path(text).name.casefold()


def _definition_aliases(definition: dict[str, Any]) -> list[str]:
    aliases: list[str] = []
    path = _definition_path(
        definition.get("recorded_path")
        or (definition.get("definition") or {}).get("typedef_path")
    )
    name = _definition_name(
        definition.get("name")
        or (definition.get("definition") or {}).get("typedef_name")
    )
    if path:
        aliases.append(f"path:{path}")
    if name:
        aliases.append(f"name:{name}")
    return aliases


def _payload_definition(payload: dict[str, Any] | None) -> tuple[str, str | None] | None:
    if not payload:
        return None
    complex_type = bool(
        payload.get("typedef_name")
        or payload.get("typedef_path")
        or payload.get("fields")
        or payload.get("element_type")
        or payload.get("values")
        or _key(payload.get("kind"))
        in {"typedefref", "cluster", "array", "enum", "ring", "class"}
    )
    if not complex_type:
        return None
    name = str(payload.get("typedef_name") or payload.get("name") or "Type Definition")
    path = str(payload.get("typedef_path") or "") or None
    return name, path


def _merge_type_definitions(
    result: dict[str, Any],
    object_index: dict[str, dict[str, Any]],
) -> tuple[int, int]:
    definitions = [copy.deepcopy(item) for item in result.get("type_definitions", [])]
    by_id = {str(item.get("id")): item for item in definitions if item.get("id")}

    for item in object_index.values():
        payload = item.get("type")
        requested = _payload_definition(payload)
        if not requested:
            continue
        name, recorded_path = requested
        existing_id = item.get("type_definition_id")
        if existing_id in by_id:
            sources = by_id[existing_id].setdefault("source_object_ids", [])
            if item["id"] not in sources:
                sources.append(item["id"])
            continue
        signature = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        definition_id = _stable_id("semantic-type", name, recorded_path, signature)
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
                "source": "semantic-integrity",
            },
        )
        if item["id"] not in definition["source_object_ids"]:
            definition["source_object_ids"].append(item["id"])
        item["type_definition_id"] = definition_id

    alias_to_id: dict[str, str] = {}
    canonical: dict[str, dict[str, Any]] = {}
    remap: dict[str, str] = {}
    merged_count = 0

    def strength(definition: dict[str, Any]) -> tuple[int, int, int, int]:
        return (
            int(bool(definition.get("definition"))),
            int(bool(definition.get("target_file"))),
            len(definition.get("source_object_ids") or []),
            int(definition.get("source") == "parsed-type"),
        )

    for definition in by_id.values():
        definition_id = str(definition["id"])
        aliases = _definition_aliases(definition)
        candidates = {alias_to_id[alias] for alias in aliases if alias in alias_to_id}
        canonical_id = next(iter(candidates), None)
        if canonical_id is None:
            canonical_id = definition_id
            canonical[canonical_id] = definition
        else:
            target = canonical[canonical_id]
            if strength(definition) > strength(target):
                canonical[canonical_id] = definition
                target, definition = definition, target
                canonical[canonical_id]["id"] = canonical_id
            target = canonical[canonical_id]
            for key in ("definition", "target_file", "recorded_path", "name", "kind"):
                if not target.get(key) and definition.get(key):
                    target[key] = definition[key]
            sources = target.setdefault("source_object_ids", [])
            for source_id in definition.get("source_object_ids") or []:
                if source_id not in sources:
                    sources.append(source_id)
            target["available"] = bool(target.get("definition") or target.get("target_file"))
            merged_count += 1
        remap[definition_id] = canonical_id
        for alias in aliases:
            alias_to_id[alias] = canonical_id

    for item in object_index.values():
        definition_id = item.get("type_definition_id")
        if definition_id in remap:
            item["type_definition_id"] = remap[definition_id]

    result["type_definitions"] = sorted(
        canonical.values(),
        key=lambda item: (str(item.get("name") or "").casefold(), str(item["id"])),
    )
    unattached = sum(
        not definition.get("source_object_ids")
        for definition in result["type_definitions"]
    )
    return merged_count, unattached


def _anchor_bounds(
    item: dict[str, Any],
    owner: dict[str, Any],
    *,
    source_space: str,
) -> bool:
    bounds = item.get("bounds")
    owner_bounds = owner.get("bounds")
    if not isinstance(bounds, dict) or not isinstance(owner_bounds, dict):
        return False
    if bounds.get("relative_to_object_id") == owner.get("id"):
        return False
    try:
        raw_x = float(bounds.get("x", 0)) - float(owner_bounds.get("x", 0))
        raw_y = float(bounds.get("y", 0)) - float(owner_bounds.get("y", 0))
        owner_width = max(1.0, float(owner_bounds.get("width", 1)))
        owner_height = max(1.0, float(owner_bounds.get("height", 1)))
    except (TypeError, ValueError):
        return False
    bounds.update(
        {
            "relative_to_object_id": owner["id"],
            "raw_x": raw_x,
            "raw_y": raw_y,
            "anchor_x": max(0.0, min(1.0, raw_x / owner_width)),
            "anchor_y": max(0.0, min(1.0, raw_y / owner_height)),
            "source_coordinate_space": bounds.get("source_coordinate_space")
            or source_space,
        }
    )
    return True


def _native_signal_uid(raw_uid: object) -> tuple[str, int]:
    text = str(raw_uid or "")
    match = _BRANCH_SUFFIX_RE.fullmatch(text)
    if not match:
        return text, 0
    return match.group("base"), int(match.group("index"))


def _first_known_family(values: list[object]) -> tuple[str, list[str]]:
    known: list[str] = []
    for value in values:
        family = _family_from_text(value)
        if family != "unknown" and family not in known:
            known.append(family)
    return (known[0] if len(known) == 1 else "conflict" if known else "unknown", known)


def _sanitize_and_rebuild_relationships(
    result: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], int, int]:
    objects = [item for item in result.get("objects", []) if item.get("id")]
    object_index = {str(item["id"]): item for item in objects}
    dangling_removed = 0

    valid_wires: list[dict[str, Any]] = []
    for wire in result.get("wires", []):
        source = wire.get("source_terminal_id")
        targets = [
            target
            for target in wire.get("target_terminal_ids") or []
            if target in object_index
        ]
        if source not in object_index or not targets:
            dangling_removed += 1
            continue
        wire["target_terminal_ids"] = targets
        wire["terminal_ids"] = [source, *targets]
        valid_wires.append(wire)
    result["wires"] = valid_wires
    wire_ids = {str(item.get("id")) for item in valid_wires if item.get("id")}

    for item in objects:
        for key in ("owner_object_id", "linked_object_id", "parent_object_id"):
            value = item.get(key)
            if value and value not in object_index:
                item[key] = None
                dangling_removed += 1
        item["terminal_ids"] = []
        item["linked_terminal_ids"] = []
        item["wire_ids"] = []
        item["child_object_ids"] = []

    for item in objects:
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

    for item in objects:
        item["terminal_ids"].sort(
            key=lambda terminal_id: object_index[terminal_id].get("port_index", 10**9)
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
        target_terminals = [object_index[item] for item in wire["target_terminal_ids"]]
        source_object_id = (
            source_terminal.get("linked_object_id")
            or source_terminal.get("owner_object_id")
        )
        target_object_ids = [
            terminal.get("linked_object_id") or terminal.get("owner_object_id")
            for terminal in target_terminals
        ]
        target_object_ids = [item for item in target_object_ids if item in object_index]
        wire["source_object_id"] = source_object_id
        wire["target_object_ids"] = target_object_ids
        wire["endpoint_object_ids"] = [
            item
            for item in [source_object_id, *target_object_ids]
            if item in object_index
        ]
        for terminal_id in wire["terminal_ids"]:
            if wire["id"] not in object_index[terminal_id]["wire_ids"]:
                object_index[terminal_id]["wire_ids"].append(wire["id"])
        for object_id in wire["endpoint_object_ids"]:
            if wire["id"] not in object_index[object_id]["wire_ids"]:
                object_index[object_id]["wire_ids"].append(wire["id"])

    result["objects"] = objects
    return object_index, dangling_removed, len(wire_ids)


def _wire_integrity(
    result: dict[str, Any],
    object_index: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    warnings = result.setdefault("warnings", [])
    type_conflicts = 0
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for wire in result.get("wires", []):
        signal_uid, branch_index = _native_signal_uid(wire.get("native_uid"))
        source_terminal = object_index[wire["source_terminal_id"]]
        target_terminals = [object_index[item] for item in wire["target_terminal_ids"]]
        families = [
            source_terminal.get("data_type"),
            *(item.get("data_type") for item in target_terminals),
        ]
        family, known = _first_known_family(families)
        wire["data_type"] = family
        if family == "conflict":
            type_conflicts += 1
            wire["type_conflict"] = known
            warnings.append(
                f"配線 {wire.get('name') or wire.get('id')} の端子型が一致しません: {', '.join(known)}"
            )
        type_payloads = [
            source_terminal.get("type"),
            *(item.get("type") for item in target_terminals),
        ]
        wire["type"] = next((item for item in type_payloads if item), None)
        definition_ids = [
            item
            for item in [
                source_terminal.get("type_definition_id"),
                *(terminal.get("type_definition_id") for terminal in target_terminals),
            ]
            if item
        ]
        unique_definitions = list(dict.fromkeys(definition_ids))
        wire["type_definition_id"] = unique_definitions[0] if unique_definitions else None
        if len(unique_definitions) > 1:
            wire["type_definition_conflict_ids"] = unique_definitions
        wire["native_signal_uid"] = signal_uid
        wire["branch_index"] = branch_index
        groups[(source_terminal["id"], signal_uid)].append(wire)

    nets: list[dict[str, Any]] = []
    for (source_terminal_id, signal_uid), branches in groups.items():
        branch_ids = [item["id"] for item in branches]
        net_id = _stable_id("labview-net", source_terminal_id, signal_uid, *branch_ids)
        targets = [
            target
            for branch in branches
            for target in branch.get("target_terminal_ids") or []
        ]
        families = [branch.get("data_type") for branch in branches]
        family, known = _first_known_family(families)
        definition_ids = list(
            dict.fromkeys(
                branch.get("type_definition_id")
                for branch in branches
                if branch.get("type_definition_id")
            )
        )
        for branch in branches:
            branch["net_id"] = net_id
            branch["branch_count"] = len(branches)
        nets.append(
            {
                "id": net_id,
                "native_signal_uid": signal_uid,
                "source_terminal_id": source_terminal_id,
                "target_terminal_ids": targets,
                "branch_ids": branch_ids,
                "branch_count": len(branches),
                "data_type": family,
                "type_conflict": known if family == "conflict" else None,
                "type_definition_id": definition_ids[0] if len(definition_ids) == 1 else None,
                "type_definition_conflict_ids": definition_ids if len(definition_ids) > 1 else [],
            }
        )
    result["nets"] = nets
    return nets, type_conflicts


def _propagate_object_types(
    result: dict[str, Any],
    object_index: dict[str, dict[str, Any]],
) -> int:
    changed = 0
    for _ in range(3):
        pass_changed = 0
        for wire in result.get("wires", []):
            if wire.get("data_type") in {None, "unknown", "conflict"}:
                continue
            for object_id in wire.get("endpoint_object_ids") or []:
                item = object_index.get(object_id)
                if not item or _known_type(item.get("data_type")):
                    continue
                item["data_type"] = wire["data_type"]
                if not item.get("type") and wire.get("type"):
                    item["type"] = wire["type"]
                if not item.get("type_definition_id") and wire.get("type_definition_id"):
                    item["type_definition_id"] = wire["type_definition_id"]
                pass_changed += 1
        changed += pass_changed
        if not pass_changed:
            break
    return changed


def _recompute_summary(
    result: dict[str, Any],
    object_index: dict[str, dict[str, Any]],
    *,
    unresolved_extra: int,
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
            "wires": len(wires),
            "wire_nets": len(result.get("nets", [])),
            "resolved_wires": sum(bool(item.get("resolved", True)) for item in wires),
            "unresolved_wires": max(0, int(summary.get("unresolved_wires", 0)))
            + unresolved_extra,
            "numeric_controls": sum(item.get("data_type") == "numeric" for item in controls),
            "numeric_indicators": sum(item.get("data_type") == "numeric" for item in indicators),
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
            item["id"] for item in objects if item.get("surface") == "front-panel"
        ],
        "block-diagram": [
            item["id"]
            for item in objects
            if item.get("surface") == "block-diagram"
        ],
    }
    result["hierarchy"] = {
        "roots": [item["id"] for item in objects if not item.get("parent_object_id")],
        "containers": [item["id"] for item in objects if item.get("child_object_ids")],
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
    """Repair cross-object invariants before the editor receives the model.

    The LabVIEW parser remains the source of truth. This pass does not infer new
    dataflow edges; it normalizes ownership, types, branch/net identity, and
    stale fallback metadata so the UI cannot display dangling or contradictory
    objects.
    """

    result = copy.deepcopy(vi)
    result.setdefault("objects", [])
    result.setdefault("wires", [])
    result.setdefault("warnings", [])

    constants_typed = _resolve_constant_types(result, parsed)
    structure_owners = _resolve_structure_terminal_owners(result, parsed)
    for item in result["objects"]:
        _normalize_node_identity(item)
        payload = item.get("type")
        item["data_type"] = type_family(payload, item.get("data_type"))

    object_index, dangling_removed, _wire_id_count = _sanitize_and_rebuild_relationships(result)

    owner_anchors = 0
    hierarchy_anchors = 0
    for item in object_index.values():
        owner_id = item.get("owner_object_id")
        if owner_id and owner_id in object_index:
            owner_anchors += int(
                _anchor_bounds(
                    item,
                    object_index[owner_id],
                    source_space="absolute-owner-anchored",
                )
            )
        parent_id = item.get("parent_object_id")
        if parent_id and parent_id in object_index:
            hierarchy_anchors += int(
                _anchor_bounds(
                    item,
                    object_index[parent_id],
                    source_space="absolute-parent-anchored",
                )
            )

    merged_definitions, unattached_definitions = _merge_type_definitions(
        result, object_index
    )
    nets, type_conflicts = _wire_integrity(result, object_index)
    propagated_types = _propagate_object_types(result, object_index)
    # Propagation can attach a known type definition to a constant or generic
    # operation. Run the registry merge once more to canonicalize those IDs.
    merged_again, unattached_definitions = _merge_type_definitions(result, object_index)
    merged_definitions += merged_again

    warnings = []
    for warning in result.get("warnings", []):
        text = str(warning).strip()
        if text and text not in warnings:
            warnings.append(text)
    result["warnings"] = warnings
    _recompute_summary(
        result,
        object_index,
        unresolved_extra=dangling_removed,
    )
    result["integrity"] = {
        "version": 1,
        "dangling_wires_removed": dangling_removed,
        "structure_terminal_owners_resolved": structure_owners,
        "owner_anchors_added": owner_anchors,
        "hierarchy_anchors_added": hierarchy_anchors,
        "constant_types_resolved": constants_typed,
        "types_propagated": propagated_types,
        "type_conflicts": type_conflicts,
        "type_definitions_merged": merged_definitions,
        "unattached_type_definitions": unattached_definitions,
        "wire_nets": len(nets),
    }
    result["version"] = max(4, int(result.get("version") or 1))
    return result
