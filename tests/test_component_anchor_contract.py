from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_terminal_anchor_loads_between_projection_and_projected_fit() -> None:
    loader = read("vi-editor-runtime-fixes.js")

    assert "vi-editor-component-anchor.js?v=1" in loader
    assert loader.index("vi-editor-component-projection") < loader.index(
        "vi-editor-component-anchor"
    )
    assert loader.index("vi-editor-component-anchor") < loader.index(
        "vi-editor-component-fit"
    )


def test_terminal_anchor_uses_stable_native_owner_ratios() -> None:
    script = read("vi-editor-component-anchor.js")

    assert "terminalAnchors: new WeakMap()" in script
    assert "function anchorFor" in script
    assert "function isParentRelative" in script
    assert "parent-relative-native-bounds" in script
    assert "absolute-native-bounds" in script
    assert "ownerProjected.height * anchor.ratioY" in script
    assert "ownerProjected.x + ownerProjected.width" in script
    assert "runtime.terminalAnchors.set(item, anchor)" in script


def test_terminal_anchor_patches_projection_and_reroutes_wires() -> None:
    script = read("vi-editor-component-anchor.js")

    assert "P.projectBounds = anchoredProjectBounds" in script
    assert "P.projectedCenter = anchoredProjectedCenter" in script
    assert "P.projectedWirePoints = anchoredProjectedWirePoints" in script
    assert "function applyTerminal" in script
    assert "function applyWire" in script
    assert "terminalAnchorEndpoints" in script
    assert "orthogonalize(source, bends, target)" in script
    assert "renderCanvasWithTerminalAnchors" in script
    assert "renderAllWithTerminalAnchors" in script


def test_integrity_repair_uses_projected_centers_after_async_dom_changes() -> None:
    script = read("vi-editor-integrity.js")

    assert "VIComponentProjection?.ready" in script
    assert "VIComponentProjection.projectedCenter?.(item.id)" in script
    assert "orthogonal-projected-endpoints" in script
    assert "wire.target_terminal_ids?.[branchIndex]" in script
    assert "wire.target_object_ids?.[branchIndex]" in script


def test_terminal_anchor_only_changes_display_projection() -> None:
    script = read("vi-editor-component-anchor.js")

    assert "item.bounds =" not in script
    assert "S.local.set" not in script
    assert "S.dirty.add" not in script
    assert "source_property_id" not in script
    assert "setAttribute('viewBox'" not in script
    assert "vi-component-geometry" in script
    assert "vi-component-hit-target" in script
