from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_primer_restores_canonical_body_dimensions_before_projection() -> None:
    script = read("vi-editor-component-primer.js")

    assert "function normalizeCanonicalBodies" in script
    assert ":scope > .vi-front-panel-body" in script
    assert ":scope > .vi-block-node-body" in script
    assert ":scope > .vi-terminal-body" in script
    assert "body.setAttribute('width', String(bounds.width))" in script
    assert "body.setAttribute('height', String(bounds.height))" in script
    assert "body.dataset.nativeLogicalBody = 'true'" in script
    assert script.index("VIRealism?.decorate?.()") < script.index(
        "normalizeCanonicalBodies()"
    )


def test_body_normalization_does_not_touch_editable_vi_geometry() -> None:
    script = read("vi-editor-component-primer.js")

    assert "item.bounds =" not in script
    assert "S.local.set" not in script
    assert "S.dirty.add" not in script
    assert "source_property_id" not in script
    assert "setAttribute('viewBox'" not in script
