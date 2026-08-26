from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'app' / 'static'


def test_azure_portal_tokens_are_reused() -> None:
    styles = (STATIC / 'styles.css').read_text(encoding='utf-8')
    assert '--azure-blue: #0078d4;' in styles
    assert '--canvas: #f3f2f1;' in styles
    assert '"Segoe UI"' in styles
    assert '--radius: 2px;' in styles


def test_quantizer_targets_real_xml_editor_not_fake_layout_canvas() -> None:
    index = (STATIC / 'index.html').read_text(encoding='utf-8')
    script = (STATIC / 'quantizer.js').read_text(encoding='utf-8')
    all_frontend = index + script

    assert 'id="quantize-form"' in index
    assert 'id="quantize-grid-size"' in index
    assert 'id="quantize-connectors"' in index
    assert 'id="quantize-wires"' in index
    assert '/quantize/preview' in script
    assert '/quantize/apply' in script
    assert 'current_main_xml' in script
    assert 'await renderJob(updated' in script

    for rejected in (
        'Layout Grid',
        'layout-editor.js',
        'layout-editor.css',
        'VISUAL LAYOUT',
        'layout-canvas',
    ):
        assert rejected not in all_frontend
