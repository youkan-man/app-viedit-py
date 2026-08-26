from __future__ import annotations

import io
import zipfile


def test_zip_slip_is_rejected(client, tmp_path):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("../escaped.xml", "<RSRC />")
    response = client.post(
        "/api/import",
        files={"files": ("unsafe.zip", payload.getvalue(), "application/zip")},
        data={"output_filename": "rebuilt.vi", "text_encoding": "shift_jis"},
    )
    assert response.status_code == 400
    assert "unsafe path" in response.json()["detail"]
    assert not (tmp_path / "escaped.xml").exists()


def test_doctype_is_rejected_by_safe_xml_parser(client):
    extract = client.post(
        "/api/extract",
        files={"file": ("sample.vi", b"RSRC ORIGINAL", "application/octet-stream")},
        data={"text_encoding": "shift_jis", "verify_roundtrip": "false"},
    )
    job_id = extract.json()["id"]
    xml = "<!DOCTYPE RSRC [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]><RSRC>&xxe;</RSRC>"
    response = client.put(f"/api/jobs/{job_id}/xml", json={"content": xml})
    assert response.status_code == 400
    assert "unsafe XML" in response.json()["detail"]


def test_cross_origin_mutation_is_rejected(client):
    response = client.post(
        "/api/extract",
        headers={"Origin": "https://attacker.example"},
        files={"file": ("sample.vi", b"RSRC", "application/octet-stream")},
        data={"text_encoding": "shift_jis"},
    )
    assert response.status_code == 403
