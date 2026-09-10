from __future__ import annotations

import runpy
from pathlib import Path

import pytest

from app.component_model import DatasetComponentModel
from app.lvkit_semantic_runtime import build_authoritative_semantic_vi
from app.model_graph import build_model_graph
from app.semantic_enrichment import enrich_semantic_vi
from app.semantic_vi import build_semantic_vi

lvkit = pytest.importorskip("lvkit")
_WRITE_DATASET = runpy.run_path(
    str(Path(__file__).with_name("test_lvkit_semantic.py"))
)["_write_dataset"]


def test_lvkit_reads_only_real_nodes_and_signal_term_order(tmp_path) -> None:
    from lvkit.parser import parse_vi

    bd, fp, main = _WRITE_DATASET(tmp_path)
    parsed = parse_vi(bd_xml=bd, fp_xml=fp, main_xml=main, layout=True)

    node_uids = [str(node.uid) for node in parsed.block_diagram.nodes]
    wire_endpoints = [
        (str(wire.from_term), str(wire.to_term))
        for wire in parsed.block_diagram.wires
    ]

    assert "200" in node_uids
    assert "999" not in node_uids
    assert wire_endpoints == [("110", "210"), ("212", "112")]
    assert {"110", "210", "212", "112"} <= set(
        parsed.block_diagram.terminal_info
    )


def test_public_builder_uses_lvkit_and_never_generic_edges(tmp_path) -> None:
    _, _, main = _WRITE_DATASET(tmp_path)
    model = DatasetComponentModel.analyze(tmp_path, max_bytes=4 * 1024 * 1024)
    graph = build_model_graph(model)
    fallback = enrich_semantic_vi(model, graph, build_semantic_vi(model, graph))

    vi = build_authoritative_semantic_vi(
        tmp_path,
        model,
        fallback,
        main_xml=main,
    )

    assert vi["parser"]["name"] == "lvkit"
    assert vi["parser"]["mode"] == "authoritative"
    assert vi["debug"]["generic_graph_used_for_block_diagram"] is False
    assert vi["summary"]["block_diagram_nodes"] == 1
    assert vi["summary"]["wires"] == 2
    assert vi["summary"]["resolved_wires"] == 2
    assert [item["uid"] for item in vi["objects"] if item["category"] == "node"] == [
        "200"
    ]
    assert [
        (
            next(
                item["uid"]
                for item in vi["objects"]
                if item["id"] == wire["source_terminal_id"]
            ),
            next(
                item["uid"]
                for item in vi["objects"]
                if item["id"] == wire["target_terminal_ids"][0]
            ),
        )
        for wire in vi["wires"]
    ] == [("110", "210"), ("212", "112")]
