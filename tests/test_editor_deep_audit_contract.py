from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"
ROOT = Path(__file__).resolve().parents[1]


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_integrity_layer_is_loaded_before_canvas_view_runtimes() -> None:
    pages = read("pages.js")
    loader = read("vi-editor-runtime-fixes.js")

    assert "semantic-integrity.css?v=1" in pages
    assert "semantic-readability.css?v=1" in pages
    assert "vi-editor-runtime-fixes.js?v=10" in pages
    assert "vi-editor-integrity.js?v=1" in loader
    assert "vi-editor-readability.js?v=1" in loader
    assert "vi-editor-component-projection.js?v=1" in loader
    assert "vi-editor-component-anchor.js?v=1" in loader
    assert "vi-editor-component-coordinate-space.js?v=1" in loader
    assert "vi-editor-component-terminal-visual.js?v=1" in loader
    assert "vi-editor-component-geometry-consistency.js?v=1" in loader
    assert "vi-editor-component-fit.js?v=1" in loader
    assert loader.index("vi-editor-type-definitions") < loader.index(
        "vi-editor-integrity"
    )
    assert loader.index("vi-editor-integrity") < loader.index("vi-editor-density")
    assert loader.index("vi-editor-density-memory") < loader.index(
        "vi-editor-readability"
    )
    assert loader.index("vi-editor-readability") < loader.index(
        "vi-editor-component-projection"
    )
    assert loader.index("vi-editor-component-projection") < loader.index(
        "vi-editor-component-anchor"
    )
    assert loader.index("vi-editor-component-anchor") < loader.index(
        "vi-editor-component-coordinate-space"
    )
    assert loader.index("vi-editor-component-coordinate-space") < loader.index(
        "vi-editor-component-terminal-visual"
    )
    assert loader.index("vi-editor-component-terminal-visual") < loader.index(
        "vi-editor-component-geometry-consistency"
    )


def test_wire_integrity_layer_preserves_endpoints_nets_and_filters() -> None:
    script = read("vi-editor-integrity.js")

    assert "routePoints" in script
    assert "source_terminal_id" in script
    assert "target_terminal_ids" in script
    assert "routeIntegrity" in script
    assert "orthogonal-endpoints" in script
    assert "orthogonal-projected-endpoints" in script
    assert "VIComponentProjection.projectedCenter" in script
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
    assert "is-depth-${index}" in script
    assert "for (let index = 0; index <= 6; index += 1)" in script
    for depth in range(7):
        assert f"is-depth-{depth}" in styles


def test_workspace_progress_and_rebuild_are_core_level_fixes() -> None:
    workspace = read("workspace.js")
    styles = read("semantic-integrity.css")

    assert "function setProgressPercent" in workspace
    assert ".style.width" not in workspace
    assert ".style.removeProperty" not in workspace
    assert "is-progress-${step}" in workspace
    for step in range(21):
        assert f"is-progress-{step}" in styles
    rebuild = workspace.split("async function rebuildCurrentJob", 1)[1].split(
        "async function deleteCurrentJob", 1
    )[0]
    assert "activePage" in rebuild
    assert "open('build')" not in rebuild
    assert "現在の画面を維持" in rebuild


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
