from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

from app.component_model import DatasetComponentModel
from app.semantic_integrity_runtime import finalize_semantic_vi

_implementation = import_module("app.lvkit_semantic")
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


def _discover_primary_document(
    dataset: Path,
    main_xml: Path | None,
) -> tuple[Path, Path | None, Path | None] | None:
    """Select the block diagram adjacent to the selected main XML.

    Comparing only file stems picks the wrong VI when a dataset contains two
    directories with the same VI filename. Directory identity must win before
    any global basename fallback.
    """

    diagrams = sorted(
        (
            path
            for path in dataset.rglob("*.xml")
            if _implementation._DIAGRAM_SUFFIX.search(path.name)
        ),
        key=lambda path: (len(path.parts), path.as_posix()),
    )
    if not diagrams:
        return None

    if main_xml is not None:
        main_xml = main_xml.resolve()
        stem = main_xml.stem.casefold()
        exact = [
            path
            for path in diagrams
            if path.resolve().parent == main_xml.parent
            and _implementation._DIAGRAM_SUFFIX.sub(
                "",
                path.name,
            ).casefold()
            == stem
        ]
        if exact:
            diagrams = exact + [path for path in diagrams if path not in exact]
        else:
            same_stem = [
                path
                for path in diagrams
                if _implementation._DIAGRAM_SUFFIX.sub(
                    "",
                    path.name,
                ).casefold()
                == stem
            ]
            if same_stem:
                diagrams = same_stem + [
                    path for path in diagrams if path not in same_stem
                ]

    bd_path = diagrams[0]
    base_name = _implementation._DIAGRAM_SUFFIX.sub("", bd_path.name)
    fp_path = next(
        (
            bd_path.with_name(f"{base_name}{suffix}")
            for suffix in _implementation._FRONT_PANEL_SUFFIXES
            if bd_path.with_name(f"{base_name}{suffix}").exists()
        ),
        None,
    )
    selected_main = (
        main_xml
        if main_xml is not None and main_xml.exists()
        else _implementation._candidate_main_xml(dataset, bd_path, main_xml)
    )
    return bd_path, fp_path, selected_main


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
    if result.get("integrity", {}).get("version") == 3:
        return result
    # No block diagram, parser unavailable, or controlled parse failure. These
    # paths still need stale summary/link cleanup even though no ParsedVI exists.
    return finalize_semantic_vi(result)


# The implementation performs global name lookup for these helpers at call
# time. Install adapters once so direct and service calls follow identical
# document selection, nullable-bounds handling, and integrity finalization.
_implementation._ComponentIndex = _NullableBoundsSafeIndex
_implementation._discover_primary_document = _discover_primary_document
_implementation._build_authoritative = _build_authoritative

__all__ = [
    "build_authoritative_semantic_vi",
    "_build_authoritative",
    "_discover_primary_document",
]
