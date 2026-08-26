from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.component_model import DatasetComponentModel
from app.errors import AppError
from app.main import create_app


def extracted_job(service, store):
    paths = store.create("vi_to_xml")
    source = paths.input / "sample.vi"
    source.write_bytes(b"RSRC\r\nFAKE")
    service.extract_vi(
        paths,
        source,
        text_encoding="shift_jis",
        verbosity=1,
        raw_connectors=False,
        verify_roundtrip=True,
    )
    return paths


def find_component(model: DatasetComponentModel, *, class_name: str):
    return next(
        component
        for component in model.components.values()
        if component["class_name"] == class_name
    )


def test_component_model_accounts_for_all_xml_elements_and_values(service, store) -> None:
    paths = extracted_job(service, store)
    model = DatasetComponentModel.analyze(paths.dataset, max_bytes=8 * 1024 * 1024)
    summary = model.summary()["summary"]

    expected_elements = 0
    expected_attributes = 0
    expected_scalars = 0
    for xml_path in paths.dataset.glob("*.xml"):
        root = ET.parse(xml_path).getroot()
        for element in root.iter():
            expected_elements += 1
            expected_attributes += len(element.attrib)
            expected_scalars += int(bool((element.text or "").strip()))

    assert summary["elements"] == expected_elements
    assert summary["modeled_elements"] == expected_elements
    assert summary["attributes"] == expected_attributes
    assert summary["scalar_values"] == expected_scalars
    assert summary["properties"] == expected_attributes + expected_scalars
    assert summary["xml_files"] == 2
    assert summary["failed_files"] == 0


def test_components_are_grouped_by_sl_object_with_identity_geometry_and_refs(service, store) -> None:
    paths = extracted_job(service, store)
    model = DatasetComponentModel.analyze(paths.dataset, max_bytes=8 * 1024 * 1024)

    control = find_component(model, class_name="NumericControl")
    terminal = find_component(model, class_name="Terminal")
    primitive = find_component(model, class_name="AddPrimitive")
    wire = find_component(model, class_name="Wire")

    assert control["name"] == "Input"
    assert control["kind"] == "control"
    assert control["uid"] == "10"
    assert control["bounds"] == {
        "property_id": control["bounds"]["property_id"],
        "name": "OF__bounds",
        "left": 13,
        "top": 19,
        "right": 113,
        "bottom": 69,
        "x": 13,
        "y": 19,
        "width": 100,
        "height": 50,
    }
    assert terminal["kind"] == "connector"
    assert terminal["points"][0]["x"] == 121
    assert terminal["points"][0]["y"] == 43
    assert primitive["kind"] == "function"
    assert primitive["name"] == "Add"
    assert wire["kind"] == "wire"

    control_detail = model.detail(control["id"])
    outbound = control_detail["relationships"]["outbound"]
    assert any(
        relation["target_component_id"] == terminal["id"] and relation["resolved"]
        for relation in outbound
    )
    terminal_detail = model.detail(terminal["id"])
    assert any(
        relation["target_component_id"] == control["id"] and relation["resolved"]
        for relation in terminal_detail["relationships"]["outbound"]
    )
    assert control_detail["property_tree"]["kind"] == "group"
    assert any(
        child.get("kind") == "reference" or child.get("tag") == "OF__termList"
        for child in control_detail["property_tree"]["children"]
    )


def test_component_model_exposes_safe_and_read_only_properties(service, store) -> None:
    paths = extracted_job(service, store)
    model = DatasetComponentModel.analyze(paths.dataset, max_bytes=8 * 1024 * 1024)
    control = find_component(model, class_name="NumericControl")
    detail = model.detail(control["id"])
    properties = {prop["name"]: prop for prop in detail["properties"]}

    assert properties["@SL__class"]["editable"] is False
    assert properties["@SL__uid"]["editable"] is False
    assert properties["OF__displayName"]["editable"] is True
    assert properties["OF__bounds"]["editable"] is True
    assert properties["OF__fgColor"]["editable"] is True
    reference = next(prop for prop in detail["properties"] if prop["reference_like"])
    assert reference["editable"] is False


def test_component_property_update_writes_auxiliary_xml_and_refreshes_bundle(service, store) -> None:
    paths = extracted_job(service, store)
    metadata = store.load(paths)
    metadata["reconstructed"] = {"name": "old.vi", "stale": False}
    store.save(paths, metadata)

    model = service._load_component_model(paths)
    control = find_component(model, class_name="NumericControl")
    detail = model.detail(control["id"])
    by_name = {prop["name"]: prop for prop in detail["properties"]}

    result = service.update_component(
        paths,
        control["id"],
        expected_file_sha256=detail["file_sha256"],
        updates=[
            {"property_id": by_name["OF__displayName"]["id"], "value": '"Input aligned"'},
            {"property_id": by_name["OF__bounds"]["id"], "value": "(16, 24, 116, 74)"},
            {"property_id": by_name["OF__fgColor"]["id"], "value": "255"},
        ],
    )

    heap = (paths.dataset / "diagram.xml").read_text(encoding="utf-8")
    assert '"Input aligned"' in heap
    assert "(16, 24, 116, 74)" in heap
    assert "<OF__fgColor>255</OF__fgColor>" in heap
    assert result["job"]["reconstructed"]["stale"] is True
    assert result["job"]["verification"]["stale"] is True
    assert set(result["updated_properties"]) == {
        by_name["OF__displayName"]["id"],
        by_name["OF__bounds"]["id"],
        by_name["OF__fgColor"]["id"],
    }
    assert result["component"]["name"] == "Input aligned"
    assert result["component"]["bounds"]["x"] == 16
    assert result["component"]["bounds"]["y"] == 24

    bundle = service.artifact_path(paths, "dataset")
    with zipfile.ZipFile(bundle) as archive:
        stored = archive.read("diagram.xml").decode("utf-8")
    assert '"Input aligned"' in stored
    assert "(16, 24, 116, 74)" in stored


def test_component_update_rejects_structural_reference_and_stale_sha(service, store) -> None:
    paths = extracted_job(service, store)
    model = service._load_component_model(paths)
    control = find_component(model, class_name="NumericControl")
    detail = model.detail(control["id"])
    class_prop = next(prop for prop in detail["properties"] if prop["name"] == "@SL__class")
    reference_prop = next(prop for prop in detail["properties"] if prop["reference_like"])

    with pytest.raises(AppError) as structural:
        service.update_component(
            paths,
            control["id"],
            expected_file_sha256=detail["file_sha256"],
            updates=[{"property_id": class_prop["id"], "value": "OtherClass"}],
        )
    assert structural.value.code == "component_property_read_only"

    with pytest.raises(AppError) as reference:
        service.update_component(
            paths,
            control["id"],
            expected_file_sha256=detail["file_sha256"],
            updates=[{"property_id": reference_prop["id"], "value": "999"}],
        )
    assert reference.value.code == "component_property_read_only"

    with pytest.raises(AppError) as stale:
        service.update_component(
            paths,
            control["id"],
            expected_file_sha256="0" * 64,
            updates=[
                {
                    "property_id": next(prop for prop in detail["properties"] if prop["name"] == "OF__displayName")["id"],
                    "value": '"Changed"',
                }
            ],
        )
    assert stale.value.code == "component_model_stale"


def test_component_api_lists_details_and_edits_properties(settings, store, service) -> None:
    app = create_app(settings, store, service)
    with TestClient(app, raise_server_exceptions=False) as client:
        converted = client.post(
            "/api/convert/vi-to-xml",
            files={"file": ("sample.vi", b"RSRC\r\nFAKE", "application/octet-stream")},
            data={"text_encoding": "shift_jis", "verify_roundtrip": "true"},
        )
        assert converted.status_code == 200, converted.text
        job = converted.json()

        model_response = client.get(f"/api/jobs/{job['job_id']}/model")
        assert model_response.status_code == 200, model_response.text
        summary = model_response.json()["summary"]
        assert summary["elements"] == summary["modeled_elements"]
        assert summary["components"] >= 7
        assert summary["properties"] > 20
        assert summary["resolved_relationships"] >= 2

        listing = client.get(
            f"/api/jobs/{job['job_id']}/components",
            params={"query": "NumericControl"},
        )
        assert listing.status_code == 200, listing.text
        control = listing.json()["items"][0]
        assert control["name"] == "Input"
        assert control["bounds"]["x"] == 13

        detail_response = client.get(
            f"/api/jobs/{job['job_id']}/components/{control['id']}"
        )
        assert detail_response.status_code == 200, detail_response.text
        detail = detail_response.json()
        display = next(prop for prop in detail["properties"] if prop["name"] == "OF__displayName")
        assert detail["property_tree"]
        assert detail["relationships"]["outbound"]

        updated = client.patch(
            f"/api/jobs/{job['job_id']}/components/{control['id']}",
            json={
                "expected_file_sha256": detail["file_sha256"],
                "updates": [
                    {"property_id": display["id"], "value": '"Renamed input"'}
                ],
            },
        )
        assert updated.status_code == 200, updated.text
        payload = updated.json()
        assert payload["component"]["name"] == "Renamed input"
        assert payload["job"]["verification"]["stale"] is True

        refreshed = client.get(
            f"/api/jobs/{job['job_id']}/components",
            params={"query": "Renamed input"},
        )
        assert refreshed.status_code == 200
        assert refreshed.json()["total"] == 1


def test_component_model_keeps_parsed_files_when_one_auxiliary_xml_is_invalid(service, store) -> None:
    paths = extracted_job(service, store)
    (paths.dataset / "broken.xml").write_text("<broken", encoding="utf-8")
    summary = service.component_model_summary(paths)

    assert summary["summary"]["parsed_files"] == 2
    assert summary["summary"]["failed_files"] == 1
    assert any("broken.xml" in warning for warning in summary["warnings"])
