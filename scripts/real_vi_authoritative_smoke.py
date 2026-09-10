from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.component_model import DatasetComponentModel  # noqa: E402
from app.lvkit_semantic_runtime import build_authoritative_semantic_vi  # noqa: E402
from app.model_graph import build_model_graph  # noqa: E402
from app.semantic_enrichment import enrich_semantic_vi  # noqa: E402
from app.semantic_vi import build_semantic_vi  # noqa: E402
from lvkit.extractor import extract_vi_xml  # noqa: E402
from lvkit.parser import parse_vi  # noqa: E402

SOURCE_REPOSITORY = "JKISoftware/JKI-EasyXML"
SOURCE_COMMIT = "24ee88b54793d3c2a36833839f5e99a6eb5b9404"
SOURCE_PATH = "Build.vi"
SOURCE_URL = (
    "https://raw.githubusercontent.com/"
    f"{SOURCE_REPOSITORY}/{SOURCE_COMMIT}/{SOURCE_PATH}"
)
EXPECTED_SIZE = 14109


def download_real_vi(destination: Path) -> dict[str, object]:
    request = urllib.request.Request(
        SOURCE_URL,
        headers={"User-Agent": "app-viedit-py-sandbox-smoke/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = response.read()
    destination.write_bytes(payload)
    return {
        "repository": SOURCE_REPOSITORY,
        "commit": SOURCE_COMMIT,
        "path": SOURCE_PATH,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="real-vi-authoritative-") as directory:
        root = Path(directory)
        source = root / SOURCE_PATH
        source_info = download_real_vi(source)
        require(
            source_info["bytes"] == EXPECTED_SIZE,
            f"unexpected source size: {source_info['bytes']}",
            failures,
        )

        dataset = root / "dataset"
        dataset.mkdir()
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
        model = DatasetComponentModel.analyze(
            dataset,
            max_bytes=64 * 1024 * 1024,
        )
        generic_graph = build_model_graph(model)
        fallback = enrich_semantic_vi(
            model,
            generic_graph,
            build_semantic_vi(model, generic_graph),
        )
        vi = build_authoritative_semantic_vi(
            dataset,
            model,
            fallback,
            main_xml=main_xml,
        )

        objects = {item["id"]: item for item in vi["objects"]}
        block_nodes = [
            item
            for item in vi["objects"]
            if item.get("surface") == "block-diagram"
            and item.get("category") == "node"
        ]
        terminals = [
            item for item in vi["objects"] if item.get("category") == "terminal"
        ]
        wires = vi["wires"]
        exact_endpoints = []
        bad_directions = []
        bad_membership = []
        routed_wire_count = 0
        for wire in wires:
            source_terminal = objects.get(wire.get("source_terminal_id"))
            target_ids = wire.get("target_terminal_ids") or []
            target_terminals = [objects.get(item) for item in target_ids]
            exact_endpoints.append(
                {
                    "source": source_terminal.get("uid") if source_terminal else None,
                    "targets": [
                        target.get("uid") if target else None
                        for target in target_terminals
                    ],
                    "confidence": wire.get("direction_confidence"),
                    "route_points": len(wire.get("route_points") or []),
                }
            )
            if wire.get("route_points"):
                routed_wire_count += 1
            if not source_terminal or source_terminal.get("direction") != "source":
                bad_directions.append(wire["id"])
            if not target_terminals or any(
                target is None or target.get("direction") != "sink"
                for target in target_terminals
            ):
                bad_directions.append(wire["id"])
            if wire.get("direction_confidence") != "signal-term-list":
                bad_directions.append(wire["id"])
            if any(
                terminal_id not in objects
                for terminal_id in wire.get("terminal_ids") or []
            ):
                bad_membership.append(wire["id"])

        parser_node_count = len(parsed.block_diagram.nodes)
        parser_constant_count = len(parsed.block_diagram.constants)
        parser_wire_count = len(parsed.block_diagram.wires)
        parser_terminal_count = len(parsed.block_diagram.terminal_info)
        require(
            vi["parser"]["mode"] == "authoritative",
            "real VI did not use authoritative parser mode",
            failures,
        )
        require(
            vi["debug"]["generic_graph_used_for_block_diagram"] is False,
            "generic XML graph leaked into real VI block diagram",
            failures,
        )
        require(parser_node_count > 0, "real VI parser returned no nodes", failures)
        require(parser_wire_count > 0, "real VI parser returned no wire branches", failures)
        require(block_nodes, "editor projection returned no block diagram nodes", failures)
        require(terminals, "editor projection returned no terminals", failures)
        require(wires, "editor projection returned no wires", failures)
        require(
            len(wires) == parser_wire_count,
            f"wire branch loss: parser={parser_wire_count}, editor={len(wires)}",
            failures,
        )
        require(
            vi["summary"]["resolved_wires"] == len(wires),
            "real VI contains unresolved projected wires",
            failures,
        )
        require(not bad_directions, f"bad wire directions: {bad_directions[:8]}", failures)
        require(not bad_membership, f"missing wire terminals: {bad_membership[:8]}", failures)
        require(routed_wire_count > 0, "no real VI wire retained native route points", failures)
        require(
            all(item.get("semantic_source") == "lvkit" for item in block_nodes),
            "non-parser objects were promoted to block diagram components",
            failures,
        )

        type_definitions = vi.get("type_definitions") or []
        summary = {
            "source": source_info,
            "extracted": {
                "block_diagram": bd_xml.name,
                "front_panel": fp_xml.name if fp_xml else None,
                "main_xml": main_xml.name if main_xml else None,
            },
            "parser": {
                "nodes": parser_node_count,
                "constants": parser_constant_count,
                "wire_branches": parser_wire_count,
                "terminals": parser_terminal_count,
            },
            "editor": {
                "nodes": len(block_nodes),
                "wires": len(wires),
                "terminals": len(terminals),
                "routed_wires": routed_wire_count,
                "type_definitions": len(type_definitions),
                "node_kinds": sorted(
                    {
                        item.get("kind") or "unknown"
                        for item in block_nodes
                    }
                ),
            },
            "sample_wire_endpoints": exact_endpoints[:8],
            "type_definition_samples": [
                {
                    "name": item.get("name"),
                    "kind": item.get("kind"),
                    "recorded_path": item.get("recorded_path"),
                    "has_definition": bool(item.get("definition")),
                }
                for item in type_definitions[:8]
            ],
            "failures": failures,
        }
        print(
            "REAL_VI_AUTHORITATIVE_JSON="
            + json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
        )
        if failures:
            print("REAL_VI_AUTHORITATIVE_TEST_FAILED")
            return 1
        print("REAL_VI_AUTHORITATIVE_TEST_OK")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
