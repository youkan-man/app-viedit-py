from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_compact_resize_assets_load_after_selection_runtimes() -> None:
    pages = read("pages.js")
    loader = read("vi-editor-runtime-fixes.js")

    assert "semantic-resize-handles.css?v=1" in pages
    assert "vi-editor-runtime-fixes.js?v=12.4" in pages
    assert "vi-editor-compact-resize-handles.js?v=1" in loader
    assert "VICompactResizeHandles" in loader
    assert loader.index("vi-editor-multi-selection-polish") < loader.index(
        "vi-editor-compact-resize-handles"
    )
    assert loader.index("vi-editor-compact-resize-handles") < loader.index(
        "vi-editor-wire-stability"
    )


def test_visible_handle_and_hit_target_are_separate_sizes() -> None:
    script = read("vi-editor-compact-resize-handles.js")

    assert "const VISUAL_SIZE_PX = 5" in script
    assert "const HIT_SIZE_PX = 14" in script
    assert "vi-resize-hit-target" in script
    assert "visual.removeAttribute('data-resize')" in script
    assert "hit.dataset.resize = 'true'" in script
    assert "visual.setAttribute('pointer-events', 'none')" in script
    assert "hit.setAttribute('pointer-events', 'all')" in script
    assert "const visualX = corner.x" in script
    assert "const visualY = corner.y" in script


def test_hit_target_stays_outside_projected_geometry_and_finalizes_last() -> None:
    script = read("vi-editor-compact-resize-handles.js")
    styles = read("semantic-resize-handles.css")

    assert "hit.classList.add('vi-resize-hit-target', 'vi-resize-handle')" in script
    assert "if (hit.parentNode !== group || visual.nextSibling !== hit)" in script
    assert "group.insertBefore(hit, visual.nextSibling)" in script
    assert "function patchProjection" in script
    assert "P.decorate = function decorateWithCompactResizeHandles" in script
    assert "P.schedule = function scheduleWithCompactResizeHandles" in script
    for attribute in ("'x'", "'y'", "'width'", "'height'"):
        assert attribute in script
    assert ".vi-resize-handle.vi-resize-hit-target" in styles
    assert "transform: none" in styles


def test_resize_handle_stays_screen_sized_across_zoom() -> None:
    script = read("vi-editor-compact-resize-handles.js")

    assert "function screenScale" in script
    assert "Math.hypot(matrix.a, matrix.b)" in script
    assert "Math.hypot(matrix.c, matrix.d)" in script
    assert "VISUAL_SIZE_PX / scale.x" in script
    assert "VISUAL_SIZE_PX / scale.y" in script
    assert "HIT_SIZE_PX / scale.x" in script
    assert "HIT_SIZE_PX / scale.y" in script
    assert "ResizeObserver" in script
    assert "viewport.addEventListener('wheel', schedule" in script


def test_multi_selection_and_terminals_do_not_expose_resize_targets() -> None:
    script = read("vi-editor-compact-resize-handles.js")
    styles = read("semantic-resize-handles.css")

    assert "multiCount > 1" in script
    assert "item.category === 'terminal'" in script
    assert "removeHitTarget(group)" in script
    assert ".has-multi-selection" in styles
    assert ".vi-object.is-terminal" in styles


def test_resize_handle_decorator_is_display_only() -> None:
    script = read("vi-editor-compact-resize-handles.js")

    assert "S.local.set" not in script
    assert "S.dirty.add" not in script
    assert "item.bounds =" not in script
    assert "source_property_id" not in script
    assert "setAttribute('viewBox'" not in script


def test_resize_handle_css_does_not_compact_application_chrome() -> None:
    styles = read("semantic-resize-handles.css")

    assert ".vi-resize-handle.is-compact-resize-handle" in styles
    assert ".vi-resize-hit-target" in styles
    assert "pointer-events: all" in styles
    assert "--commandbar-height" not in styles
    assert "--navigation-width" not in styles
    assert "--context-width" not in styles
    assert ".azure-command-bar" not in styles
    assert ".azure-navigation" not in styles
