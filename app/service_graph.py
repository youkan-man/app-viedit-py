from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .errors import AppError
from .filesystem import JobPaths, resolve_inside, utc_now_iso
from .lvkit_semantic_runtime import build_authoritative_semantic_vi
from .model_graph import build_model_graph
from .semantic_enrichment import enrich_semantic_vi
from .semantic_vi import build_semantic_vi


def _existing_inside(base: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        candidate = resolve_inside(base, Path(value))
    except AppError:
        return None
    return candidate if candidate.exists() and candidate.is_file() else None


def _resolve_primary_main_xml(paths: JobPaths, metadata: dict[str, Any]) -> Path | None:
    """Resolve metadata paths using the base they were written against.

    ``metadata.main_xml`` is dataset-relative, while
    ``metadata.artifacts.main_xml`` is job-root-relative. Treating the former as
    job-root-relative silently selected the alphabetically first VI whenever a
    converted dataset contained several VIs.
    """

    direct = _existing_inside(paths.dataset, metadata.get("main_xml"))
    if direct is not None:
        return direct
    artifacts = metadata.get("artifacts")
    artifact_value = artifacts.get("main_xml") if isinstance(artifacts, dict) else None
    artifact = _existing_inside(paths.root, artifact_value)
    if artifact is not None:
        return artifact
    # Backward compatibility for older jobs that stored main_xml root-relative.
    return _existing_inside(paths.root, metadata.get("main_xml"))


def _semantic_cache_key(
    fingerprint: tuple[tuple[str, int, int], ...],
    paths: JobPaths,
    main_xml: Path | None,
) -> tuple[tuple[tuple[str, int, int], ...], str, int, int]:
    if main_xml is None:
        return fingerprint, "", 0, 0
    try:
        relative = main_xml.relative_to(paths.root).as_posix()
    except ValueError:
        relative = main_xml.as_posix()
    stat = main_xml.stat()
    return fingerprint, relative, stat.st_size, stat.st_mtime_ns


class GraphServiceMixin:
    """Attach raw diagnostics plus an authoritative editor-facing VI model."""

    def invalidate_component_model(self, paths: JobPaths) -> None:
        super().invalidate_component_model(paths)
        _, lock = self._component_cache_state()
        with lock:
            if hasattr(self, "_model_graph_cache"):
                self._model_graph_cache.pop(paths.job_id, None)
            if hasattr(self, "_semantic_vi_cache"):
                self._semantic_vi_cache.pop(paths.job_id, None)

    def component_model_summary(self, paths: JobPaths) -> dict[str, Any]:
        payload = super().component_model_summary(paths)
        model = self._load_component_model(paths)
        fingerprint = self._component_fingerprint(paths)
        _, lock = self._component_cache_state()
        with lock:
            if not hasattr(self, "_model_graph_cache"):
                self._model_graph_cache = {}
            cached_graph = self._model_graph_cache.get(paths.job_id)
            if cached_graph and cached_graph[0] == fingerprint:
                graph = cached_graph[1]
            else:
                graph = build_model_graph(model)
                self._model_graph_cache[paths.job_id] = (fingerprint, graph)

        metadata = self.store.load(paths)
        main_xml = _resolve_primary_main_xml(paths, metadata)
        cache_key = _semantic_cache_key(fingerprint, paths, main_xml)
        with lock:
            if not hasattr(self, "_semantic_vi_cache"):
                self._semantic_vi_cache = {}
            cached_semantic = self._semantic_vi_cache.get(paths.job_id)
            semantic = (
                copy.deepcopy(cached_semantic[1])
                if cached_semantic and cached_semantic[0] == cache_key
                else None
            )

        if semantic is None:
            fallback = enrich_semantic_vi(model, graph, build_semantic_vi(model, graph))
            semantic = build_authoritative_semantic_vi(
                paths.dataset,
                model,
                fallback,
                main_xml=main_xml,
            )
            with lock:
                self._semantic_vi_cache[paths.job_id] = (
                    cache_key,
                    copy.deepcopy(semantic),
                )

        payload["graph"] = graph
        payload["vi"] = semantic
        payload["graph_generated_at"] = utc_now_iso()
        payload["primary_main_xml"] = (
            main_xml.relative_to(paths.dataset).as_posix()
            if main_xml is not None and main_xml.is_relative_to(paths.dataset)
            else None
        )
        return payload
