from __future__ import annotations

from app.component_model import DatasetComponentModel
from app.model_graph import build_model_graph


def _write_dataset(tmp_path):
    (tmp_path / "main.xml").write_text(
        """
<RSRC FormatVersion="3" Type="LVIN">
  <Section File="diagram.xml" />
  <Section File="panel.xml" />
</RSRC>
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "diagram.xml").write_text(
        """
<SL__rootObject>
  <SL__object>
    <SL__class>function</SL__class>
    <SL__uid>1</SL__uid>
    <OF__name>Add</OF__name>
    <OF__bounds>(10, 20, 110, 80)</OF__bounds>
    <OF__termList><SL__reference>10</SL__reference></OF__termList>
  </SL__object>
  <SL__object>
    <SL__class>term</SL__class>
    <SL__uid>10</SL__uid>
    <OF__name>x</OF__name>
    <OF__termBounds>(4, 24, 16, 36)</OF__termBounds>
    <OF__wireID>100</OF__wireID>
    <OF__owner>1</OF__owner>
  </SL__object>
  <SL__object>
    <SL__class>function</SL__class>
    <SL__uid>2</SL__uid>
    <OF__name>Multiply</OF__name>
    <OF__bounds>(220, 20, 330, 80)</OF__bounds>
  </SL__object>
  <SL__object>
    <SL__class>wire</SL__class>
    <SL__uid>100</SL__uid>
    <OF__wireID>100</OF__wireID>
    <OF__bounds>(110, 44, 220, 48)</OF__bounds>
    <OF__nodeList>
      <SL__reference>1</SL__reference>
      <SL__reference>2</SL__reference>
    </OF__nodeList>
  </SL__object>
</SL__rootObject>
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "panel.xml").write_text(
        """
<SL__rootObject>
  <SL__object>
    <SL__class>control</SL__class>
    <SL__uid>20</SL__uid>
    <OF__name>Input</OF__name>
    <OF__bounds>(12, 14, 112, 54)</OF__bounds>
    <OF__dco>1</OF__dco>
  </SL__object>
</SL__rootObject>
""".strip(),
        encoding="utf-8",
    )


def test_builds_one_cross_xml_model_graph_with_positions_and_connections(tmp_path) -> None:
    _write_dataset(tmp_path)
    model = DatasetComponentModel.analyze(tmp_path, max_bytes=10 * 1024 * 1024)
    graph = build_model_graph(model)

    by_uid = {node["uid"]: node for node in graph["models"] if node["uid"]}
    assert by_uid["1"]["name"] == "Add"
    position = by_uid["1"]["position"]
    assert position is not None
    assert {
        "x": position["x"],
        "y": position["y"],
        "width": position["width"],
        "height": position["height"],
        "source_property": position["source_property"],
        "coordinate_space": position["coordinate_space"],
    } == {
        "x": 10,
        "y": 20,
        "width": 100,
        "height": 60,
        "source_property": "OF__bounds",
        "coordinate_space": "block-diagram",
    }
    assert by_uid["1"]["layer"] == "block-diagram"
    assert by_uid["20"]["layer"] == "front-panel"

    resolved_pairs = {
        (edge["source"], edge["target"], edge["type"])
        for edge in graph["connections"]
        if edge["resolved"]
    }
    assert any(
        edge["type"] == "connection"
        and edge["resolved"]
        and {edge["source"], edge["target"]}
        == {by_uid["10"]["id"], by_uid["100"]["id"]}
        for edge in graph["connections"]
    )
    assert (by_uid["10"]["id"], by_uid["1"]["id"], "ownership") in resolved_pairs
    assert (by_uid["100"]["id"], by_uid["1"]["id"], "connection") in resolved_pairs
    assert (by_uid["100"]["id"], by_uid["2"]["id"], "connection") in resolved_pairs
    assert (by_uid["20"]["id"], by_uid["1"]["id"], "connection") in resolved_pairs

    wire_net = next(net for net in graph["nets"] if net["wire_id"] == by_uid["100"]["id"])
    assert wire_net["connector_ids"] == [by_uid["10"]["id"]]
    assert set(wire_net["endpoint_ids"]) == {by_uid["1"]["id"], by_uid["2"]["id"]}
    assert wire_net["id"] in by_uid["1"]["net_ids"]

    document_paths = {document["path"] for document in graph["documents"]}
    assert document_paths == {"main.xml", "diagram.xml", "panel.xml"}
    resolved_document_pairs = {
        (edge["source_path"], edge["target_path"])
        for edge in graph["document_connections"]
        if edge["resolved"]
    }
    assert resolved_document_pairs == {
        ("main.xml", "diagram.xml"),
        ("main.xml", "panel.xml"),
    }
    assert graph["summary"]["documents"] == 3
    assert graph["summary"]["positioned_models"] == 5
    assert graph["summary"]["connections"] >= 4
    assert graph["version"] == 2


def test_duplicate_ids_are_resolved_by_xml_context_instead_of_guessed(tmp_path) -> None:
    (tmp_path / "diagram.xml").write_text(
        """
<SL__rootObject>
  <SL__object>
    <SL__class>function</SL__class>
    <SL__uid>7</SL__uid>
    <OF__name>Diagram node</OF__name>
    <OF__bounds>(0, 0, 40, 30)</OF__bounds>
  </SL__object>
  <SL__object>
    <SL__class>wire</SL__class>
    <SL__uid>90</SL__uid>
    <OF__bounds>(40, 10, 100, 12)</OF__bounds>
    <OF__nodeList><SL__reference>7</SL__reference></OF__nodeList>
  </SL__object>
</SL__rootObject>
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "panel.xml").write_text(
        """
<SL__rootObject>
  <SL__object>
    <SL__class>control</SL__class>
    <SL__uid>7</SL__uid>
    <OF__name>Panel control</OF__name>
    <OF__bounds>(10, 10, 80, 40)</OF__bounds>
  </SL__object>
</SL__rootObject>
""".strip(),
        encoding="utf-8",
    )

    model = DatasetComponentModel.analyze(tmp_path, max_bytes=1024 * 1024)
    graph = build_model_graph(model)
    nodes = {node["name"]: node for node in graph["models"]}
    wire = next(node for node in graph["models"] if node["kind"] == "wire")
    connection = next(
        edge
        for edge in graph["connections"]
        if edge["source"] == wire["id"]
        and edge["type"] == "connection"
        and edge["resolved"]
    )

    assert connection["target"] == nodes["Diagram node"]["id"]
    assert connection["target"] != nodes["Panel control"]["id"]


def test_ambiguous_cross_file_reference_is_reported_not_fabricated(tmp_path) -> None:
    for name, label in (("a.xml", "A"), ("b.xml", "B")):
        (tmp_path / name).write_text(
            f"""
<SL__rootObject>
  <SL__object>
    <SL__class>function</SL__class>
    <SL__uid>5</SL__uid>
    <OF__name>{label}</OF__name>
    <OF__bounds>(0, 0, 20, 20)</OF__bounds>
  </SL__object>
</SL__rootObject>
""".strip(),
            encoding="utf-8",
        )
    (tmp_path / "c.xml").write_text(
        """
<SL__rootObject>
  <SL__object>
    <SL__class>control</SL__class>
    <SL__uid>20</SL__uid>
    <OF__name>Ambiguous control</OF__name>
    <OF__bounds>(0, 0, 20, 20)</OF__bounds>
    <OF__dco>5</OF__dco>
  </SL__object>
</SL__rootObject>
""".strip(),
        encoding="utf-8",
    )

    model = DatasetComponentModel.analyze(tmp_path, max_bytes=1024 * 1024)
    graph = build_model_graph(model)
    unresolved = [
        edge
        for edge in graph["unresolved"]
        if edge.get("target_key") == "5"
    ]

    assert unresolved
    assert unresolved[0]["ambiguous"] is True
    assert unresolved[0]["target"] is None
    assert unresolved[0]["resolution"] == "ambiguous-id"


def test_service_component_summary_includes_unified_graph(service, store) -> None:
    paths = store.create("xml_to_vi")
    _write_dataset(paths.dataset)

    payload = service.component_model_summary(paths)

    assert "graph" in payload
    assert payload["graph"]["summary"]["documents"] == 3
    assert payload["graph"]["summary"]["models"] == 5
    assert payload["graph"]["connections"]
