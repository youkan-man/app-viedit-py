from __future__ import annotations

import stat
import time
import zipfile
from pathlib import Path

import pytest

from app.errors import AppError
from app.filesystem import JobStore, safe_extract_zip, safe_filename, validate_rsrc_xml


def test_safe_filename_strips_paths_and_controls() -> None:
    assert safe_filename("../../悪い\x00 name?.vi") == "悪い name_.vi"
    assert safe_filename("  ..  ", "input.vi") == "input.vi"
    assert "/" not in safe_filename("folder/file.vi")


def test_validate_requires_rsrc_root(tmp_path: Path) -> None:
    xml = tmp_path / "wrong.xml"
    xml.write_text("<root />", encoding="utf-8")
    with pytest.raises(AppError) as raised:
        validate_rsrc_xml(xml)
    assert raised.value.code == "not_rsrc_xml"


def test_safe_zip_extract_blocks_path_traversal(tmp_path: Path, settings) -> None:
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../escape.xml", "<RSRC />")
    with pytest.raises(AppError) as raised:
        safe_extract_zip(archive, tmp_path / "out", settings)
    assert raised.value.code == "unsafe_archive"
    assert not (tmp_path / "escape.xml").exists()


def test_safe_zip_extract_blocks_symlink(tmp_path: Path, settings) -> None:
    archive = tmp_path / "link.zip"
    info = zipfile.ZipInfo("link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr(info, "target")
    with pytest.raises(AppError) as raised:
        safe_extract_zip(archive, tmp_path / "out", settings)
    assert raised.value.code == "unsafe_archive"


def test_safe_zip_extract_enforces_uncompressed_limit(tmp_path: Path, settings) -> None:
    constrained = settings.__class__(
        work_root=settings.work_root,
        max_upload_bytes=settings.max_upload_bytes,
        max_archive_bytes=4,
        max_archive_files=settings.max_archive_files,
        command_timeout_seconds=settings.command_timeout_seconds,
        inline_xml_max_bytes=settings.inline_xml_max_bytes,
        job_ttl_hours=settings.job_ttl_hours,
        log_max_chars=settings.log_max_chars,
        pylabview_command=settings.pylabview_command,
    )
    archive = tmp_path / "large.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("main.xml", "<RSRC />")
    with pytest.raises(AppError) as raised:
        safe_extract_zip(archive, tmp_path / "out", constrained)
    assert raised.value.code == "archive_size_limit"


def test_job_store_cleanup(store: JobStore) -> None:
    paths = store.create("test")
    old = time.time() - 48 * 3600
    paths.root.touch(exist_ok=True)
    import os

    os.utime(paths.root, (old, old))
    assert store.cleanup_expired() == 1
    assert not paths.root.exists()
