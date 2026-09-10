from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def test_round_two_assets_are_loaded_before_first_editor_gesture() -> None:
    pages = (STATIC / "pages.js").read_text(encoding="utf-8")

    assert "semantic-workspace-enhancements.css?v=1" in pages
    assert "semantic-workspace-runtime.css?v=2" in pages
    assert "vi-editor-navigation.js?v=2" in pages
    assert "vi-editor-enhancements.js?v=1" in pages
    assert "script.async = false" in pages
    assert "ensureSemanticEditorScripts();" in pages
    assert pages.index("ensureSemanticEditorScripts();") < pages.index(
        "document.addEventListener('DOMContentLoaded'"
    )
    assert "finalizeSemanticEditor" in pages
    assert "bindSemanticEditorInteractions();" in pages
    assert "ensureScript(" in pages


def test_semantic_layout_is_csp_safe_and_externalized() -> None:
    pages = (STATIC / "pages.js").read_text(encoding="utf-8")
    runtime = (STATIC / "semantic-workspace-runtime.css").read_text(
        encoding="utf-8"
    )

    assert "createElement('style')" not in pages
    assert ".style." not in pages
    assert ".style =" not in pages
    assert "grid-template-rows: 54px 44px auto minmax(0, 1fr) auto" in runtime
    assert ".vi-source-debug:not([open])" in runtime
    assert "height: auto" in runtime


def test_linked_object_navigation_preserves_click_and_drag_gestures() -> None:
    script = (STATIC / "vi-editor-navigation.js").read_text(encoding="utf-8")
    begin = script.split("function beginGesture", 1)[1].split(
        "function moveGesture", 1
    )[0]
    move = script.split("function moveGesture", 1)[1].split(
        "function finishGesture", 1
    )[0]

    assert "counterpartId" in script
    assert "pointerdown" in script
    assert "pointermove" in script
    assert "dblclick" in script
    assert "pendingSelection" in script
    assert "renderCanvas" in script
    assert "VISemanticNavigationBridge" in script
    assert "event.stopPropagation()" in script
    assert "event.detail >= 2" in script
    assert "E.select(targetId, true)" in script
    assert "captured: false" in begin
    assert "setPointerCapture" not in begin
    assert "preventDefault()" not in begin
    assert "setPointerCapture" in move
    assert "gesture.moved = true" in move
    assert "gesture.captured = true" in move


def test_inspector_prioritizes_vi_semantics_over_xml_metadata() -> None:
    script = (STATIC / "vi-editor-enhancements.js").read_text(encoding="utf-8")

    for label in ("種類", "画面", "役割", "データ型", "接続", "配置"):
        assert label in script
    assert "vi-semantic-inspector-grid" in script
    assert "vi-inspector-source-details" in script
    assert "解析元情報（class / UID / XML）" in script
    assert "対応画面の部品へ移動" in script


def test_canvas_has_history_focus_and_keyboard_workflows() -> None:
    script = (STATIC / "vi-editor-enhancements.js").read_text(encoding="utf-8")

    assert "vi-undo-layout" in script
    assert "vi-redo-layout" in script
    assert "focusSelection" in script
    assert "Ctrl+Z" in script
    assert "ArrowDown" in script
    assert "Escape" in script
    assert "model-graph-query" in script


def test_wires_and_terminals_are_decorated_and_selectable() -> None:
    script = (STATIC / "vi-editor-enhancements.js").read_text(encoding="utf-8")
    styles = (STATIC / "semantic-workspace-enhancements.css").read_text(
        encoding="utf-8"
    )
    runtime = (STATIC / "semantic-workspace-runtime.css").read_text(
        encoding="utf-8"
    )

    assert "wireType" in script
    assert "objectType" in script
    assert "orthogonalizePath" in script
    assert "vi-terminal-type-dot" in script
    assert "vi-terminal-caption" in script
    assert ".vi-object.is-terminal" in styles
    assert "pointer-events: bounding-box" in styles
    assert ".vi-terminal-caption" in styles
    assert "pointer-events: all" in styles
    assert "#model-graph-svg .vi-wire-group" in runtime
    assert "pointer-events: bounding-box" in runtime
    assert ".vi-wire-hit" in runtime
    assert "pointer-events: stroke" in runtime
    for kind in ("numeric", "boolean", "string", "path", "array", "cluster"):
        assert f"is-type-{kind}" in styles
    assert "has-semantic-selection" in styles


def test_round_two_assets_exist_as_plain_static_files() -> None:
    assert (STATIC / "vi-editor-navigation.js").is_file()
    assert (STATIC / "vi-editor-enhancements.js").is_file()
    assert (STATIC / "semantic-workspace-enhancements.css").is_file()
    assert (STATIC / "semantic-workspace-runtime.css").is_file()
