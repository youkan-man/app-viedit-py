from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_projection_loads_after_readability_and_before_projected_fit() -> None:
    pages = read("pages.js")
    loader = read("vi-editor-runtime-fixes.js")

    assert "semantic-density.css?v=2" in pages
    assert "semantic-density-runtime.css?v=2" in pages
    assert "vi-editor-runtime-fixes.js?v=6" in pages
    assert "vi-editor-component-projection.js?v=1" in loader
    assert "vi-editor-component-fit.js?v=1" in loader
    assert loader.index("vi-editor-readability") < loader.index(
        "vi-editor-component-projection"
    )
    assert loader.index("vi-editor-component-projection") < loader.index(
        "vi-editor-component-fit"
    )


def test_normal_application_chrome_is_not_scaled_or_compacted() -> None:
    density = read("semantic-density.css")
    runtime = read("semantic-density-runtime.css")
    shell = read("azure-shell.css")
    layout = read("semantic-workspace-layout.css")

    assert "--commandbar-height: 40px" not in density
    assert "--navigation-width: 168px" not in density
    assert "--context-width: 248px" not in density
    assert ".azure-command-bar" not in density
    assert ".azure-navigation" not in density
    assert ".azure-context-pane" not in density
    assert "--commandbar-height: 48px" in shell
    assert "--navigation-width: 216px" in shell
    assert "--context-width: 292px" in shell
    assert "grid-template-columns: 224px minmax(0, 1fr)" in layout
    assert "grid-template-rows: 54px 44px auto minmax(0, 1fr) auto" in layout
    assert "grid-template-rows: 42px minmax(0, 1fr) 36px" in layout
    assert "font-size: 7px" not in runtime


def test_projection_scales_only_component_geometry() -> None:
    script = read("vi-editor-component-projection.js")

    assert "vi-component-geometry" in script
    assert "GEOMETRY_EXCLUSIONS" in script
    for selector in (
        ".vi-object-label",
        ".vi-terminal-caption",
        ".vi-cluster-count",
        ".vi-structure-frame-badge",
        ".vi-resize-handle",
        ".vi-component-hit-target",
    ):
        assert selector in script
    assert "wrapper.setAttribute" in script
    assert "scale(${projected.factor_x} ${projected.factor_y})" in script
    assert "group.dataset.projectedWidth" in script
    assert "group.dataset.projectedHeight" in script


def test_native_bounds_and_edit_state_are_not_changed_during_projection() -> None:
    script = read("vi-editor-component-projection.js")
    before_resize = script.split("function moveResize", 1)[0]

    assert "item.bounds =" not in script
    assert "item.bounds." not in script
    assert "source_property_id" not in script
    assert "S.local.set" not in before_resize
    assert "S.dirty.add" not in before_resize
    assert "logicalBounds" in script
    assert "projectBounds" in script
    assert "native_visual_bounds" in script
    assert "source: 'native-visual-bounds'" in script


def test_surface_and_kind_specific_body_factors_exist() -> None:
    script = read("vi-editor-component-projection.js")

    assert "const SURFACE_FACTORS" in script
    assert "'front-panel'" in script
    assert "'block-diagram'" in script
    for key in (
        "boolean",
        "numeric",
        "string",
        "path",
        "ring",
        "table",
        "primitive",
        "constant",
        "subvi",
        "terminal",
    ):
        assert key in script
    assert "function isContainer" in script
    assert "if (!item || isContainer(item)) return 1" in script


def test_terminals_and_wires_follow_projected_component_bodies() -> None:
    script = read("vi-editor-component-projection.js")

    assert "function projectTerminal" in script
    assert "ownerProjected" in script
    assert "owner-boundary-terminal" in script
    assert "function projectedCenter" in script
    assert "function projectedWirePoints" in script
    assert "orthogonalize(source, bends, target)" in script
    assert "group.dataset.projectedEndpoints = 'true'" in script
    assert "vi-wire-hit" in script


def test_projection_keeps_small_components_clickable_and_resizable() -> None:
    script = read("vi-editor-component-projection.js")

    assert "function ensureHitTarget" in script
    assert "Math.max(16, projected.width)" in script
    assert "pointer-events', 'all'" in script
    assert "function beginResize" in script
    assert "function moveResize" in script
    assert "displayDeltaX / Math.max(0.05, gesture.factorX)" in script
    assert "displayDeltaY / Math.max(0.05, gesture.factorY)" in script
    assert "S.local.set(gesture.id" in script
    assert "S.dirty.add(gesture.id)" in script


def test_projected_fit_uses_projected_extents_not_raw_vi_footprints() -> None:
    fit = read("vi-editor-component-fit.js")

    assert "projection()?.projectBounds" in fit
    assert "projection()?.projectedWirePoints" in fit
    assert "function projectedContentBounds" in fit
    assert "function representativeMetrics" in fit
    assert "mode === 'overview'" in fit
    assert "mode === 'focus'" in fit
    assert "componentScale" in fit
    assert "minimumScale: 0.42" in fit
    assert "minimumScale: 0.50" in fit
    assert "minimumScale: 1" not in fit
    assert "activeDensity.fit = fit" in fit


def test_projection_reports_logical_and_projected_geometry() -> None:
    script = read("vi-editor-component-projection.js")

    assert "function projectedMetrics" in script
    assert "componentScaleX" in script
    assert "componentScaleY" in script
    assert "projectedX" in script
    assert "projectedY" in script
    assert "projectedWidth" in script
    assert "projectedHeight" in script
    assert "projectedMetrics" in script
