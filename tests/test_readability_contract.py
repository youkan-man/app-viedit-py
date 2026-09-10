from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_runtime_loader_adds_readability_after_density() -> None:
    loader = read("vi-editor-runtime-fixes.js")
    bridge = read("vi-editor-readability-loader.js")

    assert "vi-editor-density-memory" in loader
    assert "vi-editor-readability-loader" in loader
    assert loader.index("vi-editor-density-memory") < loader.index(
        "vi-editor-readability-loader"
    )
    assert "semantic-readability.css?v=1" in bridge
    assert "vi-editor-readability.js?v=1" in bridge
    assert "script.async = false" in bridge


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
    assert "is-readability-primary" in script
    assert "is-readability-related" in script
    assert "is-readability-muted" in script
    assert ".has-readability-focus" in styles
    assert ".is-readability-muted" in styles
    assert ".is-readability-related" in styles
    assert ".is-readability-primary" in styles


def test_label_collision_prioritizes_semantic_context() -> None:
    script = read("vi-editor-readability.js")

    assert "labelPriority" in script
    assert "isProtectedLabel" in script
    assert "collisionMargin" in script
    assert "intersection" in script
    assert "currentLod()" in script
    assert "context.primaryObjects.has" in script
    assert "context.relatedObjects.has" in script
    assert "measureLabelCollisions" in script
    assert "visibleLabelCount" in script
    assert "suppressedLabelCount" in script
    assert "labelOverlapCount" in script


def test_structure_frame_and_tunnel_semantics_are_visible() -> None:
    script = read("vi-editor-readability.js")
    styles = read("semantic-readability.css")

    assert "active_frame_label" in script
    assert "active_frame_index" in script
    assert "displayed_frame" in script
    assert "vi-structure-frame-badge" in script
    assert "is-structure-tunnel" in script
    assert "tunnelDirection" in script
    assert "is-bidirectional" in script
    assert ".vi-structure-frame-badge" in styles
    assert ".vi-tunnel-direction" in styles
    assert '[data-tunnel-direction="bidirectional"]' in styles


def test_zoom_surface_filter_and_resize_recompute_readability() -> None:
    script = read("vi-editor-readability.js")

    assert "ResizeObserver" in script
    assert "data-vi-lod" in script
    assert "data-vi-scale" in script
    assert "viewport.addEventListener('wheel'" in script
    assert "model-graph-query" in script
    assert "model-graph-kind" in script
    assert "[data-vi-surface]" in script
    assert "requestAnimationFrame" in script
