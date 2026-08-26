from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path


def _env_int(name: str, default: int, minimum: int = 1) -> int:
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


def _env_float(name: str, default: float, minimum: float = 0.0) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number") from exc
    if value < minimum:
        raise RuntimeError(f"{name} must be >= {minimum}")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    work_root: Path
    max_upload_bytes: int
    max_archive_bytes: int
    max_archive_files: int
    command_timeout_seconds: int
    inline_xml_max_bytes: int
    job_ttl_hours: float
    log_max_chars: int
    pylabview_command: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "Settings":
        command = tuple(shlex.split(os.getenv("PYLABVIEW_COMMAND", "readRSRC")))
        if not command:
            raise RuntimeError("PYLABVIEW_COMMAND must not be empty")
        return cls(
            work_root=Path(os.getenv("WORK_ROOT", "/data/jobs")).resolve(),
            max_upload_bytes=_env_int("MAX_UPLOAD_BYTES", 256 * 1024 * 1024),
            max_archive_bytes=_env_int("MAX_ARCHIVE_BYTES", 512 * 1024 * 1024),
            max_archive_files=_env_int("MAX_ARCHIVE_FILES", 10_000),
            command_timeout_seconds=_env_int("COMMAND_TIMEOUT_SECONDS", 300),
            inline_xml_max_bytes=_env_int("INLINE_XML_MAX_BYTES", 8 * 1024 * 1024),
            job_ttl_hours=_env_float("JOB_TTL_HOURS", 24.0),
            log_max_chars=_env_int("LOG_MAX_CHARS", 100_000),
            pylabview_command=command,
        )
