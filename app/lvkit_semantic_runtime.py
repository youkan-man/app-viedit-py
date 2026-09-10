from __future__ import annotations

from typing import Any

from . import lvkit_semantic as _implementation


class _NullableBoundsSafeIndex(_implementation._ComponentIndex):
    """Normalize component rows whose optional bounds field is explicitly null."""

    def find(
        self,
        uid: str | None,
        file_hint: str | None,
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


# The component analyzer intentionally emits ``bounds: null`` for semantic
# objects that have no directly editable rectangle. The authoritative parser
# can still place their terminals from layout coordinates, so normalize those
# rows before the implementation derives terminal sizes.
_implementation._ComponentIndex = _NullableBoundsSafeIndex

build_authoritative_semantic_vi = _implementation.build_authoritative_semantic_vi
_build_authoritative = _implementation._build_authoritative

__all__ = ["build_authoritative_semantic_vi", "_build_authoritative"]
