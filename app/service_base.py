from __future__ import annotations

import codecs
import json
import os
import shlex
import shutil
import subprocess
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from defusedxml import ElementTree as DefusedET

from .config import Settings
from .errors import AppError
from .filesystem import (
    MANIFEST_NAME,
    JobPaths,
    JobStore,
    file_inventory,
    make_zip,
    read_json,
    resolve_inside,
    safe_extract_zip,
    safe_filename,
    safe_relative_path,
    sha256_file,
    utc_now_iso,
    validate_rsrc_xml,
    write_json_atomic,
)


TYPE_EXTENSION = {
    "LVCC": "ctl",
    "LVDL": "dlog",
    "CLIB": "lvclass",
    "LVPJ": "lvproj",
    "LIBR": "lvlib",
    "LIBP": "lvlibp",
    "LVAR": "llb",
    "LMNU": "mnu",
    "sVCC": "ctt",
    "sVIN": "vit",
    "LVXC": "xctl",
    "iUWl": "uir",
    "LVSB": "lsb",
    "LVIN": "vi",
}

TYPE_NAME_EXTENSION = {
    "control": "ctl",
    "dlog": "dlog",
    "classlib": "lvclass",
    "project": "lvproj",
    "library": "lvlib",
    "packedprojlib": "lvlibp",
    "llb": "llb",
    "menupalette": "mnu",
    "templatecontrol": "ctt",
    "templatevi": "vit",
    "xcontrol": "xctl",
    "usrifaceresrc": "uir",
    "subroutine": "lsb",
    "vi": "vi",
}

COMMON_ENCODINGS = (
    "shift_jis",
    "utf-8",
    "mac_roman",
    "cp1252",
    "cp1250",
    "cp1251",
    "cp1253",
    "cp1254",
    "cp1255",
    "cp1256",
    "cp1257",
    "cp1258",
    "gbk",
    "cp949",
    "cp950",
    "mac_cyrillic",
    "mac_greek",
    "mac_iceland",
    "mac_latin2",
    "mac_turkish",
)


@dataclass(slots=True)
class CommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str
    duration_ms: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": self.duration_ms,
        }


class CommandRunner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _truncate(self, text: str | bytes | None) -> str:
        if text is None:
            return ""
        if isinstance(text, bytes):
            text = text.decode("utf-8", errors="replace")
        if len(text) <= self.settings.log_max_chars:
            return text
        half = max(1, self.settings.log_max_chars // 2)
        omitted = len(text) - half * 2
        return f"{text[:half]}\n... <{omitted} characters omitted> ...\n{text[-half:]}"

    def _display_command(self, command: Sequence[str]) -> str:
        rendered = shlex.join(command)
        return rendered.replace(str(self.settings.work_root), "<workspace>")

    def run(
        self,
        arguments: Sequence[str],
        *,
        cwd: Path,
        timeout: int | None = None,
    ) -> CommandResult:
        command = [*self.settings.pylabview_command, *arguments]
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout or self.settings.command_timeout_seconds,
                check=False,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
        except FileNotFoundError as exc:
            raise AppError(
                "pylabview の readRSRC コマンドが見つかりません。Dockerイメージを再ビルドしてください。",
                code="pylabview_not_found",
                status_code=503,
                details={"command": self.settings.pylabview_command[0]},
            ) from exc
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            raise AppError(
                "pylabview の処理がタイムアウトしました。",
                code="pylabview_timeout",
                status_code=504,
                details={
                    "command": self._display_command(command),
                    "duration_ms": duration_ms,
                    "stdout": self._truncate(exc.stdout),
                    "stderr": self._truncate(exc.stderr),
                },
            ) from exc
        duration_ms = int((time.monotonic() - started) * 1000)
        return CommandResult(
            command=self._display_command(command),
            returncode=completed.returncode,
            stdout=self._truncate(completed.stdout),
            stderr=self._truncate(completed.stderr),
            duration_ms=duration_ms,
        )


class BaseServiceMixin:
    def __init__(
        self,
        settings: Settings,
        store: JobStore,
        runner: CommandRunner | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.runner = runner or CommandRunner(settings)
        self._probe_cache: tuple[float, dict[str, Any]] | None = None

    @staticmethod
    def validate_encoding(value: str) -> str:
        candidate = value.strip()
        if not candidate or len(candidate) > 64:
            raise AppError("文字コードの指定が不正です。", code="invalid_encoding", status_code=422)
        try:
            codecs.lookup(candidate)
        except LookupError as exc:
            raise AppError(
                f"Pythonが認識できない文字コードです: {candidate}",
                code="invalid_encoding",
                status_code=422,
            ) from exc
        return candidate

    @staticmethod
    def _verbosity_arguments(verbosity: int) -> list[str]:
        if verbosity < 0 or verbosity > 3:
            raise AppError("ログ詳細度は0〜3で指定してください。", code="invalid_verbosity", status_code=422)
        return ["-v"] * verbosity

    @staticmethod
    def _relative(paths: JobPaths, path: Path) -> str:
        return path.resolve().relative_to(paths.root.resolve()).as_posix()

    def _run_stage(self, stage: str, arguments: Sequence[str], cwd: Path) -> CommandResult:
        result = self.runner.run(arguments, cwd=cwd)
        if result.returncode != 0:
            raise AppError(
                f"pylabview の {stage} 処理に失敗しました。",
                code="pylabview_failed",
                status_code=422,
                details={"stage": stage, **result.as_dict()},
            )
        return result

    def probe(self, *, force: bool = False) -> dict[str, Any]:
        now = time.monotonic()
        if not force and self._probe_cache and now - self._probe_cache[0] < 60:
            return self._probe_cache[1]
        try:
            result = self.runner.run(["--version"], cwd=self.settings.work_root, timeout=10)
            payload = {
                "available": result.returncode == 0,
                "version": (result.stdout or result.stderr).strip(),
                "returncode": result.returncode,
            }
        except AppError as exc:
            payload = {"available": False, "version": "", "error": exc.message}
        self._probe_cache = (now, payload)
        return payload

    def _write_workspace_manifest(
        self,
        paths: JobPaths,
        metadata: dict[str, Any],
        main_xml: Path,
        **extra: Any,
    ) -> Path:
        manifest_path = paths.dataset / MANIFEST_NAME
        manifest: dict[str, Any] = {}
        if manifest_path.is_file():
            try:
                manifest = read_json(manifest_path)
            except AppError:
                manifest = {}
        manifest.update(
            {
                "format": "pylabview-web-dataset",
                "format_version": 1,
                "updated_at": utc_now_iso(),
                "main_xml": main_xml.relative_to(paths.dataset).as_posix(),
                "text_encoding": metadata.get("text_encoding", "shift_jis"),
                **extra,
            }
        )
        manifest.setdefault("created_at", utc_now_iso())
        write_json_atomic(manifest_path, manifest)
        return manifest_path

    def _refresh_dataset_archive(
        self,
        paths: JobPaths,
        metadata: dict[str, Any],
        *,
        fallback_stem: str,
    ) -> Path:
        artifacts = metadata.setdefault("artifacts", {})
        relative = artifacts.get("dataset")
        dataset_zip: Path | None = None
        if isinstance(relative, str):
            try:
                candidate = resolve_inside(paths.root, Path(relative))
            except AppError:
                candidate = paths.output / "invalid"
            if candidate.parent == paths.output.resolve() and candidate.suffix.lower() == ".zip":
                dataset_zip = candidate
        if dataset_zip is None:
            stem = safe_filename(fallback_stem, "dataset")
            dataset_zip = paths.output / f"{stem}-xml-dataset.zip"
        make_zip(paths.dataset, dataset_zip)
        artifacts["dataset"] = self._relative(paths, dataset_zip)
        return dataset_zip

    @staticmethod
    def infer_extension(attributes: dict[str, str]) -> str:
        type_value = attributes.get("Type", "")
        if type_value in TYPE_EXTENSION:
            return TYPE_EXTENSION[type_value]
        by_name = TYPE_NAME_EXTENSION.get(type_value.replace("_", "").replace(" ", "").lower())
        if by_name:
            return by_name
        type_hex = attributes.get("TypeHex", "")
        if type_hex:
            try:
                decoded = bytes.fromhex(type_hex).decode("ascii")
            except (ValueError, UnicodeDecodeError):
                decoded = ""
            if decoded in TYPE_EXTENSION:
                return TYPE_EXTENSION[decoded]
        return "vi"
