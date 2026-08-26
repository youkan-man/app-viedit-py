from __future__ import annotations

import io
import json
import zipfile

from fastapi.testclient import TestClient

from app.filesystem import MANIFEST_NAME
from app.main import create_app


def test_health_and_vi_to_xml_api(settings, store, service) -> None:
    app = create_app(settings, store, service)
    with TestClient(app, raise_server_exceptions=False) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["pylabview"]["available"] is True

        response = client.post(
            "/api/convert/vi-to-xml",
            files={"file": ("sample.vi", b"RSRC\r\nFAKE", "application/octet-stream")},
            data={
                "text_encoding": "shift_jis",
                "verbosity": "1",
                "raw_connectors": "false",
                "verify_roundtrip": "true",
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "completed"
        xml = client.get(payload["xml_url"])
        assert xml.status_code == 200
        assert b"<RSRC" in xml.content
        download = client.get(payload["urls"]["dataset"])
        assert download.status_code == 200
        assert download.headers["content-type"].startswith("application/zip")


def test_xml_to_vi_and_editor_api(settings, store, service) -> None:
    app = create_app(settings, store, service)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/convert/xml-to-vi",
            files={
                "dataset": (
                    "main.xml",
                    b'<RSRC FormatVersion="3" Type="LVIN" />',
                    "application/xml",
                )
            },
            data={"output_name": "made.vi", "text_encoding": "shift_jis", "verbosity": "1"},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["reconstructed"]["name"] == "made.vi"

        update = client.put(
            payload["xml_url"],
            content=b'<RSRC FormatVersion="3" Type="LVIN"><Edited /></RSRC>',
            headers={"content-type": "application/xml"},
        )
        assert update.status_code == 200
        assert update.json()["reconstructed"]["stale"] is True

        rebuilt = client.post(
            payload["rebuild_url"],
            json={"output_name": "made-again.vi", "verbosity": 2},
        )
        assert rebuilt.status_code == 200, rebuilt.text
        assert rebuilt.json()["reconstructed"]["name"] == "made-again.vi"


def test_invalid_zip_is_reported_as_json(settings, store, service) -> None:
    app = create_app(settings, store, service)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/convert/xml-to-vi",
            files={"dataset": ("broken.zip", b"not a zip", "application/zip")},
            data={"text_encoding": "shift_jis"},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "unsupported_dataset"


def test_swagger_docs_csp_allows_required_assets(settings, store, service) -> None:
    app = create_app(settings, store, service)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/docs")
        assert response.status_code == 200
        policy = response.headers["content-security-policy"]
        assert "https://cdn.jsdelivr.net" in policy
        assert "'unsafe-inline'" in policy
        assert "frame-ancestors 'none'" in policy


def test_xml_editor_request_limit_is_enforced_before_body_read(settings, store, service) -> None:
    app = create_app(settings, store, service)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.put(
            "/api/jobs/00000000000000000000000000000000/xml",
            content=b"x" * (settings.inline_xml_max_bytes + 1),
            headers={"content-type": "application/xml"},
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "xml_too_large_for_editor"


def test_quantize_xml_api_uses_current_editor_content(settings, store, service) -> None:
    app = create_app(settings, store, service)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/quantize/xml",
            json={
                "content": "<RSRC><bounds>(3, 5, 103, 55)</bounds><termHotPoint>(7, 11)</termHotPoint></RSRC>",
                "grid_size": 8,
                "rounding": "nearest",
                "include_objects": True,
                "include_connectors": True,
                "include_wires": False,
                "resize_rectangles": False,
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert "<bounds>(0, 8, 100, 58)</bounds>" in payload["content"]
        assert "<termHotPoint>(8, 8)</termHotPoint>" in payload["content"]
        assert payload["report"]["changed_by_kind"]["connector"] == 1


def test_quantize_xml_api_enforces_editor_limit(settings, store, service) -> None:
    app = create_app(settings, store, service)
    with TestClient(app, raise_server_exceptions=False) as client:
        content = "<RSRC>" + (" " * settings.inline_xml_max_bytes) + "</RSRC>"
        response = client.post(
            "/api/quantize/xml",
            json={"content": content, "grid_size": 8},
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "xml_too_large_for_editor"


def test_job_quantize_preview_and_apply_updates_auxiliary_xml(
    settings, store, service
) -> None:
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        archive.writestr(
            "main.xml",
            '<RSRC FormatVersion="3" Type="LVIN"><Section File="heap.xml" /></RSRC>',
        )
        archive.writestr(
            "heap.xml",
            '<SL__rootObject><OF__bounds>(3, 5, 13, 15)</OF__bounds>'
            '<wireTable><SL__arrayElement>(13, 19)</SL__arrayElement></wireTable>'
            '</SL__rootObject>',
        )
        archive.writestr(MANIFEST_NAME, json.dumps({"main_xml": "main.xml"}))

    app = create_app(settings, store, service)
    with TestClient(app, raise_server_exceptions=False) as client:
        imported = client.post(
            "/api/convert/xml-to-vi",
            files={
                "dataset": (
                    "dataset.zip",
                    archive_bytes.getvalue(),
                    "application/zip",
                )
            },
            data={"output_name": "before.vi", "text_encoding": "shift_jis"},
        )
        assert imported.status_code == 200, imported.text
        job = imported.json()
        edited_main = (
            '<RSRC FormatVersion="3" Type="LVIN"><Edited />'
            '<Section File="heap.xml" /></RSRC>'
        )

        preview = client.post(
            f"/api/jobs/{job['job_id']}/quantize/preview",
            json={
                "current_main_xml": edited_main,
                "grid_size": 8,
                "rounding": "nearest",
                "include_objects": True,
                "include_connectors": True,
                "include_wires": True,
                "resize_rectangles": False,
            },
        )
        assert preview.status_code == 200, preview.text
        report = preview.json()
        assert report["staged_files"] == 2
        assert report["changed_by_kind"]["object"] == 1
        assert report["changed_by_kind"]["wire"] == 1

        applied = client.post(
            f"/api/jobs/{job['job_id']}/quantize/apply",
            json={"preview_id": report["preview_id"]},
        )
        assert applied.status_code == 200, applied.text
        applied_job = applied.json()
        assert applied_job["quantization"]["applied"] is True
        assert applied_job["reconstructed"]["stale"] is True

        dataset = client.get(applied_job["urls"]["dataset"])
        assert dataset.status_code == 200
        with zipfile.ZipFile(io.BytesIO(dataset.content)) as archive:
            assert b"<Edited" in archive.read("main.xml")
            heap = archive.read("heap.xml")
            assert b"(0, 8, 10, 18)" in heap
            assert b"(16, 16)" in heap
