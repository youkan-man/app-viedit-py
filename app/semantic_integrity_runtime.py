from __future__ import annotations

from typing import Any

from .semantic_integrity_v2 import finalize_semantic_vi as _finalize_v2


def finalize_semantic_vi(
    vi: dict[str, Any],
    *,
    parsed: object | None = None,
) -> dict[str, Any]:
    """Apply integrity v2 while preserving cumulative removals on re-entry."""

    previous = vi.get("integrity") or {}
    previous_version = int(previous.get("version") or 0)
    previous_removed = (
        max(0, int(previous.get("dangling_wires_removed") or 0))
        if previous_version >= 2
        else 0
    )
    result = _finalize_v2(vi, parsed=parsed)
    current_removed = max(
        0,
        int(result.get("integrity", {}).get("dangling_wires_removed") or 0),
    )
    removed_total = previous_removed + current_removed
    integrity = result.setdefault("integrity", {})
    integrity["version"] = 3
    integrity["dangling_wires_removed"] = removed_total
    input_unresolved = max(
        0,
        int(integrity.get("input_unresolved_wires") or 0),
    )
    result.setdefault("summary", {})["unresolved_wires"] = (
        input_unresolved + removed_total
    )
    result["version"] = max(6, int(result.get("version") or 1))
    return result


__all__ = ["finalize_semantic_vi"]
