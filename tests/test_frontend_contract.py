from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


def test_azure_portal_tokens_are_reused() -> None:
    styles = (STATIC / "styles.css").read_text(encoding="utf-8")
    shell = (STATIC / "azure-shell.css").read_text(encoding="utf-8")
    assert "--azure-blue: #0078d4;" in styles
    assert "--canvas: #f3f2f1;" in styles
    assert '"Segoe UI"' in styles
    assert "--radius: 2px;" in styles
    assert ".azure-application-shell" in shell
    assert ".azure-navigation" in shell
    assert ".azure-context-pane" in shell


def test_header_modal_and_left_navigation_replace_stacked_import_page() -> None:
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    workspace = (STATIC / "workspace.js").read_text(encoding="utf-8")
    pages = (STATIC / "pages.js").read_text(encoding="utf-8")

    assert 'id="header-open"' in index
    assert 'id="open-dialog"' in index
    assert 'id="open-dropzone"' in index
    assert 'id="open-progress-view"' in index
    assert 'id="header-reconvert"' in index
    assert 'id="header-refresh"' in index
    assert 'id="header-rebuild"' in index
    assert 'data-app-page="model"' in index
    assert 'data-app-page="properties"' in index
    assert 'data-app-page="xml"' in index
    assert 'data-app-page="align"' in index
    assert 'data-app-page="build"' in index
    assert 'data-app-page="import"' not in index
    assert "new XMLHttpRequest()" in workspace
    assert "beginProcessingProgress" in workspace
    assert "globalThis.viPages?.setJob" in workspace
    assert "model: { title: 'モデル'" in pages
    assert "properties: { title: 'プロパティ'" in pages

    for rejected in ("Convert", "Inspect", "Edit", "Rebuild", "page-heading-facts", "変換ジョブ"):
        assert rejected not in index


def test_unified_model_graph_and_xml_structure_are_separate_pages() -> None:
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    graph = (STATIC / "graph.js").read_text(encoding="utf-8")
    explorer = (STATIC / "components.js").read_text(encoding="utf-8")

    assert 'id="model-graph-svg"' in index
    assert 'id="model-inspector-connections"' in index
    assert 'id="component-model-mount"' in index
    assert 'data-app-page-panel="model"' in index
    assert 'data-app-page-panel="properties"' in index
    assert "payload.graph" in graph
    assert "model.position" in graph
    assert "graph.connections" in graph
    assert "method: 'PATCH'" in explorer
    assert "expected_file_sha256" in explorer


def test_quantizer_targets_real_xml_dataset_not_fake_layout_canvas() -> None:
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    script = (STATIC / "quantizer.js").read_text(encoding="utf-8")
    all_frontend = index + script
    assert 'id="quantize-form"' in index
    assert 'id="quantize-grid-size"' in index
    assert 'id="quantize-connectors"' in index
    assert 'id="quantize-wires"' in index
    assert "/quantize/preview" in script
    assert "/quantize/apply" in script
    for rejected in ("Layout Grid", "layout-editor.js", "layout-editor.css", "VISUAL LAYOUT", "layout-canvas", "AzureGridView"):
        assert rejected not in all_frontend


def test_component_explorer_does_not_render_dataset_values_as_html() -> None:
    explorer = (STATIC / "components.js").read_text(encoding="utf-8")
    assert "section.innerHTML = `" in explorer
    assert "explorer.elements.inspector.innerHTML = inspectorMarkup()" in explorer
    assert "element.textContent = value" in explorer
    assert "row.innerHTML" not in explorer
    assert "prop.preview}`" not in explorer
