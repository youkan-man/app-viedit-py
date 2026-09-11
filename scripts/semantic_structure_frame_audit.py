from __future__ import annotations

import dataclasses
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lvkit.extractor import extract_vi_xml  # noqa: E402
from lvkit.parser import parse_vi  # noqa: E402

from app.component_model import DatasetComponentModel  # noqa: E402
from app.lvkit_semantic_runtime import build_authoritative_semantic_vi  # noqa: E402
from app.model_graph import build_model_graph  # noqa: E402
from app.semantic_enrichment import enrich_semantic_vi  # noqa: E402
from app.semantic_vi import build_semantic_vi  # noqa: E402

SOURCE_COMMIT = "24ee88b54793d3c2a36833839f5e99a6eb5b9404"
SOURCE_BASE = (
    "https://raw.githubusercontent.com/JKISoftware/JKI-EasyXML/"
    f"{SOURCE_COMMIT}/"
)
REAL_VIS = (
    ("Build.vi", "Build.vi"),
    ("Easy Generate XML.vi", "Source/Easy%20Generate%20XML.vi"),
    ("Easy Parse XML.vi", "Source/Easy%20Parse%20XML.vi"),
    ("Easy Read XML File.vi", "Source/Easy%20Read%20XML%20File.vi"),
    ("Easy Write XML File.vi", "Source/Easy%20Write%20XML%20File.vi"),
)
ARTIFACTS = Path(
    os.getenv("BUILD_ARTIFACT_DIR", str(ROOT / "artifacts" / "structure-frame-audit"))
)


def download(relative: str, destination: Path) -> None:
    request = urllib.request.Request(
        SOURCE_BASE + relative,
        headers={"User-Agent": "app-viedit-structure-frame-audit/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        destination.write_bytes(response.read())


def safe(value: object, depth: int = 0) -> Any:
    if depth > 6:
        return "…"
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if dataclasses.is_dataclass(value):
        return {
            field.name: safe(getattr(value, field.name), depth + 1)
            for field in dataclasses.fields(value)
        }
    if isinstance(value, dict):
        return {str(key): safe(item, depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [safe(item, depth + 1) for item in value]
    if hasattr(value, "value"):
        return safe(value.value, depth + 1)
    return str(value)


def frame_label(frame: object, index: int) -> str:
    if bool(getattr(frame, "is_default", False)):
        return "Default"
    for attribute in ("selector_value", "event_label", "label", "name"):
        value = getattr(frame, attribute, None)
        if value not in (None, ""):
            return str(value)
    return str(getattr(frame, "index", index))


def structure_collections(block: object) -> tuple[tuple[str, list[object]], ...]:
    return tuple(
        (name, list(getattr(block, name, ()) or ()))
        for name in (
            "case_structures",
            "flat_sequences",
            "disable_structures",
            "event_structures",
        )
    )


def selected_frame_hint(structure: object) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for name in dir(structure):
        if name.startswith("_"):
            continue
        key = name.lower()
        if not any(token in key for token in ("frame", "active", "display", "select")):
            continue
        try:
            value = getattr(structure, name)
        except Exception:
            continue
        if callable(value):
            continue
        payload[name] = safe(value)
    return payload


def audit_vi(source: Path, dataset: Path) -> dict[str, Any]:
    bd_xml, fp_xml, main_xml = extract_vi_xml(
        source,
        output_dir=dataset,
        force=True,
    )
    parsed = parse_vi(
        bd_xml=bd_xml,
        fp_xml=fp_xml,
        main_xml=main_xml,
        layout=True,
    )
    model = DatasetComponentModel.analyze(dataset, max_bytes=128 * 1024 * 1024)
    graph = build_model_graph(model)
    fallback = enrich_semantic_vi(model, graph, build_semantic_vi(model, graph))
    vi = build_authoritative_semantic_vi(
        dataset,
        model,
        fallback,
        main_xml=main_xml,
    )
    semantic_nodes = {
        str(item.get("uid") or ""): item
        for item in vi.get("objects", [])
        if item.get("surface") == "block-diagram"
        and item.get("category") == "node"
    }

    structures: list[dict[str, Any]] = []
    simultaneous_inactive_nodes = 0
    multi_frame_with_content = 0
    for collection_name, collection in structure_collections(parsed.block_diagram):
        for structure in collection:
            uid = str(getattr(structure, "uid", "") or "")
            frames = list(getattr(structure, "frames", ()) or ())
            frame_records = []
            nonempty_frames = 0
            for index, frame in enumerate(frames):
                node_uids = [
                    str(item)
                    for item in getattr(frame, "inner_node_uids", ()) or ()
                ]
                if node_uids:
                    nonempty_frames += 1
                projected = [node_uid for node_uid in node_uids if node_uid in semantic_nodes]
                frame_records.append(
                    {
                        "uid": str(getattr(frame, "uid", "") or ""),
                        "index": int(getattr(frame, "index", index) or index),
                        "label": frame_label(frame, index),
                        "is_default": bool(getattr(frame, "is_default", False)),
                        "node_uids": node_uids,
                        "projected_node_uids": projected,
                    }
                )
            if nonempty_frames > 1:
                multi_frame_with_content += 1
                simultaneous_inactive_nodes += sum(
                    len(record["projected_node_uids"])
                    for record in frame_records[1:]
                )
            semantic_structure = semantic_nodes.get(uid)
            structures.append(
                {
                    "collection": collection_name,
                    "uid": uid,
                    "semantic_object_id": semantic_structure.get("id")
                    if semantic_structure
                    else None,
                    "semantic_has_frames": bool(
                        semantic_structure
                        and semantic_structure.get("frames")
                    ),
                    "frame_count": len(frames),
                    "nonempty_frame_count": nonempty_frames,
                    "selection_hints": selected_frame_hint(structure),
                    "frames": frame_records,
                }
            )

    return {
        "name": source.name,
        "structure_count": len(structures),
        "multi_frame_with_content": multi_frame_with_content,
        "simultaneous_inactive_nodes": simultaneous_inactive_nodes,
        "structures": structures,
    }


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    reports: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="structure-frame-audit-") as directory:
        root = Path(directory)
        for name, relative in REAL_VIS:
            source = root / name
            dataset = root / f"{source.stem}-dataset"
            dataset.mkdir()
            try:
                download(relative, source)
                reports.append(audit_vi(source, dataset))
            except Exception as error:
                reports.append(
                    {
                        "name": name,
                        "error": f"{type(error).__name__}: {error}",
                    }
                )
    payload = {
        "source_commit": SOURCE_COMMIT,
        "reports": reports,
        "total_multi_frame_with_content": sum(
            int(report.get("multi_frame_with_content") or 0)
            for report in reports
        ),
        "total_simultaneous_inactive_nodes": sum(
            int(report.get("simultaneous_inactive_nodes") or 0)
            for report in reports
        ),
    }
    (ARTIFACTS / "semantic-structure-frame-audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "STRUCTURE_FRAME_AUDIT_JSON="
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )
    print("STRUCTURE_FRAME_AUDIT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
