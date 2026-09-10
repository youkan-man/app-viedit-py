from __future__ import annotations

from pathlib import Path
from typing import Any

from . import lvkit_semantic as _implementation
from .component_model import DatasetComponentModel
from .semantic_integrity import finalize_semantic_vi


_BaseComponentIndex = _implementation._ComponentIndex
_OriginalBuildAuthoritative = _implementation._build_authoritative
_OriginalBuildPublic = _implementation.build_authoritative_semantic_vi


class _NullableBoundsSafeIndex(_BaseComponentIndex):
    """Normalize component rows whose optional bounds field is explicitly null."""

    def find(
        self,
        uid: str | None,
        file_hint: str | Path | None,
        *,
        class_hint: str | None = None,
        kind_hint: str | None = None,
    ) -> dict[str, Any] | None:
        component = super().find(
            uid,
            file_hint,
            class_hint=class_hint,
            kind_hint=kind_hint,
        )
        if component is None or component.get("bounds") is not None:
            return component
        return {**component, "bounds": {}}


def _build_authoritative(
    dataset: Path,
    model: DatasetComponentModel,
    fallback_vi: dict[str, Any],
    parsed: object,
    bd_path: Path,
    fp_path: Path | None,
    main_path: Path | None,
) -> dict[str, Any]:
    result = _OriginalBuildAuthoritative(
        dataset,
        model,
        fallback_vi,
        parsed,
        bd_path,
        fp_path,
        main_path,
    )
    return finalize_semantic_vi(result, parsed=parsed)


def build_authoritative_semantic_vi(
    dataset: Path,
    model: DatasetComponentModel,
    fallback_vi: dict[str, Any],
    *,
    main_xml: Path | None = None,
) -> dict[str, Any]:
    result = _OriginalBuildPublic(
        dataset,
        model,
        fallback_vi,
        main_xml=main_xml,
    )
    if result.get("integrity", {}).get("version") == 1:
        return result
    # No block diagram, parser unavailable, or controlled parse failure. These
    # paths still need stale summary/link cleanup even though no ParsedVI exists.
    return finalize_semantic_vi(result)


# The implementation performs global name lookup for both helpers at call time.
# Install the adapters once so every direct and service call follows the same
# integrity path without forking the parser implementation.
_implementation._ComponentIndex = _NullableBoundsSafeIndex
_implementation._build_authoritative = _build_authoritative

__all__ = ["build_authoritative_semantic_vi", "_build_authoritative"]
