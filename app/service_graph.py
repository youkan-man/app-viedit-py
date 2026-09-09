from __future__ import annotations

from typing import Any

from .filesystem import JobPaths, utc_now_iso
from .model_graph import build_model_graph
from .semantic_vi import build_semantic_vi


class GraphServiceMixin:
    """Attach cached connectivity and an editor-facing semantic VI model."""

    def component_model_summary(self, paths: JobPaths) -> dict[str, Any]:
        payload = super().component_model_summary(paths)
        model = self._load_component_model(paths)
        fingerprint = self._component_fingerprint(paths)
        _, lock = self._component_cache_state()
        with lock:
            if not hasattr(self, "_model_graph_cache"):
                self._model_graph_cache = {}
            cached = self._model_graph_cache.get(paths.job_id)
            if cached and cached[0] == fingerprint:
                graph = cached[1]
            else:
                graph = build_model_graph(model)
                self._model_graph_cache[paths.job_id] = (fingerprint, graph)
        payload["graph"] = graph
        payload["vi"] = build_semantic_vi(model, graph)
        payload["graph_generated_at"] = utc_now_iso()
        return payload
