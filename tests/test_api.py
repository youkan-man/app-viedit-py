from __future__ import annotations

import io
import json
import zipfile


def extract_job(client):
    response = client.post(
        "/api/extract",
        files={"file": ("sample.vi", b"RSRC ORIGINAL", "application/octet-stream")},
        data={
            "text_encoding": "shift_jis",
            "raw_connectors": "false",
            "verify_roundtrip": "true",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_extract_edit_rebuild_and_download(client):
    job = extract_job(client)
    assert job["status"] == "ready"
    assert job["main_xml"] == "main.xml"
    assert job["verification"]["status"] == "different"
    assert {item["name"] for item in job["dataset_files"]} == {
        "main.xml",
        "main_TEST.bin",
    }

    xml_response = client.get(f"/api/jobs/{job['id']}/xml")
    assert xml_response.status_code == 200
    edited = xml_response.text.replace("Ident='TEST'", "Ident='EDITED'")

    save_response = client.put(
        f"/api/jobs/{job['id']}/xml", json={"content": edited}
    )
    assert save_response.status_code == 200, save_response.text
    assert save_response.json()["xml_modified_at"]

    rebuild_response = client.post(
        f"/api/jobs/{job['id']}/rebuild",
        json={"output_filename": "edited.vi"},
    )
    assert rebuild_response.status_code == 200, rebuild_response.text
    rebuilt_job = rebuild_response.json()
    assert any(item["name"] == "edited.vi" for item in rebuilt_job["outputs"])

    download = client.get(f"/api/jobs/{job['id']}/outputs/edited.vi")
    assert download.status_code == 200
    assert b"EDITED" in download.content

    bundle = client.get(f"/api/jobs/{job['id']}/bundle")
    assert bundle.status_code == 200
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        names = set(archive.namelist())
        assert names == {"manifest.json", "main.xml", "main_TEST.bin"}
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["main_xml"] == "main.xml"


def test_import_bundle_rebuilds_vi(client):
    source_job = extract_job(client)
    bundle = client.get(f"/api/jobs/{source_job['id']}/bundle").content

    response = client.post(
        "/api/import",
        files={"files": ("dataset.zip", bundle, "application/zip")},
        data={"output_filename": "from-xml.vi", "text_encoding": "shift_jis"},
    )
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["rebuilt_output"] == "from-xml.vi"
    output = client.get(f"/api/jobs/{job['id']}/outputs/from-xml.vi")
    assert output.status_code == 200
    assert output.content.startswith(b"RSRC-REBUILT")


def test_rejects_invalid_xml_update(client):
    job = extract_job(client)
    response = client.put(
        f"/api/jobs/{job['id']}/xml",
        json={"content": "<not-rsrc />"},
    )
    assert response.status_code == 400
    assert "<RSRC>" in response.json()["detail"]


def test_job_path_traversal_is_not_available(client):
    response = client.get("/api/jobs/../../etc/passwd")
    assert response.status_code in {404, 405}


def test_output_extension_is_restricted(client):
    job = extract_job(client)
    response = client.post(
        f"/api/jobs/{job['id']}/rebuild",
        json={"output_filename": "payload.sh"},
    )
    assert response.status_code == 400


def test_extract_validation_failure_marks_job_failed(client, monkeypatch):
    services = client.app.state.services
    captured = {}
    original_create = services.workspaces.create_job

    def create_and_capture(*, kind):
        paths = original_create(kind=kind)
        captured["paths"] = paths
        return paths

    monkeypatch.setattr(services.workspaces, "create_job", create_and_capture)
    response = client.post(
        "/api/extract",
        files={"file": ("not-a-vi.txt", b"not rsrc", "text/plain")},
        data={"text_encoding": "shift_jis"},
    )
    assert response.status_code == 400
    meta = services.workspaces.read_meta(captured["paths"])
    assert meta["status"] == "failed"
    assert "Unsupported source extension" in meta["error"]
