from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.pylabview_service import CommandResult


class FakePylabviewService:
    def health(self) -> dict[str, object]:
        return {"available": True, "version": "readRSRC 0.1.0 test-double"}

    def extract(
        self,
        source: Path,
        dataset_dir: Path,
        *,
        main_xml_name: str,
        text_encoding: str,
        raw_connectors: bool = False,
    ) -> tuple[Path, CommandResult]:
        dataset_dir.mkdir(parents=True, exist_ok=True)
        main_xml = dataset_dir / main_xml_name
        main_xml.write_text(
            "<?xml version='1.0' encoding='utf-8'?>\n"
            "<RSRC Type='VI'><Block Ident='TEST' File='main_TEST.bin' /></RSRC>\n",
            encoding="utf-8",
        )
        (dataset_dir / "main_TEST.bin").write_bytes(b"sidecar:" + source.read_bytes())
        result = CommandResult(
            command=("fake-readRSRC", "-x", source.name),
            stdout=f"encoding={text_encoding} raw={raw_connectors}\n",
            stderr="",
            returncode=0,
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
        sidecar = main_xml.parent / "main_TEST.bin"
        if not sidecar.exists():
            raise RuntimeError("missing sidecar")
        output.write_bytes(
            b"RSRC-REBUILT\n"
            + text_encoding.encode("ascii")
            + b"\n"
            + main_xml.read_bytes()
            + sidecar.read_bytes()
        )
        return CommandResult(
            command=("fake-readRSRC", "-c", output.name),
            stdout="created\n",
            stderr="",
            returncode=0,
        )


@pytest.fixture()
def client(tmp_path: Path):
    settings = Settings.for_tests(tmp_path / "jobs")
    app = create_app(settings, converter=FakePylabviewService())
    with TestClient(app) as test_client:
        yield test_client
