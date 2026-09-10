from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lvkit.extractor import extract_vi_xml  # noqa: E402

from app.component_model import DatasetComponentModel  # noqa: E402
from app.lvkit_semantic_runtime import build_authoritative_semantic_vi  # noqa: E402
from app.model_graph import build_model_graph  # noqa: E402
from app.semantic_enrichment import enrich_semantic_vi  # noqa: E402
from app.semantic_vi import build_semantic_vi  # noqa: E402

SOURCE_COMMIT = "24ee88b54793d3c2a36833839f5e99a6eb5b9404"
SOURCE_URL = (
    "https://raw.githubusercontent.com/JKISoftware/JKI-EasyXML/"
    f"{SOURCE_COMMIT}/Source/Easy%20Write%20XML%20File.vi"
)


def normalized_path(definition: dict[str, Any]) -> str:
    payload = definition.get("definition") or {}
    value = (
        definition.get("recorded_path")
        or payload.get("typedef_path")
        or definition.get("target_file")
        or ""
    )
    return str(value).replace("\\", "/").lstrip("/").casefold()


def normalized_name(definition: dict[str, Any]) -> str:
    payload = definition.get("definition") or {}
    value = (
        definition.get("name")
        or payload.get("typedef_name")
        or definition.get("recorded_path")
        or definition.get("target_file")
        or ""
    )
    return Path(str(value).replace("\\", "/")).name.casefold()


def signature(definition: dict[str, Any]) -> str:
    payload = definition.get("definition")
    if not payload:
        return ""
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="typedef-collision-audit-") as directory:
        root = Path(directory)
        source = root / "Easy Write XML File.vi"
        request = urllib.request.Request(
            SOURCE_URL,
            headers={"User-Agent": "app-viedit-typedef-audit/1.0"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            source.write_bytes(response.read())
        dataset = root / "dataset"
        dataset.mkdir()
        _, _, main_xml = extract_vi_xml(source, output_dir=dataset, force=True)
        model = DatasetComponentModel.analyze(dataset, max_bytes=128 * 1024 * 1024)
        graph = build_model_graph(model)
        fallback = enrich_semantic_vi(model, graph, build_semantic_vi(model, graph))
        vi = build_authoritative_semantic_vi(
            dataset,
            model,
            fallback,
            main_xml=main_xml,
        )

    objects = {item["id"]: item for item in vi.get("objects", [])}
    definitions = vi.get("type_definitions", [])
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for definition in definitions:
        groups[(normalized_name(definition), normalized_path(definition))].append(definition)
        by_name[normalized_name(definition)].append(definition)

    duplicate_groups = []
    for (name, path), items in groups.items():
        if len(items) < 2:
            continue
        duplicate_groups.append(
            {
                "name": name,
                "path": path,
                "definitions": [
                    {
                        "id": item.get("id"),
                        "kind": item.get("kind"),
                        "source": item.get("source"),
                        "recorded_path": item.get("recorded_path"),
                        "target_file": item.get("target_file"),
                        "available": item.get("available"),
                        "signature": signature(item),
                        "payload_kind": (item.get("definition") or {}).get("kind"),
                        "payload_name": (item.get("definition") or {}).get("name"),
                        "typedef_name": (item.get("definition") or {}).get("typedef_name"),
                        "typedef_path": (item.get("definition") or {}).get("typedef_path"),
                        "source_object_ids": item.get("source_object_ids") or [],
                        "source_objects": [
                            {
                                "id": object_id,
                                "name": objects.get(object_id, {}).get("name"),
                                "category": objects.get(object_id, {}).get("category"),
                                "kind": objects.get(object_id, {}).get("kind"),
                                "data_type": objects.get(object_id, {}).get("data_type"),
                            }
                            for object_id in item.get("source_object_ids") or []
                        ],
                    }
                    for item in items
                ],
            }
        )

    ambiguous_names = []
    for name, items in by_name.items():
        paths = sorted({normalized_path(item) for item in items if normalized_path(item)})
        signatures = sorted({signature(item) for item in items if signature(item)})
        if len(paths) > 1 or len(signatures) > 1:
            ambiguous_names.append(
                {
                    "name": name,
                    "paths": paths,
                    "signatures": signatures,
                    "ids": [item.get("id") for item in items],
                }
            )

    payload = {
        "source": {
            "repository": "JKISoftware/JKI-EasyXML",
            "commit": SOURCE_COMMIT,
            "path": "Source/Easy Write XML File.vi",
        },
        "integrity": vi.get("integrity"),
        "definition_count": len(definitions),
        "duplicate_groups": duplicate_groups,
        "ambiguous_names": ambiguous_names,
        "unattached": [
            item.get("id")
            for item in definitions
            if not item.get("source_object_ids")
        ],
    }
    print(
        "TYPEDEF_COLLISION_AUDIT_JSON="
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )
    print("TYPEDEF_COLLISION_AUDIT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
