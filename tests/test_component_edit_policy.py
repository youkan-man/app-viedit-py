from __future__ import annotations

from pathlib import Path

from app.service import PylabviewService


def _extracted_job(service: PylabviewService, store):
    paths = store.create("vi_to_xml")
    source = paths.input / "sample.vi"
    source.write_bytes(b"RSRC\r\nFAKE")
    service.extract_vi(
        paths,
        source,
        text_encoding="shift_jis",
        verbosity=1,
        raw_connectors=False,
        verify_roundtrip=False,
    )
    return paths


def test_structure_counts_and_unclassified_scalars_are_read_only(
    service: PylabviewService, store
) -> None:
    paths = _extracted_job(service, store)
    model = service._load_component_model(paths)
    primitive = next(
        component
        for component in model.components.values()
        if component["class_name"] == "AddPrimitive"
    )
    detail = model.detail(primitive["id"])
    n_inputs = next(
        prop for prop in detail["properties"] if prop["name"] == "OF__nInputs"
    )

    assert n_inputs["editable"] is False
    assert n_inputs["edit_level"] == "read_only_structure"


def test_readme_contains_only_user_facing_application_sections() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    forbidden = (
        "サブエージェント",
        "Luna",
        "プロンプト",
        "内部指示",
        "PR #",
        "コミットSHA",
        "敵対的レビュー",
        "実装経緯",
    )
    for phrase in forbidden:
        assert phrase not in readme

    assert "## 主な機能" in readme
    assert "## 基本操作" in readme
    assert "## VI構造・コンポーネント" in readme
    assert "## 対応範囲と制約" in readme
