from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
import time
import unicodedata
import uuid
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from defusedxml import ElementTree as DefusedET

from .config import Settings
from .errors import AppError

MANIFEST_NAME = "pylabview-web-manifest.json"


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def safe_filename(value: str | None, fallback: str = "upload.bin") -> str:
    raw = unicodedata.normalize("NFKC", value or "")
    raw = raw.replace("\\", "/").split("/")[-1]
    cleaned_chars: list[str] = []
    for char in raw:
        if char == "\x00" or (char.isspace() and char != " "):
            continue
        cleaned_chars.append(char if (char.isalnum() or char in "._- ()[]") else "_")
    cleaned = "".join(cleaned_chars)
    cleaned = " ".join(cleaned.split()).strip(" .")
    if not cleaned or cleaned in {".", ".."}:
        cleaned = fallback
    # Keep paths and Content-Disposition headers manageable.
    if len(cleaned) > 180:
        suffix = Path(cleaned).suffix[:20]
        stem_limit = max(1, 180 - len(suffix))
        cleaned = f"{Path(cleaned).stem[:stem_limit]}{suffix}"
    return cleaned


def safe_relative_path(value: str) -> Path:
    normalized = value.replace("\\", "/").strip()
    candidate = PurePosixPath(normalized)
    if not normalized or candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise AppError(
            "メインXMLのパスが不正です。ZIP内の相対パスを指定してください。",
            code="invalid_relative_path",
            status_code=422,
        )
    return Path(*candidate.parts)


def resolve_inside(root: Path, relative: Path) -> Path:
    root_resolved = root.resolve()
    target = (root_resolved / relative).resolve()
    try:
        target.relative_to(root_resolved)
    except ValueError as exc:
        raise AppError(
            "作業領域外のパスは使用できません。",
            code="unsafe_path",
            status_code=422,
        ) from exc
    return target


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def file_inventory(root: Path, limit: int = 2_000) -> tuple[list[dict[str, Any]], bool]:
    files: list[dict[str, Any]] = []
    truncated = False
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if len(files) >= limit:
            truncated = True
            break
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size": path.stat().st_size,
            }
        )
    return files, truncated


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise AppError(
            "ジョブ情報を読み込めませんでした。",
            code="job_metadata_error",
            status_code=500,
        ) from exc
    if not isinstance(value, dict):
        raise AppError(
            "ジョブ情報の形式が不正です。",
            code="job_metadata_error",
            status_code=500,
        )
    return value


def validate_rsrc_xml(path: Path) -> dict[str, str]:
    try:
        root = DefusedET.parse(path).getroot()
    except Exception as exc:  # defusedxml exposes several parser-specific exceptions
        raise AppError(
            f"XMLを解析できません: {path.name}",
            code="invalid_xml",
            status_code=422,
            details={"reason": str(exc)},
        ) from exc
    if root.tag != "RSRC":
        raise AppError(
            f"メインXMLのルート要素は RSRC である必要があります: {path.name}",
            code="not_rsrc_xml",
            status_code=422,
            details={"root_tag": root.tag},
        )
    return {str(key): str(value) for key, value in root.attrib.items()}


def safe_extract_zip(zip_path: Path, destination: Path, settings: Settings) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    seen: set[str] = set()
    declared_total = 0
    actual_total = 0
    file_count = 0

    try:
        archive = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        raise AppError(
            "ZIPファイルを開けません。",
            code="invalid_zip",
            status_code=422,
        ) from exc

    try:
        with archive:
            for info in archive.infolist():
                raw_name = info.filename.replace("\\", "/")
                if "\x00" in raw_name or len(raw_name) > 1024:
                    raise AppError(
                        "ZIP内に不正なファイル名があります。",
                        code="unsafe_archive",
                        status_code=422,
                    )
                relative = PurePosixPath(raw_name)
                if (
                    not raw_name
                    or relative.as_posix() in {"", "."}
                    or relative.is_absolute()
                    or any(part in {"", ".", ".."} for part in relative.parts)
                ):
                    raise AppError(
                        f"ZIP内に危険なパスがあります: {raw_name}",
                        code="unsafe_archive",
                        status_code=422,
                    )
                normalized = relative.as_posix()
                if normalized in seen:
                    raise AppError(
                        f"ZIP内に重複したパスがあります: {normalized}",
                        code="duplicate_archive_path",
                        status_code=422,
                    )
                seen.add(normalized)

                unix_mode = info.external_attr >> 16
                if unix_mode and stat.S_ISLNK(unix_mode):
                    raise AppError(
                        f"ZIP内のシンボリックリンクは展開できません: {normalized}",
                        code="unsafe_archive",
                        status_code=422,
                    )
                if info.flag_bits & 0x1:
                    raise AppError(
                        f"暗号化ZIPには対応していません: {normalized}",
                        code="encrypted_archive",
                        status_code=422,
                    )

                target = resolve_inside(destination, Path(*relative.parts))
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue

                file_count += 1
                if file_count > settings.max_archive_files:
                    raise AppError(
                        "ZIP内のファイル数が上限を超えています。",
                        code="archive_file_limit",
                        status_code=413,
                        details={"max_files": settings.max_archive_files},
                    )
                declared_total += info.file_size
                if declared_total > settings.max_archive_bytes:
                    raise AppError(
                        "ZIPの展開後サイズが上限を超えています。",
                        code="archive_size_limit",
                        status_code=413,
                        details={"max_bytes": settings.max_archive_bytes},
                    )

                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info, "r") as source, target.open("wb") as output:
                    while chunk := source.read(1024 * 1024):
                        actual_total += len(chunk)
                        if actual_total > settings.max_archive_bytes:
                            raise AppError(
                                "ZIPの実展開サイズが上限を超えています。",
                                code="archive_size_limit",
                                status_code=413,
                                details={"max_bytes": settings.max_archive_bytes},
                            )
                        output.write(chunk)
                extracted.append(target)
    except AppError:
        raise
    except (zipfile.BadZipFile, RuntimeError, OSError, NotImplementedError) as exc:
        raise AppError(
            "ZIPの展開に失敗しました。破損または未対応の圧縮方式を確認してください。",
            code="invalid_zip",
            status_code=422,
            details={"reason": str(exc)},
        ) from exc
    return extracted


def make_zip(source_root: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(item for item in source_root.rglob("*") if item.is_file()):
            archive.write(path, path.relative_to(source_root).as_posix())


@dataclass(frozen=True, slots=True)
class JobPaths:
    job_id: str
    root: Path
    input: Path
    dataset: Path
    output: Path
    metadata: Path


class JobStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.settings.work_root.mkdir(parents=True, exist_ok=True)

    def create(self, kind: str) -> JobPaths:
        self.cleanup_expired()
        job_id = uuid.uuid4().hex
        root = self.settings.work_root / job_id
        paths = JobPaths(
            job_id=job_id,
            root=root,
            input=root / "input",
            dataset=root / "dataset",
            output=root / "output",
            metadata=root / "job.json",
        )
        paths.input.mkdir(parents=True)
        paths.dataset.mkdir()
        paths.output.mkdir()
        self.save(
            paths,
            {
                "job_id": job_id,
                "kind": kind,
                "status": "created",
                "created_at": utc_now_iso(),
                "updated_at": utc_now_iso(),
                "artifacts": {},
                "logs": {},
            },
        )
        return paths

    def get(self, job_id: str) -> JobPaths:
        try:
            normalized = uuid.UUID(job_id).hex
        except ValueError as exc:
            raise AppError("ジョブIDが不正です。", code="invalid_job_id", status_code=404) from exc
        if normalized != job_id.lower():
            raise AppError("ジョブIDが不正です。", code="invalid_job_id", status_code=404)
        root = self.settings.work_root / normalized
        paths = JobPaths(
            job_id=normalized,
            root=root,
            input=root / "input",
            dataset=root / "dataset",
            output=root / "output",
            metadata=root / "job.json",
        )
        if not paths.metadata.is_file():
            raise AppError("ジョブが見つかりません。", code="job_not_found", status_code=404)
        return paths

    def load(self, paths: JobPaths) -> dict[str, Any]:
        return read_json(paths.metadata)

    def save(self, paths: JobPaths, metadata: dict[str, Any]) -> None:
        metadata["updated_at"] = utc_now_iso()
        write_json_atomic(paths.metadata, metadata)
        now = time.time()
        os.utime(paths.root, (now, now), follow_symlinks=False)

    def delete(self, job_id: str) -> None:
        paths = self.get(job_id)
        shutil.rmtree(paths.root, ignore_errors=False)

    def cleanup_expired(self) -> int:
        cutoff = time.time() - self.settings.job_ttl_hours * 3600
        removed = 0
        try:
            candidates: Iterable[Path] = self.settings.work_root.iterdir()
        except FileNotFoundError:
            self.settings.work_root.mkdir(parents=True, exist_ok=True)
            return 0
        for candidate in candidates:
            if not candidate.is_dir():
                continue
            try:
                modified = candidate.stat().st_mtime
            except FileNotFoundError:
                continue
            if modified < cutoff:
                shutil.rmtree(candidate, ignore_errors=True)
                removed += 1
        return removed
