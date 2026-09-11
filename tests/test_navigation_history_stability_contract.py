from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_history_stability_runtime_loads_after_navigation_workflow() -> None:
    pages = read("pages.js")

    assert "vi-editor-navigation-history-stability.js?v=1" in pages
    assert "data-vi-navigation-history-stability" in pages
    assert pages.index("vi-editor-runtime-fixes.js?v=12") < pages.index(
        "vi-editor-navigation-history-stability.js?v=1"
    )


def test_history_replay_waits_for_density_surface_restore_to_settle() -> None:
    script = read("vi-editor-navigation-history-stability.js")

    assert "function settleReplay" in script
    assert "!D?.scheduled" in script
    assert "!D?.pendingSurface" in script
    assert "!D?.applying" in script
    assert "S.selected === snapshot.id" in script
    assert "S.surface === snapshot.surface" in script
    assert "stableFrames + 1" in script
    assert "MAX_SETTLE_ATTEMPTS = 24" in script


def test_history_replay_primes_target_surface_and_uses_one_path() -> None:
    script = read("vi-editor-navigation-history-stability.js")

    assert "function primeSurfaceView" in script
    assert "D.runtime.surfaceViews.set(snapshot.surface" in script
    assert "W.goBack = goBack" in script
    assert "W.goForward = goForward" in script
    assert "window.addEventListener('keydown', handleHistoryKey, true)" in script
    assert "event.stopImmediatePropagation()" in script
    assert "bindButton(R.elements?.back, goBack)" in script
    assert "bindButton(R.elements?.forward, goForward)" in script


def test_stale_history_replays_are_cancelled_without_geometry_edits() -> None:
    script = read("vi-editor-navigation-history-stability.js")

    assert "const token = ++runtime.token" in script
    assert "token !== runtime.token" in script
    assert "cancelPendingReplay" in script
    assert "runtime.token += 1" in script
    assert "source.jobKey !== jobKey()" in script
    assert "S.local.set" not in script
    assert "S.dirty.add" not in script
    assert "item.bounds =" not in script
    assert "source_property_id" not in script
    assert "apiRequest(" not in script
