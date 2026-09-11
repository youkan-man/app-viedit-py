from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_density_assets_and_component_projection_load_in_order() -> None:
    pages = read("pages.js")
    loader = read("vi-editor-runtime-fixes.js")

    assert "semantic-density.css?v=2" in pages
    assert "semantic-density-runtime.css?v=2" in pages
    assert pages.index("semantic-density.css?v=2") < pages.index(
        "semantic-density-runtime.css?v=2"
    )
    assert "semantic-readability.css?v=1" in pages
    assert "vi-editor-runtime-fixes.js?v=8" in pages
    assert "vi-editor-density.js?v=1" in loader
    assert "vi-editor-density-toolbar.js?v=1" in loader
    assert "vi-editor-density-memory.js?v=1" in loader
    assert "vi-editor-readability.js?v=1" in loader
    assert "vi-editor-component-primer.js?v=1" in loader
    assert "vi-editor-component-projection.js?v=1" in loader
    assert "vi-editor-component-anchor.js?v=1" in loader
    assert "vi-editor-component-coordinate-space.js?v=1" in loader
    assert "vi-editor-component-fit.js?v=1" in loader
    assert loader.index("vi-editor-integrity") < loader.index("vi-editor-density")
    assert loader.index("vi-editor-density") < loader.index("vi-editor-density-toolbar")
    assert loader.index("vi-editor-density-toolbar") < loader.index(
        "vi-editor-density-memory"
    )
    assert loader.index("vi-editor-density-memory") < loader.index(
        "vi-editor-readability"
    )
    assert loader.index("vi-editor-readability") < loader.index(
        "vi-editor-component-primer"
    )
    assert loader.index("vi-editor-component-primer") < loader.index(
        "vi-editor-component-projection"
    )
    assert loader.index("vi-editor-component-projection") < loader.index(
        "vi-editor-component-anchor"
    )
    assert loader.index("vi-editor-component-anchor") < loader.index(
        "vi-editor-component-coordinate-space"
    )
    assert loader.index("vi-editor-component-coordinate-space") < loader.index(
        "vi-editor-component-fit"
    )


def test_normal_application_chrome_is_not_a_density_optimization() -> None:
    styles = read("semantic-density.css")
    runtime = read("semantic-density-runtime.css")
    shell = read("azure-shell.css")
    layout = read("semantic-workspace-layout.css")

    assert "--commandbar-height: 40px" not in styles
    assert "--navigation-width: 168px" not in styles
    assert "--context-width: 248px" not in styles
    assert ".azure-command-bar" not in styles
    assert ".azure-navigation" not in styles
    assert styles.count(".azure-context-pane") == 1
    assert (
        'body[data-active-page="model"].vi-context-pane-collapsed '
        ".azure-context-pane"
    ) in styles
    assert "--commandbar-height: 48px" in shell
    assert "--navigation-width: 216px" in shell
    assert "--context-width: 292px" in shell
    assert "grid-template-columns: 224px minmax(0, 1fr)" in layout
    assert "grid-template-rows: 54px 44px auto minmax(0, 1fr) auto" in layout
    assert "grid-template-rows: 42px minmax(0, 1fr) 36px" in layout
    assert "grid-template-rows: 42px 34px auto" not in runtime
    assert "font-size: 7px" not in runtime


def test_original_density_camera_does_not_modify_vi_geometry() -> None:
    script = read("vi-editor-density.js")

    assert "S.local.set" not in script
    assert "S.dirty.add" not in script
    assert "source_property_id" not in script
    assert "modelGraphSvg.setAttribute" in script
    assert "viewBox" in script
    assert "surfaceViews" in script
    assert "ResizeObserver" in script


def test_pane_collapse_reclaims_canvas_without_compacting_chrome() -> None:
    styles = read("semantic-density.css")
    runtime = read("semantic-density-runtime.css")

    assert ".is-object-pane-collapsed" in styles
    assert ".vi-context-pane-collapsed" in styles
    assert "#page-stack.is-model-page .vi-editor-shell.is-object-pane-collapsed" in runtime
    assert "display: block" in runtime
    assert "inset: 0 0 0 var(--navigation-width)" in runtime
    assert "#page-stack.is-model-page .vi-canvas-actions" in runtime
    assert "justify-content: flex-end" in runtime
    assert "overflow: visible" in runtime
    assert "z-index: 5" in runtime


def test_secondary_settings_remain_available_at_normal_ui_size() -> None:
    script = read("vi-editor-density-toolbar.js")
    runtime = read("semantic-density-runtime.css")

    assert "vi-density-options" in script
    assert "グリッド、吸着、名称表示" in script
    assert "labels.forEach((label) => panel.append(label))" in script
    assert "VICanvasDensityToolbar" in script
    assert ".vi-density-options-panel" in runtime
    assert "min-height: 28px" in runtime
    assert "font-size: 10px" in runtime
    assert "z-index: 40" in runtime


def test_zoom_lod_only_changes_canvas_detail() -> None:
    styles = read("semantic-density.css")
    script = read("vi-editor-density.js")

    for level in ("overview", "compact", "normal", "detail"):
        assert f'data-vi-lod="{level}"' in styles
    assert ".vi-terminal-caption" in styles
    assert ".vi-terminal-type-dot" in styles
    assert ".vi-object.is-selected .vi-object-label" in styles
    assert ".azure-command-bar" not in styles
    assert ".azure-navigation" not in styles
    assert styles.count(".azure-context-pane") == 1
    assert (
        'body[data-active-page="model"].vi-context-pane-collapsed '
        ".azure-context-pane"
    ) in styles
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
