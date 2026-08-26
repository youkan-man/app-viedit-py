from __future__ import annotations

import os
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < minimum:
        raise RuntimeError(f"{name} must be >= {minimum}")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path = field(
        default_factory=lambda: Path(os.getenv("VIEDIT_DATA_DIR", "./data/jobs"))
    )
    max_upload_bytes: int = field(
        default_factory=lambda: _env_int("VIEDIT_MAX_UPLOAD_BYTES", 128 * 1024 * 1024)
    )
    max_archive_files: int = field(
        default_factory=lambda: _env_int("VIEDIT_MAX_ARCHIVE_FILES", 4096)
    )
    max_xml_editor_bytes: int = field(
        default_factory=lambda: _env_int("VIEDIT_MAX_XML_EDITOR_BYTES", 8 * 1024 * 1024)
    )
    command_timeout_seconds: int = field(
        default_factory=lambda: _env_int("VIEDIT_COMMAND_TIMEOUT_SECONDS", 180)
    )
    job_ttl_seconds: int = field(
        default_factory=lambda: _env_int("VIEDIT_JOB_TTL_SECONDS", 24 * 60 * 60)
    )
    default_text_encoding: str = field(
        default_factory=lambda: os.getenv("VIEDIT_DEFAULT_TEXT_ENCODING", "shift_jis")
    )
    pylabview_command: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            shlex.split(
                os.getenv(
                    "VIEDIT_PYLABVIEW_COMMAND",
                    f"{shlex.quote(sys.executable)} -m pylabview.readRSRC",
                )
            )
        )
    )

    @classmethod
    def for_tests(cls, data_dir: Path, **overrides: object) -> "Settings":
        values: dict[str, object] = {
            "data_dir": data_dir,
            "max_upload_bytes": 4 * 1024 * 1024,
            "max_archive_files": 128,
            "max_xml_editor_bytes": 1024 * 1024,
            "command_timeout_seconds": 10,
            "job_ttl_seconds": 3600,
            "default_text_encoding": "shift_jis",
            "pylabview_command": (sys.executable, "-m", "pylabview.readRSRC"),
        }
        values.update(overrides)
        return cls(**values)
