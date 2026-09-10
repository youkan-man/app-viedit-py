from __future__ import annotations

import re
from typing import Any


def _key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def data_type_for(item: dict[str, Any]) -> str:
    haystack = " ".join(
        _key(item.get(name)) for name in ("kind", "widget", "class_name")
    )
    groups = (
        ("cluster", ("cluster", "clust", "record", "struct")),
        ("array", ("array", "indarr")),
        ("boolean", ("boolean", "bool", "and", "or", "xor")),
        ("string", ("string", "text", "char")),
        ("path", ("path",)),
        ("refnum", ("refnum", "reference")),
        ("ring", ("ring", "enum")),
        ("table", ("table",)),
        (
            "numeric",
            (
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
            ),
        ),
    )
    for data_type, tokens in groups:
        if any(token in haystack for token in tokens):
            return data_type
    return "unknown"


def visual_kind_for(item: dict[str, Any]) -> str:
    kind = str(item.get("kind") or "")
    data_type = str(item.get("data_type") or "unknown")
    if data_type in {"cluster", "array"}:
        return data_type
    if item.get("surface") == "front-panel":
        return data_type
    if kind in {"add", "subtract", "multiply", "divide"}:
        return "arithmetic"
    if kind in {"equal", "greater", "less", "and", "or", "xor", "select"}:
        return "primitive"
    if kind in {"structure", "subvi", "constant"}:
        return kind
    if item.get("category") == "terminal":
        return "terminal"
    return "node"


def annotate_semantic_types(objects: list[dict[str, Any]]) -> None:
    for item in objects:
        item["data_type"] = data_type_for(item)
        item["visual_kind"] = visual_kind_for(item)
        item["parent_object_id"] = None
        item["child_object_ids"] = []
        item["nesting_depth"] = 0
