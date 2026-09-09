from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from .component_model import DatasetComponentModel, parse_integer, strip_quotes

_FRONT_PANEL_WIDGETS = {
    "stdnum": "numeric",
    "stdnumeric": "numeric",
    "stdslide": "numeric",
    "stdknob": "numeric",
    "stdring": "ring",
    "stdstring": "string",
    "stdbool": "boolean",
    "stdpath": "path",
    "stdrefnum": "refnum",
    "stdclust": "cluster",
    "indarr": "array",
    "tablecontrol": "table",
}

_INDICATOR_NAME_TOKENS = (
    "indicator",
    "output",
    "result",
    "answer",
    "status",
    "結果",
    "出力",
    "表示",
)

_OPERATION_HINTS = (
    (("subtract", "minus", "減算"), "subtract", "−"),
    (("multiply", "times", "乗算"), "multiply", "×"),
    (("divide", "division", "除算"), "divide", "÷"),
    (("equal", "equals", "等しい"), "equal", "="),
    (("greater", "大きい"), "greater", ">"),
    (("less", "小さい"), "less", "<"),
    (("select", "選択"), "select", "?"),
    (("and", "論理積"), "and", "AND"),
    (("xor", "排他的"), "xor", "XOR"),
    (("or", "論理和"), "or", "OR"),
    (("add", "plus", "sum", "加算"), "add", "+"),
)


def _key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _property_values(
    model: DatasetComponentModel,
    component: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    values: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for property_id in component.get("property_ids", []):
        prop = model.properties.get(property_id)
        if not prop:
            continue
        field = _key(prop.get("field_name") or prop.get("name"))
        values[field].append(prop)
    return values


def _property_text(properties: dict[str, list[dict[str, Any]]], *names: str) -> str:
    for name in names:
        for prop in properties.get(_key(name), []):
            value = prop.get("value")
            if value is None:
                value = prop.get("preview")
            text = strip_quotes(str(value or "").strip())
            if text:
                return text
    return ""


def _property_int(properties: dict[str, list[dict[str, Any]]], *names: str) -> int | None:
    for name in names:
        for prop in properties.get(_key(name), []):
            parsed = prop.get("parsed")
            if isinstance(parsed, int) and not isinstance(parsed, bool):
                return parsed
            value = prop.get("value")
            if value is None:
                value = prop.get("preview")
            try:
                return parse_integer(str(value))
            except (TypeError, ValueError):
                continue
    return None


def _semantic_control(
    model: DatasetComponentModel,
    graph_node: dict[str, Any],
) -> tuple[str, str, bool]:
    component = model.components[graph_node["id"]]
    properties = _property_values(model, component)
    class_key = _key(graph_node.get("class_name"))
    widget_key = _key(graph_node.get("widget"))
    flavor = _FRONT_PANEL_WIDGETS.get(widget_key)
    if not flavor:
        flavor = _FRONT_PANEL_WIDGETS.get(class_key, "control")

    indicator: bool | None = None
    if class_key == "fpdco":
        obj_flags = _property_int(properties, "objFlags")
        if obj_flags is not None:
            indicator = bool(obj_flags & 0x1)
    if indicator is None:
        haystack = f"{graph_node.get('name', '')} {graph_node.get('role', '')}".lower()
        indicator = any(token in haystack for token in _INDICATOR_NAME_TOKENS)

    category = "indicator" if indicator else "control"
    kind = f"{flavor}-{category}" if flavor != "control" else category
    return kind, category, indicator


def _semantic_operation(
    model: DatasetComponentModel,
    graph_node: dict[str, Any],
) -> tuple[str, str]:
    component = model.components[graph_node["id"]]
    properties = _property_values(model, component)
    class_key = _key(graph_node.get("class_name"))
    operation = _property_text(properties, "operation", "op", "nodeName")
    filler = _property_int(properties, "dcoFiller")
    if class_key == "cpdarith":
        if filler == 1:
            operation = "or"
        elif filler == 2:
            operation = "and"
        elif filler == 256 or not operation:
            operation = "add"

    haystack = " ".join(
        str(value or "")
        for value in (
            operation,
            graph_node.get("name"),
            graph_node.get("class_name"),
            graph_node.get("widget"),
        )
    ).lower()
    for hints, kind, symbol in _OPERATION_HINTS:
        if any(hint in haystack for hint in hints):
            return kind, symbol
    return "function", "ƒ"


def _base_bounds(node: dict[str, Any]) -> dict[str, Any] | None:
    position = node.get("position")
    if not position:
        return None
    source_property = position.get("source_property")
    source_key = _key(source_property)
    storage_order = position.get("storage_order")
    if not storage_order:
        storage_order = (
            "left,top,right,bottom"
            if source_key.startswith("of")
            else "top,left,bottom,right"
        )
    return {
        "x": float(position.get("x", 0)),
        "y": float(position.get("y", 0)),
        "width": float(position.get("width", 0)),
        "height": float(position.get("height", 0)),
        "source_property_id": position.get("source_property_id"),
        "source_property": source_property,
        "storage_order": storage_order,
        "coordinate_space": position.get("coordinate_space") or node.get("layer"),
    }


def _center(bounds: dict[str, Any] | None) -> tuple[float, float] | None:
    if not bounds:
        return None
    return (
        float(bounds["x"]) + float(bounds["width"]) / 2,
        float(bounds["y"]) + float(bounds["height"]) / 2,
    )


def _is_visible_node(node: dict[str, Any]) -> bool:
    if node.get("layer") == "front-panel":
        return node.get("kind") == "control"
    if node.get("layer") != "block-diagram":
        return False
    if node.get("kind") in {"wire", "connector", "container", "decoration"}:
        return False
    return node.get("kind") in {
        "component",
        "control",
        "function",
        "structure",
        "subvi",
        "constant",
    }


def _find_terminal_owners(
    graph: dict[str, Any],
    node_by_id: dict[str, dict[str, Any]],
) -> dict[str, str]:
    owners: dict[str, str] = {}
    for node in node_by_id.values():
        if node.get("kind") != "connector":
            continue
        parent_id = node.get("parent_id")
        parent = node_by_id.get(parent_id)
        if parent and parent.get("kind") not in {"connector", "wire", "container", "decoration"}:
            owners[node["id"]] = parent_id

    for edge in graph.get("connections", []):
        if not edge.get("resolved") or edge.get("type") not in {"ownership", "containment"}:
            continue
        source = node_by_id.get(edge.get("source"))
        target = node_by_id.get(edge.get("target"))
        if not source or not target:
            continue
        if source.get("kind") == "connector" and target.get("kind") not in {"connector", "wire"}:
            owners.setdefault(source["id"], target["id"])
        elif target.get("kind") == "connector" and source.get("kind") not in {"connector", "wire"}:
            owners.setdefault(target["id"], source["id"])
    return owners


def _terminal_linked_objects(
    graph: dict[str, Any],
    node_by_id: dict[str, dict[str, Any]],
) -> dict[str, str]:
    linked: dict[str, str] = {}
    for edge in graph.get("connections", []):
        if not edge.get("resolved") or edge.get("type") not in {"connection", "mate", "reference"}:
            continue
        source = node_by_id.get(edge.get("source"))
        target = node_by_id.get(edge.get("target"))
        if not source or not target:
            continue
        pairs = ((source, target), (target, source))
        for terminal, candidate in pairs:
            if (
                terminal.get("kind") == "connector"
                and candidate.get("layer") == "front-panel"
                and candidate.get("kind") == "control"
            ):
                linked.setdefault(terminal["id"], candidate["id"])
    return linked


def _terminal_bounds(
    terminal_node: dict[str, Any],
    owner: dict[str, Any] | None,
) -> dict[str, Any] | None:
    bounds = _base_bounds(terminal_node)
    if not bounds:
        return None
    source_name = _key(bounds.get("source_property"))
    if owner and source_name.endswith("termbounds") and owner.get("bounds"):
        owner_bounds = owner["bounds"]
        bounds["raw_x"] = bounds["x"]
        bounds["raw_y"] = bounds["y"]
        bounds["x"] += owner_bounds["x"]
        bounds["y"] += owner_bounds["y"]
        bounds["relative_to_object_id"] = owner["id"]
    if bounds["width"] <= 0:
        bounds["width"] = 8.0
    if bounds["height"] <= 0:
        bounds["height"] = 8.0
    return bounds


def _terminal_direction(
    model: DatasetComponentModel,
    terminal_node: dict[str, Any],
    owner: dict[str, Any] | None,
    linked_object: dict[str, Any] | None,
    bounds: dict[str, Any] | None,
) -> tuple[str, str]:
    if linked_object:
        if linked_object.get("category") == "indicator":
            return "sink", "front-panel-indicator"
        if linked_object.get("category") == "control":
            return "source", "front-panel-control"

    component = model.components[terminal_node["id"]]
    properties = _property_values(model, component)
    direction = _property_text(properties, "direction", "terminalDirection", "ioDirection").lower()
    if direction in {"source", "output", "out", "write"}:
        return "source", "stored-direction"
    if direction in {"sink", "input", "in", "read"}:
        return "sink", "stored-direction"

    if owner and bounds and owner.get("bounds"):
        center = _center(bounds)
        owner_center = _center(owner["bounds"])
        if center and owner_center:
            return (
                ("sink", "terminal-side")
                if center[0] <= owner_center[0]
                else ("source", "terminal-side")
            )
    return "unknown", "unresolved"


def _endpoint_object_id(terminal: dict[str, Any]) -> str | None:
    return terminal.get("owner_object_id") or terminal.get("linked_object_id")


def _pick_wire_direction(
    terminal_ids: list[str],
    endpoint_ids: list[str],
    objects: dict[str, dict[str, Any]],
) -> tuple[str | None, list[str], str]:
    terminals = [objects[item] for item in terminal_ids if item in objects]
    sources = [item for item in terminals if item.get("direction") == "source"]
    sinks = [item for item in terminals if item.get("direction") == "sink"]
    if len(sources) == 1 and sinks:
        return sources[0]["id"], [item["id"] for item in sinks], "terminal-direction"

    source_candidates: list[dict[str, Any]] = []
    sink_candidates: list[dict[str, Any]] = []
    for terminal in terminals:
        endpoint = objects.get(_endpoint_object_id(terminal) or "")
        category = endpoint.get("category") if endpoint else None
        if category == "control":
            source_candidates.append(terminal)
        elif category == "indicator":
            sink_candidates.append(terminal)
    if len(source_candidates) == 1 and sink_candidates:
        return (
            source_candidates[0]["id"],
            [item["id"] for item in sink_candidates],
            "front-panel-role",
        )

    if terminals:
        source = sources[0] if sources else terminals[0]
        targets = [item["id"] for item in terminals if item["id"] != source["id"]]
        if targets:
            return source["id"], targets, "heuristic"

    endpoint_objects = [objects[item] for item in endpoint_ids if item in objects]
    controls = [item for item in endpoint_objects if item.get("category") == "control"]
    if controls and len(endpoint_objects) > 1:
        return None, [], "object-only"
    return None, [], "unresolved"


def _route_points(net: dict[str, Any]) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []
    for point in net.get("points", []):
        if not isinstance(point, dict):
            continue
        try:
            points.append({"x": float(point["x"]), "y": float(point["y"])})
        except (KeyError, TypeError, ValueError):
            continue
    return points


def build_semantic_vi(
    model: DatasetComponentModel,
    graph: dict[str, Any],
) -> dict[str, Any]:
    """Project XML-derived graph records into editor-facing LabVIEW objects.

    XML identity and source locations are retained only as diagnostics. The
    primary model contains front-panel controls/indicators, diagram nodes,
    terminals and wires with explicit endpoint relationships.
    """

    graph_nodes = graph.get("models", [])
    node_by_id = {node["id"]: node for node in graph_nodes}
    owner_by_terminal = _find_terminal_owners(graph, node_by_id)
    linked_by_terminal = _terminal_linked_objects(graph, node_by_id)

    objects: dict[str, dict[str, Any]] = {}
    for node in graph_nodes:
        if not _is_visible_node(node):
            continue
        if node.get("layer") == "front-panel":
            kind, category, indicator = _semantic_control(model, node)
            symbol = "OUT" if indicator else "IN"
        else:
            graph_kind = node.get("kind")
            class_key = _key(node.get("class_name"))
            operation_kind, operation_symbol = _semantic_operation(model, node)
            if graph_kind == "function" or class_key in {"cpdarith", "prim"} or operation_kind != "function":
                kind, symbol = operation_kind, operation_symbol
                category = "node"
            else:
                kind = {
                    "structure": "structure",
                    "subvi": "subvi",
                    "constant": "constant",
                    "control": "diagram-control",
                }.get(graph_kind, "node")
                category = "node"
                symbol = {
                    "structure": "▣",
                    "subvi": "VI",
                    "constant": "C",
                }.get(graph_kind, "◇")
        bounds = _base_bounds(node)
        objects[node["id"]] = {
            "id": node["id"],
            "component_id": node["id"],
            "surface": node.get("layer"),
            "kind": kind,
            "category": category,
            "name": node.get("name") or node.get("class_name") or kind,
            "symbol": symbol,
            "class_name": node.get("class_name") or "",
            "widget": node.get("widget") or "",
            "uid": node.get("uid") or "",
            "bounds": bounds,
            "positioned": bounds is not None,
            "resizable": bounds is not None,
            "movable": bounds is not None,
            "terminal_ids": [],
            "wire_ids": [],
            "linked_terminal_ids": [],
            "source": {
                "file": node.get("file") or "",
                "xml_path": node.get("xml_path") or "",
            },
        }

    terminal_nodes = [
        node
        for node in graph_nodes
        if node.get("kind") == "connector" and node.get("layer") == "block-diagram"
    ]
    for node in terminal_nodes:
        owner = objects.get(owner_by_terminal.get(node["id"], ""))
        linked = objects.get(linked_by_terminal.get(node["id"], ""))
        bounds = _terminal_bounds(node, owner)
        direction, direction_source = _terminal_direction(
            model,
            node,
            owner,
            linked,
            bounds,
        )
        terminal = {
            "id": node["id"],
            "component_id": node["id"],
            "surface": "block-diagram",
            "kind": "terminal",
            "category": "terminal",
            "name": node.get("name") or "端子",
            "symbol": "",
            "class_name": node.get("class_name") or "",
            "widget": node.get("widget") or "",
            "uid": node.get("uid") or "",
            "bounds": bounds,
            "positioned": bounds is not None,
            "resizable": False,
            "movable": False,
            "direction": direction,
            "direction_source": direction_source,
            "owner_object_id": owner["id"] if owner else None,
            "linked_object_id": linked["id"] if linked else None,
            "wire_ids": [],
            "terminal_ids": [],
            "linked_terminal_ids": [],
            "source": {
                "file": node.get("file") or "",
                "xml_path": node.get("xml_path") or "",
            },
        }
        objects[node["id"]] = terminal
        if owner:
            owner["terminal_ids"].append(node["id"])
        if linked:
            linked["linked_terminal_ids"].append(node["id"])

    wires: list[dict[str, Any]] = []
    for net in graph.get("nets", []):
        terminal_ids = [item for item in net.get("connector_ids", []) if item in objects]
        endpoint_ids = [item for item in net.get("endpoint_ids", []) if item in objects]
        source_terminal_id, target_terminal_ids, confidence = _pick_wire_direction(
            terminal_ids,
            endpoint_ids,
            objects,
        )
        source_terminal = objects.get(source_terminal_id or "")
        targets = [objects[item] for item in target_terminal_ids if item in objects]
        source_object_id = _endpoint_object_id(source_terminal) if source_terminal else None
        target_object_ids = [
            endpoint
            for endpoint in (_endpoint_object_id(item) for item in targets)
            if endpoint
        ]
        if not source_object_id:
            control_sources = [
                item
                for item in endpoint_ids
                if objects[item].get("category") == "control"
            ]
            if len(control_sources) == 1:
                source_object_id = control_sources[0]
        if not target_object_ids:
            target_object_ids = [
                item
                for item in endpoint_ids
                if item != source_object_id
                and objects[item].get("category") != "control"
            ]
        resolved = bool(source_object_id and target_object_ids)
        wire = {
            "id": net.get("wire_id") or net.get("id"),
            "net_id": net.get("id"),
            "name": net.get("name") or "配線",
            "surface": "block-diagram",
            "source_terminal_id": source_terminal_id,
            "target_terminal_ids": target_terminal_ids,
            "terminal_ids": terminal_ids,
            "source_object_id": source_object_id,
            "target_object_ids": list(dict.fromkeys(target_object_ids)),
            "endpoint_object_ids": list(dict.fromkeys(endpoint_ids)),
            "route_points": _route_points(net),
            "resolved": resolved,
            "direction_confidence": confidence,
        }
        wires.append(wire)
        for object_id in {
            *terminal_ids,
            *endpoint_ids,
            *([source_object_id] if source_object_id else []),
            *target_object_ids,
        }:
            if object_id in objects and wire["id"] not in objects[object_id]["wire_ids"]:
                objects[object_id]["wire_ids"].append(wire["id"])

    category_order = {"control": 0, "node": 1, "indicator": 2}

    def wire_sort_key(wire: dict[str, Any]) -> tuple[Any, ...]:
        source = objects.get(wire.get("source_object_id") or "", {})
        source_bounds = source.get("bounds") or {}
        return (
            category_order.get(source.get("category"), 3),
            float(source_bounds.get("y", 10**9)),
            float(source_bounds.get("x", 10**9)),
            str(source.get("name") or ""),
            str(wire.get("id") or ""),
        )

    wires.sort(key=wire_sort_key)

    ordered_objects = sorted(
        objects.values(),
        key=lambda item: (
            0 if item["surface"] == "front-panel" else 1,
            1 if item["category"] == "terminal" else 0,
            float((item.get("bounds") or {}).get("y", 10**9)),
            float((item.get("bounds") or {}).get("x", 10**9)),
            item["name"],
            item["id"],
        ),
    )
    kind_counts = Counter(item["kind"] for item in ordered_objects)
    category_counts = Counter(item["category"] for item in ordered_objects)
    surfaces = {
        "front-panel": [
            item["id"] for item in ordered_objects if item["surface"] == "front-panel"
        ],
        "block-diagram": [
            item["id"] for item in ordered_objects if item["surface"] == "block-diagram"
        ],
    }
    warnings: list[str] = []
    unresolved_wires = [wire for wire in wires if not wire["resolved"]]
    if unresolved_wires:
        warnings.append(
            f"{len(unresolved_wires)}本の配線で入出力方向を確定できませんでした。"
        )
    if not surfaces["front-panel"]:
        warnings.append("フロントパネル上の操作対象を検出できませんでした。")
    if not any(item["category"] == "node" for item in ordered_objects):
        warnings.append("ブロックダイアグラム上の演算ノードを検出できませんでした。")

    return {
        "version": 1,
        "objects": ordered_objects,
        "wires": wires,
        "surfaces": surfaces,
        "summary": {
            "front_panel_objects": len(surfaces["front-panel"]),
            "block_diagram_nodes": category_counts["node"],
            "controls": category_counts["control"],
            "indicators": category_counts["indicator"],
            "terminals": category_counts["terminal"],
            "wires": len(wires),
            "resolved_wires": len(wires) - len(unresolved_wires),
            "numeric_controls": kind_counts["numeric-control"],
            "numeric_indicators": kind_counts["numeric-indicator"],
            "add_nodes": kind_counts["add"],
            "kinds": dict(kind_counts.most_common()),
        },
        "warnings": warnings,
        "debug": {
            "documents": len(graph.get("documents", [])),
            "unresolved_references": len(graph.get("unresolved", [])),
            "graph_version": graph.get("version"),
        },
    }
