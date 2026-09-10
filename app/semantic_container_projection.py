from __future__ import annotations

from typing import Any


def is_container(item: dict[str, Any]) -> bool:
    kind = str(item.get("kind") or "")
    return (
        item.get("data_type") in {"cluster", "array"}
        or kind == "structure"
        or kind.startswith(("cluster-", "array-"))
    )


def nearest_container(
    object_id: str,
    *,
    node_by_id: dict[str, dict[str, Any]],
    objects: dict[str, dict[str, Any]],
) -> str | None:
    node = node_by_id.get(object_id)
    parent_id = node.get("parent_id") if node else None
    seen: set[str] = set()
    while parent_id and parent_id not in seen:
        seen.add(parent_id)
        parent = objects.get(parent_id)
        child = objects[object_id]
        if (
            parent
            and parent.get("surface") == child.get("surface")
            and is_container(parent)
        ):
            return parent_id
        node = node_by_id.get(parent_id)
        parent_id = node.get("parent_id") if node else None
    return None


def _inside(parent: dict[str, Any], child: dict[str, Any], tolerance: float = 2) -> bool:
    return (
        child["x"] >= parent["x"] - tolerance
        and child["y"] >= parent["y"] - tolerance
        and child["x"] + child["width"] <= parent["x"] + parent["width"] + tolerance
        and child["y"] + child["height"] <= parent["y"] + parent["height"] + tolerance
    )


def _relative_fit(
    parent: dict[str, Any], child: dict[str, Any], tolerance: float = 2
) -> bool:
    return (
        child["x"] >= -tolerance
        and child["y"] >= -tolerance
        and child["x"] + child["width"] <= parent["width"] + tolerance
        and child["y"] + child["height"] <= parent["height"] + tolerance
    )


def project_child_bounds(child: dict[str, Any], parent: dict[str, Any]) -> None:
    bounds = child.get("bounds")
    parent_bounds = parent.get("bounds")
    if not bounds or not parent_bounds:
        return
    bounds["parent_object_id"] = parent["id"]
    bounds["source_x"] = float(bounds.get("x", 0))
    bounds["source_y"] = float(bounds.get("y", 0))
    if _inside(parent_bounds, bounds):
        bounds["source_coordinate_space"] = "absolute"
        return
    if not _relative_fit(parent_bounds, bounds):
        bounds["source_coordinate_space"] = "unknown"
        return
    raw_x = float(bounds.get("x", 0))
    raw_y = float(bounds.get("y", 0))
    bounds.update(
        {
            "raw_x": raw_x,
            "raw_y": raw_y,
            "x": float(parent_bounds.get("x", 0)) + raw_x,
            "y": float(parent_bounds.get("y", 0)) + raw_y,
            "relative_to_object_id": parent["id"],
            "source_coordinate_space": "parent-relative",
        }
    )


def annotate_container_hierarchy(
    objects_list: list[dict[str, Any]], graph: dict[str, Any]
) -> dict[str, Any]:
    objects = {item["id"]: item for item in objects_list}
    node_by_id = {node["id"]: node for node in graph.get("models", [])}
    for item in objects_list:
        if item.get("category") == "terminal":
            continue
        parent_id = nearest_container(
            item["id"], node_by_id=node_by_id, objects=objects
        )
        if not parent_id:
            continue
        parent = objects[parent_id]
        item["parent_object_id"] = parent_id
        parent["child_object_ids"].append(item["id"])
        parent["clip_children"] = True
        project_child_bounds(item, parent)

    def depth(object_id: str, seen: set[str] | None = None) -> int:
        seen = set() if seen is None else seen
        if object_id in seen:
            return 0
        seen.add(object_id)
        parent_id = objects[object_id].get("parent_object_id")
        if not parent_id or parent_id not in objects:
            return 0
        return 1 + depth(parent_id, seen)

    for item in objects_list:
        item["nesting_depth"] = depth(item["id"])
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

    clusters = [item for item in objects_list if item.get("data_type") == "cluster"]
    members = [
        item
        for item in objects_list
        if item.get("parent_object_id")
        and objects.get(item["parent_object_id"], {}).get("data_type") == "cluster"
    ]
    return {
        "clusters": len(clusters),
        "cluster_members": len(members),
        "hierarchy": {
            "roots": [
                item["id"] for item in objects_list if not item.get("parent_object_id")
            ],
            "containers": [item["id"] for item in objects_list if is_container(item)],
            "children_by_parent": {
                item["id"]: list(item["child_object_ids"])
                for item in objects_list
                if item.get("child_object_ids")
            },
        },
    }
