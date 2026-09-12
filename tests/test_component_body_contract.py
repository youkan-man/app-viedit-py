from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_primer_restores_canonical_body_dimensions_before_projection() -> None:
    script = read("vi-editor-component-primer.js")
    prepare = script.split("function prepare()", 1)[1].split(
        "function schedule()", 1
    )[0]

    assert "function normalizeCanonicalBodies" in script
    assert ".vi-front-panel-body" in script
    assert ".vi-block-node-body" in script
    assert ".vi-terminal-body" in script
    assert "setAttribute(body, 'width', bounds.width)" in script
    assert "setAttribute(body, 'height', bounds.height)" in script
    assert "body.dataset.nativeLogicalBody = 'true'" in script
    assert prepare.index("VIRealism?.decorate?.()") < prepare.index(
        "VIComponentVisuals?.decorate?.()"
    )
    assert prepare.index("VIComponentVisuals?.decorate?.()") < prepare.index(
        "normalizeCanonicalBodies()"
    )
    assert prepare.index("normalizeCanonicalBodies()") < prepare.index(
        "VIReadability?.decorate?.()"
    )


def test_primer_reasserts_canonical_body_size_after_async_dom_updates() -> None:
    script = read("vi-editor-component-primer.js")

    assert "runtime.observer = new MutationObserver" in script
    assert "attributeFilter: ['x', 'y', 'width', 'height']" in script
    assert "mutation.type !== 'childList'" in script
    assert "function mutationContainsObjectNode" in script
    assert "node.matches?.('[data-object-id]')" in script
    assert "node.querySelector?.('[data-object-id]')" in script
    assert "VIComponentVisuals.runtime?.observer?.disconnect?.()" in script
    assert "if (element.getAttribute(name) !== next)" in script
    assert "function schedule" in script


def test_body_normalization_does_not_touch_editable_vi_geometry() -> None:
    script = read("vi-editor-component-primer.js")

    assert "item.bounds =" not in script
    assert "S.local.set" not in script
    assert "S.dirty.add" not in script
    assert "source_property_id" not in script
    assert "setAttribute('viewBox'" not in script
