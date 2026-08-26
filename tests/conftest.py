from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.filesystem import JobStore
from app.service import PylabviewService


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        work_root=tmp_path / "jobs",
        max_upload_bytes=4 * 1024 * 1024,
        max_archive_bytes=8 * 1024 * 1024,
        max_archive_files=100,
        command_timeout_seconds=30,
        inline_xml_max_bytes=1 * 1024 * 1024,
        job_ttl_hours=24.0,
        log_max_chars=10_000,
        pylabview_command=("readRSRC",),
    )


@pytest.fixture()
def store(settings: Settings) -> JobStore:
    return JobStore(settings)


@pytest.fixture()
def fake_runner():
    from tests.fakes import FakeRunner

    return FakeRunner()


@pytest.fixture()
def service(settings: Settings, store: JobStore, fake_runner) -> PylabviewService:
    return PylabviewService(settings, store, runner=fake_runner)
