from __future__ import annotations

import os
from pathlib import Path

import pytest

# test_api imports app.main during collection. Keep the module-level JobStore
# inside the current isolated workspace rather than attempting to create the
# container production default at /data/jobs.
_TEST_BASE = Path(os.getenv("BUILD_WORKSPACE", "/tmp"))
os.environ.setdefault("WORK_ROOT", str(_TEST_BASE / ".pytest-app-viedit-jobs"))

from app.config import Settings  # noqa: E402
from app.filesystem import JobStore  # noqa: E402
from app.service import PylabviewService  # noqa: E402


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
