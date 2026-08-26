from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import time
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from defusedxml import ElementTree as SafeET
from fastapi import UploadFile

from app.config import Settings

JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")
SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._()\-\u0080-\uffff]+")
ALLOWED_OUTPUT_EXTENSIONS = {
    ".vi",
    ".vit",
    ".ctl",
    ".ctt",
    ".llb",
    ".mnu",
    ".rsc",
    ".rsrc",
    ".lvlibp",
}


class WorkspaceError(RuntimeError):
    """Base error for workspace operations."""


class InvalidArchiveError(WorkspaceError):
    """Raised when an uploaded ZIP is unsafe or invalid."""


class UploadTooLargeError(WorkspaceError):
    """Raised when an upload exceeds the configured limit."""


class JobNotFoundError(WorkspaceError):
    """Raised when a job does not exist or its ID is invalid."""


@dataclass(frozen=True, slots=True)
class JobPaths:
    root: Path
    source: Path
    dataset: Path
    outputs: Path
    logs: Path
    meta: Path


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def sanitize_filename(name: str, fallback: str = "upload.bin") -> str:
    base = Path(name or "").name.strip().replace("\x00", "")
    base = SAFE_FILENAME_RE.sub("_", base)
    base = base.strip(". ")
    if not base or base in {".", ".."}:
        return fallback
    return base[:180]


def sanitize_output_filename(name: str, fallback: str = "rebuilt.vi") -> str:
    filename = sanitize_filename(name, fallback=fallback)
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_OUTPUT_EXTENSIONS:
        raise WorkspaceError(
            "Output file must use a LabVIEW/RSRC extension: "
            + ", ".join(sorted(ALLOWED_OUTPUT_EXTENSIONS))
        )
    return filename


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class WorkspaceManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = settings.data_dir.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def cleanup_expired(self) -> int:
        removed = 0
        threshold = time.time() - self.settings.job_ttl_seconds
        for entry in self.root.iterdir():
            if not entry.is_dir() or not JOB_ID_RE.fullmatch(entry.name):
                continue
            try:
                if entry.stat().st_mtime < threshold:
                    shutil.rmtree(entry, ignore_errors=True)
                    removed += 1
            except FileNotFoundError:
                continue
        return removed

    def create_job(self, *, kind: str) -> JobPaths:
        self.cleanup_expired()
        job_id = uuid4().hex
        root = self.root / job_id
        source = root / "source"
        dataset = root / "dataset"
        outputs = root / "outputs"
        logs = root / "logs"
        for directory in (source, dataset, outputs, logs):
            directory.mkdir(parents=True, exist_ok=False)
        paths = JobPaths(
            root=root,
            source=source,
            dataset=dataset,
            outputs=outputs,
            logs=logs,
            meta=root / "meta.json",
        )
        self.write_meta(
            paths,
            {
                "id": job_id,
                "kind": kind,
                "status": "created",
                "created_at": utc_now_iso(),
                "updated_at": utc_now_iso(),
            },
        )
        return paths

    def get_job(self, job_id: str) -> JobPaths:
        if not JOB_ID_RE.fullmatch(job_id):
            raise JobNotFoundError("Invalid job ID")
        root = (self.root / job_id).resolve()
        if root.parent != self.root or not root.is_dir():
            raise JobNotFoundError("Job not found or expired")
        return JobPaths(
            root=root,
            source=root / "source",
            dataset=root / "dataset",
            outputs=root / "outputs",
            logs=root / "logs",
            meta=root / "meta.json",
        )

    def read_meta(self, paths: JobPaths) -> dict[str, object]:
        try:
            return json.loads(paths.meta.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise JobNotFoundError("Job metadata is unavailable") from exc

    def write_meta(self, paths: JobPaths, data: dict[str, object]) -> None:
        payload = dict(data)
        payload["updated_at"] = utc_now_iso()
        self._atomic_write_text(
            paths.meta, json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        )
        os.utime(paths.root, None)

    def update_meta(self, paths: JobPaths, **changes: object) -> dict[str, object]:
        meta = self.read_meta(paths)
        meta.update(changes)
        self.write_meta(paths, meta)
        return meta

    async def save_upload(
        self,
        upload: UploadFile,
        destination_dir: Path,
        *,
        fallback_name: str = "upload.bin",
    ) -> Path:
        filename = sanitize_filename(upload.filename or "", fallback=fallback_name)
        destination = self.resolve_inside(destination_dir, filename)
        if destination.exists():
            raise WorkspaceError(f"Duplicate uploaded filename: {filename}")
        total = 0
        with destination.open("wb") as handle:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > self.settings.max_upload_bytes:
                    handle.close()
                    destination.unlink(missing_ok=True)
                    raise UploadTooLargeError(
                        f"Upload exceeds {self.settings.max_upload_bytes} bytes"
                    )
                handle.write(chunk)
        await upload.close()
        if total == 0:
            destination.unlink(missing_ok=True)
            raise WorkspaceError("Uploaded file is empty")
        return destination

    def extract_zip_safely(self, archive: Path, destination: Path) -> list[Path]:
        extracted: list[Path] = []
        total = 0
        try:
            with zipfile.ZipFile(archive) as zf:
                members = zf.infolist()
                if len(members) > self.settings.max_archive_files:
                    raise InvalidArchiveError(
                        f"Archive has more than {self.settings.max_archive_files} entries"
                    )
                seen: set[str] = set()
                for info in members:
                    if info.flag_bits & 0x1:
                        raise InvalidArchiveError("Encrypted ZIP entries are not supported")
                    mode = info.external_attr >> 16
                    if stat.S_ISLNK(mode):
                        raise InvalidArchiveError("Symbolic links are not allowed in ZIP files")
                    member = PurePosixPath(info.filename.replace("\\", "/"))
                    if member.is_absolute() or ".." in member.parts:
                        raise InvalidArchiveError("Archive contains an unsafe path")
                    if not member.parts:
                        continue
                    normalized = member.as_posix()
                    if normalized in seen:
                        raise InvalidArchiveError("Archive contains duplicate paths")
                    seen.add(normalized)
                    target = self.resolve_inside(destination, *member.parts)
                    if info.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    if total + info.file_size > self.settings.max_upload_bytes:
                        raise UploadTooLargeError(
                            "Expanded archive exceeds the configured upload limit"
                        )
                    target.parent.mkdir(parents=True, exist_ok=True)
                    written = 0
                    try:
                        with zf.open(info) as src, target.open("wb") as dst:
                            while True:
                                chunk = src.read(1024 * 1024)
                                if not chunk:
                                    break
                                written += len(chunk)
                                if total + written > self.settings.max_upload_bytes:
                                    raise UploadTooLargeError(
                                        "Expanded archive exceeds the configured upload limit"
                                    )
                                dst.write(chunk)
                    except Exception:
                        target.unlink(missing_ok=True)
                        raise
                    total += written
                    extracted.append(target)
        except zipfile.BadZipFile as exc:
            raise InvalidArchiveError("Uploaded file is not a valid ZIP archive") from exc
        return extracted

    def find_main_xml(self, dataset: Path, preferred: str | None = None) -> Path:
        if preferred:
            candidate = self.resolve_inside(dataset, *PurePosixPath(preferred).parts)
            if candidate.is_file() and candidate.suffix.lower() == ".xml":
                return candidate
            raise WorkspaceError("The selected main XML file was not found")

        manifest = dataset / "manifest.json"
        if manifest.is_file():
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                main_name = data.get("main_xml")
                if isinstance(main_name, str):
                    candidate = self.resolve_inside(
                        dataset, *PurePosixPath(main_name).parts
                    )
                    if candidate.is_file():
                        return candidate
            except (json.JSONDecodeError, WorkspaceError):
                pass

        xml_files = sorted(
            dataset.rglob("*.xml"),
            key=lambda path: (len(path.relative_to(dataset).parts), -path.stat().st_size),
        )
        if not xml_files:
            raise WorkspaceError("No XML file was found in the dataset")

        # Main pylabview catalogues use an RSRC root. Stop at the first start
        # element so large companion XML files do not need to be fully parsed.
        for candidate in xml_files:
            try:
                for _, element in SafeET.iterparse(candidate, events=("start",)):
                    tag = (
                        element.tag.rsplit("}", 1)[-1]
                        if isinstance(element.tag, str)
                        else ""
                    )
                    if tag == "RSRC":
                        return candidate
                    break
            except (OSError, ValueError, SafeET.ParseError):
                continue
        if len(xml_files) == 1:
            return xml_files[0]
        raise WorkspaceError(
            "Could not identify the main pylabview XML. Upload a bundle created by this app."
        )

    def list_dataset_files(self, paths: JobPaths) -> list[dict[str, object]]:
        files: list[dict[str, object]] = []
        for path in sorted(paths.dataset.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(paths.dataset).as_posix()
            files.append(
                {
                    "name": relative,
                    "size": path.stat().st_size,
                    "type": path.suffix.lower().lstrip(".") or "file",
                }
            )
        return files

    def create_dataset_bundle(self, paths: JobPaths, main_xml: Path) -> Path:
        bundle = paths.outputs / "pylabview-dataset.zip"
        manifest = {
            "format": "app-viedit-py/pylabview-dataset",
            "version": 1,
            "main_xml": main_xml.relative_to(paths.dataset).as_posix(),
            "created_at": utc_now_iso(),
        }
        with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            )
            for path in sorted(paths.dataset.rglob("*")):
                if path.is_file() and path.name != "manifest.json":
                    zf.write(path, path.relative_to(paths.dataset).as_posix())
        return bundle

    def resolve_dataset_file(self, paths: JobPaths, relative_path: str) -> Path:
        parts = PurePosixPath(relative_path).parts
        candidate = self.resolve_inside(paths.dataset, *parts)
        if not candidate.is_file():
            raise JobNotFoundError("Dataset file not found")
        return candidate

    def resolve_output_file(self, paths: JobPaths, filename: str) -> Path:
        candidate = self.resolve_inside(paths.outputs, sanitize_filename(filename))
        if not candidate.is_file():
            raise JobNotFoundError("Output file not found")
        return candidate

    @staticmethod
    def resolve_inside(base: Path, *parts: str) -> Path:
        base = base.resolve()
        candidate = base.joinpath(*parts).resolve()
        if candidate != base and base not in candidate.parents:
            raise WorkspaceError("Unsafe path")
        return candidate

    @staticmethod
    def _atomic_write_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
