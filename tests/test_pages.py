from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def test_ui_is_split_into_function_pages() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")

    for page in ("import", "model", "xml", "align", "build"):
        assert f'data-app-page="{page}"' in html
        assert f'data-app-page-panel="{page}"' in html

    assert 'id="model-view-graph"' in html
    assert 'id="model-view-properties"' in html
    assert 'class="metrics component-model-anchor"' in html
    assert '/static/pages.js' in html
    assert '/static/graph.js' in html

    # The former single scrolling page must not return.
    assert html.index('id="page-model"') < html.index('id="page-xml"')
    assert html.index('id="page-xml"') < html.index('id="page-align"')
    assert html.index('id="page-align"') < html.index('id="page-build"')


def test_model_page_is_graph_first_and_uses_dataset_wide_model() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    script = (STATIC / "graph.js").read_text(encoding="utf-8")

    for element_id in (
        "model-graph-svg",
        "model-document-list",
        "model-unresolved-list",
        "model-inspector-connections",
        "model-graph-layer",
        "model-graph-kind",
    ):
        assert f'id="{element_id}"' in html

    assert "/api/jobs/" in script
    assert "/model" in script
    assert "graph.models" in script
    assert "graph.connections" in script
    assert "model.position" in script
    assert "edge.source" in script
    assert "edge.target" in script
