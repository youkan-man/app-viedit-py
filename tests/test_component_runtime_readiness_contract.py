from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_runtime_loader_waits_for_each_component_projection_layer() -> None:
    loader = read("vi-editor-runtime-fixes.js")

    for global_name in (
        "VIComponentPrimer",
        "VIComponentProjection",
        "VIComponentAnchors",
        "VIComponentCoordinateSpace",
        "VIComponentFit",
    ):
        assert global_name in loader
    assert "async function waitForReady" in loader
    assert "value?.ready === true" in loader
    assert "value?.error" in loader
    assert "did not become ready" in loader
    assert "await waitForReady(readyGlobal, flag)" in loader


def test_projected_fit_cannot_load_before_coordinate_normalization_is_ready() -> None:
    loader = read("vi-editor-runtime-fixes.js")

    coordinate = loader.index("'VIComponentCoordinateSpace'")
    fit = loader.index("'VIComponentFit'")
    loop = loader.index("await waitForReady(readyGlobal, flag)")
    assert coordinate < fit
    assert loop > fit
