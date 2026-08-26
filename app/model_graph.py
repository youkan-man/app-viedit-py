from __future__ import annotations

import re
from collections import Counter, defaultdict, deque
from collections.abc import Iterable
from typing import Any

from .component_model import DatasetComponentModel, normalized_name, strip_quotes

GRAPH_NODE_KINDS = {
    "component",
    "control",
    "connector",
    "wire",
    "structure",
    "subvi",
    "function",
    "constant",
    "container",
    "decoration",
}

IDENTITY_FIELDS = {
    "uid",
    "id",
    "wireid",
    "conid",
    "partid",
    "omid",
    "rsrcid",
    "signalindex",
}

CONNECTION_FIELDS = {
    "wireid",
    "conid",
    "termlist",
    "termlistlength",
    "nodelist",
    "datanodelist",
    "filternodelist",
    "hgrownodelist",
    "tunnellist",
    "signallist",
    "ownersignal",
    "outputnode",
    "inputnode",
    "srcdco",
    "srcdco1",
    "srcdco2",
    "srcdco3",
    "srcdco4",
    "dco",
    "dcolist",
    "dcoagg",
    "conpane",
    "connector",
    "terminal",
    "tunnel",
    "port",
}
OWNERSHIP_FIELDS = {"owner", "parent", "root"}
MATE_FIELDS = {"mate", "otherside"}
NUMBER_RE = re.compile(r"[+-]?(?:0[xX][0-9A-Fa-f]+|\d+)")


def _value_text(prop: dict[str, Any]) -> str:
    return str(prop.get("value") or prop.get("preview") or "").strip()


def _key_variants(value: object) -> set[str]:
    text = strip_quotes(str(value).strip())
    if not text:
        return set()
    variants = {text, text.lower()}
    try:
        number = int(text, 0)
    except ValueError:
        return variants
    variants.update({str(number), hex(number).lower()})
    return variants


def _numeric_tokens(value: str) -> list[str]:
    return [match.group(0) for match in NUMBER_RE.finditer(value)]


def _field_key(value: object) -> str:
    raw = str(value or "").rsplit("}", 1)[-1].rsplit(":", 1)[-1]
    lowered = raw.lower()
    for prefix in ("of__", "sl__"):
        if lowered.startswith(prefix):
            lowered = lowered[len(prefix) :]
            break
    return lowered.replace("_", "")


def _component_aliases(model: DatasetComponentModel, component: dict[str, Any]) -> set[str]:
    aliases: set[str] = set()
    if component.get("uid"):
        aliases.update(_key_variants(component["uid"]))
    for property_id in component.get("property_ids", []):
        prop = model.properties[property_id]
        field = _field_key(prop.get("field_name"))
        if field not in IDENTITY_FIELDS:
            continue
        # wireID and conID are references when they occur on terminals/nodes.
        # They identify the component itself only on a wire/connector component.
        if field == "wireid" and component.get("kind") != "wire":
            continue
        if field == "conid" and component.get("kind") != "connector":
            continue
        value = _value_text(prop)
        if not value:
            continue
        for token in _numeric_tokens(value) or [value]:
            aliases.update(_key_variants(token))
    return aliases


def _file_layer(path: str, *hints: str) -> str:
    normalized_path = path.lower().replace("_", "").replace("-", "")
    haystack = " ".join((path, *hints)).lower().replace("_", "").replace("-", "")
    if any(token in haystack for token in ("bdhb", "blockdiagram", "diagram", "userdiagram")):
        return "block-diagram"
    if any(token in haystack for token in ("conpane", "connectorpane")):
        return "connector-pane"
    if (
        any(token in haystack for token in ("fphb", "frontpanel", "frontpane"))
        or "panel" in normalized_path
        or any(token in haystack for token in (" control ", " indicator "))
    ):
        return "front-panel"
    return "other"


def _semantic_field(field: str) -> str | None:
    normalized = _field_key(field)
    if normalized in MATE_FIELDS:
        return "mate"
    if normalized in OWNERSHIP_FIELDS:
        return "ownership"
    if normalized in CONNECTION_FIELDS:
        return "connection"
    # LabVIEW adds numeric suffixes and variant list names to several fields.
    if any(
        token in normalized
        for token in ("wire", "signal", "tunnel", "terminal", "connector")
    ) and normalized.endswith(("id", "list", "node", "dco")):
        return "connection"
    if "dco" in normalized and normalized.endswith(("dco", "list", "agg")):
        return "connection"
    if "node" in normalized and normalized.endswith(("node", "list")):
        return "connection"
    return None


def _relation_type(
    name: str,
    source_kind: str,
    target_kind: str,
    relation_type: str,
) -> str:
    normalized = normalized_name(name)
    if relation_type == "file":
        return "document"
    semantic = _semantic_field(normalized)
    if semantic:
        return semantic
    if source_kind in {"wire", "connector"} or target_kind in {"wire", "connector"}:
        return "connection"
    return "reference"


def _target_kind_hint(field: str) -> set[str] | None:
    normalized = _field_key(field)
    if "wire" in normalized or "signal" in normalized:
        return {"wire"}
    if any(token in normalized for token in ("conid", "term", "connector", "tunnel", "port")):
        return {"connector"}
    if "node" in normalized or "dco" in normalized or normalized in OWNERSHIP_FIELDS:
        return GRAPH_NODE_KINDS - {"wire", "connector"}
    return None


def _preferred_candidate(
    candidate_ids: Iterable[str],
    *,
    source: dict[str, Any],
    components: dict[str, dict[str, Any]],
    layers: dict[str, str],
    kind_hint: set[str] | None = None,
) -> tuple[str | None, bool, str, str]:
    candidates = [
        candidate_id
        for candidate_id in dict.fromkeys(candidate_ids)
        if candidate_id != source["id"]
    ]
    if kind_hint:
        hinted = [
            candidate_id
            for candidate_id in candidates
            if components[candidate_id].get("kind") in kind_hint
        ]
        if hinted:
            candidates = hinted
    if len(candidates) == 1:
        return candidates[0], False, "exact", "unique-id"

    same_file = [
        candidate_id
        for candidate_id in candidates
        if components[candidate_id]["file"] == source["file"]
    ]
    if len(same_file) == 1:
        return same_file[0], False, "contextual", "same-xml"
    if same_file:
        candidates = same_file

    source_layer = layers.get(source["id"], "other")
    same_layer = [
        candidate_id
        for candidate_id in candidates
        if layers.get(candidate_id) == source_layer
    ]
    if len(same_layer) == 1:
        return same_layer[0], False, "contextual", "same-layer"
    if same_layer:
        candidates = same_layer

    return None, bool(candidates), "unresolved", "ambiguous-id" if candidates else "missing-id"


def _graph_parent_id(
    component: dict[str, Any],
    *,
    components: dict[str, dict[str, Any]],
    graph_ids: set[str],
) -> str | None:
    parent_id = component.get("parent_id")
    while parent_id:
        if parent_id in graph_ids:
            return parent_id
        parent = components.get(parent_id)
        parent_id = parent.get("parent_id") if parent else None
    return None


def _node_public(
    component: dict[str, Any],
    *,
    aliases: set[str],
    layer: str,
    parent_id: str | None,
    child_ids: list[str],
) -> dict[str, Any]:
    bounds = component.get("bounds")
    points = component.get("points", [])
    position = None
    if bounds:
        position = {
            "x": bounds["x"],
            "y": bounds["y"],
            "width": bounds["width"],
            "height": bounds["height"],
            "source_property_id": bounds["property_id"],
            "source_property": bounds["name"],
            "coordinate_space": layer,
        }
    elif points:
        position = {
            "x": points[0]["x"],
            "y": points[0]["y"],
            "width": 0,
            "height": 0,
            "source_property_id": points[0]["property_id"],
            "source_property": points[0]["name"],
            "coordinate_space": layer,
        }
    return {
        "id": component["id"],
        "name": component["name"] or component["tag"],
        "kind": component["kind"],
        "class_name": component["class_name"],
        "uid": component["uid"],
        "aliases": sorted(aliases),
        "file": component["file"],
        "xml_path": component["path"],
        "role": component["role"],
        "tag": component["tag"],
        "parent_id": parent_id,
        "source_parent_id": component.get("parent_id"),
        "child_ids": child_ids,
        "property_count": len(component["property_ids"]),
        "editable_property_count": component["editable_property_count"],
        "layer": layer,
        "positioned": position is not None,
        "position": position,
        "points": list(points),
        "connection_ids": [],
        "net_ids": [],
    }


def _relationship_context(
    model: DatasetComponentModel,
    relationship: dict[str, Any],
) -> tuple[str, str]:
    prop = model.properties.get(relationship.get("property_id", ""))
    if prop is None:
        name = relationship.get("name") or relationship.get("type") or "reference"
        return name, name
    path = str(prop.get("path") or "")
    name = str(prop.get("name") or relationship.get("name") or "reference")
    if normalized_name(name) == "slreference":
        segments = [segment for segment in path.split("/") if segment]
        if len(segments) >= 2:
            name = segments[-2]
    return name, f"{path} {name}"


def build_model_graph(model: DatasetComponentModel) -> dict[str, Any]:
    """Build one dataset-wide graph from every parsed pylabview XML document.

    Only model-like components are emitted as graph nodes. XML files remain
    visible as documents, while UID, wireID, conID, DCO, terminal, node and
    explicit SL__reference values are resolved globally. Ambiguous references
    are reported instead of being guessed.
    """

    graph_ids = {
        component_id
        for component_id, component in model.components.items()
        if component.get("kind") in GRAPH_NODE_KINDS
    }
    layers = {
        component_id: _file_layer(
            component["file"],
            component.get("class_name", ""),
            component.get("name", ""),
            component.get("path", ""),
            component.get("kind", ""),
        )
        for component_id, component in model.components.items()
    }

    aliases_by_component: dict[str, set[str]] = {}
    alias_index: dict[str, list[str]] = defaultdict(list)
    for component_id in graph_ids:
        component = model.components[component_id]
        aliases = _component_aliases(model, component)
        aliases_by_component[component_id] = aliases
        for alias in aliases:
            alias_index[alias].append(component_id)

    graph_children: dict[str, list[str]] = defaultdict(list)
    graph_parents: dict[str, str | None] = {}
    for component_id in graph_ids:
        parent_id = _graph_parent_id(
            model.components[component_id],
            components=model.components,
            graph_ids=graph_ids,
        )
        graph_parents[component_id] = parent_id
        if parent_id:
            graph_children[parent_id].append(component_id)

    nodes = [
        _node_public(
            model.components[component_id],
            aliases=aliases_by_component[component_id],
            layer=layers[component_id],
            parent_id=graph_parents[component_id],
            child_ids=sorted(graph_children.get(component_id, [])),
        )
        for component_id in sorted(
            graph_ids,
            key=lambda item: (
                model.components[item]["file"],
                model.components[item]["path"],
                item,
            ),
        )
    ]
    node_by_id = {node["id"]: node for node in nodes}

    documents = []
    document_by_path: dict[str, dict[str, Any]] = {}
    for file in model.files:
        if getattr(file, "format", ""):
            continue
        root = model.components.get(file.root_component_id)
        document = {
            "id": f"document:{file.path}",
            "path": file.path,
            "root_tag": file.root_tag,
            "root_component_id": file.root_component_id or None,
            "layer": _file_layer(
                file.path,
                root.get("class_name", "") if root else "",
                root.get("name", "") if root else "",
            ),
            "model_ids": sorted(
                component_id
                for component_id in file.components
                if component_id in graph_ids
            ),
            "component_count": len(file.components),
            "model_count": sum(
                1 for component_id in file.components if component_id in graph_ids
            ),
            "elements": file.elements,
            "attributes": file.attributes,
            "scalar_values": file.scalar_values,
            "error": file.error,
            "outbound_document_ids": [],
            "inbound_document_ids": [],
        }
        documents.append(document)
        document_by_path[file.path] = document

    document_connections: list[dict[str, Any]] = []
    document_edge_keys: set[tuple[str, str, str]] = set()
    for relationship in model.relationships:
        if relationship.get("type") != "file":
            continue
        source_component = model.components.get(relationship["source_component_id"])
        if source_component is None:
            continue
        source_path = source_component["file"]
        target_path = str(relationship.get("target_file") or "").replace("\\", "/")
        key = (source_path, target_path, relationship.get("name", "file"))
        if key in document_edge_keys:
            continue
        document_edge_keys.add(key)
        resolved = bool(relationship.get("resolved") and target_path in document_by_path)
        document_connection = {
            "id": f"document-edge:{len(document_connections) + 1}",
            "source": f"document:{source_path}",
            "target": f"document:{target_path}" if resolved else None,
            "source_path": source_path,
            "target_path": target_path,
            "label": relationship.get("name") or "File",
            "property_id": relationship.get("property_id"),
            "resolved": resolved,
        }
        document_connections.append(document_connection)
        if resolved:
            source_document = document_by_path.get(source_path)
            target_document = document_by_path.get(target_path)
            if source_document and target_document:
                source_document["outbound_document_ids"].append(target_document["id"])
                target_document["inbound_document_ids"].append(source_document["id"])

    edges: list[dict[str, Any]] = []
    edge_by_key: dict[tuple[object, ...], dict[str, Any]] = {}
    unresolved: list[dict[str, Any]] = []
    confidence_rank = {"unresolved": 0, "inferred": 1, "contextual": 2, "exact": 3}

    def add_edge(
        *,
        source_id: str,
        target_id: str | None,
        edge_type: str,
        label: str,
        property_id: str | None = None,
        target_key: str = "",
        resolved: bool = True,
        ambiguous: bool = False,
        origin: str,
        confidence: str,
        resolution: str,
    ) -> None:
        if source_id not in graph_ids:
            return
        if target_id is not None and target_id not in graph_ids:
            target_id = None
            resolved = False
        if target_id is None:
            key: tuple[object, ...] = (
                source_id,
                None,
                edge_type,
                property_id,
                target_key,
                label,
            )
        else:
            key = (source_id, target_id, edge_type)
        existing = edge_by_key.get(key)
        evidence = {
            "origin": origin,
            "property_id": property_id,
            "label": label,
            "target_key": target_key,
            "confidence": confidence,
            "resolution": resolution,
        }
        if existing is not None:
            if label and label not in existing["labels"]:
                existing["labels"].append(label)
            if evidence not in existing["evidence"]:
                existing["evidence"].append(evidence)
            if confidence_rank.get(confidence, 0) > confidence_rank.get(
                existing["confidence"], 0
            ):
                existing["confidence"] = confidence
                existing["resolution"] = resolution
            return
        edge = {
            "id": f"edge:{len(edges) + 1}",
            "source": source_id,
            "target": target_id,
            "type": edge_type,
            "direction": (
                "undirected"
                if edge_type in {"connection", "mate"}
                else "directed"
            ),
            "label": label,
            "labels": [label] if label else [],
            "property_id": property_id,
            "target_key": target_key,
            "resolved": bool(resolved and target_id),
            "ambiguous": ambiguous,
            "origin": origin,
            "confidence": confidence,
            "resolution": resolution,
            "evidence": [evidence],
        }
        edge_by_key[key] = edge
        edges.append(edge)
        if not edge["resolved"]:
            unresolved.append(edge)

    for component_id in graph_ids:
        parent_id = graph_parents[component_id]
        if parent_id:
            add_edge(
                source_id=parent_id,
                target_id=component_id,
                edge_type="containment",
                label="contains",
                origin="xml-hierarchy",
                confidence="exact",
                resolution="nearest-model-parent",
            )

    for relationship in model.relationships:
        if relationship.get("type") == "file":
            continue
        source = model.components.get(relationship["source_component_id"])
        if source is None or source["id"] not in graph_ids:
            continue
        target_id = relationship.get("target_component_id")
        label, context_name = _relationship_context(model, relationship)
        ambiguous = False
        confidence = "exact" if relationship.get("resolved") else "unresolved"
        resolution = "global-uid" if relationship.get("resolved") else "unresolved-uid"
        if target_id is None and relationship.get("target_key"):
            candidate_ids: list[str] = []
            for variant in _key_variants(relationship["target_key"]):
                candidate_ids.extend(alias_index.get(variant, []))
            target_id, ambiguous, confidence, resolution = _preferred_candidate(
                candidate_ids,
                source=source,
                components=model.components,
                layers=layers,
                kind_hint=_target_kind_hint(normalized_name(context_name)),
            )
        target = model.components.get(target_id) if target_id else None
        edge_type = _relation_type(
            context_name,
            source.get("kind", ""),
            target.get("kind", "") if target else "",
            relationship.get("type", "reference"),
        )
        add_edge(
            source_id=source["id"],
            target_id=target_id,
            edge_type=edge_type,
            label=label,
            property_id=relationship.get("property_id"),
            target_key=relationship.get("target_key", ""),
            resolved=target_id is not None,
            ambiguous=ambiguous,
            origin="xml-reference",
            confidence=confidence,
            resolution=resolution,
        )

    # OF__wireID / OF__conId / DCO / owner fields are scalar integers in
    # pylabview XML. They need semantic interpretation before they can be
    # resolved as references.
    for prop in model.properties.values():
        source = model.components.get(prop["component_id"])
        if source is None or source["id"] not in graph_ids:
            continue
        field = _field_key(prop.get("field_name"))
        semantic = _semantic_field(field)
        if semantic is None:
            continue
        if field == "wireid" and source.get("kind") == "wire":
            continue
        if field == "conid" and source.get("kind") == "connector":
            continue
        raw_value = _value_text(prop)
        tokens = _numeric_tokens(raw_value)
        if not tokens and prop.get("value_type") in {"reference", "string"}:
            tokens = [raw_value]
        for token in tokens[:256]:
            candidate_ids: list[str] = []
            for variant in _key_variants(token):
                candidate_ids.extend(alias_index.get(variant, []))
            target_id, ambiguous, confidence, resolution = _preferred_candidate(
                candidate_ids,
                source=source,
                components=model.components,
                layers=layers,
                kind_hint=_target_kind_hint(field),
            )
            add_edge(
                source_id=source["id"],
                target_id=target_id,
                edge_type=semantic,
                label=prop.get("name") or field,
                property_id=prop["id"],
                target_key=token,
                resolved=target_id is not None,
                ambiguous=ambiguous,
                origin="labview-id",
                confidence=confidence,
                resolution=resolution,
            )

    connection_edges = [
        edge
        for edge in edges
        if edge["resolved"] and edge["type"] in {"connection", "mate"}
    ]
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in connection_edges:
        target_id = edge["target"]
        if target_id is None:
            continue
        adjacency[edge["source"]].add(target_id)
        adjacency[target_id].add(edge["source"])
        node_by_id[edge["source"]]["connection_ids"].append(edge["id"])
        node_by_id[target_id]["connection_ids"].append(edge["id"])

    nets: list[dict[str, Any]] = []
    for wire_id in sorted(
        component_id
        for component_id in graph_ids
        if model.components[component_id].get("kind") == "wire"
    ):
        wire = model.components[wire_id]
        direct = adjacency.get(wire_id, set())
        connector_ids = sorted(
            component_id
            for component_id in direct
            if model.components[component_id].get("kind") == "connector"
        )
        endpoint_ids = {
            component_id
            for component_id in direct
            if model.components[component_id].get("kind")
            not in {"wire", "connector"}
        }
        for connector_id in connector_ids:
            endpoint_ids.update(
                component_id
                for component_id in adjacency.get(connector_id, set())
                if component_id != wire_id
                and model.components[component_id].get("kind")
                not in {"wire", "connector"}
            )
        member_ids = sorted(
            {wire_id, *direct, *connector_ids, *endpoint_ids}
        )
        net_id = f"net:{wire_id}"
        net = {
            "id": net_id,
            "name": wire.get("name") or wire.get("uid") or "wire",
            "wire_id": wire_id,
            "connector_ids": connector_ids,
            "endpoint_ids": sorted(endpoint_ids),
            "member_ids": member_ids,
            "position": node_by_id[wire_id].get("position"),
            "points": node_by_id[wire_id].get("points", []),
        }
        nets.append(net)
        for member_id in member_ids:
            if net_id not in node_by_id[member_id]["net_ids"]:
                node_by_id[member_id]["net_ids"].append(net_id)

    # Connected groups expose independent data-flow islands and disconnected
    # models without inventing links that are absent from the XML.
    flow_adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in connection_edges:
        target_id = edge["target"]
        if target_id is None:
            continue
        flow_adjacency[edge["source"]].add(target_id)
        flow_adjacency[target_id].add(edge["source"])

    groups: list[dict[str, Any]] = []
    remaining = set(graph_ids)
    while remaining:
        start = min(remaining)
        queue = deque([start])
        members: list[str] = []
        remaining.remove(start)
        while queue:
            current = queue.popleft()
            members.append(current)
            for neighbor in flow_adjacency.get(current, set()):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    queue.append(neighbor)
        groups.append(
            {
                "id": f"group:{len(groups) + 1}",
                "member_ids": sorted(members),
                "positioned_members": sum(
                    1 for component_id in members
                    if node_by_id[component_id]["positioned"]
                ),
            }
        )
    groups.sort(key=lambda group: (-len(group["member_ids"]), group["id"]))

    unresolved_documents = [
        {
            "id": edge["id"],
            "scope": "document",
            "source": edge["source"],
            "target": None,
            "type": "document",
            "label": edge["label"],
            "target_key": edge["target_path"],
            "resolved": False,
            "ambiguous": False,
            "confidence": "unresolved",
            "resolution": "missing-file",
        }
        for edge in document_connections
        if not edge["resolved"]
    ]
    all_unresolved = [
        {**edge, "scope": "model"} for edge in unresolved
    ] + unresolved_documents

    edge_counts = Counter(edge["type"] for edge in edges)
    layer_counts = Counter(node["layer"] for node in nodes)
    kind_counts = Counter(node["kind"] for node in nodes)
    warnings = list(model.warnings)
    if all_unresolved:
        warnings.append(
            f"{len(all_unresolved)}件の参照を一意に解決できませんでした。"
        )
    if not connection_edges:
        warnings.append(
            "接続として解決できるwire / terminal / node参照が見つかりませんでした。"
        )

    return {
        "version": 2,
        "documents": documents,
        "document_connections": document_connections,
        "models": nodes,
        "connections": edges,
        "nets": nets,
        "groups": groups,
        "unresolved": all_unresolved,
        "summary": {
            "documents": len(documents),
            "document_connections": sum(
                1 for edge in document_connections if edge["resolved"]
            ),
            "models": len(nodes),
            "positioned_models": sum(1 for node in nodes if node["positioned"]),
            "connections": len(connection_edges),
            "all_edges": len(edges),
            "nets": len(nets),
            "groups": len(groups),
            "unresolved": len(all_unresolved),
            "kinds": dict(kind_counts.most_common()),
            "layers": dict(layer_counts.most_common()),
            "edge_types": dict(edge_counts.most_common()),
        },
        "warnings": warnings,
    }
