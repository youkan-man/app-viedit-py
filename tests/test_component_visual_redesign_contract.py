from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_visual_assets_load_before_projection_primer() -> None:
    pages = read("pages.js")
    loader = read("vi-editor-runtime-fixes.js")
    primer = read("vi-editor-component-primer.js")

    assert "semantic-component-visuals.css?v=1" in pages
    assert "data-vi-component-visuals" in pages
    assert "vi-editor-runtime-fixes.js?v=12.4" in pages
    assert "vi-editor-component-visuals.js?v=1" in loader
    assert "VIComponentVisuals" in loader
    assert loader.index("vi-editor-readability") < loader.index(
        "vi-editor-component-visuals"
    )
    assert loader.index("vi-editor-component-visuals") < loader.index(
        "vi-editor-component-primer"
    )
    assert "globalThis.VIComponentVisuals?.decorate?.()" in primer
    assert "!globalThis.VIComponentVisuals?.ready" in primer
    prepare = primer.split("function prepare()", 1)[1].split(
        "function schedule()", 1
    )[0]
    assert prepare.index("VIRealism?.decorate?.()") < prepare.index(
        "VIComponentVisuals?.decorate?.()"
    )
    assert prepare.index("VIComponentVisuals?.decorate?.()") < prepare.index(
        "normalizeCanonicalBodies()"
    )


def test_major_front_panel_types_have_distinct_semantic_skins() -> None:
    script = read("vi-editor-component-visuals.js")

    for function_name in (
        "numericSkin",
        "booleanSkin",
        "stringSkin",
        "pathSkin",
        "ringSkin",
        "tableSkin",
        "arraySkin",
        "clusterSkin",
        "frontGenericSkin",
    ):
        assert f"function {function_name}" in script
    for class_name in (
        "vi-skin-numeric-display",
        "vi-skin-boolean-track",
        "vi-skin-boolean-led",
        "vi-skin-string-display",
        "vi-skin-path-folder",
        "vi-skin-ring-button",
        "vi-skin-table-grid",
        "vi-skin-array-viewport",
        "vi-skin-cluster-interior",
    ):
        assert class_name in script


def test_control_and_indicator_roles_are_visually_distinct() -> None:
    script = read("vi-editor-component-visuals.js")
    styles = read("semantic-component-visuals.css")

    assert "return item?.category === 'indicator' ? 'indicator' : 'control'" in script
    assert "role === 'control'" in script
    assert "role === 'indicator'" in script
    assert "vi-skin-role-accent" in script
    assert "vi-skin-indicator-dot" in script
    assert "vi-skin-spinner" in script
    assert "vi-skin-boolean-track" in script
    assert "vi-skin-boolean-led" in script
    assert ".is-component-role-control .vi-skin-frame" in styles
    assert ".is-component-role-indicator .vi-skin-frame" in styles
    assert ".is-component-role-indicator .vi-skin-role-accent" in styles


def test_block_diagram_types_are_not_generic_rectangles() -> None:
    script = read("vi-editor-component-visuals.js")

    for function_name in (
        "primitiveSkin",
        "constantSkin",
        "subviSkin",
        "structureSkin",
        "terminalSkin",
        "nodeSkin",
    ):
        assert f"function {function_name}" in script
    assert "function primitiveBodyPath" in script
    assert "vi-skin-primitive-body" in script
    assert "vi-skin-constant-fold" in script
    assert "vi-skin-subvi-wave" in script
    assert "vi-skin-structure-selector" in script
    assert "vi-skin-terminal-direction" in script
    for operator in ("add", "subtract", "multiply", "divide", "equal", "select"):
        assert operator in script


def test_visible_skin_is_separate_from_geometry_and_interaction_layers() -> None:
    script = read("vi-editor-component-visuals.js")
    styles = read("semantic-component-visuals.css")

    assert "function geometryParent" in script
    assert "vi-component-geometry" in script
    assert "vi-component-skin" in script
    assert "vi-semantic-body-anchor" in script
    assert "vi-component-hit-target" in script
    assert "vi-resize-hit-target" in script
    assert "pointer-events: none" in styles
    assert ".vi-semantic-body-anchor" in styles
    assert "fill: transparent !important" in styles
    assert "stroke: transparent !important" in styles
    assert ".has-component-visual-system.is-selected .vi-skin-frame" in styles


def test_container_skins_keep_children_visible() -> None:
    script = read("vi-editor-component-visuals.js")
    styles = read("semantic-component-visuals.css")

    assert "raiseTerminalLayers" in script
    assert "vi-skin-array-viewport" in script
    assert "vi-skin-cluster-interior" in script
    assert "vi-skin-structure-interior" in script
    assert "rgba(255, 255, 255, .10)" in styles
    assert "rgba(255, 255, 255, .03)" in styles
    assert ".is-component-visual-array .vi-skin-frame" in styles
    assert ".is-component-visual-cluster .vi-skin-frame" in styles


def test_lod_preserves_silhouette_and_hides_secondary_detail() -> None:
    styles = read("semantic-component-visuals.css")

    assert '[data-vi-lod="overview"] .vi-component-skin .vi-skin-detail' in styles
    assert '[data-vi-lod="overview"] .vi-component-skin .vi-skin-value' in styles
    assert '[data-vi-lod="compact"] .vi-component-skin .vi-skin-detail' in styles
    assert '[data-vi-lod="overview"] .vi-object.is-selected .vi-skin-value' in styles
    assert ".vi-skin-frame" in styles
    assert ".vi-skin-symbol" in styles


def test_visual_redesign_is_display_only_and_does_not_compact_web_ui() -> None:
    script = read("vi-editor-component-visuals.js")
    styles = read("semantic-component-visuals.css")

    assert "S.local.set" not in script
    assert "S.dirty.add" not in script
    assert "item.bounds =" not in script
    assert "source_property_id" not in script
    assert "setAttribute('viewBox'" not in script
    assert "--commandbar-height" not in styles
    assert "--navigation-width" not in styles
    assert "--context-width" not in styles
    assert ".azure-command-bar" not in styles
    assert ".azure-navigation" not in styles
    assert ".azure-context-pane" not in styles
