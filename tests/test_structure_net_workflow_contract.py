from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_structure_frame_switch_rebuilds_visibility_without_writing_vi() -> None:
    script = read("vi-editor-structure-net.js")

    assert "function hiddenObjectIds" in script
    assert "function applyFrameVisibility" in script
    assert "function switchFrame" in script
    assert "inactive_structure_frame_wires" in script
    assert "block-diagram-inactive" in script
    assert "frame_view_mode = 'browser-only'" in script
    assert "VIには未保存" in script
    assert "apiRequest(" not in script
    assert "S.local.clear" not in script
    assert "S.dirty.clear" not in script


def test_frame_switch_rebuilds_object_wire_and_net_relationships() -> None:
    script = read("vi-editor-structure-net.js")

    assert "function rebuildRelationships" in script
    assert "function rebuildNets" in script
    assert "terminal_ids = []" in script
    assert "linked_terminal_ids = []" in script
    assert "wire_ids = []" in script
    assert "child_object_ids = []" in script
    assert "wire.endpoint_object_ids" in script
    assert "summary.wire_nets" in script
    assert "structure_frame_runtime" in script


def test_structure_inspector_exposes_previous_next_and_select() -> None:
    script = read("vi-editor-structure-net.js")
    styles = read("semantic-structure-net.css")

    for control in (
        "vi-structure-frame-section",
        "vi-structure-frame-previous",
        "vi-structure-frame-select",
        "vi-structure-frame-next",
    ):
        assert control in script
    assert "Structureフレーム" in script
    assert "閲覧のみ" in script
    assert ".vi-frame-controls" in styles
    assert ".vi-workflow-note" in styles


def test_net_inspector_tracks_complete_net_and_endpoints() -> None:
    script = read("vi-editor-structure-net.js")
    styles = read("semantic-structure-net.css")

    assert "function selectedNet" in script
    assert "function netEndpoints" in script
    assert "function selectNet" in script
    assert "function cycleNetEndpoint" in script
    assert "function focusNet" in script
    assert "net.branch_ids" in script
    assert "source_terminal_id" in script
    assert "target_terminal_ids" in script
    assert "is-net-selected" in script
    assert "is-net-source" in script
    assert "is-net-sink" in script
    assert "has-net-workflow-selection" in styles
    assert ".vi-net-endpoint.is-source" in styles
    assert ".vi-net-endpoint.is-sink" in styles


def test_stability_layer_prevents_title_observer_loop_and_aligns_targets() -> None:
    script = read("vi-editor-structure-net-stability.js")

    assert "stabilizeStructureTitles" in script
    assert "group.querySelector(':scope > title')?.remove()" in script
    assert "aria-description" in script
    assert "normalizeNetEndpoints" in script
    assert "terminal?.linked_object_id" in script
    assert "terminal?.owner_object_id" in script
    assert "vi-structure-frame-changed" in script


def test_workflow_loads_after_density_and_integrity() -> None:
    pages = read("pages.js")
    loader = read("vi-editor-runtime-fixes.js")

    assert "semantic-structure-net.css?v=1" in pages
    assert "vi-editor-runtime-fixes.js?v=5" in pages
    assert "vi-editor-structure-net-stability.js?v=1" in loader
    assert "vi-editor-structure-net.js?v=1" in loader
    assert loader.index("vi-editor-integrity") < loader.index("vi-editor-structure-net")
    assert loader.index("vi-editor-density-memory") < loader.index(
        "vi-editor-structure-net-stability"
    )
    assert loader.index("vi-editor-structure-net-stability") < loader.index(
        "vi-editor-structure-net.js"
    )
