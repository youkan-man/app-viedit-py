from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_wire_stability_loads_after_final_interaction_overlays() -> None:
    pages = read("pages.js")
    loader = read("vi-editor-runtime-fixes.js")

    assert "vi-editor-runtime-fixes.js?v=12.3" in pages
    assert "vi-editor-wire-stability.js?v=1" in loader
    assert "VIWireStability" in loader
    assert loader.index("vi-editor-multi-selection-polish") < loader.index(
        "vi-editor-compact-resize-handles"
    )
    assert loader.index("vi-editor-compact-resize-handles") < loader.index(
        "vi-editor-wire-stability"
    )
    assert "await waitForReady(readyGlobal, flag)" in loader


def test_canonical_routes_are_strictly_orthogonal_and_endpoint_anchored() -> None:
    script = read("vi-editor-wire-stability.js")

    assert "function branchEndpoints" in script
    assert "projectedCenter(wire?.source_terminal_id)" in script
    assert "projectedCenter(targetTerminalId)" in script
    assert "function canonicalizePoints" in script
    assert "function orientPoints" in script
    assert "function trimEndpointPoints" in script
    assert "function collapseRepeatedVertices" in script
    assert "function removeRedundant" in script
    assert "function validOrthogonalRoute" in script
    assert "compact[0] = source" in script
    assert "compact[compact.length - 1] = target" in script
    assert "samePoint(source, target)" in script
    assert "segmentAxis(points[index], point)" in script
    assert "commands.push(`H ${current.x}`)" in script
    assert "commands.push(`V ${current.y}`)" in script
    assert "commands.push(`L ${current.x} ${current.y}`)" not in script


def test_visible_and_hit_paths_share_one_canonical_path() -> None:
    script = read("vi-editor-wire-stability.js")

    assert "const visible = ensurePath(group, 'vi-wire')" in script
    assert "const hit = ensurePath(group, 'vi-wire-hit', visible)" in script
    assert "setPath(visible, path)" in script
    assert "setPath(hit, path)" in script
    assert "paths.forEach((element) => element.remove())" in script
    assert "function uniqueWireGroups" in script
    assert "if (seen.has(key))" in script
    assert "group.remove()" in script
    assert "group.dataset.wireStable = 'true'" in script
    assert "group.dataset.stablePointCount" in script


def test_render_completion_applies_wires_synchronously() -> None:
    script = read("vi-editor-wire-stability.js")
    render_canvas = script.split(
        "E.renderCanvas = function renderCanvasWithStableWires", 1
    )[1].split("E.renderAll = function", 1)[0]
    render_all = script.split(
        "E.renderAll = function renderAllWithStableWires", 1
    )[1].split("return true;", 1)[0]
    projection_decorate = script.split(
        "P.decorate = function decorateWithStableWires", 1
    )[1].split("P.schedule = function", 1)[0]

    assert "decorate();" in render_canvas
    assert "decorate();" in render_all
    assert "decorate();" in projection_decorate
    assert "schedule();" not in render_canvas
    assert "schedule();" not in render_all


def test_late_legacy_path_mutations_are_repaired_before_paint() -> None:
    script = read("vi-editor-wire-stability.js")

    assert "function installObserver" in script
    assert "mutation.attributeName === 'd'" in script
    assert "mutation.target.matches?.('.vi-wire,.vi-wire-hit')" in script
    assert "if (pathChanged)" in script
    assert "decorate();" in script
    assert "attributeFilter: ['d']" in script
    assert "mutation.type === 'childList'" in script
    assert "ResizeObserver" not in script
    assert "viewport.addEventListener('wheel'" not in script
    assert "mutation.attributeName === 'viewBox'" not in script


def test_invalid_or_unresolved_routes_never_leave_stale_visible_paths() -> None:
    script = read("vi-editor-wire-stability.js")

    assert "if (!path)" in script
    assert "group.classList.add('is-wire-route-unresolved')" in script
    assert "group.setAttribute('visibility', 'hidden')" in script
    assert "group.dataset.wireStable = 'unresolved'" in script
    assert "group.removeAttribute('visibility')" in script
    assert "Number.isFinite(x) && Number.isFinite(y)" in script


def test_wire_stability_is_display_only() -> None:
    script = read("vi-editor-wire-stability.js")

    assert "S.local.set" not in script
    assert "S.dirty.add" not in script
    assert "item.bounds =" not in script
    assert "source_property_id" not in script
    assert "setAttribute('viewBox'" not in script
    assert "route_points =" not in script
