from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_density_assets_are_loaded_after_semantic_integrity() -> None:
    pages = read("pages.js")
    loader = read("vi-editor-runtime-fixes.js")

    assert "semantic-density.css?v=1" in pages
    assert "vi-editor-runtime-fixes.js?v=4" in pages
    assert "vi-editor-density.js?v=1" in loader
    assert loader.index("vi-editor-integrity") < loader.index("vi-editor-density")


def test_readable_fit_has_surface_specific_scale_limits() -> None:
    script = read("vi-editor-density.js")

    assert "'front-panel'" in script
    assert "'block-diagram'" in script
    assert "minReadableScale: 0.72" in script
    assert "maxReadableScale: 1.12" in script
    assert "minReadableScale: 0.62" in script
    assert "maxReadableScale: 1.02" in script
    assert "mode === 'overview'" in script
    assert "mode === 'focus'" in script
    assert "ABSOLUTE_MIN_SCALE" in script
    assert "ABSOLUTE_MAX_SCALE" in script
    assert "surfaceViews" in script
    assert "ResizeObserver" in script


def test_density_runtime_does_not_modify_vi_geometry() -> None:
    script = read("vi-editor-density.js")

    assert "S.local.set" not in script
    assert "S.dirty.add" not in script
    assert "source_property_id" not in script
    assert "modelGraphSvg.setAttribute" in script
    assert "viewBox" in script


def test_compact_chrome_reclaims_canvas_space() -> None:
    styles = read("semantic-density.css")

    assert "--commandbar-height: 40px" in styles
    assert "--navigation-width: 168px" in styles
    assert "--context-width: 248px" in styles
    assert "grid-template-columns: 184px minmax(0, 1fr)" in styles
    assert "grid-template-rows: 32px minmax(0, 1fr) 28px" in styles
    assert ".is-object-pane-collapsed" in styles
    assert ".vi-context-pane-collapsed" in styles


def test_zoom_lod_suppresses_clutter_without_hiding_selected_labels() -> None:
    styles = read("semantic-density.css")
    script = read("vi-editor-density.js")

    for level in ("overview", "compact", "normal", "detail"):
        assert f'data-vi-lod="{level}"' in styles
    assert ".vi-terminal-caption" in styles
    assert ".vi-terminal-type-dot" in styles
    assert ".vi-object.is-selected .vi-object-label" in styles
    assert "lodForScale" in script
    assert "vi-canvas-zoom-status" in script


def test_fit_overview_focus_and_pane_controls_exist() -> None:
    script = read("vi-editor-density.js")

    for control in (
        "model-graph-fit",
        "model-graph-overview",
        "model-graph-focus",
        "vi-toggle-object-pane",
        "vi-toggle-context-pane",
    ):
        assert control in script
    assert "実座標を保ったまま読みやすい倍率へ合わせる" in script
    assert "選択オブジェクトと接続へフォーカス" in script
