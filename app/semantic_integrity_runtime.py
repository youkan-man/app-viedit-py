from __future__ import annotations

import copy
from typing import Any

from .semantic_integrity_v2 import finalize_semantic_vi as _finalize_v2


def _prepare_endpoint_roles(vi: dict[str, Any]) -> dict[str, Any]:
    """Ensure malformed endpoint records fail visibly instead of crashing.

    Authoritative parser output should always point a wire at terminal objects.
    Real VIs exposed a legacy projection where a wire endpoint could reference
    an object whose category was not normalized to ``terminal``. Integrity v2
    records per-wire roles on endpoints; pre-seeding the list lets that pass
    complete and report the semantic mismatch in diagnostics rather than
    aborting the entire model response with ``KeyError``.
    """

    prepared = copy.deepcopy(vi)
    objects = {
        str(item.get("id")): item
        for item in prepared.get("objects", [])
        if item.get("id")
    }
    for wire in prepared.get("wires", []):
        endpoint_ids = [
            wire.get("source_terminal_id"),
            *(wire.get("target_terminal_ids") or []),
        ]
        for endpoint_id in endpoint_ids:
            endpoint = objects.get(str(endpoint_id))
            if endpoint is not None:
                endpoint.setdefault("wire_roles", [])
    return prepared


def _nonterminal_endpoint_ids(result: dict[str, Any]) -> list[str]:
    objects = {
        str(item.get("id")): item
        for item in result.get("objects", [])
        if item.get("id")
    }
    endpoint_ids: list[str] = []
    for wire in result.get("wires", []):
        for endpoint_id in [
            wire.get("source_terminal_id"),
            *(wire.get("target_terminal_ids") or []),
        ]:
            endpoint = objects.get(str(endpoint_id))
            if endpoint is not None and endpoint.get("category") != "terminal":
                endpoint_ids.append(str(endpoint_id))
    return list(dict.fromkeys(endpoint_ids))


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
    prepared = _prepare_endpoint_roles(vi)
    result = _finalize_v2(prepared, parsed=parsed)
    current_removed = max(
        0,
        int(result.get("integrity", {}).get("dangling_wires_removed") or 0),
    )
    removed_total = previous_removed + current_removed
    integrity = result.setdefault("integrity", {})
    integrity["version"] = 3
    integrity["dangling_wires_removed"] = removed_total
    nonterminal_endpoints = _nonterminal_endpoint_ids(result)
    integrity["nonterminal_wire_endpoints"] = len(nonterminal_endpoints)
    integrity["nonterminal_wire_endpoint_ids"] = nonterminal_endpoints[:50]
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
