from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

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
                "  <FakeBlock>\n"
                "    <Section Index=\"0\" Format=\"xml\" File=\"diagram.xml\" />\n"
                "    <Section Index=\"1\" Format=\"bin\" File=\"fake.bin\" />\n"
                "  </FakeBlock>\n"
                "</RSRC>\n",
                encoding="utf-8",
            )
            (xml_path.parent / "fake.bin").write_bytes(b"FAKE-BLOCK")
            (xml_path.parent / "diagram.xml").write_text(
                "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n"
                "<SL__rootObject SL__class=\"BlockDiagram\" SL__uid=\"1\">\n"
                "  <OF__displayName>\"Main Diagram\"</OF__displayName>\n"
                "  <OF__bounds>(0, 0, 640, 480)</OF__bounds>\n"
                "  <SL__object SL__class=\"NumericControl\" SL__uid=\"10\">\n"
                "    <OF__displayName>\"Input\"</OF__displayName>\n"
                "    <OF__bounds>(13, 19, 113, 69)</OF__bounds>\n"
                "    <OF__fgColor>16711680</OF__fgColor>\n"
                "    <OF__description>\"Input value\"</OF__description>\n"
                "    <OF__termList>\n"
                "      <SL__array><SL__arrayElement><SL__reference SL__uid=\"20\" /></SL__arrayElement></SL__array>\n"
                "    </OF__termList>\n"
                "  </SL__object>\n"
                "  <SL__object SL__class=\"Terminal\" SL__uid=\"20\">\n"
                "    <OF__termBounds>(113, 35, 129, 51)</OF__termBounds>\n"
                "    <OF__termHotPoint>(43, 121)</OF__termHotPoint>\n"
                "    <OF__owner><SL__reference SL__uid=\"10\" /></OF__owner>\n"
                "  </SL__object>\n"
                "  <SL__object SL__class=\"AddPrimitive\" SL__uid=\"30\">\n"
                "    <OF__nodeName>\"Add\"</OF__nodeName>\n"
                "    <OF__bounds>(205, 21, 269, 85)</OF__bounds>\n"
                "    <OF__nInputs>2</OF__nInputs>\n"
                "  </SL__object>\n"
                "  <SL__object SL__class=\"Wire\" SL__uid=\"40\">\n"
                "    <OF__wireID>40</OF__wireID>\n"
                "    <OF__wireTable>\n"
                "      <SL__array>\n"
                "        <SL__arrayElement>(43, 121)</SL__arrayElement>\n"
                "        <SL__arrayElement>(43, 205)</SL__arrayElement>\n"
                "      </SL__array>\n"
                "    </OF__wireTable>\n"
                "    <OF__srcDCO><SL__reference SL__uid=\"10\" /></OF__srcDCO>\n"
                "  </SL__object>\n"
                "</SL__rootObject>\n",
                encoding="utf-8",
            )
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
