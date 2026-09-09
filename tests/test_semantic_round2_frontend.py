from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def test_round_two_assets_are_loaded_after_core_editor() -> None:
    pages = (STATIC / "pages.js").read_text(encoding="utf-8")

    assert "semantic-workspace-enhancements.css?v=1" in pages
    assert "vi-editor-enhancements.js?v=1" in pages
    assert "finalizeSemanticEditor" in pages
    assert "bindSemanticEditorInteractions();" in pages
    assert "ensureScript(" in pages


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


def test_wires_and_terminals_are_decorated_by_data_type() -> None:
    script = (STATIC / "vi-editor-enhancements.js").read_text(encoding="utf-8")
    styles = (STATIC / "semantic-workspace-enhancements.css").read_text(
        encoding="utf-8"
    )

    assert "wireType" in script
    assert "objectType" in script
    assert "orthogonalizePath" in script
    assert "vi-terminal-type-dot" in script
    assert "vi-terminal-caption" in script
    for kind in ("numeric", "boolean", "string", "path", "array", "cluster"):
        assert f"is-type-{kind}" in styles
    assert "has-semantic-selection" in styles


def test_round_two_assets_exist_as_plain_static_files() -> None:
    assert (STATIC / "vi-editor-enhancements.js").is_file()
    assert (STATIC / "semantic-workspace-enhancements.css").is_file()
