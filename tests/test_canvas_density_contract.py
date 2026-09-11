from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_density_assets_are_loaded_after_semantic_integrity() -> None:
    pages = read("pages.js")
    loader = read("vi-editor-runtime-fixes.js")

    assert "semantic-density.css?v=2" in pages
    assert "semantic-density-runtime.css?v=2" in pages
    assert pages.index("semantic-density.css?v=2") < pages.index(
        "semantic-density-runtime.css?v=2"
    )
    assert "semantic-readability.css?v=1" in pages
    assert "vi-editor-runtime-fixes.js?v=6" in pages
    assert "vi-editor-density.js?v=2" in loader
    assert "vi-editor-density-toolbar.js?v=1" in loader
    assert "vi-editor-density-memory.js?v=1" in loader
    assert "vi-editor-readability.js?v=1" in loader
    assert loader.index("vi-editor-integrity") < loader.index("vi-editor-density")
    assert loader.index("vi-editor-density") < loader.index("vi-editor-density-toolbar")
    assert loader.index("vi-editor-density-toolbar") < loader.index(
        "vi-editor-density-memory"
    )
    assert loader.index("vi-editor-density-memory") < loader.index(
        "vi-editor-readability"
    )


def test_readable_fit_uses_component_screen_size_not_whole_page_chrome() -> None:
    script = read("vi-editor-density.js")

    assert "'front-panel'" in script
    assert "'block-diagram'" in script
    assert "componentTargetShortSide: 28" in script
    assert "componentTargetShortSide: 24" in script
    assert "minComponentScale: 0.24" in script
    assert "minComponentScale: 0.20" in script
    assert "maxComponentScale: 0.86" in script
    assert "maxComponentScale: 0.78" in script
    assert "function componentItems" in script
    assert "function componentRecords" in script
    assert "function componentMetrics" in script
    assert "function componentScale" in script
    assert "function componentScreenMetrics" in script
    assert "settings.componentTargetShortSide / metrics.medianShortSide" in script
    assert "return readable;" in script
    assert "Math.max(ideal, componentFloor)" not in script
    assert "componentScaleFloor" not in script
    assert "item.positioned !== false" in script
    assert "!item.hidden_by_structure_frame" in script
    assert "item.surface !== 'block-diagram-inactive'" in script


def test_readable_bounds_ignore_fallbacks_and_wire_route_outliers() -> None:
    script = read("vi-editor-density.js")

    assert "function hasRealBounds" in script
    assert "function fitItems" in script
    assert "function boundedWirePoints" in script
    assert "marginX = Math.max(96, width * 0.12)" in script
    assert "wireVisibleForItems(wire, itemIds)" in script
    assert "item.category === 'node'" in script
    assert "item.category === 'control'" in script
    assert "item.category === 'indicator'" in script


def test_density_runtime_does_not_modify_vi_geometry() -> None:
    script = read("vi-editor-density.js")

    assert "S.local.set" not in script
    assert "S.dirty.add" not in script
    assert "source_property_id" not in script
    assert "modelGraphSvg.setAttribute" in script
    assert "viewBox" in script


def test_normal_application_chrome_is_not_overridden_by_density() -> None:
    density = read("semantic-density.css")
    runtime = read("semantic-density-runtime.css")
    shell = read("azure-shell.css")
    layout = read("semantic-workspace-layout.css")

    for token in (
        "--commandbar-height",
        "--navigation-width",
        "--context-width",
        ".azure-command-bar",
        ".navigation-item",
        ".model-inspector h2",
        ".vi-editor-header",
        ".vi-summary",
        ".vi-object-list-item",
    ):
        assert token not in density
    assert "grid-template-rows: 42px 34px" not in runtime
    assert "height: 23px" not in runtime
    assert "font-size: 7px" not in runtime

    assert "--commandbar-height: 48px" in shell
    assert "--navigation-width: 216px" in shell
    assert "--context-width: 292px" in shell
    assert "grid-template-rows: 54px 44px" in layout
    assert "grid-template-columns: 224px minmax(0, 1fr)" in layout
    assert "grid-template-rows: 42px minmax(0, 1fr) 36px" in layout


def test_pane_collapse_stability_is_preserved_without_compacting_ui() -> None:
    styles = read("semantic-density.css")
    runtime = read("semantic-density-runtime.css")

    assert ".is-object-pane-collapsed" in styles
    assert ".vi-context-pane-collapsed" in styles
    assert ".is-object-pane-collapsed .vi-editor-layout" in runtime
    assert "display: block" in runtime
    assert 'body[data-active-page="model"].vi-context-pane-collapsed' in runtime
    assert "inset: 0 0 0 var(--navigation-width)" in runtime


def test_secondary_settings_remain_in_a_normal_sized_menu() -> None:
    script = read("vi-editor-density-toolbar.js")
    runtime = read("semantic-density-runtime.css")

    assert "vi-density-options" in script
    assert "グリッド、吸着、名称表示" in script
    assert "labels.forEach((label) => panel.append(label))" in script
    assert "VICanvasDensityToolbar" in script
    assert ".vi-density-options-panel" in runtime
    assert "z-index: 40" in runtime
    assert "height: 28px" in runtime
    assert "font-size: 9px" in runtime


def test_zoom_lod_only_changes_vi_content_and_uses_screen_component_size() -> None:
    styles = read("semantic-density.css")
    script = read("vi-editor-density.js")

    for level in ("overview", "compact", "normal", "detail"):
        assert f'data-vi-lod="{level}"' in styles
    assert ".vi-terminal-caption" in styles
    assert ".vi-terminal-type-dot" in styles
    assert ".vi-object.is-selected .vi-object-label" in styles
    assert ".azure-command-bar" not in styles
    assert ".navigation-item" not in styles
    assert "medianScreenShortSide" in script
    assert "lodForScale(scale, mode" in script
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
    assert "VIコンポーネントの画面上サイズを基準に表示する" in script
    assert "選択コンポーネントと接続へフォーカス" in script
    assert "VI部品表示倍率" in script
    assert "document.querySelector('#vi-zoom-status')?.remove()" in script


def test_surface_switch_restores_each_surface_view() -> None:
    script = read("vi-editor-density-memory.js")

    assert "density.rememberCurrentView()" in script
    assert "surface, false" in script
    assert "Normal tab" in script
    assert "VICanvasDensityMemory" in script
