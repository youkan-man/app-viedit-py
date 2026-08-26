from __future__ import annotations


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


def test_component_service_represents_every_dataset_file(service, store) -> None:
    paths = extracted_job(service, store)
    payload = service.component_model_summary(paths)
    summary = payload["summary"]

    dataset_files = {
        path.relative_to(paths.dataset).as_posix()
        for path in paths.dataset.rglob("*")
        if path.is_file()
    }
    modeled_files = {file["path"] for file in payload["files"]}

    assert modeled_files == dataset_files
    assert summary["dataset_files"] == len(dataset_files)
    assert summary["xml_files"] == 2
    assert summary["opaque_files"] == len(dataset_files) - 2
    assert summary["opaque_bytes"] > 0

    binary_listing = service.list_components(paths, kind="binary")
    assert any(item["file"] == "fake.bin" for item in binary_listing["items"])
    binary = next(item for item in binary_listing["items"] if item["file"] == "fake.bin")
    detail = service.component_detail(paths, binary["id"])
    properties = {prop["name"]: prop for prop in detail["properties"]}
    assert properties["size"]["parsed"] == len(b"FAKE-BLOCK")
    assert properties["sha256"]["editable"] is False
    assert properties["header_hex"]["binary"] is True


def test_xml_file_references_resolve_to_xml_and_binary_file_components(service, store) -> None:
    paths = extracted_job(service, store)
    model = service._load_component_model(paths)

    file_relations = [relation for relation in model.relationships if relation["type"] == "file"]
    assert any(
        relation["target_file"] == "diagram.xml"
        and relation["resolved"]
        and relation["target_component_id"]
        for relation in file_relations
    )
    assert any(
        relation["target_file"] == "fake.bin"
        and relation["resolved"]
        and relation["target_component_id"]
        for relation in file_relations
    )
