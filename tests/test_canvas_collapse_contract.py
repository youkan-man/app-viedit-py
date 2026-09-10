from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_object_pane_collapse_removes_the_grid_track() -> None:
    runtime = read("semantic-density-runtime.css")

    selector = (
        "#page-stack.is-model-page "
        ".vi-editor-shell.is-object-pane-collapsed .vi-editor-layout"
    )
    assert selector in runtime
    section = runtime.split(selector, 1)[1].split("}", 1)[0]
    assert "display: block" in section
    assert "width: 100%" in section
    assert "height: 100%" in section

    canvas_selector = (
        "#page-stack.is-model-page "
        ".vi-editor-shell.is-object-pane-collapsed .vi-canvas-pane"
    )
    assert canvas_selector in runtime
    canvas_section = runtime.split(canvas_selector, 1)[1].split("}", 1)[0]
    assert "width: 100%" in canvas_section
    assert "height: 100%" in canvas_section


def test_context_pane_collapse_bypasses_intrinsic_grid_sizing() -> None:
    runtime = read("semantic-density-runtime.css")

    shell_selector = (
        'body[data-active-page="model"].vi-context-pane-collapsed '
        ".azure-application-shell"
    )
    assert shell_selector in runtime
    shell_section = runtime.split(shell_selector, 1)[1].split("}", 1)[0]
    assert "display: block" in shell_section
    assert "grid-template-columns" not in shell_section

    navigation_selector = (
        'body[data-active-page="model"].vi-context-pane-collapsed '
        ".azure-navigation"
    )
    navigation_section = runtime.split(navigation_selector, 1)[1].split("}", 1)[0]
    assert "position: absolute" in navigation_section
    assert "width: var(--navigation-width)" in navigation_section

    stage_selector = (
        'body[data-active-page="model"].vi-context-pane-collapsed '
        ".azure-content-stage"
    )
    stage_section = runtime.split(stage_selector, 1)[1].split("}", 1)[0]
    assert "position: absolute" in stage_section
    assert "inset: 0 0 0 var(--navigation-width)" in stage_section
    assert "width: auto" in stage_section
    assert "max-width: none" in stage_section


def test_primary_canvas_actions_are_not_put_in_a_scroll_clip() -> None:
    runtime = read("semantic-density-runtime.css")
    toolbar = read("vi-editor-density-toolbar.js")

    selector = "#page-stack.is-model-page .vi-canvas-actions"
    section = runtime.split(selector, 1)[1].split("}", 1)[0]
    assert "overflow: visible" in section
    assert "overflow-x: auto" not in section
    assert "vi-density-options" in toolbar
    assert "labels.forEach((label) => panel.append(label))" in toolbar
