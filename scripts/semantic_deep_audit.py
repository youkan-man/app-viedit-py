from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import urllib.request
from collections import Counter
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

SOURCE_REPOSITORY = "JKISoftware/JKI-EasyXML"
SOURCE_COMMIT = "24ee88b54793d3c2a36833839f5e99a6eb5b9404"
SOURCE_BASE = (
    "https://raw.githubusercontent.com/"
    f"{SOURCE_REPOSITORY}/{SOURCE_COMMIT}/"
)
REAL_VIS = (
    ("Build.vi", "Build.vi"),
    ("Easy Generate XML.vi", "Source/Easy%20Generate%20XML.vi"),
    ("Easy Parse XML.vi", "Source/Easy%20Parse%20XML.vi"),
    ("Easy Read XML File.vi", "Source/Easy%20Read%20XML%20File.vi"),
    ("Easy Write XML File.vi", "Source/Easy%20Write%20XML%20File.vi"),
)
ARTIFACTS = Path(
    os.getenv("BUILD_ARTIFACT_DIR", str(ROOT / "artifacts" / "semantic-deep-audit"))
)


def download(relative: str, destination: Path) -> None:
    request = urllib.request.Request(
        SOURCE_BASE + relative,
        headers={"User-Agent": "app-viedit-semantic-deep-audit/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        destination.write_bytes(response.read())


def definition_key(definition: dict[str, Any]) -> tuple[str, str]:
    name = Path(str(definition.get("name") or "")).name.casefold()
    path = str(definition.get("recorded_path") or "").replace("\\", "/")
    return name, path.lstrip("/").casefold()


def _terminal_snapshot(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {
        "id": item.get("id"),
        "uid": item.get("uid"),
        "name": item.get("name"),
        "direction": item.get("direction"),
        "wire_roles": item.get("wire_roles"),
        "owner_object_id": item.get("owner_object_id"),
        "linked_object_id": item.get("linked_object_id"),
    }


def audit_vi(source: Path, dataset: Path) -> dict[str, Any]:
    started = time.perf_counter()
    bd_xml, fp_xml, main_xml = extract_vi_xml(
        source,
        output_dir=dataset,
        force=True,
    )
    model = DatasetComponentModel.analyze(dataset, max_bytes=128 * 1024 * 1024)
    graph = build_model_graph(model)
    fallback = enrich_semantic_vi(
        model,
        graph,
        build_semantic_vi(model, graph),
    )
    vi = build_authoritative_semantic_vi(
        dataset,
        model,
        fallback,
        main_xml=main_xml,
    )
    elapsed = time.perf_counter() - started

    objects = {item["id"]: item for item in vi.get("objects", [])}
    nodes = [
        item
        for item in objects.values()
        if item.get("surface") == "block-diagram"
        and item.get("category") == "node"
    ]
    terminals = [
        item for item in objects.values() if item.get("category") == "terminal"
    ]
    owner_terminals = [item for item in terminals if item.get("owner_object_id")]
    wires = vi.get("wires", [])
    definitions = vi.get("type_definitions", [])
    definition_counts = Counter(definition_key(item) for item in definitions)
    net_counts = Counter(item.get("net_id") for item in wires)

    direction_mismatches: list[dict[str, Any]] = []
    endpoint_mismatches = []
    for wire in wires:
        source_terminal = objects.get(wire.get("source_terminal_id"))
        target_terminals = [
            objects.get(item) for item in wire.get("target_terminal_ids") or []
        ]
        source_ok = source_terminal is not None and source_terminal.get("direction") in {
            "source",
            "bidirectional",
        }
        targets_ok = bool(target_terminals) and all(
            item is not None and item.get("direction") in {"sink", "bidirectional"}
            for item in target_terminals
        )
        source_roles_ok = source_terminal is not None and "source" in (
            source_terminal.get("wire_roles") or []
        )
        target_roles_ok = bool(target_terminals) and all(
            item is not None and "sink" in (item.get("wire_roles") or [])
            for item in target_terminals
        )
        if not (source_ok and targets_ok and source_roles_ok and target_roles_ok):
            direction_mismatches.append(
                {
                    "wire_id": wire.get("id"),
                    "native_uid": wire.get("native_uid"),
                    "source": _terminal_snapshot(source_terminal),
                    "targets": [
                        _terminal_snapshot(item) for item in target_terminals
                    ],
                }
            )
        expected_objects = [
            source_terminal.get("linked_object_id")
            or source_terminal.get("owner_object_id")
            if source_terminal
            else None,
            *[
                item.get("linked_object_id") or item.get("owner_object_id")
                for item in target_terminals
                if item
            ],
        ]
        expected_objects = list(dict.fromkeys(
            item for item in expected_objects if item
        ))
        if wire.get("endpoint_object_ids") != expected_objects:
            endpoint_mismatches.append(wire["id"])

    bidirectional = [
        item for item in terminals if item.get("direction") == "bidirectional"
    ]
    invalid_bidirectional = [
        item["id"]
        for item in bidirectional
        if set(item.get("wire_roles") or []) != {"source", "sink"}
    ]

    metrics = {
        "name": source.name,
        "seconds": round(elapsed, 3),
        "source_bytes": source.stat().st_size,
        "extracted": {
            "block_diagram": bd_xml.name,
            "front_panel": fp_xml.name if fp_xml else None,
            "main_xml": main_xml.name if main_xml else None,
        },
        "parser": vi.get("parser"),
        "integrity": vi.get("integrity"),
        "counts": {
            "nodes": len(nodes),
            "terminals": len(terminals),
            "bidirectional_terminals": len(bidirectional),
            "owner_terminals": len(owner_terminals),
            "wires": len(wires),
            "wire_nets": len(vi.get("nets", [])),
            "type_definitions": len(definitions),
        },
        "node_kinds": dict(sorted(Counter(item.get("kind") for item in nodes).items())),
        "missing_component_ids": sum(not item.get("component_id") for item in nodes),
        "missing_node_bounds": sum(not item.get("bounds") for item in nodes),
        "readonly_positioned_nodes": sum(
            bool(item.get("bounds")) and not item.get("movable") for item in nodes
        ),
        "owner_terminals_not_relative": sum(
            not (item.get("bounds") or {}).get("relative_to_object_id")
            for item in owner_terminals
        ),
        "wires_without_route": sum(not item.get("route_points") for item in wires),
        "wire_direction_mismatches": direction_mismatches,
        "invalid_bidirectional_terminals": invalid_bidirectional,
        "endpoint_object_mismatches": endpoint_mismatches,
        "branching_nets": {
            str(net_id): count
            for net_id, count in net_counts.items()
            if net_id and count > 1
        },
        "unattached_type_definitions": sum(
            not item.get("source_object_ids") for item in definitions
        ),
        "duplicate_type_definition_keys": {
            str(key): count
            for key, count in definition_counts.items()
            if count > 1
        },
        "typedef_refs_misclassified_as_cluster": sum(
            item.get("data_type") == "cluster"
            and (item.get("type") or {}).get("kind") == "typedef_ref"
            and not (item.get("type") or {}).get("fields")
            and "cluster" not in str((item.get("type") or {}).get("name") or "").lower()
            for item in objects.values()
        ),
        "warnings": vi.get("warnings", []),
        "failures": [],
    }

    failures = metrics["failures"]
    if vi.get("parser", {}).get("mode") != "authoritative":
        failures.append("authoritative parser mode was not used")
    if vi.get("debug", {}).get("generic_graph_used_for_block_diagram") is not False:
        failures.append("generic XML graph was used for block diagram")
    if not nodes:
        failures.append("no block diagram nodes were projected")
    if not wires:
        failures.append("no wire branches were projected")
    if metrics["owner_terminals_not_relative"]:
        failures.append("owned terminals do not follow their nodes")
    if metrics["wire_direction_mismatches"]:
        failures.append("wire source/sink role mismatch")
    if metrics["invalid_bidirectional_terminals"]:
        failures.append("bidirectional terminal does not have both wire roles")
    if metrics["endpoint_object_mismatches"]:
        failures.append("wire endpoint objects do not match terminals")
    if metrics["duplicate_type_definition_keys"]:
        failures.append("duplicate type definitions remain")
    if metrics["typedef_refs_misclassified_as_cluster"]:
        failures.append("scalar typedef references were classified as clusters")
    if vi.get("summary", {}).get("wires") != len(wires):
        failures.append("wire summary is stale")
    if vi.get("summary", {}).get("wire_nets") != len(vi.get("nets", [])):
        failures.append("wire-net summary is stale")
    if vi.get("summary", {}).get("bidirectional_terminals") != len(bidirectional):
        failures.append("bidirectional-terminal summary is stale")
    if int(vi.get("integrity", {}).get("version") or 0) < 3:
        failures.append("semantic integrity v3 was not applied")
    return metrics


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    reports: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="semantic-deep-audit-") as directory:
        root = Path(directory)
        for name, relative in REAL_VIS:
            source = root / name
            dataset = root / f"{source.stem}-dataset"
            dataset.mkdir()
            try:
                download(relative, source)
                reports.append(audit_vi(source, dataset))
            except Exception as error:  # keep auditing the remaining real VIs
                reports.append(
                    {
                        "name": name,
                        "failures": [f"{type(error).__name__}: {error}"],
                    }
                )

    payload = {
        "repository": SOURCE_REPOSITORY,
        "commit": SOURCE_COMMIT,
        "reports": reports,
        "failures": [
            {"name": report.get("name"), "failures": report.get("failures")}
            for report in reports
            if report.get("failures")
        ],
    }
    output = ARTIFACTS / "semantic-deep-audit.json"
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "SEMANTIC_DEEP_AUDIT_JSON="
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )
    if payload["failures"]:
        print("SEMANTIC_DEEP_AUDIT_FAILED")
        return 1
    print("SEMANTIC_DEEP_AUDIT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
