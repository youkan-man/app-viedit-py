from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_coordinate_space_normalizer_loads_after_anchor_before_fit() -> None:
    loader = read("vi-editor-runtime-fixes.js")

    assert "vi-editor-component-coordinate-space.js?v=1" in loader
    assert loader.index("vi-editor-component-anchor") < loader.index(
        "vi-editor-component-coordinate-space"
    )
    assert loader.index("vi-editor-component-coordinate-space") < loader.index(
        "vi-editor-component-fit"
    )


def test_explicit_absolute_owner_anchored_bounds_are_not_treated_as_local() -> None:
    script = read("vi-editor-component-coordinate-space.js")

    assert "space.includes('absolute')" in script
    assert "space.includes('owner-anchored')" in script
    assert "return 'absolute'" in script
    assert "space.includes('parent-relative')" in script
    assert "return 'relative'" in script
    absolute_position = script.index("space.includes('absolute')")
    relative_id_fallback = script.index(
        "item?.bounds?.relative_to_object_id === owner?.id"
    )
    assert absolute_position < relative_id_fallback


def test_semantic_anchor_ratios_have_priority_over_coordinate_heuristics() -> None:
    script = read("vi-editor-component-coordinate-space.js")

    assert "function explicitAnchor" in script
    assert "item?.bounds?.anchor_x" in script
    assert "item?.bounds?.anchor_y" in script
    assert "source: 'semantic-anchor'" in script
    assert "const semantic = explicitAnchor(item)" in script
    assert "runtime.anchors.set(item, value)" in script


def test_coordinate_space_normalizer_owns_final_terminal_and_wire_projection() -> None:
    script = read("vi-editor-component-coordinate-space.js")

    assert "P.runtime?.observer?.disconnect?.()" in script
    assert "A?.runtime?.observer?.disconnect?.()" in script
    assert "P.projectBounds = projectBounds" in script
    assert "P.projectedCenter = projectedCenter" in script
    assert "P.projectedWirePoints = projectedWirePoints" in script
    assert "function applyTerminal" in script
    assert "function applyWire" in script
    assert "coordinateSpaceEndpoints" in script
    assert "renderCanvasWithCoordinateSpaces" in script
    assert "renderAllWithCoordinateSpaces" in script


def test_coordinate_space_normalization_is_display_only() -> None:
    script = read("vi-editor-component-coordinate-space.js")

    assert "item.bounds =" not in script
    assert "S.local.set" not in script
    assert "S.dirty.add" not in script
    assert "source_property_id" not in script
    assert "setAttribute('viewBox'" not in script


def test_final_suite_exercises_absolute_owner_anchored_terminals() -> None:
    suite = (ROOT / "scripts" / "sandbox_component_projection_test.sh").read_text(
        encoding="utf-8"
    )
    browser_test = (
        ROOT / "scripts" / "semantic_component_coordinate_space_test.py"
    ).read_text(encoding="utf-8")

    assert "semantic_component_coordinate_space_test.py" in suite
    assert "semantic-component-coordinate-space.json" in suite
    assert "component-coordinate-space-1440x900.png" in suite
    assert 'run_stage coordinate-space "$PYTHON"' in suite
    assert 'source_coordinate_space": "absolute-owner-anchored"' in browser_test
    assert '"anchor_x": 1.0' in browser_test
    assert '"anchor_y": 0.75' in browser_test
    assert "source terminal native bounds changed" in browser_test
    assert "display projection dirtied terminal records" in browser_test
