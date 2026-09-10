from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_drag_uses_svg_coordinate_transform_not_viewbox_ratio() -> None:
    script = read("vi-editor-navigation.js")

    assert "getScreenCTM" in script
    assert "matrix.inverse()" in script
    assert "clientToWorld" in script
    assert "grabOffset" in script
    assert "world.x - gesture.grabOffset.x" in script
    assert "S.box.width / rect.width" not in script
    assert "!targetId || event.button" not in script


def test_layout_save_forces_reload_before_clearing_local_geometry() -> None:
    script = read("vi-editor-persistence.js")
    render_position = script.index("await globalThis.renderJob(latestJob")
    clear_position = script.index("reloaded?.local.clear()")

    assert "function geometryProperty" in script
    assert "item.bounds?.source_property_id" in script
    assert "detail.bounds?.property_id" in script
    assert "candidate.value_type === 'rect'" in script
    assert "component_modified_at" in script
    assert render_position < clear_position
    assert "S.revision =" not in script
    assert "保存後の再解析座標が一致しません" in script
    assert "source_coordinate_space !== 'parent-relative'" in script


def test_rebuild_actions_execute_without_forcing_build_page() -> None:
    script = read("vi-editor-actions.js")

    assert "activeJob.rebuild_url" in script
    assert "await globalThis.renderJob(updated" in script
    assert "activePage" in script
    assert "現在の画面を維持" in script
    assert "open('build')" not in script
    assert "stopImmediatePropagation" in script


def test_property_details_are_inline_and_raw_is_collapsed() -> None:
    script = read("vi-editor-inline-properties.js")
    pages = read("pages.js")

    assert "vi-inline-properties" in script
    assert "RAWデータ" in script
    assert "model-open-properties" in script
    assert "stopImmediatePropagation" in script
    assert "prop.structural" in script
    assert "prop.reference_like" in script
    assert "model-open-properties').addEventListener" not in pages
    assert "xml: { title: 'RAWデータ'" in pages
    assert "build: { title: '成果物'" in pages


def test_cluster_and_diagram_objects_have_native_style_projection() -> None:
    script = read("vi-editor-realism.js")
    styles = read("semantic-workspace-realism.css")

    assert "is-cluster-container" in script
    assert "child_object_ids" in script
    assert "nesting_depth" in script
    assert "vi-cluster-interior" in script
    assert "vi-primitive-body" in script
    assert "vi-structure-titlebar" in script
    assert "vi-subvi-icon" in script
    assert ".vi-object.is-cluster-container" in styles
    assert ".vi-primitive-body" in styles
    assert ".vi-object.is-native-structure" in styles


def test_property_explorer_separates_raw_and_serializes_native_rectangles() -> None:
    script = read("component-properties-semantic.js")

    assert "RAWデータ（class / UID / XML file / XML path）" in script
    assert "RAW XML構造" in script
    assert "意味プロパティ" in script
    assert "nativeGeometryOrder" in script
    assert "`(${y}, ${x}, ${y + height}, ${x + width})`" in script


def test_correction_modules_are_loaded() -> None:
    pages = read("pages.js")
    loader = read("vi-editor-runtime-fixes.js")

    assert "semantic-workspace-realism.css?v=1" in pages
    assert "component-properties-semantic.css?v=1" in pages
    assert "vi-editor-runtime-fixes.js?v=1" in pages
    for name in (
        "vi-editor-realism",
        "vi-editor-persistence",
        "vi-editor-actions",
        "vi-editor-inline-properties",
        "vi-editor-ui-labels",
        "component-properties-semantic",
    ):
        assert name in loader
