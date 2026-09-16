from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_readable_fit_uses_fresh_cache_version() -> None:
    pages = read("pages.js")
    loader = read("vi-editor-runtime-fixes.js")

    assert "vi-editor-runtime-fixes.js?v=12.4.2" in pages
    assert "vi-editor-component-fit.js?v=1.2" in loader


def test_readable_fit_uses_independent_spacing_signals() -> None:
    script = read("vi-editor-component-fit.js")

    for target in (
        "horizontalGap",
        "verticalGap",
        "bendRun",
        "labelGap",
        "flowOccupancy",
        "flowStartViewportRatio",
    ):
        assert target in script
    for function in (
        "function wireRoutes",
        "function directionalPairs",
        "function nodeSpacingMetrics",
        "function wireBendMetrics",
        "function flowMetrics",
        "function labelMetrics",
        "function readabilityMetrics",
        "function scaleDecision",
    ):
        assert function in script
    for candidate in (
        "candidates.component",
        "candidates.horizontalGap",
        "candidates.verticalGap",
        "candidates.bendRun",
        "candidates.labelGap",
        "candidates.flowOccupancy",
    ):
        assert candidate in script


def test_overview_readable_and_focus_have_distinct_bounds_policies() -> None:
    script = read("vi-editor-component-fit.js")

    assert "reason: 'full-content'" in script
    assert "reason: 'selected-flow'" in script
    assert "selectionOnly = mode === 'focus'" in script
    assert "includeWires: true" in script
    assert "includeLabels: true" in script
    assert "const selected = selectionOnly ? selectedContext() : null" in script
    assert "wiresForItem(item)" in script
    assert "wireEndpointIds(wire)" in script
    assert "metrics.flow.flowStartX" in script
    assert "policy.flowStartViewportRatio" in script


def test_readable_fit_contains_small_surfaces_and_preserves_large_ones() -> None:
    script = read("vi-editor-component-fit.js")

    assert "minimumScale: 0.64" in script
    assert "maximumScale: 1.82" in script
    assert "focusMinimum: 0.82" in script
    assert "focusMaximum: 2.10" in script
    assert "readableFullContentLimit: 8" in script
    assert "readableFitSlack: 0.96" in script
    assert "function readableContentCount" in script
    assert "function shouldContainReadableContent" in script
    assert "'small-full-content'" in script
    assert "Math.min(boundedRequested, fitScale)" in script
    assert ": boundedRequested" in script
    readable = script.split("function scaleDecision", 1)[1].split(
        "function scaleForMode", 1
    )[0]
    assert "const containFullContent" in readable
    assert "policy.overviewMinimum" in readable


def test_fit_diagnostics_are_exposed_without_editing_vi_geometry() -> None:
    script = read("vi-editor-component-fit.js")

    assert "runtime.lastMetrics" in script
    assert "runtime.lastDecision" in script
    assert "shell.dataset.viFitReason" in script
    assert "shell.dataset.viFlowDirectionality" in script
    assert "shell.dataset.viHorizontalGap" in script
    assert "shell.dataset.viBendRun" in script
    assert "activeDensity.readabilityMetrics = readabilityMetrics" in script
    assert "item.bounds =" not in script
    assert "S.local.set" not in script
    assert "S.dirty.add" not in script


def test_fit_has_no_server_or_xml_write_path() -> None:
    script = read("vi-editor-component-fit.js")

    assert "fetch(" not in script
    assert "XMLHttpRequest" not in script
    assert "sendBeacon" not in script
    assert "XMLSerializer" not in script
    assert "state().payload =" not in script
    assert "state().vi =" not in script
