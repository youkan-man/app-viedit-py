from __future__ import annotations

import copy
import dataclasses
import json
import re
from collections import defaultdict
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

from .component_model import DatasetComponentModel, short_hash

_DIAGRAM_SUFFIX = re.compile(r"_(BDH[bc])\.xml$", re.IGNORECASE)
_FRONT_PANEL_SUFFIXES = ("_FPHb.xml", "_FPHc.xml")

_OPERATION_NAMES = {
    "add": "加算",
    "subtract": "減算",
    "multiply": "乗算",
    "divide": "除算",
    "and": "AND",
    "or": "OR",
    "xor": "XOR",
    "unsupported": "Compound Arithmetic",
}
_OPERATION_SYMBOLS = {
    "add": "+",
    "subtract": "−",
    "multiply": "×",
    "divide": "÷",
    "and": "∧",
    "or": "∨",
    "xor": "⊻",
}
_STRUCTURE_LABELS = {
    "whileLoop": "While Loop",
    "forLoop": "For Loop",
    "case": "Case Structure",
    "sequence": "Sequence Structure",
    "flat-sequence": "Flat Sequence",
    "in-place": "In Place Element Structure",
    "disable": "Disable Structure",
    "event": "Event Structure",
}


class _ComponentIndex:
    def __init__(self, model: DatasetComponentModel) -> None:
        self._by_file_uid: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        self._by_uid: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for component in model.components.values():
            uid = str(component.get("uid") or "").strip()
            if not uid:
                continue
            file_name = _path_key(component.get("file"))
            for key in _uid_keys(uid):
                self._by_file_uid[(file_name, key)].append(component)
                self._by_uid[key].append(component)

    def find(
        self,
        uid: str | None,
        file_hint: str | Path | None,
        *,
        class_hint: str | None = None,
        kind_hint: str | None = None,
    ) -> dict[str, Any] | None:
        if not uid:
            return None
        file_key = _path_key(file_hint)
        candidates: list[dict[str, Any]] = []
        for uid_key in _uid_keys(uid):
            candidates.extend(self._by_file_uid.get((file_key, uid_key), ()))
        if not candidates:
            global_candidates: list[dict[str, Any]] = []
            for uid_key in _uid_keys(uid):
                global_candidates.extend(self._by_uid.get(uid_key, ()))
            unique = {item["id"]: item for item in global_candidates}
            if len(unique) == 1:
                candidates = list(unique.values())
        if not candidates:
            return None

        class_key = _key(class_hint)
        kind_key = _key(kind_hint)

        def score(component: dict[str, Any]) -> tuple[int, int, int, str]:
            component_class = _key(component.get("class_name"))
            component_kind = _key(component.get("kind"))
            return (
                int(bool(class_key and component_class == class_key)),
                int(bool(kind_key and component_kind == kind_key)),
                int(component.get("role") == "component"),
                str(component.get("id")),
            )

        return max({item["id"]: item for item in candidates}.values(), key=score)


def _key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _path_key(value: object) -> str:
    return str(value or "").replace("\\", "/").strip("/").casefold()


def _uid_keys(value: object) -> set[str]:
    text = str(value or "").strip()
    if not text:
        return set()
    keys = {text.casefold()}
    try:
        base = 16 if text.lower().startswith("0x") or re.search(r"[a-f]", text, re.I) else 10
        number = int(text, base)
        keys.update({str(number), f"0x{number:x}", f"{number:x}"})
    except ValueError:
        pass
    return keys


def _relative(dataset: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(dataset.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _candidate_main_xml(dataset: Path, bd_path: Path, explicit: Path | None) -> Path | None:
    if explicit and explicit.exists():
        return explicit
    base_name = _DIAGRAM_SUFFIX.sub("", bd_path.name)
    direct = bd_path.with_name(f"{base_name}.xml")
    if direct.exists():
        return direct
    candidates = [
        path
        for path in dataset.rglob("*.xml")
        if not _DIAGRAM_SUFFIX.search(path.name)
        and not re.search(r"_FPH[bc]\.xml$", path.name, re.IGNORECASE)
    ]
    return min(candidates, key=lambda path: (len(path.parts), path.as_posix())) if candidates else None


def _discover_primary_document(
    dataset: Path,
    main_xml: Path | None,
) -> tuple[Path, Path | None, Path | None] | None:
    diagrams = sorted(
        (path for path in dataset.rglob("*.xml") if _DIAGRAM_SUFFIX.search(path.name)),
        key=lambda path: (len(path.parts), path.as_posix()),
    )
    if not diagrams:
        return None

    if main_xml:
        stem = main_xml.stem.casefold()
        matching = [path for path in diagrams if _DIAGRAM_SUFFIX.sub("", path.name).casefold() == stem]
        if matching:
            diagrams = matching + [path for path in diagrams if path not in matching]
    bd_path = diagrams[0]
    base_name = _DIAGRAM_SUFFIX.sub("", bd_path.name)
    fp_path = next(
        (
            bd_path.with_name(f"{base_name}{suffix}")
            for suffix in _FRONT_PANEL_SUFFIXES
            if bd_path.with_name(f"{base_name}{suffix}").exists()
        ),
        None,
    )
    return bd_path, fp_path, _candidate_main_xml(dataset, bd_path, main_xml)


def _enum_value(value: object) -> object:
    return value.value if isinstance(value, Enum) else value


def _json_safe(value: object, depth: int = 0) -> Any:
    if depth > 18:
        return "…"
    value = _enum_value(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return value.as_posix()
    if dataclasses.is_dataclass(value):
        return {
            field.name: _json_safe(getattr(value, field.name), depth + 1)
            for field in dataclasses.fields(value)
            if field.name not in {"wire_style"}
        }
    if isinstance(value, dict):
        return {str(key): _json_safe(item, depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item, depth + 1) for item in value]
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump(mode="json"), depth + 1)
    return str(value)


def _type_payload(type_value: object | None, depth: int = 0) -> dict[str, Any] | None:
    if type_value is None or depth > 12:
        return None
    kind_value = _enum_value(getattr(type_value, "kind", None))
    kind = str(kind_value or "unknown")
    type_name = (
        getattr(type_value, "type_name", None)
        or getattr(type_value, "underlying_type", None)
        or kind
    )
    payload: dict[str, Any] = {
        "kind": kind,
        "name": str(type_name or kind),
    }
    for attribute in (
        "typedef_name",
        "typedef_path",
        "ref_type",
        "classname",
        "description",
        "measure_flavor",
        "dimensions",
    ):
        item = getattr(type_value, attribute, None)
        if item is not None:
            payload[attribute] = _json_safe(item)

    fields = getattr(type_value, "fields", None) or []
    if fields:
        payload["fields"] = [
            {
                "name": str(getattr(field, "name", "field")),
                "type": _type_payload(getattr(field, "type", None), depth + 1),
            }
            for field in fields
        ]
    element_type = getattr(type_value, "element_type", None)
    if element_type is not None:
        payload["element_type"] = _type_payload(element_type, depth + 1)

    enum_values = getattr(type_value, "enum_values", None)
    if enum_values is None:
        enum_values = getattr(type_value, "values", None)
    if enum_values:
        payload["values"] = [
            {
                "name": str(name),
                "value": _json_safe(getattr(value, "value", value)),
                "description": _json_safe(getattr(value, "description", None)),
            }
            for name, value in enum_values.items()
        ]
    descriptor = getattr(type_value, "type_descriptor", None)
    if callable(descriptor):
        try:
            payload["display"] = str(descriptor())
        except (TypeError, ValueError):
            pass
    return payload


def _type_family(payload: dict[str, Any] | None, fallback: str = "unknown") -> str:
    if not payload:
        return fallback
    kind = _key(payload.get("kind"))
    name = _key(payload.get("name"))
    ref_type = _key(payload.get("ref_type"))
    if kind in {"cluster", "typedefref", "class"} or payload.get("fields"):
        return "cluster" if kind != "class" else "refnum"
    if kind == "array" or payload.get("element_type"):
        return "array"
    if kind in {"enum", "ring"}:
        return "ring"
    if any(token in name for token in ("bool", "boolean")):
        return "boolean"
    if any(token in name for token in ("string", "char", "text")):
        return "string"
    if "path" in name:
        return "path"
    if ref_type or any(token in name for token in ("refnum", "reference")):
        return "refnum"
    if any(token in name for token in ("array",)):
        return "array"
    if any(token in name for token in ("cluster", "record")):
        return "cluster"
    if any(
        token in name
        for token in (
            "num",
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
    return fallback


class _TypeRegistry:
    def __init__(self, dataset: Path) -> None:
        self.dataset = dataset
        self.files = [path for path in dataset.rglob("*") if path.is_file()]
        self.definitions: dict[str, dict[str, Any]] = {}

    def _resolve_file(self, name: str | None, recorded_path: str | None) -> str | None:
        normalized_path = _path_key(recorded_path)
        normalized_name = Path(name or recorded_path or "").name.casefold()
        exact = [
            path
            for path in self.files
            if normalized_path
            and (
                _path_key(_relative(self.dataset, path)) == normalized_path
                or _path_key(_relative(self.dataset, path)).endswith(f"/{normalized_path}")
            )
        ]
        if exact:
            return _relative(self.dataset, exact[0])
        by_name = [path for path in self.files if path.name.casefold() == normalized_name]
        return _relative(self.dataset, by_name[0]) if len(by_name) == 1 else None

    def register(
        self,
        payload: dict[str, Any] | None,
        source_object_id: str,
    ) -> str | None:
        if not payload:
            return None
        complex_type = bool(
            payload.get("typedef_name")
            or payload.get("typedef_path")
            or payload.get("fields")
            or payload.get("element_type")
            or payload.get("values")
            or _key(payload.get("kind")) in {"typedefref", "cluster", "array", "enum", "ring", "class"}
        )
        if not complex_type:
            return None
        name = str(payload.get("typedef_name") or payload.get("name") or "Type Definition")
        recorded_path = str(payload.get("typedef_path") or "") or None
        signature = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        definition_id = short_hash("typedef", name, recorded_path or "", signature)
        definition = self.definitions.setdefault(
            definition_id,
            {
                "id": definition_id,
                "name": name,
                "kind": payload.get("kind") or "unknown",
                "recorded_path": recorded_path,
                "target_file": self._resolve_file(name, recorded_path),
                "available": False,
                "definition": payload,
                "source_object_ids": [],
                "source": "parsed-type",
            },
        )
        definition["available"] = bool(definition.get("target_file") or payload)
        if source_object_id not in definition["source_object_ids"]:
            definition["source_object_ids"].append(source_object_id)
        return definition_id

    def add_dependencies(self, dependencies: list[object]) -> None:
        for dependency in dependencies:
            name = str(getattr(dependency, "name", "") or "")
            if not name.lower().endswith((".ctl", ".ctt")):
                continue
            get_relative = getattr(dependency, "get_relative_path", None)
            recorded_path = str(get_relative()) if callable(get_relative) else None
            definition_id = short_hash("typedef-dependency", name, recorded_path or "")
            target_file = self._resolve_file(name, recorded_path)
            self.definitions.setdefault(
                definition_id,
                {
                    "id": definition_id,
                    "name": name,
                    "kind": "typedef_ref",
                    "recorded_path": recorded_path,
                    "target_file": target_file,
                    "available": bool(target_file),
                    "definition": None,
                    "source_object_ids": [],
                    "source": "link-table",
                },
            )

    def public(self) -> list[dict[str, Any]]:
        return sorted(
            self.definitions.values(),
            key=lambda item: (str(item.get("name")).casefold(), item["id"]),
        )


def _rect_bounds(rect: object | None) -> dict[str, float] | None:
    if not isinstance(rect, (list, tuple)) or len(rect) != 4:
        return None
    left, top, right, bottom = (float(value) for value in rect)
    return {
        "x": left,
        "y": top,
        "width": max(1.0, right - left),
        "height": max(1.0, bottom - top),
    }


def _fp_bounds(rect: object | None) -> dict[str, float] | None:
    if not isinstance(rect, (list, tuple)) or len(rect) != 4:
        return None
    top, left, bottom, right = (float(value) for value in rect)
    return {
        "x": left,
        "y": top,
        "width": max(1.0, right - left),
        "height": max(1.0, bottom - top),
    }


def _component_bounds(
    component: dict[str, Any] | None,
    geometry: dict[str, float] | None,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if geometry is None and fallback:
        geometry = {
            key: float(fallback.get(key, 0))
            for key in ("x", "y", "width", "height")
        }
    if geometry is None and component and component.get("bounds"):
        source = component["bounds"]
        geometry = {
            key: float(source.get(key, 0))
            for key in ("x", "y", "width", "height")
        }
    if geometry is None:
        return None
    result: dict[str, Any] = dict(geometry)
    source = component.get("bounds") if component else None
    if source:
        result.update(
            {
                "source_property_id": source.get("property_id"),
                "source_property": source.get("name"),
                "storage_order": source.get("storage_order", "top,left,bottom,right"),
            }
        )
    elif fallback:
        for key in (
            "source_property_id",
            "source_property",
            "storage_order",
            "source_coordinate_space",
            "relative_to_object_id",
            "raw_x",
            "raw_y",
        ):
            if fallback.get(key) is not None:
                result[key] = fallback[key]
    return result


def _object_source(component: dict[str, Any] | None, file_hint: str) -> dict[str, str]:
    return {
        "file": str(component.get("file") if component else file_hint),
        "xml_path": str(component.get("path") if component else ""),
    }


def _synthetic_id(document_id: str, category: str, uid: str) -> str:
    return short_hash("lvkit-semantic", document_id, category, uid)


@lru_cache(maxsize=1)
def _primitive_catalog() -> dict[str, dict[str, Any]]:
    try:
        from lvkit._data import data_dir

        path = data_dir() / "primitives.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        primitives = payload.get("primitives", {})
        return primitives if isinstance(primitives, dict) else {}
    except (ImportError, OSError, ValueError, TypeError):
        return {}


def _node_kind_name(node: object) -> tuple[str, str, str]:
    node_type = str(getattr(node, "node_type", "unknown") or "unknown")
    operation = str(getattr(node, "operation", "") or "")
    if node_type == "cpdArith" and operation:
        return operation, _OPERATION_NAMES.get(operation, operation), _OPERATION_SYMBOLS.get(operation, "◇")
    if node_type == "prim":
        catalog = _primitive_catalog()
        primitive = None
        for key in (getattr(node, "prim_res_id", None), getattr(node, "prim_index", None)):
            if key is not None and str(key) in catalog:
                primitive = catalog[str(key)]
                break
        primitive_name = str((primitive or {}).get("name") or "Primitive")
        return f"primitive-{_key(primitive_name) or 'unknown'}", primitive_name, "ƒ"
    if node_type in {"iUse", "polyIUse", "dynIUse", "callParentDynIUse"}:
        name = str(getattr(node, "vi_path", "") or getattr(node, "name", "") or "SubVI")
        return "subvi", name, "VI"
    mapping = {
        "aBuild": ("build-array", "Build Array", "[]"),
        "aIndx": ("index-array", "Index Array", "[i]"),
        "nMux": ("bundle", "Bundle / Unbundle", "{}"),
        "select": ("select", "Select", "?"),
        "formulaNode": ("formula", "Formula Node", "fx"),
        "propertyNode": ("property-node", "Property Node", "P"),
        "invokeNode": ("invoke-node", "Invoke Node", "I"),
    }
    if node_type in mapping:
        return mapping[node_type]
    display = str(getattr(node, "name", "") or node_type)
    return f"node-{_key(node_type) or 'unknown'}", display, "◇"


def _structure_records(block_diagram: object) -> dict[str, tuple[str, str, str, object]]:
    result: dict[str, tuple[str, str, str, object]] = {}
    collections = (
        ("loops", "structure-loop"),
        ("case_structures", "structure-case"),
        ("flat_sequences", "structure-sequence"),
        ("decompose_structures", "structure-in-place"),
        ("disable_structures", "structure-disable"),
        ("event_structures", "structure-event"),
    )
    for attribute, kind in collections:
        for structure in getattr(block_diagram, attribute, ()) or ():
            uid = str(getattr(structure, "uid", "") or "")
            if not uid:
                continue
            subtype = str(
                getattr(structure, "loop_type", "")
                or getattr(structure, "kind", "")
                or kind.removeprefix("structure-")
            )
            name = _STRUCTURE_LABELS.get(subtype, _STRUCTURE_LABELS.get(kind.removeprefix("structure-"), subtype))
            result[uid] = (kind, name, "▣", structure)
    return result


def _flatten_controls(controls: list[object]) -> list[tuple[object, str | None]]:
    flattened: list[tuple[object, str | None]] = []
    seen: set[str] = set()

    def visit(control: object, parent_uid: str | None) -> None:
        uid = str(getattr(control, "uid", "") or "")
        if not uid or uid in seen:
            return
        seen.add(uid)
        flattened.append((control, parent_uid))
        for child in getattr(control, "children", ()) or ():
            visit(child, uid)

    for control in controls:
        visit(control, None)
    return flattened


def _copy_front_panel(
    fallback_vi: dict[str, Any],
    parsed: object,
    *,
    index: _ComponentIndex,
    fp_file: str,
    document_id: str,
    type_registry: _TypeRegistry,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    existing = {
        (str(item.get("uid") or ""), item.get("surface")): copy.deepcopy(item)
        for item in fallback_vi.get("objects", [])
        if item.get("surface") == "front-panel"
    }
    fp_term_by_dco = {
        str(term.fp_dco_uid): term
        for term in getattr(parsed.block_diagram, "fp_terminals", ()) or ()
    }
    flattened = _flatten_controls(list(getattr(parsed.front_panel, "controls", ()) or ()))
    objects: list[dict[str, Any]] = []
    by_uid: dict[str, str] = {}
    parsed_uids: set[str] = set()

    for control, parent_uid in flattened:
        uid = str(getattr(control, "uid", "") or "")
        parsed_uids.add(uid)
        item = existing.get((uid, "front-panel"))
        component = index.find(uid, fp_file, class_hint="fPDCO", kind_hint="control")
        object_id = str((item or {}).get("id") or (component or {}).get("id") or _synthetic_id(document_id, "front-control", uid))
        bounds = _component_bounds(
            component,
            _fp_bounds(getattr(control, "bounds", None)),
            (item or {}).get("bounds"),
        )
        fp_terminal = fp_term_by_dco.get(uid)
        type_payload = _type_payload(getattr(fp_terminal, "parsed_type", None))
        control_type = str(getattr(control, "control_type", "") or "unknown")
        family = _type_family(type_payload, _type_family({"name": control_type}))
        indicator = bool(getattr(control, "is_indicator", False))
        item = {
            **(item or {}),
            "id": object_id,
            "component_id": (component or {}).get("id") or (item or {}).get("component_id"),
            "surface": "front-panel",
            "kind": f"{family}-{'indicator' if indicator else 'control'}",
            "category": "indicator" if indicator else "control",
            "name": str(getattr(control, "name", "") or (item or {}).get("name") or control_type),
            "symbol": "OUT" if indicator else "IN",
            "class_name": str((component or {}).get("class_name") or "fPDCO"),
            "widget": control_type,
            "uid": uid,
            "bounds": bounds,
            "positioned": bool(bounds),
            "movable": bool(bounds and bounds.get("source_property_id")),
            "resizable": bool(bounds and bounds.get("source_property_id")),
            "terminal_ids": [],
            "linked_terminal_ids": [],
            "wire_ids": [],
            "parent_object_id": None,
            "child_object_ids": [],
            "data_type": family,
            "visual_kind": family,
            "type": type_payload,
            "semantic_source": "lvkit",
            "parser_confidence": "exact",
            "source": _object_source(component, fp_file),
        }
        type_definition_id = type_registry.register(type_payload, object_id)
        if type_definition_id:
            item["type_definition_id"] = type_definition_id
        objects.append(item)
        by_uid[uid] = object_id
        item["_parent_uid"] = parent_uid

    for (uid, _surface), item in existing.items():
        if uid in parsed_uids:
            continue
        item.update(
            {
                "linked_terminal_ids": [],
                "wire_ids": [],
                "semantic_source": "component-model-front-panel",
                "parser_confidence": "fallback",
            }
        )
        objects.append(item)
        by_uid[uid] = item["id"]

    object_index = {item["id"]: item for item in objects}
    for item in objects:
        parent_uid = item.pop("_parent_uid", None)
        parent_id = by_uid.get(parent_uid or "")
        if not parent_id or parent_id == item["id"]:
            continue
        item["parent_object_id"] = parent_id
        parent = object_index[parent_id]
        if item["id"] not in parent["child_object_ids"]:
            parent["child_object_ids"].append(item["id"])
    return objects, by_uid


def _layout_rect(layout: object | None, uid: str) -> dict[str, float] | None:
    return _rect_bounds((getattr(layout, "node_bounds", {}) or {}).get(uid))


def _terminal_bounds(
    layout: object | None,
    uid: str,
    component: dict[str, Any] | None,
) -> dict[str, Any] | None:
    rectangle = _layout_rect(layout, uid)
    center = (getattr(layout, "terminal_centers", {}) or {}).get(uid) if layout else None
    if rectangle is None and center is not None:
        width = float((component or {}).get("bounds", {}).get("width", 8) or 8)
        height = float((component or {}).get("bounds", {}).get("height", 8) or 8)
        rectangle = {
            "x": float(center[0]) - width / 2,
            "y": float(center[1]) - height / 2,
            "width": max(4, width),
            "height": max(4, height),
        }
    return _component_bounds(component, rectangle)


def _endpoint_object_id(terminal: dict[str, Any]) -> str | None:
    return terminal.get("linked_object_id") or terminal.get("owner_object_id")


def _safe_structure(value: object) -> dict[str, Any]:
    payload = _json_safe(value)
    return payload if isinstance(payload, dict) else {"value": payload}


def _node_payload(
    node: object,
    *,
    document_id: str,
    bd_file: str,
    component_index: _ComponentIndex,
    layout: object | None,
    subvi_names: dict[str, str],
) -> dict[str, Any]:
    uid = str(getattr(node, "uid", "") or "")
    node_type = str(getattr(node, "node_type", "") or "unknown")
    component = component_index.find(uid, bd_file, class_hint=node_type)
    object_id = str((component or {}).get("id") or _synthetic_id(document_id, "node", uid))
    kind, default_name, symbol = _node_kind_name(node)
    label = str(getattr(node, "label", "") or getattr(node, "caption", "") or "").strip()
    if node_type in {"iUse", "polyIUse", "dynIUse", "callParentDynIUse"}:
        default_name = subvi_names.get(uid) or default_name
    name = label or default_name
    bounds = _component_bounds(component, _layout_rect(layout, uid))
    return {
        "id": object_id,
        "component_id": (component or {}).get("id"),
        "surface": "block-diagram",
        "kind": kind,
        "category": "node",
        "name": name,
        "symbol": symbol,
        "class_name": node_type,
        "widget": "",
        "uid": uid,
        "bounds": bounds,
        "positioned": bool(bounds),
        "movable": bool(bounds and bounds.get("source_property_id")),
        "resizable": bool(bounds and bounds.get("source_property_id")),
        "terminal_ids": [],
        "linked_terminal_ids": [],
        "wire_ids": [],
        "parent_object_id": None,
        "child_object_ids": [],
        "data_type": "unknown",
        "visual_kind": "subvi" if kind == "subvi" else "arithmetic" if kind in _OPERATION_NAMES else "node",
        "semantic_source": "lvkit",
        "parser_confidence": "exact" if not kind.startswith("node-") else "node-shaped",
        "semantic": _safe_structure(node),
        "source": _object_source(component, bd_file),
    }


def _constant_payload(
    constant: object,
    *,
    document_id: str,
    bd_file: str,
    component_index: _ComponentIndex,
    layout: object | None,
) -> dict[str, Any]:
    uid = str(getattr(constant, "uid", "") or "")
    component = component_index.find(uid, bd_file, kind_hint="constant")
    object_id = str((component or {}).get("id") or _synthetic_id(document_id, "constant", uid))
    value = str(getattr(constant, "value", "") or "")
    name = str(getattr(constant, "label", "") or getattr(constant, "caption", "") or value or "Constant")
    bounds = _component_bounds(component, _layout_rect(layout, uid))
    return {
        "id": object_id,
        "component_id": (component or {}).get("id"),
        "surface": "block-diagram",
        "kind": "constant",
        "category": "node",
        "name": name,
        "symbol": value[:24] or "C",
        "display_value": value,
        "class_name": str((component or {}).get("class_name") or "constant"),
        "widget": "",
        "uid": uid,
        "bounds": bounds,
        "positioned": bool(bounds),
        "movable": bool(bounds and bounds.get("source_property_id")),
        "resizable": bool(bounds and bounds.get("source_property_id")),
        "terminal_ids": [],
        "linked_terminal_ids": [],
        "wire_ids": [],
        "parent_object_id": None,
        "child_object_ids": [],
        "data_type": "unknown",
        "visual_kind": "constant",
        "semantic_source": "lvkit",
        "parser_confidence": "exact",
        "semantic": _safe_structure(constant),
        "source": _object_source(component, bd_file),
    }


def _structure_payload(
    uid: str,
    record: tuple[str, str, str, object],
    *,
    document_id: str,
    bd_file: str,
    component_index: _ComponentIndex,
    layout: object | None,
) -> dict[str, Any]:
    kind, name, symbol, structure = record
    component = component_index.find(uid, bd_file, kind_hint="structure")
    object_id = str((component or {}).get("id") or _synthetic_id(document_id, "structure", uid))
    bounds = _component_bounds(component, _layout_rect(layout, uid))
    return {
        "id": object_id,
        "component_id": (component or {}).get("id"),
        "surface": "block-diagram",
        "kind": kind,
        "category": "node",
        "name": name,
        "symbol": symbol,
        "class_name": str((component or {}).get("class_name") or kind),
        "widget": "",
        "uid": uid,
        "bounds": bounds,
        "positioned": bool(bounds),
        "movable": bool(bounds and bounds.get("source_property_id")),
        "resizable": bool(bounds and bounds.get("source_property_id")),
        "terminal_ids": [],
        "linked_terminal_ids": [],
        "wire_ids": [],
        "parent_object_id": None,
        "child_object_ids": [],
        "data_type": "unknown",
        "visual_kind": "structure",
        "semantic_source": "lvkit",
        "parser_confidence": "exact",
        "structure": _safe_structure(structure),
        "source": _object_source(component, bd_file),
    }


def _container_membership(block_diagram: object) -> dict[str, str]:
    membership: dict[str, str] = {}
    for collection_name in (
        "loops",
        "decompose_structures",
    ):
        for structure in getattr(block_diagram, collection_name, ()) or ():
            owner_uid = str(getattr(structure, "uid", "") or "")
            for child_uid in getattr(structure, "inner_node_uids", ()) or ():
                membership.setdefault(str(child_uid), owner_uid)
    for collection_name in (
        "case_structures",
        "flat_sequences",
        "disable_structures",
        "event_structures",
    ):
        for structure in getattr(block_diagram, collection_name, ()) or ():
            owner_uid = str(getattr(structure, "uid", "") or "")
            payload = _safe_structure(structure)
            stack: list[object] = [payload]
            while stack:
                value = stack.pop()
                if isinstance(value, dict):
                    for key, item in value.items():
                        if key.endswith("node_uids") and isinstance(item, list):
                            for child_uid in item:
                                membership.setdefault(str(child_uid), owner_uid)
                        else:
                            stack.append(item)
                elif isinstance(value, list):
                    stack.extend(value)
    return membership


def _build_authoritative(
    dataset: Path,
    model: DatasetComponentModel,
    fallback_vi: dict[str, Any],
    parsed: object,
    bd_path: Path,
    fp_path: Path | None,
    main_path: Path | None,
) -> dict[str, Any]:
    bd_file = _relative(dataset, bd_path) or bd_path.name
    fp_file = _relative(dataset, fp_path) or (fp_path.name if fp_path else "")
    main_file = _relative(dataset, main_path)
    document_id = short_hash("labview-document", bd_file)
    component_index = _ComponentIndex(model)
    type_registry = _TypeRegistry(dataset)
    dependencies = [
        *(getattr(parsed.metadata, "dependency_refs", ()) or ()),
        *(getattr(parsed.metadata, "link_path_refs", ()) or ()),
    ]
    type_registry.add_dependencies(list(dependencies))

    front_objects, front_by_uid = _copy_front_panel(
        fallback_vi,
        parsed,
        index=component_index,
        fp_file=fp_file,
        document_id=document_id,
        type_registry=type_registry,
    )
    objects: list[dict[str, Any]] = list(front_objects)
    object_by_id = {item["id"]: item for item in objects}
    node_by_uid: dict[str, str] = {}

    subvi_names = dict(getattr(parsed.metadata, "iuse_to_qualified_name", {}) or {})
    for node in getattr(parsed.block_diagram, "nodes", ()) or ():
        uid = str(getattr(node, "uid", "") or "")
        if not uid or uid in node_by_uid:
            continue
        item = _node_payload(
            node,
            document_id=document_id,
            bd_file=bd_file,
            component_index=component_index,
            layout=getattr(parsed, "layout", None),
            subvi_names=subvi_names,
        )
        objects.append(item)
        object_by_id[item["id"]] = item
        node_by_uid[uid] = item["id"]

    for constant in getattr(parsed.block_diagram, "constants", ()) or ():
        uid = str(getattr(constant, "uid", "") or "")
        if not uid or uid in node_by_uid:
            continue
        item = _constant_payload(
            constant,
            document_id=document_id,
            bd_file=bd_file,
            component_index=component_index,
            layout=getattr(parsed, "layout", None),
        )
        objects.append(item)
        object_by_id[item["id"]] = item
        node_by_uid[uid] = item["id"]

    structures = _structure_records(parsed.block_diagram)
    for uid, record in structures.items():
        if uid in node_by_uid:
            item = object_by_id[node_by_uid[uid]]
            item.update(
                {
                    "kind": record[0],
                    "name": record[1],
                    "symbol": record[2],
                    "visual_kind": "structure",
                    "structure": _safe_structure(record[3]),
                }
            )
            continue
        item = _structure_payload(
            uid,
            record,
            document_id=document_id,
            bd_file=bd_file,
            component_index=component_index,
            layout=getattr(parsed, "layout", None),
        )
        objects.append(item)
        object_by_id[item["id"]] = item
        node_by_uid[uid] = item["id"]

    membership = _container_membership(parsed.block_diagram)
    for child_uid, parent_uid in membership.items():
        child_id = node_by_uid.get(child_uid)
        parent_id = node_by_uid.get(parent_uid)
        if not child_id or not parent_id or child_id == parent_id:
            continue
        child = object_by_id[child_id]
        parent = object_by_id[parent_id]
        child["parent_object_id"] = parent_id
        if child_id not in parent["child_object_ids"]:
            parent["child_object_ids"].append(child_id)

    fp_term_by_uid = {
        str(term.uid): term
        for term in getattr(parsed.block_diagram, "fp_terminals", ()) or ()
    }
    terminal_by_uid: dict[str, str] = {}
    terminal_info = getattr(parsed.block_diagram, "terminal_info", {}) or {}
    for uid, terminal in terminal_info.items():
        uid = str(uid)
        parent_uid = str(getattr(terminal, "parent_uid", "") or "")
        component = component_index.find(uid, bd_file, class_hint="term", kind_hint="connector")
        object_id = str((component or {}).get("id") or _synthetic_id(document_id, "terminal", uid))
        fp_terminal = fp_term_by_uid.get(uid)
        linked_id = front_by_uid.get(str(getattr(fp_terminal, "fp_dco_uid", "") or ""))
        owner_id = node_by_uid.get(parent_uid)
        type_payload = _type_payload(getattr(terminal, "parsed_type", None))
        family = _type_family(type_payload)
        bounds = _terminal_bounds(getattr(parsed, "layout", None), uid, component)
        name = str(
            getattr(terminal, "name", "")
            or getattr(fp_terminal, "name", "")
            or ("output" if getattr(terminal, "is_output", False) else "input")
        )
        item = {
            "id": object_id,
            "component_id": (component or {}).get("id"),
            "surface": "block-diagram",
            "kind": "terminal",
            "category": "terminal",
            "name": name,
            "symbol": "",
            "class_name": str((component or {}).get("class_name") or "term"),
            "widget": "",
            "uid": uid,
            "bounds": bounds,
            "positioned": bool(bounds),
            "movable": False,
            "resizable": False,
            "direction": "source" if bool(getattr(terminal, "is_output", False)) else "sink",
            "direction_source": "lvkit-terminal-info",
            "owner_object_id": owner_id,
            "linked_object_id": linked_id,
            "terminal_ids": [],
            "linked_terminal_ids": [],
            "wire_ids": [],
            "port_index": int(getattr(terminal, "index", -1)),
            "data_type": family,
            "type": type_payload,
            "visual_kind": "terminal",
            "semantic_source": "lvkit",
            "parser_confidence": "exact",
            "semantic": _safe_structure(terminal),
            "source": _object_source(component, bd_file),
        }
        type_definition_id = type_registry.register(type_payload, object_id)
        if type_definition_id:
            item["type_definition_id"] = type_definition_id
        objects.append(item)
        object_by_id[object_id] = item
        terminal_by_uid[uid] = object_id
        if owner_id:
            object_by_id[owner_id]["terminal_ids"].append(object_id)
        if linked_id:
            linked = object_by_id[linked_id]
            linked["linked_terminal_ids"].append(object_id)
            if not linked.get("type") and type_payload:
                linked["type"] = type_payload
                linked["data_type"] = family
                linked["type_definition_id"] = type_definition_id

    for item in objects:
        if item.get("terminal_ids"):
            item["terminal_ids"].sort(
                key=lambda terminal_id: object_by_id[terminal_id].get("port_index", 10**9)
            )

    wires: list[dict[str, Any]] = []
    layout_wires = getattr(getattr(parsed, "layout", None), "wire_by_uid", {}) or {}
    for parsed_wire in getattr(parsed.block_diagram, "wires", ()) or ():
        source_uid = str(getattr(parsed_wire, "from_term", "") or "")
        target_uid = str(getattr(parsed_wire, "to_term", "") or "")
        source_terminal_id = terminal_by_uid.get(source_uid)
        target_terminal_id = terminal_by_uid.get(target_uid)
        if not source_terminal_id or not target_terminal_id:
            continue
        source_terminal = object_by_id[source_terminal_id]
        target_terminal = object_by_id[target_terminal_id]
        source_object_id = _endpoint_object_id(source_terminal)
        target_object_id = _endpoint_object_id(target_terminal)
        wire_id = short_hash(
            "lvkit-wire",
            document_id,
            getattr(parsed_wire, "uid", ""),
            source_uid,
            target_uid,
        )
        route_points = [
            {"x": float(point[0]), "y": float(point[1])}
            for point in layout_wires.get(target_uid, ())
        ]
        wire = {
            "id": wire_id,
            "name": f"{source_terminal['name']} → {target_terminal['name']}",
            "surface": "block-diagram",
            "source_terminal_id": source_terminal_id,
            "target_terminal_ids": [target_terminal_id],
            "terminal_ids": [source_terminal_id, target_terminal_id],
            "source_object_id": source_object_id,
            "target_object_ids": [target_object_id] if target_object_id else [],
            "endpoint_object_ids": [
                object_id
                for object_id in (source_object_id, target_object_id)
                if object_id
            ],
            "route_points": route_points,
            "resolved": True,
            "direction_confidence": "signal-term-list",
            "native_uid": str(getattr(parsed_wire, "uid", "") or ""),
            "data_type": source_terminal.get("data_type") or target_terminal.get("data_type") or "unknown",
            "type": source_terminal.get("type") or target_terminal.get("type"),
            "type_definition_id": source_terminal.get("type_definition_id") or target_terminal.get("type_definition_id"),
            "semantic_source": "lvkit",
        }
        wires.append(wire)
        for terminal_id in wire["terminal_ids"]:
            object_by_id[terminal_id]["wire_ids"].append(wire_id)
        for endpoint_id in wire["endpoint_object_ids"]:
            if wire_id not in object_by_id[endpoint_id]["wire_ids"]:
                object_by_id[endpoint_id]["wire_ids"].append(wire_id)

    for item in objects:
        item["nesting_depth"] = 0
        parent_id = item.get("parent_object_id")
        seen: set[str] = set()
        while parent_id and parent_id in object_by_id and parent_id not in seen:
            seen.add(parent_id)
            item["nesting_depth"] += 1
            parent_id = object_by_id[parent_id].get("parent_object_id")

    block_nodes = [item for item in objects if item.get("surface") == "block-diagram" and item.get("category") == "node"]
    terminals = [item for item in objects if item.get("category") == "terminal"]
    controls = [item for item in objects if item.get("category") == "control"]
    indicators = [item for item in objects if item.get("category") == "indicator"]
    parser_warnings: list[str] = []
    unresolved = len(getattr(parsed.block_diagram, "wires", ()) or ()) - len(wires)
    if unresolved:
        parser_warnings.append(f"{unresolved}本の配線は端子UIDを解決できなかったため非表示です。")

    return {
        "version": 3,
        "objects": objects,
        "wires": wires,
        "surfaces": {
            "front-panel": [item["id"] for item in objects if item.get("surface") == "front-panel"],
            "block-diagram": [item["id"] for item in objects if item.get("surface") == "block-diagram"],
        },
        "summary": {
            "front_panel_objects": len(controls) + len(indicators),
            "block_diagram_nodes": len(block_nodes),
            "controls": len(controls),
            "indicators": len(indicators),
            "terminals": len(terminals),
            "wires": len(wires),
            "resolved_wires": len(wires),
            "unresolved_wires": unresolved,
            "numeric_controls": sum(item.get("data_type") == "numeric" for item in controls),
            "numeric_indicators": sum(item.get("data_type") == "numeric" for item in indicators),
            "add_nodes": sum(item.get("kind") == "add" for item in block_nodes),
            "type_definitions": len(type_registry.definitions),
        },
        "warnings": parser_warnings,
        "type_definitions": type_registry.public(),
        "hierarchy": {
            "roots": [item["id"] for item in objects if not item.get("parent_object_id")],
            "containers": [item["id"] for item in objects if item.get("child_object_ids")],
            "children_by_parent": {
                item["id"]: list(item["child_object_ids"])
                for item in objects
                if item.get("child_object_ids")
            },
        },
        "documents": [
            {
                "id": document_id,
                "block_diagram": bd_file,
                "front_panel": fp_file or None,
                "main_xml": main_file,
                "qualified_name": getattr(parsed.metadata, "qualified_name", None),
            }
        ],
        "parser": {
            "name": "lvkit",
            "mode": "authoritative",
            "node_source": "operation allowlist plus node-shaped fallback",
            "wire_source": "signalList termList order",
            "layout_source": "heap layout and compressedWireTable",
            "type_source": "VCTP and terminal typeDesc",
        },
        "debug": {
            "generic_graph_retained": True,
            "generic_graph_used_for_block_diagram": False,
            "parsed_node_count": len(getattr(parsed.block_diagram, "nodes", ()) or ()),
            "parsed_wire_branch_count": len(getattr(parsed.block_diagram, "wires", ()) or ()),
            "terminal_info_count": len(terminal_info),
            "layout_node_count": len(getattr(getattr(parsed, "layout", None), "node_bounds", {}) or {}),
            "layout_wire_branch_count": len(layout_wires),
        },
    }


def build_authoritative_semantic_vi(
    dataset: Path,
    model: DatasetComponentModel,
    fallback_vi: dict[str, Any],
    *,
    main_xml: Path | None = None,
) -> dict[str, Any]:
    """Build the editor model from LabVIEW semantics, never generic XML edges."""

    document = _discover_primary_document(dataset, main_xml)
    if document is None:
        fallback = copy.deepcopy(fallback_vi)
        fallback.setdefault("warnings", []).append(
            "ブロックダイアグラムheapがないため、フロントパネル解析のみ表示しています。"
        )
        fallback["parser"] = {
            "name": "component-model",
            "mode": "front-panel-only",
            "generic_graph_used_for_block_diagram": False,
        }
        fallback["objects"] = [
            item for item in fallback.get("objects", []) if item.get("surface") == "front-panel"
        ]
        fallback["wires"] = []
        return fallback

    bd_path, fp_path, main_path = document
    try:
        from lvkit.parser import parse_vi
    except ImportError:
        fallback = copy.deepcopy(fallback_vi)
        fallback.setdefault("warnings", []).append(
            "LabVIEW意味パーサを読み込めません。ブロックダイアグラムは誤表示を避けるため非表示です。"
        )
        fallback["parser"] = {
            "name": "lvkit",
            "mode": "unavailable",
            "generic_graph_used_for_block_diagram": False,
        }
        fallback["objects"] = [
            item for item in fallback.get("objects", []) if item.get("surface") == "front-panel"
        ]
        fallback["wires"] = []
        return fallback

    try:
        parsed = parse_vi(
            bd_xml=bd_path,
            fp_xml=fp_path,
            main_xml=main_path,
            layout=True,
        )
    except (OSError, ValueError, TypeError, AttributeError) as error:
        fallback = copy.deepcopy(fallback_vi)
        fallback.setdefault("warnings", []).append(
            f"LabVIEW意味解析に失敗しました。誤ったノードや配線は表示しません: {error}"
        )
        fallback["parser"] = {
            "name": "lvkit",
            "mode": "failed",
            "error": str(error),
            "generic_graph_used_for_block_diagram": False,
        }
        fallback["objects"] = [
            item for item in fallback.get("objects", []) if item.get("surface") == "front-panel"
        ]
        fallback["wires"] = []
        return fallback

    return _build_authoritative(
        dataset,
        model,
        fallback_vi,
        parsed,
        bd_path,
        fp_path,
        main_path,
    )
