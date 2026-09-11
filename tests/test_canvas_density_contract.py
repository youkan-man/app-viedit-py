from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_density_assets_are_loaded_after_component_geometry() -> None:
    pages = read("pages.js")
    loader = read("vi-editor-runtime-fixes.js")

    assert "semantic-density.css?v=2" in pages
    assert "semantic-density-runtime.css?v=2" in pages
    assert pages.index("semantic-density.css?v=2") < pages.index(
        "semantic-density-runtime.css?v=2"
    )
    assert "semantic-readability.css?v=1" in pages
    assert "vi-editor-runtime-fixes.js?v=6" in pages
    assert "vi-editor-component-geometry.js?v=1" in loader
    assert "vi-editor-density.js?v=1" in loader
    assert "vi-editor-density-toolbar.js?v=1" in loader
    assert "vi-editor-density-memory.js?v=1" in loader
    assert "vi-editor-readability.js?v=1" in loader
    assert loader.index("vi-editor-integrity") < loader.index(
        "vi-editor-component-geometry"
    )
    assert loader.index("vi-editor-component-geometry") < loader.index(
        "vi-editor-density"
    )
    assert loader.index("vi-editor-density") < loader.index("vi-editor-density-toolbar")
    assert loader.index("vi-editor-density-toolbar") < loader.index("vi-editor-density-memory")
    assert loader.index("vi-editor-density-memory") < loader.index(
        "vi-editor-readability"
    )


def test_readable_fit_keeps_surface_specific_zoom_modes() -> None:
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


def test_normal_chrome_is_not_reduced_to_miniature_dimensions() -> None:
    styles = read("semantic-density.css")
    runtime = read("semantic-density-runtime.css")

    assert "--commandbar-height: 40px" not in styles
    assert "--navigation-width: 168px" not in styles
    assert "--context-width: 248px" not in styles
    assert "font-size: 7px" not in styles
    assert ".azure-command-bar" not in styles
    assert ".azure-navigation" not in styles
    assert "grid-template-rows: 54px 44px auto minmax(0, 1fr) auto" in runtime
    assert "grid-template-rows: 42px minmax(0, 1fr) 36px" in runtime
    assert "#page-stack.is-model-page .vi-source-debug:not([open])" in runtime


def test_normal_toolbar_status_never_intercepts_action_buttons() -> None:
    runtime = read("semantic-density-runtime.css")

    assert "#page-stack.is-model-page .vi-canvas-toolbar > div:first-child" in runtime
    assert "overflow: hidden" in runtime
    assert "#page-stack.is-model-page .vi-semantic-integrity-status" in runtime
    assert "pointer-events: none" in runtime
    assert "#page-stack.is-model-page .vi-canvas-actions" in runtime
    assert "justify-content: flex-end" in runtime
    assert "overflow-x: auto" in runtime
    assert "z-index: 5" in runtime


def test_secondary_settings_remain_in_a_non_miniature_menu() -> None:
    script = read("vi-editor-density-toolbar.js")
    runtime = read("semantic-density-runtime.css")

    assert "vi-density-options" in script
    assert "グリッド、吸着、名称表示" in script
    assert "labels.forEach((label) => panel.append(label))" in script
    assert "VICanvasDensityToolbar" in script
    assert ".vi-density-options-panel" in runtime
    assert "min-width: 180px" in runtime
    assert "z-index: 40" in runtime


def test_zoom_lod_suppresses_canvas_clutter_not_application_ui() -> None:
    styles = read("semantic-density.css")
    script = read("vi-editor-density.js")

    for level in ("overview", "compact", "normal", "detail"):
        assert f'data-vi-lod="{level}"' in styles
    assert ".vi-terminal-caption" in styles
    assert ".vi-terminal-type-dot" in styles
    assert ".vi-object.is-selected .vi-object-label" in styles
    assert ".header-command" not in styles
    assert ".navigation-item" not in styles
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


def test_surface_switch_restores_each_surface_view() -> None:
    script = read("vi-editor-density-memory.js")

    assert "density.rememberCurrentView()" in script
    assert "surface, false" in script
    assert "Normal tab" in script
    assert "VICanvasDensityMemory" in script
