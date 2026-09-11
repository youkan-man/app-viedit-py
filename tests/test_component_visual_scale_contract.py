from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_component_scale_assets_load_after_density_memory() -> None:
    pages = read("pages.js")
    loader = read("vi-editor-runtime-fixes.js")

    assert "semantic-component-scale.css?v=1" in pages
    assert "vi-editor-runtime-fixes.js?v=6" in pages
    assert "vi-editor-component-scale.js?v=1" in loader
    assert loader.index("vi-editor-density-memory") < loader.index(
        "vi-editor-component-scale"
    )
    assert loader.index("vi-editor-readability") < loader.index(
        "vi-editor-component-scale"
    )


def test_readable_fit_never_auto_shrinks_vi_components() -> None:
    script = read("vi-editor-component-scale.js")

    assert "'front-panel'" in script
    assert "'block-diagram'" in script
    assert "minScale: 1" in script
    assert "maxScale: 1.45" in script
    assert "maxScale: 1.35" in script
    assert "targetWidth: 96" in script
    assert "targetHeight: 40" in script
    assert "targetWidth: 50" in script
    assert "targetHeight: 38" in script
    assert "Math.max(1, measurement.scale || 1)" in script
    assert "mode === 'readable' || mode === 'fit'" in script


def test_scale_is_derived_from_components_not_page_chrome() -> None:
    script = read("vi-editor-component-scale.js")

    assert "representativeItems" in script
    assert "isRepresentative" in script
    assert "item.category === 'control'" in script
    assert "item.category === 'indicator'" in script
    assert "item.category === 'node'" in script
    assert "item.category === 'terminal'" not in script
    assert "medianWidth" in script
    assert "medianHeight" in script
    assert "centerFor" in script
    assert "getBoundingClientRect" in script


def test_unreliable_and_inactive_geometry_does_not_drive_fit() -> None:
    script = read("vi-editor-component-scale.js")

    assert "item.positioned === false" in script
    assert "item.hidden_by_structure_frame" in script
    assert "block-diagram-inactive" in script
    assert "source.includes('fallback')" in script
    assert "source.includes('synthetic-grid')" in script
    assert "robustRecords" in script


def test_component_scale_layer_does_not_write_vi_geometry() -> None:
    script = read("vi-editor-component-scale.js")

    assert "S.local.set" not in script
    assert "S.dirty.add" not in script
    assert "source_property_id" not in script
    assert "item.bounds =" not in script
    assert "applyBox" in script
    assert "viewBox" in script


def test_normal_workbench_chrome_is_restored() -> None:
    styles = read("semantic-component-scale.css")

    for declaration in (
        "--commandbar-height: 48px",
        "--navigation-width: 216px",
        "--context-width: 292px",
        "grid-template-columns: 224px minmax(0, 1fr)",
        "grid-template-rows: 54px 44px auto minmax(0, 1fr) auto",
        "grid-template-rows: 42px minmax(0, 1fr) 36px",
    ):
        assert declaration in styles
    assert ".vi-object-list-item" in styles
    assert "font-size: 10px" in styles


def test_overview_mode_still_uses_the_original_whole_vi_fit() -> None:
    script = read("vi-editor-component-scale.js")

    assert "runtime.originalDensityFit(...args)" in script
    assert "runtime.originalEditorFit(...args)" in script
    assert "mode === 'overview'" not in script.split(
        "if (mode === 'readable' || mode === 'fit')", 1
    )[0]
