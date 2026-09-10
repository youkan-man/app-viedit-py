from __future__ import annotations

from pathlib import Path

import app.service_graph as service_graph
from app.service_graph import _resolve_primary_main_xml


def test_primary_main_xml_uses_dataset_relative_metadata(store) -> None:
    paths = store.create("vi_to_xml")
    selected = paths.dataset / "z-selected.xml"
    selected.write_text('<RSRC FormatVersion="3" Type="LVIN"/>', encoding="utf-8")
    wrong = paths.root / "z-selected.xml"
    wrong.write_text('<RSRC FormatVersion="3" Type="LVIN"/>', encoding="utf-8")
    metadata = store.load(paths)
    metadata["main_xml"] = "z-selected.xml"
    metadata["artifacts"] = {"main_xml": "dataset/not-selected.xml"}
    store.save(paths, metadata)

    assert _resolve_primary_main_xml(paths, store.load(paths)) == selected


def test_primary_main_xml_falls_back_to_root_relative_artifact(store) -> None:
    paths = store.create("dataset_to_vi")
    selected = paths.dataset / "nested" / "selected.xml"
    selected.parent.mkdir()
    selected.write_text('<RSRC FormatVersion="3" Type="LVIN"/>', encoding="utf-8")
    metadata = store.load(paths)
    metadata["main_xml"] = "missing.xml"
    metadata["artifacts"] = {"main_xml": "dataset/nested/selected.xml"}
    store.save(paths, metadata)

    assert _resolve_primary_main_xml(paths, store.load(paths)) == selected


def test_semantic_parser_is_cached_until_dataset_fingerprint_changes(
    service,
    store,
    monkeypatch,
) -> None:
    paths = store.create("xml_to_vi")
    main = paths.dataset / "selected.xml"
    main.write_text('<RSRC FormatVersion="3" Type="LVIN"/>', encoding="utf-8")
    auxiliary = paths.dataset / "selected_FPHb.xml"
    auxiliary.write_text("<SL__rootObject/>", encoding="utf-8")
    metadata = store.load(paths)
    metadata["main_xml"] = "selected.xml"
    store.save(paths, metadata)

    calls: list[Path | None] = []

    def fake_builder(dataset, model, fallback, *, main_xml=None):
        calls.append(main_xml)
        return {
            "version": 4,
            "objects": [],
            "wires": [],
            "nets": [],
            "summary": {},
            "surfaces": {"front-panel": [], "block-diagram": []},
            "hierarchy": {"roots": [], "containers": [], "children_by_parent": {}},
            "warnings": [],
            "parser": {"name": "test", "mode": "authoritative"},
            "integrity": {"version": 1},
        }

    monkeypatch.setattr(service_graph, "build_authoritative_semantic_vi", fake_builder)

    first = service.component_model_summary(paths)
    second = service.component_model_summary(paths)

    assert calls == [main]
    assert first["primary_main_xml"] == "selected.xml"
    assert second["primary_main_xml"] == "selected.xml"
    assert first["vi"] == second["vi"]
    assert first["vi"] is not second["vi"]

    auxiliary.write_text("<SL__rootObject><changed/></SL__rootObject>", encoding="utf-8")
    third = service.component_model_summary(paths)

    assert calls == [main, main]
    assert third["vi"]["version"] == 4


def test_graph_invalidation_clears_semantic_cache(service, store, monkeypatch) -> None:
    paths = store.create("xml_to_vi")
    main = paths.dataset / "selected.xml"
    main.write_text('<RSRC FormatVersion="3" Type="LVIN"/>', encoding="utf-8")
    metadata = store.load(paths)
    metadata["main_xml"] = "selected.xml"
    store.save(paths, metadata)

    calls = 0

    def fake_builder(dataset, model, fallback, *, main_xml=None):
        nonlocal calls
        calls += 1
        return {
            "version": 4,
            "objects": [],
            "wires": [],
            "nets": [],
            "summary": {},
            "surfaces": {"front-panel": [], "block-diagram": []},
            "hierarchy": {"roots": [], "containers": [], "children_by_parent": {}},
            "warnings": [],
            "integrity": {"version": 1},
        }

    monkeypatch.setattr(service_graph, "build_authoritative_semantic_vi", fake_builder)
    service.component_model_summary(paths)
    service.invalidate_component_model(paths)
    service.component_model_summary(paths)

    assert calls == 2
