from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_component_projection_is_loaded_without_compacting_application_ui() -> None:
    pages = read("pages.js")
    projection = read("vi-editor-component-projection.js")
    fit = read("vi-editor-component-fit.js")
    density_styles = read("semantic-density.css")

    assert "vi-editor-component-projection.js?v=1" in pages
    assert "vi-editor-component-fit.js?v=1" in pages
    assert "VIComponentProjection" in projection
    assert "VIComponentFit" in fit
    assert "--commandbar-height: 40px" not in density_styles
    assert "--navigation-width: 168px" not in density_styles
    assert "--context-width: 248px" not in density_styles


def test_projection_scales_component_geometry_not_labels_or_chrome() -> None:
    script = read("vi-editor-component-projection.js")

    assert "vi-component-geometry" in script
    assert "vi-object-label" in script
    assert "vi-terminal-caption" in script
    assert "vi-resize-handle" in script
    assert "factorFor" in script
    assert "front-panel" in script
    assert "block-diagram" in script
    assert "isContainer" in script
    assert "structure_frames" in script
    assert "cluster-container" in script
    assert "array-container" in script
    assert ".azure-command-bar" not in script
    assert ".azure-navigation" not in script
    assert ".azure-context-pane" not in script


def test_projection_prefers_native_visual_geometry_before_fallback_scaling() -> None:
    script = read("vi-editor-component-projection.js")

    for field in (
        "visual_bounds",
        "display_bounds",
        "body_bounds",
        "icon_bounds",
        "native_visual_bounds",
    ):
        assert field in script
    assert "native-visual-bounds" in script
    assert "semantic-fallback" in script


def test_terminal_projection_and_wires_share_projected_endpoints() -> None:
    script = read("vi-editor-component-projection.js")

    assert "owner-relative-terminal" in script
    assert "projectedCenter" in script
    assert "projectedWirePoints" in script
    assert "applyWireProjection" in script
    assert "targetTerminalId" in script
    assert "pathFromPoints" in script
    assert "projectedEndpoints" in script


def test_resize_inverts_projection_without_overwriting_source_bounds() -> None:
    script = read("vi-editor-component-projection.js")

    assert "displayDeltaX /" in script
    assert "displayDeltaY /" in script
    assert "gesture.factorX" in script
    assert "gesture.factorY" in script
    assert "S.local.set" in script
    assert "S.dirty.add" in script
    assert "item.bounds =" not in script
    assert "source_property_id" not in script
    assert "apiRequest(" not in script


def test_readable_fit_uses_projected_component_metrics_not_fixed_100_percent() -> None:
    script = read("vi-editor-component-fit.js")

    assert "representativeMetrics" in script
    assert "projectedContentBounds" in script
    assert "policy.width / metrics.medianWidth" in script
    assert "policy.height / metrics.medianHeight" in script
    assert "mode === 'overview'" in script
    assert "mode === 'focus'" in script
    assert "minimumScale: 0.62" in script
    assert "minimumScale: 0.68" in script
    assert "minimumScale: 1" not in script
