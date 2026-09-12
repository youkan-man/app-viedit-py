from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_runtime_loader_waits_for_each_component_projection_layer() -> None:
    loader = read("vi-editor-runtime-fixes.js")

    for global_name in (
        "VIComponentVisuals",
        "VIComponentPrimer",
        "VIComponentProjection",
        "VIComponentAnchors",
        "VIComponentCoordinateSpace",
        "VIComponentTerminalVisual",
        "VIComponentGeometryConsistency",
        "VIComponentFit",
        "VINavigationWorkflow",
        "VINavigationKeyboardGuard",
    ):
        assert global_name in loader
    assert "async function waitForReady" in loader
    assert "value?.ready === true" in loader
    assert "value?.error" in loader
    assert "did not become ready" in loader
    assert "await waitForReady(readyGlobal, flag)" in loader


def test_semantic_visuals_load_before_projection_and_navigation_layers() -> None:
    loader = read("vi-editor-runtime-fixes.js")

    visuals = loader.index("'VIComponentVisuals'")
    primer = loader.index("'VIComponentPrimer'")
    projection = loader.index("'VIComponentProjection'")
    coordinate = loader.index("'VIComponentCoordinateSpace'")
    terminal = loader.index("'VIComponentTerminalVisual'")
    consistency = loader.index("'VIComponentGeometryConsistency'")
    fit = loader.index("'VIComponentFit'")
    navigation = loader.index("'VINavigationWorkflow'")
    guard = loader.index("'VINavigationKeyboardGuard'")
    loop = loader.index("await waitForReady(readyGlobal, flag)")
    assert visuals < primer < projection < coordinate < terminal < consistency
    assert consistency < fit < navigation < guard
    assert loop > guard
