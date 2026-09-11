from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_terminal_visual_loads_after_coordinate_space_before_consistency() -> None:
    loader = read("vi-editor-runtime-fixes.js")

    assert "vi-editor-component-terminal-visual.js?v=1" in loader
    assert "vi-editor-component-geometry-consistency.js?v=1" in loader
    assert "VIComponentTerminalVisual" in loader
    assert loader.index("vi-editor-component-coordinate-space") < loader.index(
        "vi-editor-component-terminal-visual"
    )
    assert loader.index("vi-editor-component-terminal-visual") < loader.index(
        "vi-editor-component-geometry-consistency"
    )
    assert loader.index("vi-editor-component-geometry-consistency") < loader.index(
        "vi-editor-component-fit"
    )


def test_oversized_semantic_terminal_envelopes_become_compact_ports() -> None:
    script = read("vi-editor-component-terminal-visual.js")

    assert "function terminalSize" in script
    assert "return isStructure(item) ? 10 : 8" in script
    assert "function cappedProjectBounds" in script
    assert "const oversized = finite(projected.width) > size" in script
    assert "x: centerX - size / 2" in script
    assert "y: centerY - size / 2" in script
    assert "width: size" in script
    assert "height: size" in script
    assert "terminal_visual_capped: oversized" in script
    assert "compact-port" in script


def test_native_ports_smaller_than_the_cap_are_not_enlarged() -> None:
    script = read("vi-editor-component-terminal-visual.js")

    assert "width: finite(projected.width)" in script
    assert "height: finite(projected.height)" in script
    assert ": projected.source" in script
    assert "Math.max(compact.width, compact.height)" in script
    assert "group.dataset.terminalVisualCapped" in script
    assert "group.classList.toggle" in script


def test_compact_terminal_ports_remain_directly_interactive() -> None:
    script = read("vi-editor-component-terminal-visual.js")

    assert "function ensureHitTarget" in script
    assert "Math.max(16, projected.width)" in script
    assert "Math.max(16, projected.height)" in script
    assert "pointer-events', 'all'" in script
    assert "compact-terminal-port" in script
    assert "has-compact-terminal-port" in script


def test_terminal_labels_and_resize_handles_follow_the_compact_body() -> None:
    script = read("vi-editor-component-terminal-visual.js")

    assert "function moveOverlay" in script
    assert "componentBaseTransform" in script
    assert ":scope > .vi-terminal-caption" in script
    assert ":scope > .vi-object-label" in script
    assert ":scope > .vi-resize-handle" in script
    assert "translateX + projected.width - 7" in script
    assert "translateY + projected.height - 7" in script


def test_terminal_visual_wraps_coordinate_space_projection() -> None:
    script = read("vi-editor-component-terminal-visual.js")

    assert "VIComponentCoordinateSpace.runtime?.observer?.disconnect?.()" in script
    assert "P.projectBounds = cappedProjectBounds" in script
    assert "P.decorate = function decorateWithCompactTerminals" in script
    assert "P.schedule = schedule" in script
    assert "coordinate.projectBounds = cappedProjectBounds" in script
    assert "renderCanvasWithCompactTerminalPorts" in script
    assert "renderAllWithCompactTerminalPorts" in script


def test_terminal_visual_does_not_modify_vi_geometry() -> None:
    script = read("vi-editor-component-terminal-visual.js")

    assert "item.bounds =" not in script
    assert "S.local.set" not in script
    assert "S.dirty.add" not in script
    assert "source_property_id" not in script
    assert "setAttribute('viewBox'" not in script
