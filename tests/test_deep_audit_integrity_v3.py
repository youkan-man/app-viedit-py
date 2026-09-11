from __future__ import annotations

from app.deep_audit_runtime_patch import _postprocess


def test_deep_audit_postprocess_preserves_integrity_v3() -> None:
    vi = {
        "version": 6,
        "objects": [],
        "wires": [],
        "nets": [],
        "surfaces": {"front-panel": [], "block-diagram": []},
        "summary": {},
        "integrity": {"version": 3, "dangling_wires_removed": 0},
        "type_definitions": [],
    }

    result = _postprocess(vi)

    assert result["integrity"]["version"] == 3
    assert result["version"] == 6


def test_deep_audit_source_uses_runtime_v3_finalizer() -> None:
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1] / "app" / "deep_audit_runtime_patch.py"
    ).read_text(encoding="utf-8")

    postprocess = source.split("def _postprocess", 1)[1].split(
        "def _patch_module", 1
    )[0]
    install = source.split("def install()", 1)[1]
    assert "from .semantic_integrity_runtime import finalize_semantic_vi" in postprocess
    assert "from .semantic_integrity_v2 import finalize_semantic_vi" not in postprocess
    assert 'sys.modules.get("app.lvkit_semantic_runtime")' in install
