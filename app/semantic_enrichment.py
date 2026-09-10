from __future__ import annotations

import copy
import re
from collections import defaultdict
from typing import Any

from .component_model import DatasetComponentModel, strip_quotes


def _key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _data_type(item: dict[str, Any]) -> str:
    kind = _key(item.get("kind"))
    widget = _key(item.get("widget"))
    class_name = _key(item.get("class_name"))
    haystack = " ".join((kind, widget, class_name))
    if any(token in haystack for token in ("cluster", "clust", "record", "struct")):
        return "cluster"
    if any(token in haystack for token in ("array", "indarr")):
        return "array"
    if any(token in haystack for token in ("boolean", "bool", "and", "or", "xor")):
        return "boolean"
    if any(token in haystack for token in ("string", "text", "char")):
        return "string"
    if "path" in haystack:
        return "path"
    if any(token in haystack for token in ("refnum", "reference")):
        return "refnum"
    if any(token in haystack for token in ("ring", "enum")):
        return "ring"
    if "table" in haystack:
        return "table"
    if any(
        token in haystack
        for token in (
            "numeric",
            "number",
            "stdnum",
            "slide",
            "knob",
            "add",
            "subtract",
            "multiply",
            "divide",
            "arith",
        )
    ):
        return "numeric"
    return "unknown"


def _visual_kind(item: dict[str, Any]) -> str:
    kind = str(item.get("kind") or "")
    data_type = item.get("data_type")
    if data_type == "cluster":
        return "cluster"
    if data_type == "array":
        return "array"
    if item.get("surface") == "front-panel":
        return str(data_type or "control")
    if kind in {"add", "subtract", "multiply", "divide"}:
        return "arithmetic"
    if kind in {"equal", "greater", "less", "and", "or", "xor", "select"}:
        return "primitive"
    if kind in {"structure", "subvi", "constant"}:
        return kind
    if item.get("category") == "terminal":
        return "terminal"
    return "node"


def _property_value(
    model: DatasetComponentModel,
    component_id: str,
    names: tuple[str, ...],
) -> str | None:
    component = model.components.get(component_id)
    if not component:
        return None
    expected = {_key(name) for name in names}
    property_ids = [
        *component.get("property_ids", []),
        *component.get("presentation_property_ids", []),
    ]
    for property_id in dict.fromkeys(property_ids):
        prop = model.properties.get(property_id)
        if not prop or prop.get("binary") or prop.get("reference_like"):
            continue
        field = _key(prop.get("field_name") or prop.get("name"))
        if field not in expected:
            continue
        value = prop.get("value")
        if value is None:
            value = prop.get("preview")
        text = strip_quotes(str(value or "").strip())
        if text:
            return text
    return None


def _is_container(item: dict[str, Any]) -> bool:
    kind = str(item.get("kind") or "")
    return (
        item.get("data_type") in {"cluster", "array"}
        or kind == "structure"
        or kind.startswith(("cluster-", "array-"))
    )


def _nearest_semantic_container(
    object_id: str,
    *,
    object_ids: set[str],
    node_by_id: dict[str, dict[str, Any]],
    objects: dict[str, dict[str, Any]],
) -> str | None:
    node = node_by_id.get(object_id)
    parent_id = node.get("parent_id") if node else None
    seen: set[str] = set()
    while parent_id and parent_id not in seen:
        seen.add(parent_id)
        if parent_id in object_ids:
            parent = objects[parent_id]
            child = objects[object_id]
            if parent.get("surface") == child.get("surface") and _is_container(parent):
                return parent_id
        parent = node_by_id.get(parent_id)
        parent_id = parent.get("parent_id") if parent else None
    return None


def _contains_absolute(
    parent: dict[str, Any],
    child: dict[str, Any],
    tolerance: float = 2.0,
) -> bool:
    return (
        child["x"] >= parent["x"] - tolerance
        and child["y"] >= parent["y"] - tolerance
        and child["x"] + child["width"] <= parent["x"] + parent["width"] + tolerance
        and child["y"] + child["height"] <= parent["y"] + parent["height"] + tolerance
    )


def _fits_relative(
    parent: dict[str, Any],
    child: dict[str, Any],
    tolerance: float = 2.0,
) -> bool:
    return (
        child["x"] >= -tolerance
        and child["y"] >= -tolerance
        and child["x"] + child["width"] <= parent["width"] + tolerance
        and child["y"] + child["height"] <= parent["height"] + tolerance
    )


def _apply_parent_coordinates(
    child: dict[str, Any],
    parent: dict[str, Any],
) -> None:
    child_bounds = child.get("bounds")
    parent_bounds = parent.get("bounds")
    if not child_bounds or not parent_bounds:
        return

    child_bounds["parent_object_id"] = parent["id"]
    child_bounds["source_x"] = float(child_bounds.get("x", 0))
    child_bounds["source_y"] = float(child_bounds.get("y", 0))
    if _contains_absolute(parent_bounds, child_bounds):
        child_bounds["source_coordinate_space"] = "absolute"
        return
    if not _fits_relative(parent_bounds, child_bounds):
        child_bounds["source_coordinate_space"] = "unknown"
        return

    raw_x = float(child_bounds.get("x", 0))
    raw_y = float(child_bounds.get("y", 0))
    child_bounds.update(
        {
            "raw_x": raw_x,
            "raw_y": raw_y,
            "x": float(parent_bounds.get("x", 0)) + raw_x,
            "y": float(parent_bounds.get("y", 0)) + raw_y,
            "relative_to_object_id": parent["id"],
            "source_coordinate_space": "parent-relative",
        }
    )


def enrich_semantic_vi(
    model: DatasetComponentModel,
    graph: dict[str, Any],
    semantic_vi: dict[str, Any],
) -> dict[str, Any]:
    """Add hierarchy and rendering hints without exposing XML as the UI model."""

    result = copy.deepcopy(semantic_vi)
    ordered_objects = result.get("objects", [])
    objects = {item["id"]: item for item in ordered_objects}
    object_ids = set(objects)
    node_by_id = {node["id"]: node for node in graph.get("models", [])}

    for item in ordered_objects:
        item["data_type"] = _data_type(item)
        item["visual_kind"] = _visual_kind(item)
        item["parent_object_id"] = None
        item["child_object_ids"] = []
        item["nesting_depth"] = 0
        if item.get("category") != "terminal":
            value = _property_value(
                model,
                item.get("component_id") or item["id"],
                (
                    "value",
                    "defaultValue",
                    "default",
                    "dflt",
                    "text",
                    "displayText",
                ),
            )
            if value is not None:
                item["display_value"] = value

    for item in ordered_objects:
        if item.get("category") == "terminal":
            continue
        parent_id = _nearest_semantic_container(
            item["id"],
            object_ids=object_ids,
            node_by_id=node_by_id,
            objects=objects,
        )
        if not parent_id:
            continue
        parent = objects[parent_id]
        item["parent_object_id"] = parent_id
        parent["child_object_ids"].append(item["id"])
        parent["clip_children"] = True
        _apply_parent_coordinates(item, parent)

    def depth_for(object_id: str, seen: set[str] | None = None) -> int:
        seen = set() if seen is None else seen
        if object_id in seen:
            return 0
        seen.add(object_id)
        parent_id = objects[object_id].get("parent_object_id")
        if not parent_id or parent_id not in objects:
            return 0
        return 1 + depth_for(parent_id, seen)

    for item in ordered_objects:
        item["nesting_depth"] = depth_for(item["id"])
        item["child_object_ids"].sort(
            key=lambda child_id: (
                float((objects[child_id].get("bounds") or {}).get("y", 10**9)),
                float((objects[child_id].get("bounds") or {}).get("x", 10**9)),
                objects[child_id].get("name") or "",
            )
        )
        for index, terminal_id in enumerate(item.get("terminal_ids", [])):
            terminal = objects.get(terminal_id)
            if terminal:
                terminal["port_index"] = index

    ordered_objects.sort(
        key=lambda item: (
            0 if item.get("surface") == "front-panel" else 1,
            item.get("nesting_depth", 0),
            float((item.get("bounds") or {}).get("y", 10**9)),
            float((item.get("bounds") or {}).get("x", 10**9)),
            item.get("name") or "",
            item["id"],
        )
    )

    clusters = [item for item in ordered_objects if item.get("data_type") == "cluster"]
    cluster_members = [
        item
        for item in ordered_objects
        if item.get("parent_object_id")
        and objects.get(item["parent_object_id"], {}).get("data_type") == "cluster"
    ]
    result.setdefault("summary", {}).update(
        {
            "clusters": len(clusters),
            "cluster_members": len(cluster_members),
        }
    )
    result["hierarchy"] = {
        "roots": [item["id"] for item in ordered_objects if not item.get("parent_object_id")],
        "containers": [item["id"] for item in ordered_objects if _is_container(item)],
        "children_by_parent": dict(
            sorted(
                (
                    (item["id"], list(item["child_object_ids"]))
                    for item in ordered_objects
                    if item.get("child_object_ids")
                ),
                key=lambda pair: pair[0],
            )
        ),
    }
    result["version"] = max(2, int(result.get("version") or 1))
    return result
