from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def editor_scripts() -> str:
    return "\n".join(
        (STATIC / name).read_text(encoding="utf-8")
        for name in ("graph.js", "vi-editor-list.js", "vi-editor-canvas.js")
    )


def test_model_page_loads_semantic_editor_assets() -> None:
    index = (STATIC / "index.html").read_text(encoding="utf-8")

    assert '<link rel="stylesheet" href="/static/semantic-workspace.css">' in index
    graph_position = index.index('<script src="/static/graph.js" defer></script>')
    list_position = index.index('<script src="/static/vi-editor-list.js" defer></script>')
    canvas_position = index.index('<script src="/static/vi-editor-canvas.js" defer></script>')
    assert graph_position < list_position < canvas_position


def test_model_page_is_a_semantic_two_surface_editor() -> None:
    script = editor_scripts()
    styles = (STATIC / "semantic-workspace.css").read_text(encoding="utf-8")

    assert "payload.vi" in script
    assert 'data-vi-surface="front-panel"' in script
    assert 'data-vi-surface="block-diagram"' in script
    assert 'id="vi-object-list"' in script
    assert 'id="vi-geometry-editor"' in script
    assert "source_terminal_id" in script
    assert "target_terminal_ids" in script
    assert "linked_terminal_ids" in script
    assert "method: 'PATCH'" in script
    assert "expected_file_sha256" in script
    assert "vi-resize-handle" in script
    assert ".vi-front-panel-body" in styles
    assert ".vi-block-node-body" in styles
    assert ".vi-terminal-body" in styles
    assert ".vi-wire" in styles


def test_editor_uses_native_routes_and_cross_surface_links() -> None:
    script = editor_scripts()

    assert "route_points" in script
    assert "data-route-source" in script
    assert "data-route-point-count" in script
    assert "vi-wire-bend" in script
    assert "counterpartId" in script
    assert "linked_object_id" in script
    assert "dblclick" in script
    assert "対応部品へ移動" in script


def test_editor_preserves_view_and_selection_on_same_job_reload() -> None:
    script = editor_scripts()

    assert "captureView" in script
    assert "preserveView" in script
    assert "restore?.selected" in script
    assert "restore?.box" in script
    assert "sameJob" in script


def test_xml_is_demoted_to_collapsed_diagnostics() -> None:
    script = editor_scripts()

    assert 'id="vi-source-debug"' in script
    assert "解析元（デバッグ）" in script
    assert "XMLは解析元としてのみ保持します" in script
    assert "XMLドキュメント" not in script


def test_editor_keeps_existing_browser_acceptance_ids() -> None:
    script = editor_scripts()

    for selector_id in (
        "model-graph-svg",
        "model-graph-layer",
        "model-graph-fit",
        "model-graph-zoom-in",
        "model-graph-zoom-out",
        "model-graph-state",
    ):
        assert f'id="{selector_id}"' in script
    assert "model-node" in script
    assert "model-edge" in script
