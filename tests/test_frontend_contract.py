from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


def test_azure_portal_tokens_are_reused() -> None:
    styles = (STATIC / "styles.css").read_text(encoding="utf-8")
    assert "--azure-blue: #0078d4;" in styles
    assert "--canvas: #f3f2f1;" in styles
    assert '"Segoe UI"' in styles
    assert "--radius: 2px;" in styles


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
    assert "current_main_xml" in script
    assert "await renderJob(updated" in script

    for rejected in (
        "Layout Grid",
        "layout-editor.js",
        "layout-editor.css",
        "VISUAL LAYOUT",
        "layout-canvas",
        "AzureGridView",
    ):
        assert rejected not in all_frontend


def test_workspace_is_grouped_by_task_instead_of_stacking_every_tool() -> None:
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    workspace = (STATIC / "workspace.js").read_text(encoding="utf-8")
    styles = (STATIC / "styles-workspace.css").read_text(encoding="utf-8")

    assert '<details id="converter-card"' in index
    assert 'id="new-job"' in index
    assert 'data-workspace-tab="components"' in index
    assert 'data-workspace-tab="xml"' in index
    assert 'data-workspace-tab="coordinates"' in index
    assert 'data-workspace-tab="logs"' in index
    assert 'id="workspace-panel-components"' in index
    assert 'id="workspace-panel-xml"' in index and 'data-workspace-panel="xml" hidden' in index
    assert 'id="workspace-panel-coordinates"' in index and 'data-workspace-panel="coordinates" hidden' in index
    assert 'id="workspace-panel-logs"' in index and 'data-workspace-panel="logs" hidden' in index
    assert 'id="component-model-mount"' in index
    assert "function activateWorkspaceTab" in workspace
    assert "converter.open = false" in workspace
    assert "document.body.classList.add('has-active-job')" in workspace
    assert ".workspace-tabs" in styles
    assert ".workspace-panel[hidden]" in styles
    assert ".workspace-menu-popover" in styles


def test_component_explorer_is_loaded_and_uses_component_apis() -> None:
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    workspace = (STATIC / "workspace.js").read_text(encoding="utf-8")
    explorer = (STATIC / "components.js").read_text(encoding="utf-8")
    styles = (STATIC / "components.css").read_text(encoding="utf-8")

    assert '<script src="/static/components.js" defer></script>' in index
    assert 'data-component-explorer-style' in index
    assert "mountComponentExplorer" in workspace
    assert "viComponentExplorer" in workspace
    assert "/model`" in explorer
    assert "/components?" in explorer
    assert "method: 'PATCH'" in explorer
    assert "expected_file_sha256" in explorer
    assert "property_tree" in explorer
    assert "component-model-layout" in styles
    assert "component-property-row" in styles
    assert "component-geometry" in styles


def test_component_explorer_does_not_render_dataset_values_as_html() -> None:
    explorer = (STATIC / "components.js").read_text(encoding="utf-8")

    # innerHTML is used only for static application-owned templates. Dataset
    # values are assigned through textContent/textNode and never interpolated.
    assert "section.innerHTML = `" in explorer
    assert "explorer.elements.inspector.innerHTML = inspectorMarkup()" in explorer
    assert "element.textContent = value" in explorer
    assert "row.innerHTML" not in explorer
    assert "prop.preview}`" not in explorer
