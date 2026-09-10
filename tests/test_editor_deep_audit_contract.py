from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"
ROOT = Path(__file__).resolve().parents[1]


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_integrity_layer_is_loaded_after_semantic_runtime() -> None:
    pages = read("pages.js")
    loader = read("vi-editor-runtime-fixes.js")

    assert "semantic-integrity.css?v=1" in pages
    assert "vi-editor-runtime-fixes.js?v=3" in pages
    assert "vi-editor-integrity.js?v=1" in loader
    assert loader.index("vi-editor-type-definitions") < loader.index("vi-editor-integrity")


def test_wire_integrity_layer_preserves_endpoints_nets_and_filters() -> None:
    script = read("vi-editor-integrity.js")

    assert "routePoints" in script
    assert "source_terminal_id" in script
    assert "target_terminal_ids" in script
    assert "routeIntegrity" in script
    assert "orthogonal-endpoints" in script
    assert "net_id" in script
    assert "is-net-related" in script
    assert "is-filter-hidden" in script
    assert "model-graph-query" in script
    assert "model-graph-kind" in script
    assert "generic XML" not in script


def test_hierarchy_rendering_does_not_require_inline_styles() -> None:
    script = read("vi-editor-realism.js")
    styles = read("semantic-integrity.css")

    assert ".style." not in script
    assert ".style =" not in script
    assert "setDepthClass" in script
    for depth in range(7):
        assert f"is-depth-{depth}" in script
        assert f"is-depth-{depth}" in styles


def test_semantic_parser_dependency_has_a_notice() -> None:
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert "pragmatest-dev/lvkit" in requirements
    assert "pragmatest-dev/lvkit" in notices
    assert "6ed96ce2ebc93940544b713755956bd1be5f3848" in notices


def test_integrity_model_exposes_diagnostics_instead_of_silent_repair() -> None:
    script = read("vi-editor-integrity.js")

    assert "vi-semantic-integrity-status" in script
    assert "意味解析済み" in script
    assert "誤ったブロック図は表示しません" in script
    assert "type_conflicts" in script
