from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_multi_selection_assets_load_after_navigation_history() -> None:
    pages = read("pages.js")
    loader = read("vi-editor-runtime-fixes.js")

    assert "semantic-multi-selection.css?v=1" in pages
    assert "vi-editor-runtime-fixes.js?v=12.3" in pages
    assert "vi-editor-navigation-history-stability.js?v=1" in pages
    assert "vi-editor-multi-selection-prelude.js?v=1" in loader
    assert "vi-editor-multi-selection.js?v=1" in loader
    assert "vi-editor-multi-selection-polish.js?v=1" in loader
    assert "VIMultiSelectionPrelude" in loader
    assert "VIMultiSelection" in loader
    assert "VIMultiSelectionPolish" in loader
    assert loader.index("vi-editor-component-fit.js?v=1") < loader.index(
        "vi-editor-multi-selection-prelude.js?v=1"
    )
    assert loader.index("vi-editor-multi-selection-prelude.js?v=1") < loader.index(
        "vi-editor-multi-selection.js?v=1"
    )
    assert loader.index("vi-editor-multi-selection.js?v=1") < loader.index(
        "vi-editor-multi-selection-polish.js?v=1"
    )
    assert loader.index("vi-editor-multi-selection-polish") < loader.index(
        "vi-editor-compact-resize-handles"
    )
    assert loader.index("vi-editor-compact-resize-handles") < loader.index(
        "vi-editor-wire-stability"
    )
    assert "await waitForReady(readyGlobal, flag)" in loader


def test_selection_state_keeps_single_primary_for_existing_editor_apis() -> None:
    script = read("vi-editor-multi-selection.js")

    assert "selectedIds: new Set()" in script
    assert "primaryId: null" in script
    assert "rangeAnchorId: null" in script
    assert "runtime.originalSelect = E.select" in script
    assert "runtime.selectedIds = new Set([id])" in script
    assert "S.selected = runtime.primaryId" in script
    assert "navigationHistory()?.ready" in script


def test_selection_only_paths_do_not_modify_geometry_or_dirty_state() -> None:
    script = read("vi-editor-multi-selection.js")
    before_translation = script.split("function applyTranslation", 1)[0]

    assert "S.local.set" not in before_translation
    assert "S.dirty.add" not in before_translation
    assert "function setSelection" in before_translation
    assert "function toggleSelection" in before_translation
    assert "function selectListRange" in before_translation
    assert "function objectsInMarquee" in script


def test_ctrl_shift_and_csp_safe_marquee_selection_paths_are_available() -> None:
    script = read("vi-editor-multi-selection.js")
    prelude = read("vi-editor-multi-selection-prelude.js")

    assert "event.ctrlKey || event.metaKey" in script
    assert "event.shiftKey && listButton" in script
    assert "selectListRange" in script
    assert "createElementNS(SVG_NS, 'rect')" in prelude
    assert "vi-multi-selection-marquee-safe" in prelude
    assert "beginMarquee" in prelude
    assert "moveMarquee" in prelude
    assert "finishMarquee" in prelude
    assert "centerX >= rect.left" in prelude
    assert "centerY <= rect.bottom" in prelude
    assert ".style." not in prelude


def test_group_movement_preserves_parent_child_roots_and_shared_delta() -> None:
    script = read("vi-editor-multi-selection.js")

    assert "function hasMovableSelectedAncestor" in script
    assert "function movementRoots" in script
    assert "item?.bounds?.relative_to_object_id" in script
    assert "function beforeMapForRoots" in script
    assert "function applyTranslation" in script
    assert "x: before.x + dx" in script
    assert "y: before.y + dy" in script
    assert "magneticSnapDelta" in script
    assert "clientToWorld" in script


def test_group_keyboard_move_and_batch_history_are_single_actions() -> None:
    script = read("vi-editor-multi-selection.js")

    assert "ArrowLeft: [-step, 0]" in script
    assert "ArrowRight: [step, 0]" in script
    assert "const step = event.shiftKey ? 10 : 1" in script
    assert "multi_selection: true" in script
    assert "entries" in script
    assert "function undoBatch" in script
    assert "function redoBatch" in script
    assert "historyState.future = []" in script
    assert "複数移動" in script
    assert "複数キー移動" in script


def test_prelude_preserves_group_when_switching_primary_and_copies_reliably() -> None:
    prelude = read("vi-editor-multi-selection-prelude.js")

    assert "capturePrimaryCandidate" in prelude
    assert "finishPrimaryCandidate" in prelude
    assert "M.setSelection([...M.runtime.selectedIds], candidate.id)" in prelude
    assert "suppressPrimaryClickUntil" in prelude
    assert "typeof navigator.clipboard?.writeText === 'function'" in prelude
    assert "document.execCommand('copy')" in prelude
    assert "#vi-copy-selection-summary" in prelude


def test_polish_adds_select_all_outlines_and_surface_cleanup() -> None:
    polish = read("vi-editor-multi-selection-polish.js")

    assert "modifier && key === 'a'" in polish
    assert "visibleObjectIds" in polish
    assert "normalizeSurfaceSelection" in polish
    assert "S.objects.get(id)?.surface === S.surface" in polish
    assert "vi-multi-selection-item-outline" in polish


def test_aggregate_inspector_and_copyable_summary_are_exposed() -> None:
    script = read("vi-editor-multi-selection.js")

    for identifier in (
        "vi-multi-selection-inspector",
        "vi-copy-selection-summary",
        "vi-multi-selection-count",
        "vi-multi-selection-surface",
        "vi-multi-selection-primary",
        "vi-multi-selection-movable",
        "vi-multi-selection-geometry",
        "vi-multi-selection-status",
    ):
        assert identifier in script
    assert "function summaryText" in script
    assert "navigator.clipboard" in script
    assert "document.execCommand('copy')" in script
    assert "グループのリサイズは無効" in script


def test_multi_selection_visuals_do_not_compact_normal_application_ui() -> None:
    styles = read("semantic-multi-selection.css")

    assert ".is-multi-selected" in styles
    assert ".is-multi-primary" in styles
    assert ".vi-multi-selection-item-outline" in styles
    assert ".vi-multi-selection-bounds" in styles
    assert ".vi-multi-selection-marquee" in styles
    assert ".vi-multi-selection-inspector" in styles
    assert ".vi-multi-selection-status" in styles
    assert ".vi-resize-handle" in styles
    assert "#vi-editor-shell.has-multi-selection #vi-geometry-editor" in styles
    assert "--commandbar-height" not in styles
    assert "--navigation-width" not in styles
    assert "--context-width" not in styles