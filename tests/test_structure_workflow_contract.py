from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_structure_workflow_assets_load_after_readability() -> None:
    pages = read("pages.js")
    loader = read("vi-editor-runtime-fixes.js")

    assert "semantic-structure-workflow.css?v=1" in pages
    assert "vi-editor-runtime-fixes.js?v=6" in pages
    assert "vi-editor-structure-workflow.js?v=1" in loader
    assert loader.index("vi-editor-density-memory") < loader.index(
        "vi-editor-readability"
    )
    assert loader.index("vi-editor-readability") < loader.index(
        "vi-editor-structure-workflow"
    )


def test_frame_switch_uses_an_immutable_all_frame_wire_catalog() -> None:
    script = read("vi-editor-structure-workflow.js")

    assert "wireCatalog: new Map()" in script
    assert "all_structure_frame_wires" in script
    assert "inactive_structure_frame_wires" in script
    assert "function cloneWire" in script
    assert "function catalogWires" in script
    assert "function visibleWireProjection" in script
    assert "runtime.wireCatalog.forEach" in script
    assert "hidden_target_terminal_ids" in script
    assert "visible_branch_count" in script


def test_frame_visibility_is_recursive_and_browser_only() -> None:
    script = read("vi-editor-structure-workflow.js")

    assert "function directInactiveIds" in script
    assert "function hiddenObjectIds" in script
    assert "parentIds(item).some" in script
    assert "block-diagram-inactive" in script
    assert "frame_view_mode = 'browser-only'" in script
    assert "VIには未保存" in script
    assert "apiRequest(" not in script
    assert "S.local.clear" not in script
    assert "S.dirty.clear" not in script
    assert "source_property_id" not in script


def test_frame_sessions_preserve_selection_and_view_per_frame() -> None:
    script = read("vi-editor-structure-workflow.js")

    assert "frameSessions: new Map()" in script
    assert "function sessionKey" in script
    assert "function rememberFrameSession" in script
    assert "selectedId" in script
    assert "targetSession?.selectedId" in script
    assert "targetSession?.box" in script
    assert "targetSession?.mode" in script
    assert "VICanvasDensity.applyBox" in script
    assert "function belongsToStructure" in script


def test_switch_rebuilds_relationships_nets_summary_and_hierarchy() -> None:
    script = read("vi-editor-structure-workflow.js")

    assert "function resetRelationships" in script
    assert "function rebuildRelationships" in script
    assert "function rebuildNets" in script
    assert "terminal_ids = []" in script
    assert "linked_terminal_ids = []" in script
    assert "wire_ids = []" in script
    assert "child_object_ids = []" in script
    assert "wire.net_id = id" in script
    assert "branch_count: branchCount" in script
    assert "S.vi.hierarchy" in script
    assert "summary.hidden_structure_frame_wire_branches" in script
    assert "integrity.structure_frame_runtime" in script


def test_structure_frame_controls_run_in_place() -> None:
    script = read("vi-editor-structure-workflow.js")
    styles = read("semantic-structure-workflow.css")

    for control in (
        "vi-structure-frame-workflow",
        "vi-frame-previous",
        "vi-frame-select",
        "vi-frame-next",
    ):
        assert control in script
    assert "Structureフレーム" in script
    assert "閲覧のみ" in script
    assert "switchFrame(structureId" in script
    assert ".vi-frame-workflow-controls" in styles
    assert ".vi-workflow-note" in styles


def test_net_inspector_tracks_all_branches_and_endpoints() -> None:
    script = read("vi-editor-structure-workflow.js")
    styles = read("semantic-structure-workflow.css")

    for symbol in (
        "selectedNet",
        "netEndpoints",
        "selectNet",
        "cycleNetEndpoint",
        "focusNet",
    ):
        assert f"function {symbol}" in script
    for control in (
        "vi-net-workflow",
        "vi-net-focus",
        "vi-net-next-endpoint",
        "vi-net-open-type",
        "vi-net-branch-list",
    ):
        assert control in script
    assert "type_definition_id" in script
    assert "VITypeDefinitions?.open" in script
    assert "is-workflow-net" in script
    assert "is-workflow-net-source" in script
    assert "is-workflow-net-sink" in script
    assert ".has-workflow-net" in styles
    assert ".vi-net-endpoint.is-source" in styles
    assert ".vi-net-endpoint.is-sink" in styles


def test_frame_change_notifies_existing_readability_runtime() -> None:
    script = read("vi-editor-structure-workflow.js")

    assert "vi-structure-frame-changed" in script
    assert "VIReadability?.schedule?.()" in script
    assert "E.renderAll(false)" in script
