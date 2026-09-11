from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_component_geometry_loads_before_density() -> None:
    pages = read("pages.js")
    loader = read("vi-editor-runtime-fixes.js")

    assert "semantic-density.css?v=2" in pages
    assert "semantic-density-runtime.css?v=2" in pages
    assert "vi-editor-runtime-fixes.js?v=6" in pages
    assert "vi-editor-component-geometry.js?v=1" in loader
    assert loader.index("vi-editor-integrity") < loader.index(
        "vi-editor-component-geometry"
    )
    assert loader.index("vi-editor-component-geometry") < loader.index(
        "vi-editor-density"
    )


def test_fallback_geometry_is_kind_specific_not_one_giant_box() -> None:
    script = read("vi-editor-component-geometry.js")

    for profile in (
        "terminal",
        "front-boolean",
        "front-field",
        "front-text",
        "front-container",
        "block-primitive",
        "block-constant",
        "block-subvi",
        "block-structure",
        "block-node",
    ):
        assert f"'{profile}'" in script or f"{profile}:" in script
    assert "width: 124" not in script
    assert "height: 44" not in script
    assert "kind-specific-fallback" in script
    assert "profileFor" in script
    assert "fallbackFor" in script


def test_geometry_layer_only_populates_display_fallbacks() -> None:
    script = read("vi-editor-component-geometry.js")

    assert "S.fallback.set" in script
    assert "S.local.set" not in script
    assert "S.dirty.add" not in script
    assert "source_property_id" not in script
    assert "apiRequest(" not in script
    assert "item.bounds =" not in script
    assert "delete item.bounds" not in script


def test_authoritative_bounds_are_not_rescaled_without_evidence() -> None:
    script = read("vi-editor-component-geometry.js")

    assert "hasAuthoritativeBounds" in script
    assert "if (hasAuthoritativeBounds(item)) return" in script
    assert "authoritative-bounds" in script
    assert "geometry_source" in script


def test_geometry_audit_exposes_native_and_screen_dimensions() -> None:
    script = read("vi-editor-component-geometry.js")

    assert "body_screen_width" in script
    assert "body_screen_height" in script
    assert "effective_width" in script
    assert "effective_height" in script
    assert "median_screen_width" in script
    assert "median_screen_height" in script
    assert "VIComponentGeometry" in script
    assert "report: () => runtime.report || measure()" in script


def test_normal_web_ui_is_not_compacted_by_density_styles() -> None:
    styles = read("semantic-density.css")
    runtime = read("semantic-density-runtime.css")

    for compact_override in (
        "--commandbar-height: 40px",
        "--navigation-width: 168px",
        "--context-width: 248px",
        "font-size: 7px",
    ):
        assert compact_override not in styles
    assert "grid-template-rows: 54px 44px auto minmax(0, 1fr) auto" in runtime
    assert "grid-template-rows: 42px minmax(0, 1fr) 36px" in runtime
    assert "height: 42px" in runtime
    assert "height: 30px" in runtime


def test_density_styles_only_reduce_canvas_annotation_detail() -> None:
    styles = read("semantic-density.css")

    assert 'data-vi-lod="overview"' in styles
    assert ".vi-object-label" in styles
    assert ".vi-terminal-caption" in styles
    assert ".azure-command-bar" not in styles
    assert ".azure-navigation" not in styles
    assert ".context-file-name" not in styles
    assert ".model-inspector-grid" not in styles
