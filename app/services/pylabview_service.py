from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from app.config import Settings


class ConversionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        command: Sequence[str] | None = None,
        stdout: str = "",
        stderr: str = "",
        returncode: int | None = None,
    ) -> None:
        super().__init__(message)
        self.command = tuple(command or ())
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


@dataclass(frozen=True, slots=True)
class CommandResult:
    command: tuple[str, ...]
    stdout: str
    stderr: str
    returncode: int

    @property
    def log_text(self) -> str:
        command = " ".join(self.command)
        sections = [f"$ {command}", f"exit: {self.returncode}"]
        if self.stdout:
            sections.extend(["", "[stdout]", self.stdout.rstrip()])
        if self.stderr:
            sections.extend(["", "[stderr]", self.stderr.rstrip()])
        return "\n".join(sections).rstrip() + "\n"


class PylabviewService:
    """Thin subprocess boundary around pylabview's readRSRC CLI."""

    def __init__(self, settings: Settings):
        self.settings = settings
        if not settings.pylabview_command:
            raise RuntimeError("VIEDIT_PYLABVIEW_COMMAND cannot be empty")

    def extract(
        self,
        source: Path,
        dataset_dir: Path,
        *,
        main_xml_name: str = "main.xml",
        text_encoding: str,
        raw_connectors: bool = False,
    ) -> tuple[Path, CommandResult]:
        main_xml = dataset_dir / main_xml_name
        args = [
            "-i",
            str(source.resolve()),
            "-m",
            main_xml.name,
            "-x",
            "-v",
            "-t",
            text_encoding,
        ]
        if raw_connectors:
            args.append("--raw-connectors")
        result = self._run(args, cwd=dataset_dir)
        if not main_xml.is_file() or main_xml.stat().st_size == 0:
            raise ConversionError(
                "pylabview completed without creating the main XML file",
                command=result.command,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
            )
        return main_xml, result

    def create(
        self,
        main_xml: Path,
        output: Path,
        *,
        text_encoding: str,
    ) -> CommandResult:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.unlink(missing_ok=True)
        args = [
            "-i",
            str(output.resolve()),
            "-m",
            str(main_xml.resolve()),
            "-c",
            "-v",
            "-t",
            text_encoding,
        ]
        result = self._run(args, cwd=main_xml.parent)
        if not output.is_file() or output.stat().st_size == 0:
            raise ConversionError(
                "pylabview completed without creating an RSRC output file",
                command=result.command,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
            )
        return result

    def health(self) -> dict[str, object]:
        try:
            result = self._run(["--version"], cwd=self.settings.data_dir)
            version = (result.stdout or result.stderr).strip()
            return {"available": True, "version": version}
        except ConversionError as exc:
            return {"available": False, "error": str(exc)}

    def _run(self, args: Sequence[str], *, cwd: Path) -> CommandResult:
        command = (*self.settings.pylabview_command, *args)
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.settings.command_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ConversionError(
                f"pylabview timed out after {self.settings.command_timeout_seconds} seconds",
                command=command,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
            ) from exc
        except OSError as exc:
            raise ConversionError(
                f"Could not start pylabview: {exc}", command=command
            ) from exc

        result = CommandResult(
            command=tuple(command),
            stdout=completed.stdout,
            stderr=completed.stderr,
            returncode=completed.returncode,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            if len(detail) > 800:
                detail = detail[-800:]
            message = f"pylabview failed with exit code {completed.returncode}"
            if detail:
                message += f": {detail}"
            raise ConversionError(
                message,
                command=command,
                stdout=completed.stdout,
                stderr=completed.stderr,
                returncode=completed.returncode,
            )
        return result
