from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from app.component_model import (
    DatasetComponentModel,
    classify_component,
    classify_value,
    component_candidate,
    parse_tuple,
)
from app.errors import AppError
from app.model_graph import build_model_graph

# Native (unprefixed) heap shape rather than only synthetic SL__object fixtures.
HEAP = '''<SL__rootObject class="oHExt"><root class="supC" uid="1">
<zPlaneList elements="1"><SL__arrayElement class="fPDCO" uid="10">
<terminal>20</terminal><ddo class="stdString" uid="11">
<bounds>(10, 20, 210, 80)</bounds><fgColor>01000000</fgColor>
<partsList elements="1"><SL__arrayElement class="label" uid="12">
<partID>16</partID><bounds>(0, 0, 100, 17)</bounds>
<textRec class="textHair"><text>"Setpoint"</text></textRec>
</SL__arrayElement></partsList></ddo></SL__arrayElement></zPlaneList>
</root></SL__rootObject>'''


def write_heap(path):
    target = path / "sample_FPHb.xml"
    target.write_text(HEAP, encoding="utf-8")
    return target


@pytest.mark.parametrize("text, expected", [("010", 10), ("-009", -9), ("0x10", 16), ("000", 0)])
def test_zero_padded_decimal_is_not_octal(text, expected):
    assert classify_value("value", text) == ("int", expected)


def test_native_color_and_digit_only_binary_keep_raw_encoding():
    assert classify_value("fgColor", "01000000") == ("color", {"hex": "01000000", "storage": "hex32"})
    assert classify_value("bgColor", "00FAFAFA")[0] == "color"
    assert classify_value("OF__fgColor", "16711680") == ("int", 16711680)
    assert classify_value("buffer", "01000000")[0] == "binary"
    assert classify_value("fgColor", "unsupported")[0] == "string"
    assert classify_value("value", "1" * 5000)[0] == "string"
    assert parse_tuple("(001, 002, 010, 020)") == (1, 2, 10, 20)


def test_classed_array_object_is_not_an_array_wrapper():
    root = ET.fromstring('<root><SL__arrayElement class="term" uid="2"/><SL__arrayElement>3</SL__arrayElement><SL__reference class="term">2</SL__reference></root>')
    assert component_candidate(root[0], root, root) == (True, "component")
    assert component_candidate(root[1], root, root) == (False, "")
    assert component_candidate(root[2], root, root) == (False, "")
    assert classify_component("SL__arrayElement", "fPDCO", [{"name": "terminal"}], "component") == "control"
    assert classify_component("SL__arrayElement", "forLoop", [{"name": "termList"}], "component") == "structure"
    assert classify_component("SL__object", "NumericControl", [{"name": "wireID"}], "component") == "control"


def test_logical_control_owns_visible_label_geometry_without_cosmetic_nodes(tmp_path):
    write_heap(tmp_path)
    model = DatasetComponentModel.analyze(tmp_path, max_bytes=1024 * 1024)
    assert model.summary()["summary"]["failed_files"] == 0
    control = next(c for c in model.components.values() if c["class_name"] == "fPDCO")
    assert control["name"] == "Setpoint"
    assert control["kind"] == "control"
    assert control["bounds"]["width"] == 200
    graph = build_model_graph(model)
    assert len(graph["models"]) == 1
    assert graph["models"][0]["id"] == control["id"]
    assert graph["models"][0]["widget"] == "stdString"
    assert graph["models"][0]["positioned"]
    detail = model.detail(control["id"])
    props = {prop["name"]: prop for prop in detail["properties"]}
    assert props["text"]["editable"]
    assert props["bounds"]["id"] == control["bounds"]["property_id"]
    assert props["fgColor"]["value"] == "01000000"
    assert props["text"]["component_id"] != control["id"]
    assert model.list_components()["items"][0]["id"] == control["id"]
    assert all(c["kind"] for c in model.components.values())


def test_failed_file_is_transactional_even_after_objects_are_allocated(tmp_path, monkeypatch):
    write_heap(tmp_path)
    (tmp_path / "broken.xml").write_text(HEAP, encoding="utf-8")
    original = DatasetComponentModel._property_record

    def fail_mid_file(self, **kwargs):
        if kwargs["file"] == "broken.xml" and kwargs["name"] == "fgColor":
            raise ValueError("injected failure after component allocation")
        return original(self, **kwargs)

    monkeypatch.setattr(DatasetComponentModel, "_property_record", fail_mid_file)
    model = DatasetComponentModel.analyze(tmp_path, max_bytes=1024 * 1024)
    assert len(model.files) == 2
    assert model.summary()["summary"]["failed_files"] == 1
    assert model.summary()["summary"]["parsed_files"] == 1
    assert not any(c["file"] == "broken.xml" for c in model.components.values())
    assert not any(p["file"] == "broken.xml" for p in model.properties.values())
    assert all(i in model.components for ids in model._uid_index.values() for i in ids)


def test_logical_control_visual_edit_is_scoped_and_reloaded(service, store):
    paths = store.create("vi_to_xml")
    target = write_heap(paths.dataset)
    model = service._load_component_model(paths)
    control = next(c for c in model.components.values() if c["class_name"] == "fPDCO")
    detail = model.detail(control["id"])
    props = {prop["name"]: prop for prop in detail["properties"]}
    before = target.read_bytes()
    with pytest.raises(AppError) as invalid:
        service.update_component(paths, control["id"], expected_file_sha256=detail["file_sha256"],
                                 updates=[{"property_id": props["fgColor"]["id"], "value": "255"}])
    assert invalid.value.code == "invalid_component_value"
    assert target.read_bytes() == before
    result = service.update_component(paths, control["id"], expected_file_sha256=detail["file_sha256"], updates=[
        {"property_id": props["text"]["id"], "value": '"Renamed"'},
        {"property_id": props["bounds"]["id"], "value": "(16, 24, 216, 84)"},
        {"property_id": props["fgColor"]["id"], "value": "00FF0000"},
    ])
    assert result["component"]["name"] == "Renamed"
    assert result["component"]["bounds"]["x"] == 16
    saved = ET.parse(target).getroot()
    assert saved.find(".//fgColor").text == "00FF0000"
    assert saved.find(".//text").text == '"Renamed"'
    assert saved.find(".//SL__arrayElement").get("uid") == "10"
