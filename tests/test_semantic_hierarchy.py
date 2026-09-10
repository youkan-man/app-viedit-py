from __future__ import annotations

from app.component_model import DatasetComponentModel
from app.model_graph import build_model_graph
from app.semantic_enrichment import enrich_semantic_vi
from app.semantic_vi import build_semantic_vi


def _write_cluster_vi(tmp_path) -> None:
    (tmp_path / "cluster_FPHb.xml").write_text(
        """
<SL__rootObject>
  <SL__object>
    <SL__class>fPDCO</SL__class><SL__uid>20</SL__uid>
    <name>"Settings"</name><objFlags>0</objFlags><terminal>120</terminal>
    <ddo class="stdClust" uid="1020">
      <bounds>(100, 200, 300, 500)</bounds>
      <objectList>
        <SL__object>
          <SL__class>fPDCO</SL__class><SL__uid>21</SL__uid>
          <name>"Gain"</name><objFlags>0</objFlags><terminal>121</terminal>
          <ddo class="stdNum" uid="1021">
            <bounds>(30, 20, 70, 120)</bounds>
          </ddo>
        </SL__object>
        <SL__object>
          <SL__class>fPDCO</SL__class><SL__uid>22</SL__uid>
          <name>"Enabled"</name><objFlags>0</objFlags><terminal>122</terminal>
          <ddo class="stdBool" uid="1022">
            <bounds>(90, 20, 126, 72)</bounds>
          </ddo>
        </SL__object>
      </objectList>
    </ddo>
  </SL__object>
</SL__rootObject>
""".strip(),
        encoding="utf-8",
    )


def _analyze(tmp_path):
    _write_cluster_vi(tmp_path)
    model = DatasetComponentModel.analyze(tmp_path, max_bytes=4 * 1024 * 1024)
    graph = build_model_graph(model)
    semantic = build_semantic_vi(model, graph)
    return model, graph, enrich_semantic_vi(model, graph, semantic)


def test_cluster_members_remain_semantic_objects(tmp_path) -> None:
    _, _, vi = _analyze(tmp_path)
    by_name = {item["name"]: item for item in vi["objects"]}

    cluster = by_name["Settings"]
    gain = by_name["Gain"]
    enabled = by_name["Enabled"]

    assert cluster["data_type"] == "cluster"
    assert cluster["visual_kind"] == "cluster"
    assert cluster["clip_children"] is True
    assert cluster["child_object_ids"] == [gain["id"], enabled["id"]]
    assert gain["parent_object_id"] == cluster["id"]
    assert enabled["parent_object_id"] == cluster["id"]
    assert gain["nesting_depth"] == 1
    assert enabled["nesting_depth"] == 1
    assert vi["summary"]["clusters"] == 1
    assert vi["summary"]["cluster_members"] == 2
    assert vi["hierarchy"]["children_by_parent"][cluster["id"]] == [
        gain["id"],
        enabled["id"],
    ]


def test_relative_cluster_member_bounds_are_projected_to_panel_space(tmp_path) -> None:
    _, _, vi = _analyze(tmp_path)
    by_name = {item["name"]: item for item in vi["objects"]}
    cluster = by_name["Settings"]
    gain = by_name["Gain"]

    assert cluster["bounds"]["x"] == 200
    assert cluster["bounds"]["y"] == 100
    assert gain["bounds"]["source_coordinate_space"] == "parent-relative"
    assert gain["bounds"]["relative_to_object_id"] == cluster["id"]
    assert gain["bounds"]["raw_x"] == 20
    assert gain["bounds"]["raw_y"] == 30
    assert gain["bounds"]["x"] == 220
    assert gain["bounds"]["y"] == 130


def test_service_payload_contains_enriched_cluster_hierarchy(service, store) -> None:
    paths = store.create("xml_to_vi")
    _write_cluster_vi(paths.dataset)

    payload = service.component_model_summary(paths)

    assert payload["vi"]["version"] == 4
    assert payload["vi"]["integrity"]["version"] == 1
    assert payload["vi"]["summary"]["clusters"] == 1
    assert payload["vi"]["summary"]["cluster_members"] == 2
    cluster = next(
        item for item in payload["vi"]["objects"] if item["data_type"] == "cluster"
    )
    assert len(cluster["child_object_ids"]) == 2
