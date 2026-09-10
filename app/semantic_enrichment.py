from __future__ import annotations

import copy
from typing import Any

from .component_model import DatasetComponentModel
from .semantic_container_projection import annotate_container_hierarchy
from .semantic_type_projection import annotate_semantic_types


def enrich_semantic_vi(
    model: DatasetComponentModel,
    graph: dict[str, Any],
    semantic_vi: dict[str, Any],
) -> dict[str, Any]:
    """Add hierarchy and rendering hints without exposing XML as the UI model."""

    del model  # Kept in the public signature for future descriptor joins.
    result = copy.deepcopy(semantic_vi)
    objects = result.get("objects", [])
    annotate_semantic_types(objects)
    hierarchy = annotate_container_hierarchy(objects, graph)
    objects.sort(
        key=lambda item: (
            0 if item.get("surface") == "front-panel" else 1,
            item.get("nesting_depth", 0),
            float((item.get("bounds") or {}).get("y", 10**9)),
            float((item.get("bounds") or {}).get("x", 10**9)),
            item.get("name") or "",
            item["id"],
        )
    )
    result.setdefault("summary", {}).update(
        {
            "clusters": hierarchy["clusters"],
            "cluster_members": hierarchy["cluster_members"],
        }
    )
    result["hierarchy"] = hierarchy["hierarchy"]
    result["version"] = max(2, int(result.get("version") or 1))
    return result
