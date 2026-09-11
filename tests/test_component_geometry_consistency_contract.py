from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_geometry_consistency_loads_after_terminal_visual_before_fit() -> None:
    loader = read("vi-editor-runtime-fixes.js")

    assert "vi-editor-component-geometry-consistency.js?v=1" in loader
    assert "VIComponentGeometryConsistency" in loader
    assert loader.index("vi-editor-component-terminal-visual") < loader.index(
        "vi-editor-component-geometry-consistency"
    )
    assert loader.index("vi-editor-component-geometry-consistency") < loader.index(
        "vi-editor-component-fit"
    )


def test_minimum_projected_dimensions_drive_independent_svg_scale_factors() -> None:
    script = read("vi-editor-component-geometry-consistency.js")

    assert "function normalizedProjectBounds" in script
    assert "factor_x: width / Math.max(1, finite(logical.width, 1))" in script
    assert "factor_y: height / Math.max(1, finite(logical.height, 1))" in script
    assert "projection_scale_consistent: true" in script
    assert "scale(${projected.factor_x} ${projected.factor_y})" in script
    assert "projectionScaleConsistent" in script


def test_consistency_layer_wraps_final_projection_before_fit_metrics() -> None:
    script = read("vi-editor-component-geometry-consistency.js")

    assert "runtime.originalProjectBounds = P.projectBounds" in script
    assert "P.projectBounds = normalizedProjectBounds" in script
    assert "P.decorate = function decorateWithConsistentGeometry" in script
    assert "P.schedule = schedule" in script
    assert "P.decorate?.()" in script


def test_consistency_layer_only_changes_display_projection() -> None:
    script = read("vi-editor-component-geometry-consistency.js")

    assert "item.bounds =" not in script
    assert "S.local.set" not in script
    assert "S.dirty.add" not in script
    assert "source_property_id" not in script
    assert "setAttribute('viewBox'" not in script
