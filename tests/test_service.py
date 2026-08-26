from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from app.errors import AppError
from app.filesystem import MANIFEST_NAME
from app.service import PylabviewService


def test_extract_creates_dataset_and_roundtrip(service: PylabviewService, store, fake_runner) -> None:
    paths = store.create("vi_to_xml")
    source = paths.input / "sample.vi"
    source.write_bytes(b"RSRC\r\nFAKE")

    result = service.extract_vi(
        paths,
        source,
        text_encoding="shift_jis",
        verbosity=2,
        raw_connectors=True,
        verify_roundtrip=True,
    )

    assert result["status"] == "completed"
    assert result["verification"]["binary_identical"] is True
    assert result["main_xml_attributes"]["Type"] == "LVIN"
    assert {"dataset", "main_xml", "roundtrip"} <= result["urls"].keys()
    dataset_zip = service.artifact_path(paths, "dataset")
    with zipfile.ZipFile(dataset_zip) as archive:
        names = set(archive.namelist())
    assert {"sample.xml", "fake.bin", MANIFEST_NAME} <= names
    assert any("--raw-connectors" in call[0] for call in fake_runner.calls)


def test_extract_records_failed_verification_without_losing_dataset(settings, store) -> None:
    from tests.fakes import FakeRunner

    service = PylabviewService(settings, store, runner=FakeRunner(fail_create=True))
    paths = store.create("vi_to_xml")
    source = paths.input / "sample.vi"
    source.write_bytes(b"RSRC\r\nFAKE")

    result = service.extract_vi(
        paths,
        source,
        text_encoding="shift_jis",
        verbosity=1,
        raw_connectors=False,
        verify_roundtrip=True,
    )

    assert result["status"] == "completed"
    assert result["verification"]["status"] == "failed"
    assert "dataset" in result["urls"]


def test_import_zip_uses_manifest_and_rebuilds(service: PylabviewService, store, tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "nested").mkdir()
    (source_dir / "nested" / "main.xml").write_text(
        '<RSRC FormatVersion="3" Type="LVIN" />', encoding="utf-8"
    )
    (source_dir / "nested" / "raw.bin").write_bytes(b"raw")
    (source_dir / MANIFEST_NAME).write_text(
        json.dumps({"main_xml": "nested/main.xml"}), encoding="utf-8"
    )
    archive = tmp_path / "dataset.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        for file in source_dir.rglob("*"):
            if file.is_file():
                handle.write(file, file.relative_to(source_dir).as_posix())

    paths = store.create("xml_to_vi")
    upload = paths.input / archive.name
    upload.write_bytes(archive.read_bytes())
    service.import_dataset(
        paths,
        upload,
        original_name=archive.name,
        main_xml_hint=None,
        text_encoding="shift_jis",
    )
    result = service.rebuild(
        paths,
        output_name="restored.vi",
        text_encoding=None,
        verbosity=1,
    )

    assert result["status"] == "completed"
    assert result["reconstructed"]["name"] == "restored.vi"
    assert service.artifact_path(paths, "reconstructed").read_bytes() == b"RSRC\r\nFAKE"


def test_ambiguous_main_xml_requires_hint(service: PylabviewService, store) -> None:
    paths = store.create("xml_to_vi")
    (paths.dataset / "one.xml").write_text("<RSRC />", encoding="utf-8")
    (paths.dataset / "two.xml").write_text("<RSRC />", encoding="utf-8")
    with pytest.raises(AppError) as raised:
        service.find_main_xml(paths.dataset)
    assert raised.value.code == "ambiguous_main_xml"
    assert len(raised.value.details["candidates"]) == 2


def test_invalid_editor_update_is_atomic(service: PylabviewService, store) -> None:
    paths = store.create("xml_to_vi")
    xml = paths.dataset / "main.xml"
    original = b'<RSRC FormatVersion="3" Type="LVIN" />'
    xml.write_bytes(original)
    metadata = store.load(paths)
    metadata.update(
        {
            "main_xml": "main.xml",
            "artifacts": {"main_xml": "dataset/main.xml"},
            "text_encoding": "shift_jis",
        }
    )
    store.save(paths, metadata)

    with pytest.raises(AppError) as raised:
        service.update_main_xml(paths, b"<broken")
    assert raised.value.code == "invalid_xml"
    assert xml.read_bytes() == original


def test_editor_update_marks_existing_output_stale(service: PylabviewService, store) -> None:
    paths = store.create("xml_to_vi")
    xml = paths.dataset / "main.xml"
    xml.write_text('<RSRC FormatVersion="3" Type="LVIN" />', encoding="utf-8")
    metadata = store.load(paths)
    metadata.update(
        {
            "artifacts": {"main_xml": "dataset/main.xml"},
            "reconstructed": {"name": "old.vi", "stale": False},
        }
    )
    store.save(paths, metadata)

    result = service.update_main_xml(
        paths,
        b'<RSRC FormatVersion="3" Type="LVIN"><Changed /></RSRC>',
    )
    assert result["reconstructed"]["stale"] is True


def test_validate_encoding_rejects_unknown() -> None:
    with pytest.raises(AppError) as raised:
        PylabviewService.validate_encoding("definitely-not-an-encoding")
    assert raised.value.code == "invalid_encoding"


def test_editor_update_enforces_inline_limit(service: PylabviewService, store) -> None:
    paths = store.create("xml_to_vi")
    xml = paths.dataset / "main.xml"
    original = b'<RSRC FormatVersion="3" Type="LVIN" />'
    xml.write_bytes(original)
    metadata = store.load(paths)
    metadata.update({"artifacts": {"main_xml": "dataset/main.xml"}})
    store.save(paths, metadata)

    with pytest.raises(AppError) as raised:
        service.update_main_xml(paths, b"x" * (service.settings.inline_xml_max_bytes + 1))
    assert raised.value.code == "xml_too_large_for_editor"
    assert xml.read_bytes() == original


def test_dataset_quantization_updates_auxiliary_heap_xml_and_current_main_editor(
    service: PylabviewService, store
) -> None:
    from app.quantizer import QuantizeOptions

    paths = store.create("xml_to_vi")
    main = paths.dataset / "main.xml"
    heap = paths.dataset / "diagram-heap.xml"
    main.write_text(
        '<RSRC FormatVersion="3" Type="LVIN"><Section File="diagram-heap.xml" /></RSRC>',
        encoding="utf-8",
    )
    heap.write_text(
        '<SL__rootObject><OF__bounds>(3, 5, 103, 55)</OF__bounds>'
        '<wireTable><SL__arrayElement>(13, 19)</SL__arrayElement></wireTable>'
        '</SL__rootObject>',
        encoding="utf-8",
    )
    metadata = store.load(paths)
    metadata.update(
        {
            "main_xml": "main.xml",
            "artifacts": {"main_xml": "dataset/main.xml"},
            "text_encoding": "shift_jis",
            "reconstructed": {"name": "old.vi", "stale": False},
            "verification": {"status": "completed", "stale": False},
        }
    )
    store.save(paths, metadata)

    edited_main = (
        '<RSRC FormatVersion="3" Type="LVIN"><Edited />'
        '<Section File="diagram-heap.xml" /></RSRC>'
    )
    preview = service.preview_dataset_quantization(
        paths,
        current_main_xml=edited_main,
        options=QuantizeOptions(grid_size=8),
    )

    assert preview["scanned_files"] == 2
    assert preview["staged_files"] == 2
    assert preview["changed_by_kind"]["object"] == 1
    assert preview["changed_by_kind"]["wire"] == 1
    assert any(sample["file"] == "diagram-heap.xml" for sample in preview["samples"])
    # Preview must not mutate the actual dataset.
    assert "(3, 5, 103, 55)" in heap.read_text(encoding="utf-8")
    assert "<Edited" not in main.read_text(encoding="utf-8")

    result = service.apply_dataset_quantization(
        paths,
        preview_id=preview["preview_id"],
    )

    assert "<Edited" in main.read_text(encoding="utf-8")
    heap_text = heap.read_text(encoding="utf-8")
    assert "(0, 8, 100, 58)" in heap_text
    assert "(16, 16)" in heap_text
    assert result["reconstructed"]["stale"] is True
    assert result["verification"]["stale"] is True
    assert result["quantization"]["applied"] is True
    assert service.artifact_path(paths, "dataset").is_file()


def test_dataset_quantization_rejects_stale_preview(
    service: PylabviewService, store
) -> None:
    from app.quantizer import QuantizeOptions

    paths = store.create("xml_to_vi")
    main = paths.dataset / "main.xml"
    heap = paths.dataset / "heap.xml"
    main.write_text(
        '<RSRC FormatVersion="3" Type="LVIN"><Section File="heap.xml" /></RSRC>',
        encoding="utf-8",
    )
    heap.write_text('<heap><OF__bounds>(3, 5, 13, 15)</OF__bounds></heap>', encoding="utf-8")
    metadata = store.load(paths)
    metadata.update(
        {
            "main_xml": "main.xml",
            "artifacts": {"main_xml": "dataset/main.xml"},
        }
    )
    store.save(paths, metadata)

    preview = service.preview_dataset_quantization(
        paths,
        current_main_xml=main.read_text(encoding="utf-8"),
        options=QuantizeOptions(grid_size=8),
    )
    heap.write_text('<heap><OF__bounds>(99, 99, 109, 109)</OF__bounds></heap>', encoding="utf-8")

    with pytest.raises(AppError) as raised:
        service.apply_dataset_quantization(paths, preview_id=preview["preview_id"])
    assert raised.value.code == "quantize_preview_stale"
    assert "(99, 99, 109, 109)" in heap.read_text(encoding="utf-8")
