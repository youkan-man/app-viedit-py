from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_readability_assets_load_after_density_state_restoration() -> None:
    pages = read("pages.js")
    loader = read("vi-editor-runtime-fixes.js")

    assert "semantic-readability.css?v=1" in pages
    assert "vi-editor-runtime-fixes.js?v=5" in pages
    assert "vi-editor-readability.js?v=1" in loader
    assert loader.index("vi-editor-density-memory") < loader.index(
        "vi-editor-readability"
    )
    assert "vi-editor-readability-loader" not in loader


def test_readability_observer_ignores_its_own_svg_descendant_mutations() -> None:
    script = read("vi-editor-readability.js")
    install = script.split("function install()", 1)[1]

    assert "runtime.observer.observe(canvas, { childList: true })" in install
    assert "runtime.observer.observe(canvas, { childList: true, subtree: true })" not in install
    assert "badge.textContent !== label" in script
    assert "mark.getAttribute('d') !== path" in script


def test_readability_never_edits_native_geometry() -> None:
    script = read("vi-editor-readability.js")

    assert "S.local.set" not in script
    assert "S.dirty.add" not in script
    assert "source_property_id" not in script
    assert "setAttribute('viewBox'" not in script
    assert "getBoundingClientRect" in script
    assert "is-label-suppressed" in script


def test_selection_focus_expands_to_direct_connections_and_whole_net() -> None:
    script = read("vi-editor-readability.js")
    styles = read("semantic-readability.css")

    assert "selectedContext" in script
    assert "selectedItem.wire_ids" in script
    assert "context.netIds" in script
    assert "wire.net_id" in script
    assert "group.dataset.netId" in script
    assert "is-readability-primary" in script
    assert "is-readability-related" in script
    assert "is-readability-muted" in script
    assert ".has-readability-focus" in styles
    assert ".is-readability-muted" in styles
    assert ".is-readability-related" in styles
    assert ".is-readability-primary" in styles


def test_label_collision_prioritizes_semantics_and_uses_spatial_index() -> None:
    script = read("vi-editor-readability.js")

    assert "labelPriority" in script
    assert "isProtectedLabel" in script
    assert "collisionMargin" in script
    assert "intersection" in script
    assert "currentLod()" in script
    assert "context.primaryObjects.has" in script
    assert "context.relatedObjects.has" in script
    assert "COLLISION_CELL_SIZE" in script
    assert "createSpatialIndex" in script
    assert "cellKeys" in script
    assert "index.query(box)" in script
    assert "labelCollisionChecks" in script
    assert "labelIndexCells" in script
    assert "labelPassMs" in script
    assert "measureLabelCollisions" in script
    assert "visibleLabelCount" in script
    assert "suppressedLabelCount" in script
    assert "labelOverlapCount" in script


def test_collision_work_is_limited_to_the_visible_viewport() -> None:
    script = read("vi-editor-readability.js")

    assert "VIEWPORT_MARGIN" in script
    assert "expandedViewportRect" in script
    assert "value.right < clipRect.left" in script
    assert "value.bottom < clipRect.top" in script


def test_structure_frame_and_tunnel_semantics_are_visible() -> None:
    script = read("vi-editor-readability.js")
    styles = read("semantic-readability.css")

    assert "active_frame_label" in script
    assert "active_frame_index" in script
    assert "displayed_frame" in script
    assert "vi-structure-frame-badge" in script
    assert "is-structure-tunnel" in script
    assert "terminalDirection" in script
    assert "wire_roles" in script
    assert "tunnelDirection" in script
    assert "is-bidirectional" in script
    assert ".vi-structure-frame-badge" in styles
    assert ".vi-tunnel-direction" in styles
    assert '[data-tunnel-direction="bidirectional"]' in styles


def test_zoom_surface_filter_resize_and_frame_change_recompute_readability() -> None:
    script = read("vi-editor-readability.js")

    assert "ResizeObserver" in script
    assert "data-vi-lod" in script
    assert "data-vi-scale" in script
    assert "canvasViewport.addEventListener('wheel'" in script
    assert "model-graph-query" in script
    assert "model-graph-kind" in script
    assert "[data-vi-surface]" in script
    assert "vi-structure-frame-changed" in script
    assert "document.fonts?.ready" in script
    assert "requestAnimationFrame" in script


def test_final_sandbox_suite_cannot_mask_failures_with_placeholder_artifacts() -> None:
    script = (ROOT / "scripts" / "sandbox_readability_test.sh").read_text(
        encoding="utf-8"
    )

    assert "READABILITY_STAGE_FAILED" in script
    assert 'exit "$status"' in script
    assert "diagnostic_placeholder" not in script
    assert "emit_diagnostic_placeholders" not in script
    assert "READABILITY_DIAGNOSTIC_ONLY" not in script
    assert "READABILITY_FINAL_SUMMARY" in script
