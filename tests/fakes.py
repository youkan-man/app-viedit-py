from __future__ import annotations

from pathlib import Path
from typing import Sequence

from app.service import CommandResult


class FakeRunner:
    """Small readRSRC stand-in used to test orchestration without LabVIEW files."""

    def __init__(self, *, fail_extract: bool = False, fail_create: bool = False) -> None:
        self.fail_extract = fail_extract
        self.fail_create = fail_create
        self.calls: list[tuple[list[str], Path]] = []

    @staticmethod
    def _value(arguments: Sequence[str], flag: str) -> str:
        index = list(arguments).index(flag)
        return str(arguments[index + 1])

    def run(
        self,
        arguments: Sequence[str],
        *,
        cwd: Path,
        timeout: int | None = None,
    ) -> CommandResult:
        del timeout
        args = list(arguments)
        self.calls.append((args, cwd))
        if "--version" in args:
            return CommandResult("readRSRC --version", 0, "0.1.2\n", "", 1)

        if "--extract" in args:
            if self.fail_extract:
                return CommandResult("readRSRC --extract", 2, "", "extract failed", 3)
            xml_path = Path(self._value(args, "--xml"))
            xml_path.parent.mkdir(parents=True, exist_ok=True)
            xml_path.write_text(
                "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n"
                "<RSRC FormatVersion=\"3\" Type=\"LVIN\" Encoding=\"shift_jis\">\n"
                "  <FakeBlock><Section Index=\"0\" Format=\"bin\" File=\"fake.bin\" /></FakeBlock>\n"
                "</RSRC>\n",
                encoding="utf-8",
            )
            (xml_path.parent / "fake.bin").write_bytes(b"FAKE-BLOCK")
            return CommandResult("readRSRC --extract", 0, "extract ok\n", "", 5)

        if "--create" in args:
            if self.fail_create:
                return CommandResult("readRSRC --create", 2, "", "create failed", 3)
            xml_name = self._value(args, "--xml")
            xml_path = cwd / xml_name
            if not xml_path.is_file():
                return CommandResult("readRSRC --create", 2, "", "xml missing", 2)
            output = Path(self._value(args, "--rsrc"))
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"RSRC\r\nFAKE")
            return CommandResult("readRSRC --create", 0, "create ok\n", "", 5)

        return CommandResult("readRSRC", 2, "", "unsupported fake command", 1)
