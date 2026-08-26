from __future__ import annotations

from fastapi.testclient import TestClient

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
