from __future__ import annotations

from pathlib import Path
from typing import Any

from .filesystem import JobPaths, resolve_inside, utc_now_iso
from .lvkit_semantic_runtime import build_authoritative_semantic_vi
from .model_graph import build_model_graph
from .semantic_enrichment import enrich_semantic_vi
from .semantic_vi import build_semantic_vi


class GraphServiceMixin:
    """Attach raw diagnostics plus an authoritative editor-facing VI model."""

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

        metadata = self.store.load(paths)
        main_value = metadata.get("main_xml")
        if not isinstance(main_value, str):
            artifacts = metadata.get("artifacts", {})
            main_value = artifacts.get("main_xml") if isinstance(artifacts, dict) else None
        main_xml = (
            resolve_inside(paths.root, Path(main_value))
            if isinstance(main_value, str)
            else None
        )
        if main_xml is not None and not main_xml.exists():
            main_xml = None

        payload["graph"] = graph
        fallback = enrich_semantic_vi(model, graph, build_semantic_vi(model, graph))
        payload["vi"] = build_authoritative_semantic_vi(
            paths.dataset,
            model,
            fallback,
            main_xml=main_xml,
        )
        payload["graph_generated_at"] = utc_now_iso()
        return payload
