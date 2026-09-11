from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_navigation_assets_load_after_projected_fit() -> None:
    pages = read("pages.js")
    loader = read("vi-editor-runtime-fixes.js")

    assert "semantic-navigation-workflow.css?v=1" in pages
    assert "data-vi-navigation-workflow" in pages
    assert "vi-editor-runtime-fixes.js?v=12" in pages
    assert "vi-editor-navigation-workflow.js?v=1" in loader
    assert "vi-editor-navigation-keyboard-guard.js?v=1" in loader
    assert "VINavigationWorkflow" in loader
    assert "VINavigationKeyboardGuard" in loader
    assert loader.index("vi-editor-component-fit") < loader.index(
        "vi-editor-navigation-workflow"
    )
    assert loader.index("vi-editor-navigation-workflow") < loader.index(
        "vi-editor-navigation-keyboard-guard"
    )
    assert "await waitForReady(readyGlobal, flag)" in loader


def test_quick_navigator_searches_objects_wires_and_both_surfaces() -> None:
    script = read("vi-editor-navigation-workflow.js")

    assert "...S.objects.keys()" in script
    assert "...S.wires.keys()" in script
    assert "'front-panel': 'フロントパネル'" in script
    assert "'block-diagram': 'ブロックダイアグラム'" in script
    for field in (
        "item?.kind",
        "item?.class_name",
        "item?.uid",
        "item?.data_type",
        "wire?.net_id",
    ):
        assert field in script
    assert "connectedIds()" in script
    assert "最近の選択" in script
    assert "現在の選択に接続" in script
    assert "clearRevealFilters" in script
    assert "E.select(id, true)" in script


def test_quick_navigator_is_keyboard_and_modal_accessible() -> None:
    script = read("vi-editor-navigation-workflow.js")
    guard = read("vi-editor-navigation-keyboard-guard.js")
    styles = read("semantic-navigation-workflow.css")

    assert 'role="dialog"' in script
    assert 'aria-modal="true"' in script
    assert 'role="combobox"' in script
    assert 'role="listbox"' in script
    for key in (
        "ArrowDown",
        "ArrowUp",
        "Home",
        "End",
        "Enter",
        "Escape",
        "Tab",
    ):
        assert key in script
        assert key in guard
    assert "event.key.toLowerCase() === 'k'" in script
    assert "event.altKey && event.key === 'ArrowLeft'" in script
    assert "event.altKey && event.key === 'ArrowRight'" in script
    assert "setBackgroundInert(true)" in script
    assert "setBackgroundInert(false)" in script
    assert "trapTab" in script
    assert "window.addEventListener('keydown', handle, true)" in guard
    assert "dialog?.contains(event.target)" in guard
    assert "event.stopImmediatePropagation()" in guard
    assert "width: min(720px, calc(100vw - 48px))" in styles
    assert "max-height: min(760px, calc(100vh - 48px))" in styles
    assert "@media (max-width: 760px)" in styles


def test_selection_history_restores_surface_and_view_without_geometry_edits() -> None:
    script = read("vi-editor-navigation-workflow.js")

    for field in (
        "id,",
        "surface:",
        "box:",
        "mode:",
        "revision:",
        "jobKey:",
    ):
        assert field in script
    assert "activeDensity.applyBox(snapshot.box" in script
    assert "runtime.originalSelect.call(E, snapshot.id, true)" in script
    assert "E.install = function installWithNavigationReset" in script
    assert "resetHistory('model-installed')" in script
    assert "resetHistory('revision-changed')" in script
    assert "samePlace(current, snapshot)" in script
    assert "MAX_HISTORY = 50" in script
    assert "S.local.set" not in script
    assert "S.dirty.add" not in script
    assert "item.bounds =" not in script
    assert "source_property_id" not in script
    assert "xml-editor" not in script
    assert "apiRequest(" not in script


def test_navigation_controls_do_not_compact_normal_editor_chrome() -> None:
    styles = read("semantic-navigation-workflow.css")

    assert ".vi-navigation-launcher" in styles
    assert ".vi-selection-history" in styles
    assert "position: fixed" in styles
    assert "z-index: 3000" in styles
    assert ".azure-command-bar" not in styles
    assert ".azure-navigation" not in styles
    assert ".azure-context-pane" not in styles
    assert "--commandbar-height" not in styles
    assert "--navigation-width" not in styles
    assert "--context-width" not in styles


def test_dialog_key_events_are_processed_only_once() -> None:
    guard = read("vi-editor-navigation-keyboard-guard.js")

    assert "dialog?.contains(event.target)" in guard
    assert "runtime.handled += 1" in guard
    assert "window.addEventListener('keydown', handle, true)" in guard
    assert "event.stopImmediatePropagation()" in guard
