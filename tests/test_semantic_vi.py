from __future__ import annotations

from app.component_model import DatasetComponentModel
from app.model_graph import build_model_graph
from app.semantic_vi import build_semantic_vi


def _write_sum_vi(tmp_path) -> None:
    (tmp_path / "sum_FPHb.xml").write_text(
        """
<SL__rootObject>
  <SL__object>
    <SL__class>fPDCO</SL__class><SL__uid>10</SL__uid>
    <name>"Input A"</name><objFlags>0</objFlags><terminal>110</terminal>
    <ddo class="stdNum" uid="1010"><bounds>(24, 20, 64, 120)</bounds></ddo>
  </SL__object>
  <SL__object>
    <SL__class>fPDCO</SL__class><SL__uid>11</SL__uid>
    <name>"Input B"</name><objFlags>0</objFlags><terminal>111</terminal>
    <ddo class="stdNum" uid="1011"><bounds>(92, 20, 132, 120)</bounds></ddo>
  </SL__object>
  <SL__object>
    <SL__class>fPDCO</SL__class><SL__uid>12</SL__uid>
    <name>"Result"</name><objFlags>1</objFlags><terminal>112</terminal>
    <ddo class="stdNum" uid="1012"><bounds>(58, 240, 98, 340)</bounds></ddo>
  </SL__object>
</SL__rootObject>
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "sum_BDHb.xml").write_text(
        """
<SL__rootObject>
  <SL__object>
    <SL__class>fPTerm</SL__class><SL__uid>110</SL__uid>
    <name>"Input A terminal"</name><OF__dco>10</OF__dco>
    <termBounds>(80, 20, 88, 28)</termBounds><OF__wireID>301</OF__wireID>
  </SL__object>
  <SL__object>
    <SL__class>fPTerm</SL__class><SL__uid>111</SL__uid>
    <name>"Input B terminal"</name><OF__dco>11</OF__dco>
    <termBounds>(140, 20, 148, 28)</termBounds><OF__wireID>302</OF__wireID>
  </SL__object>
  <SL__object>
    <SL__class>fPTerm</SL__class><SL__uid>112</SL__uid>
    <name>"Result terminal"</name><OF__dco>12</OF__dco>
    <termBounds>(108, 280, 116, 288)</termBounds><OF__wireID>303</OF__wireID>
  </SL__object>
  <SL__object>
    <SL__class>cpdArith</SL__class><SL__uid>200</SL__uid>
    <name>"Add"</name><operation>add</operation><bounds>(88, 160, 128, 200)</bounds>
    <termList>
      <SL__reference>210</SL__reference><SL__reference>211</SL__reference><SL__reference>212</SL__reference>
    </termList>
  </SL__object>
  <SL__object>
    <SL__class>term</SL__class><SL__uid>210</SL__uid><name>"x"</name>
    <OF__owner>200</OF__owner><termBounds>(8, 0, 16, 8)</termBounds><OF__wireID>301</OF__wireID>
  </SL__object>
  <SL__object>
    <SL__class>term</SL__class><SL__uid>211</SL__uid><name>"y"</name>
    <OF__owner>200</OF__owner><termBounds>(24, 0, 32, 8)</termBounds><OF__wireID>302</OF__wireID>
  </SL__object>
  <SL__object>
    <SL__class>term</SL__class><SL__uid>212</SL__uid><name>"sum"</name>
    <OF__owner>200</OF__owner><termBounds>(16, 32, 24, 40)</termBounds><OF__wireID>303</OF__wireID>
  </SL__object>
  <SL__object>
    <SL__class>wire</SL__class><SL__uid>301</SL__uid><OF__wireID>301</OF__wireID>
    <pos>(84, 64)</pos><pos>(100, 64)</pos><pos>(100, 144)</pos>
    <OF__nodeList><SL__reference>110</SL__reference><SL__reference>210</SL__reference></OF__nodeList>
  </SL__object>
  <SL__object>
    <SL__class>wire</SL__class><SL__uid>302</SL__uid><OF__wireID>302</OF__wireID>
    <OF__nodeList><SL__reference>111</SL__reference><SL__reference>211</SL__reference></OF__nodeList>
  </SL__object>
  <SL__object>
    <SL__class>wire</SL__class><SL__uid>303</SL__uid><OF__wireID>303</OF__wireID>
    <OF__nodeList><SL__reference>212</SL__reference><SL__reference>112</SL__reference></OF__nodeList>
  </SL__object>
</SL__rootObject>
""".strip(),
        encoding="utf-8",
    )


def _analyze(tmp_path):
    _write_sum_vi(tmp_path)
    model = DatasetComponentModel.analyze(tmp_path, max_bytes=4 * 1024 * 1024)
    graph = build_model_graph(model)
    return model, graph, build_semantic_vi(model, graph)


def test_projects_controls_indicator_add_terminals_and_wires(tmp_path) -> None:
    _, _, vi = _analyze(tmp_path)

    assert vi["summary"]["numeric_controls"] == 2
    assert vi["summary"]["numeric_indicators"] == 1
    assert vi["summary"]["add_nodes"] == 1
    assert vi["summary"]["terminals"] == 6
    assert vi["summary"]["wires"] == 3
    assert vi["summary"]["resolved_wires"] == 3

    by_name = {item["name"]: item for item in vi["objects"]}
    assert by_name["Input A"]["kind"] == "numeric-control"
    assert by_name["Input B"]["kind"] == "numeric-control"
    assert by_name["Result"]["kind"] == "numeric-indicator"
    assert by_name["Add"]["kind"] == "add"
    assert by_name["Input A"]["surface"] == "front-panel"
    assert by_name["Add"]["surface"] == "block-diagram"
    assert by_name["Input A"]["bounds"]["x"] == 20
    assert by_name["Input A"]["bounds"]["y"] == 24
    assert by_name["Add"]["bounds"]["x"] == 160
    assert by_name["Add"]["bounds"]["y"] == 88


def test_wires_expose_ordered_semantic_endpoints(tmp_path) -> None:
    _, _, vi = _analyze(tmp_path)
    objects = {item["id"]: item for item in vi["objects"]}
    endpoints = [
        (
            objects[wire["source_object_id"]]["name"],
            [objects[item]["name"] for item in wire["target_object_ids"]],
        )
        for wire in vi["wires"]
    ]

    assert endpoints == [
        ("Input A", ["Add"]),
        ("Input B", ["Add"]),
        ("Add", ["Result"]),
    ]
    assert all(wire["source_terminal_id"] for wire in vi["wires"])
    assert all(len(wire["target_terminal_ids"]) == 1 for wire in vi["wires"])
    assert all(wire["direction_confidence"] != "unresolved" for wire in vi["wires"])


def test_wires_preserve_native_route_points(tmp_path) -> None:
    _, graph, vi = _analyze(tmp_path)
    graph_wire = next(net for net in graph["nets"] if net["points"])
    semantic_wire = next(wire for wire in vi["wires"] if wire["route_points"])

    expected = [
        {"x": 64, "y": 84},
        {"x": 64, "y": 100},
        {"x": 144, "y": 100},
    ]
    assert [
        {"x": point["x"], "y": point["y"]} for point in graph_wire["points"]
    ] == expected
    assert semantic_wire["route_points"] == [
        {"x": float(point["x"]), "y": float(point["y"])} for point in expected
    ]


def test_terminal_bounds_follow_owner_coordinate_space(tmp_path) -> None:
    _, _, vi = _analyze(tmp_path)
    by_name = {item["name"]: item for item in vi["objects"]}
    add = by_name["Add"]
    first_input = by_name["x"]
    output = by_name["sum"]

    assert first_input["owner_object_id"] == add["id"]
    assert first_input["direction"] == "sink"
    assert output["direction"] == "source"
    assert first_input["bounds"]["relative_to_object_id"] == add["id"]
    assert first_input["bounds"]["x"] == 160
    assert first_input["bounds"]["y"] == 96
    assert output["bounds"]["x"] == 192
    assert output["bounds"]["y"] == 104


def test_service_summary_contains_editor_facing_vi(service, store) -> None:
    paths = store.create("xml_to_vi")
    _write_sum_vi(paths.dataset)

    payload = service.component_model_summary(paths)

    assert payload["vi"]["version"] == 2
    assert payload["vi"]["summary"]["add_nodes"] == 1
    assert payload["vi"]["summary"]["wires"] == 3
    assert payload["vi"]["summary"]["clusters"] == 0
    assert payload["vi"]["hierarchy"]["roots"]
