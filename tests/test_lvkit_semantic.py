from __future__ import annotations

from types import SimpleNamespace

from app.component_model import DatasetComponentModel
from app.lvkit_semantic import _build_authoritative
from app.model_graph import build_model_graph
from app.semantic_enrichment import enrich_semantic_vi
from app.semantic_vi import build_semantic_vi


def _write_dataset(tmp_path) -> tuple[object, object, object]:
    bd = tmp_path / "sum_BDHb.xml"
    fp = tmp_path / "sum_FPHb.xml"
    main = tmp_path / "sum.xml"
    fp.write_text(
        """
<SL__rootObject class="oHExt" uid="1">
  <root class="supC" uid="2">
    <zPlaneList>
      <SL__arrayElement class="fPDCO" uid="10">
        <name>"Input"</name><objFlags>0</objFlags><terminal>110</terminal>
        <ddo class="stdClust" uid="1010"><bounds>(20, 30, 100, 190)</bounds></ddo>
      </SL__arrayElement>
      <SL__arrayElement class="fPDCO" uid="12">
        <name>"Result"</name><objFlags>1</objFlags><terminal>112</terminal>
        <ddo class="stdNum" uid="1012"><bounds>(40, 320, 80, 420)</bounds></ddo>
      </SL__arrayElement>
    </zPlaneList>
  </root>
</SL__rootObject>
""".strip(),
        encoding="utf-8",
    )
    bd.write_text(
        """
<SL__rootObject class="oHExt" uid="3">
  <root class="diag" uid="4">
    <zPlaneList>
      <SL__arrayElement class="internalDCO" uid="999">
        <name>"Must not become a node"</name><bounds>(1, 1, 10, 10)</bounds>
      </SL__arrayElement>
      <SL__arrayElement class="cpdArith" uid="200">
        <bounds>(80, 180, 120, 220)</bounds>
        <termList>
          <SL__arrayElement class="term" uid="210"><dco class="parm" uid="1210"><parmIndex>0</parmIndex></dco></SL__arrayElement>
          <SL__arrayElement class="term" uid="212"><dco class="parm" uid="1212"><parmIndex>1</parmIndex></dco></SL__arrayElement>
        </termList>
      </SL__arrayElement>
      <SL__arrayElement class="sRN" uid="100">
        <termList>
          <SL__arrayElement class="fPTerm" uid="110"><dco uid="10" /></SL__arrayElement>
          <SL__arrayElement class="fPTerm" uid="112"><dco uid="12" /></SL__arrayElement>
        </termList>
      </SL__arrayElement>
    </zPlaneList>
    <signalList>
      <SL__arrayElement class="signal" uid="301"><termList><SL__arrayElement uid="110"/><SL__arrayElement uid="210"/></termList></SL__arrayElement>
      <SL__arrayElement class="signal" uid="302"><termList><SL__arrayElement uid="212"/><SL__arrayElement uid="112"/></termList></SL__arrayElement>
    </signalList>
  </root>
</SL__rootObject>
""".strip(),
        encoding="utf-8",
    )
    main.write_text('<RSRC FormatVersion="3" Type="LVIN"/>', encoding="utf-8")
    return bd, fp, main


def _type(kind: str, name: str, **kwargs):
    return SimpleNamespace(kind=kind, type_name=name, **kwargs)


def _fake_parsed() -> SimpleNamespace:
    numeric = _type("primitive", "NumFloat64")
    cluster = _type(
        "typedef_ref",
        "Cluster",
        typedef_name="Settings.ctl",
        typedef_path="types/Settings.ctl",
        fields=[SimpleNamespace(name="Gain", type=numeric)],
    )
    node = SimpleNamespace(
        uid="200",
        node_type="cpdArith",
        operation="add",
        name="Compound Arithmetic",
        label=None,
        caption=None,
    )
    controls = [
        SimpleNamespace(
            uid="10",
            name="Input",
            control_type="stdClust",
            bounds=(20, 30, 100, 190),
            is_indicator=False,
            children=[],
        ),
        SimpleNamespace(
            uid="12",
            name="Result",
            control_type="stdNum",
            bounds=(40, 320, 80, 420),
            is_indicator=True,
            children=[],
        ),
    ]
    fp_terminals = [
        SimpleNamespace(uid="110", fp_dco_uid="10", name="Input", parsed_type=cluster),
        SimpleNamespace(uid="112", fp_dco_uid="12", name="Result", parsed_type=numeric),
    ]
    terminal_info = {
        "110": SimpleNamespace(uid="110", parent_uid="100", index=0, is_output=True, parsed_type=cluster, name="Input"),
        "210": SimpleNamespace(uid="210", parent_uid="200", index=0, is_output=False, parsed_type=cluster, name="x"),
        "212": SimpleNamespace(uid="212", parent_uid="200", index=1, is_output=True, parsed_type=numeric, name="sum"),
        "112": SimpleNamespace(uid="112", parent_uid="100", index=1, is_output=False, parsed_type=numeric, name="Result"),
    }
    block = SimpleNamespace(
        nodes=[node],
        constants=[],
        wires=[
            SimpleNamespace(uid="301", from_term="110", to_term="210"),
            SimpleNamespace(uid="302", from_term="212", to_term="112"),
        ],
        fp_terminals=fp_terminals,
        terminal_info=terminal_info,
        loops=[],
        case_structures=[],
        flat_sequences=[],
        decompose_structures=[],
        disable_structures=[],
        event_structures=[],
    )
    layout = SimpleNamespace(
        node_bounds={"200": (180, 80, 220, 120)},
        terminal_centers={
            "110": (80, 60),
            "210": (180, 96),
            "212": (220, 104),
            "112": (320, 60),
        },
        wire_by_uid={
            "210": [(80, 60), (130, 60), (130, 96), (180, 96)],
            "112": [(220, 104), (270, 104), (270, 60), (320, 60)],
        },
    )
    metadata = SimpleNamespace(
        qualified_name="sum.vi",
        iuse_to_qualified_name={},
        dependency_refs=[
            SimpleNamespace(
                name="Settings.ctl",
                get_relative_path=lambda: "types/Settings.ctl",
            )
        ],
        link_path_refs=[],
    )
    return SimpleNamespace(
        metadata=metadata,
        block_diagram=block,
        front_panel=SimpleNamespace(controls=controls),
        layout=layout,
    )


def _project(tmp_path):
    bd, fp, main = _write_dataset(tmp_path)
    model = DatasetComponentModel.analyze(tmp_path, max_bytes=4 * 1024 * 1024)
    graph = build_model_graph(model)
    fallback = enrich_semantic_vi(model, graph, build_semantic_vi(model, graph))
    vi = _build_authoritative(
        tmp_path,
        model,
        fallback,
        _fake_parsed(),
        bd,
        fp,
        main,
    )
    return vi


def test_only_parser_confirmed_block_diagram_nodes_are_exposed(tmp_path) -> None:
    vi = _project(tmp_path)
    block_nodes = [
        item
        for item in vi["objects"]
        if item["surface"] == "block-diagram" and item["category"] == "node"
    ]

    assert [(item["uid"], item["kind"], item["name"]) for item in block_nodes] == [
        ("200", "add", "加算")
    ]
    assert all(item["uid"] != "999" for item in vi["objects"])
    assert vi["parser"]["mode"] == "authoritative"
    assert vi["debug"]["generic_graph_used_for_block_diagram"] is False


def test_signal_term_order_produces_exact_connected_wires(tmp_path) -> None:
    vi = _project(tmp_path)
    objects = {item["id"]: item for item in vi["objects"]}

    assert vi["summary"]["wires"] == 2
    assert vi["summary"]["resolved_wires"] == 2
    assert vi["summary"]["unresolved_wires"] == 0
    endpoints = [
        (
            objects[wire["source_terminal_id"]]["uid"],
            objects[wire["target_terminal_ids"][0]]["uid"],
            wire["direction_confidence"],
        )
        for wire in vi["wires"]
    ]
    assert endpoints == [
        ("110", "210", "signal-term-list"),
        ("212", "112", "signal-term-list"),
    ]
    assert all(len(wire["route_points"]) == 4 for wire in vi["wires"])
    assert all(wire["resolved"] for wire in vi["wires"])


def test_typedef_is_attached_to_control_terminal_and_wire(tmp_path) -> None:
    vi = _project(tmp_path)
    definitions = {item["id"]: item for item in vi["type_definitions"]}
    input_control = next(item for item in vi["objects"] if item["name"] == "Input")
    input_terminal = next(
        item
        for item in vi["objects"]
        if item["category"] == "terminal" and item["uid"] == "110"
    )
    input_wire = next(
        wire for wire in vi["wires"] if wire["source_terminal_id"] == input_terminal["id"]
    )

    definition_id = input_control["type_definition_id"]
    assert definition_id == input_terminal["type_definition_id"]
    assert definition_id == input_wire["type_definition_id"]
    definition = definitions[definition_id]
    assert definition["name"] == "Settings.ctl"
    assert definition["definition"]["fields"] == [
        {
            "name": "Gain",
            "type": {"kind": "primitive", "name": "NumFloat64"},
        }
    ]
    assert definition["source_object_ids"]
    assert vi["summary"]["type_definitions"] >= 1
