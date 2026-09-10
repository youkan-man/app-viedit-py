from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, Route, sync_playwright

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
SOURCE_PATH = "Build.vi"
SOURCE_URL = (
    "https://raw.githubusercontent.com/"
    f"{SOURCE_REPOSITORY}/{SOURCE_COMMIT}/{SOURCE_PATH}"
)
PORT = int(os.getenv("VI_REAL_READABILITY_PORT", "8089"))
BASE_URL = f"http://127.0.0.1:{PORT}"
ARTIFACTS = Path(
    os.getenv(
        "BUILD_ARTIFACT_DIR",
        str(ROOT / "artifacts" / "real-vi-readability"),
    )
)
VIEWPORTS = (
    {"width": 1365, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1920, "height": 1080},
)


def wait_for_server(process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output, _ = process.communicate(timeout=3)
            raise RuntimeError(f"application exited before ready:\n{output}")
        try:
            with urllib.request.urlopen(f"{BASE_URL}/api/health", timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("application did not become ready")


def download_vi(destination: Path) -> None:
    request = urllib.request.Request(
        SOURCE_URL,
        headers={"User-Agent": "app-viedit-real-readability/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        destination.write_bytes(response.read())


def build_payload() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="real-vi-readability-") as directory:
        root = Path(directory)
        source = root / SOURCE_PATH
        dataset = root / "dataset"
        dataset.mkdir()
        download_vi(source)
        _, _, main_xml = extract_vi_xml(source, output_dir=dataset, force=True)
        model = DatasetComponentModel.analyze(
            dataset,
            max_bytes=128 * 1024 * 1024,
        )
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
        return {
            "summary": {"failed_files": 0},
            "warnings": list(vi.get("warnings") or []),
            "graph": copy.deepcopy(graph),
            "vi": copy.deepcopy(vi),
        }


def job() -> dict[str, Any]:
    return {
        "job_id": "real-readability",
        "status": "ready",
        "component_modified_at": "2026-09-10T12:20:00Z",
        "xml_modified_at": "2026-09-10T12:20:00Z",
        "source": {"name": SOURCE_PATH},
        "files": [],
    }


def route_payload(page: Page, payload: dict[str, Any]) -> None:
    def model_route(route: Route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload, ensure_ascii=False),
        )

    page.route("**/api/jobs/real-readability/model*", model_route)


def require(condition: bool, message: str, diagnostics: dict[str, Any]) -> None:
    if not condition:
        diagnostics["failures"].append(message)


def choose_node(vi: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        item
        for item in vi.get("objects", [])
        if item.get("surface") == "block-diagram"
        and item.get("category") == "node"
        and item.get("wire_ids")
    ]
    if not candidates:
        raise AssertionError("real VI has no connected block-diagram node")
    return max(
        candidates,
        key=lambda item: (
            len(item.get("wire_ids") or []),
            int(item.get("kind") == "subvi"),
            str(item.get("name") or ""),
        ),
    )


def choose_branching_wire(vi: dict[str, Any]) -> dict[str, Any] | None:
    wires = vi.get("wires", []) or []
    counts: dict[str, int] = {}
    for wire in wires:
        net_id = str(wire.get("net_id") or "")
        if net_id:
            counts[net_id] = counts.get(net_id, 0) + 1
    return next(
        (
            wire
            for wire in wires
            if wire.get("net_id") and counts.get(str(wire["net_id"]), 0) > 1
        ),
        None,
    )


def load(page: Page) -> None:
    value = job()
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_function("() => Boolean(window.viPages && window.viModelGraph)")
    page.evaluate("job => window.viPages.setJob(job, {openModel: true})", value)
    page.evaluate("async job => { await window.viModelGraph.setJob(job); }", value)
    page.wait_for_function(
        "() => Boolean(window.VIReadability?.ready && window.VICanvasDensity?.ready && window.VISemanticEditor?.S?.vi)"
    )
    page.wait_for_timeout(300)


def audit_viewport(
    browser,
    size: dict[str, int],
    payload: dict[str, Any],
    diagnostics: dict[str, Any],
) -> None:
    context = browser.new_context(viewport=size)
    page = context.new_page()
    key = f"{size['width']}x{size['height']}"
    page.on(
        "console",
        lambda message: diagnostics["console_errors"].append(
            f"{key}: {message.text}"
        )
        if message.type == "error"
        else None,
    )
    page.on(
        "pageerror",
        lambda error: diagnostics["page_errors"].append(f"{key}: {error}"),
    )
    route_payload(page, payload)
    load(page)

    page.locator('[data-vi-surface="block-diagram"]').click()
    page.wait_for_function(
        "() => document.querySelectorAll('#model-graph-svg [data-object-id]').length > 0"
    )
    page.evaluate("() => window.VICanvasDensity.fit('readable')")
    page.wait_for_timeout(220)
    page.evaluate("() => window.VIReadability.decorate()")
    block = page.evaluate(
        """() => ({
          lod: document.querySelector('#vi-editor-shell')?.dataset.viLod,
          scale: window.VICanvasDensity.runtime.currentScale,
          metrics: window.VIReadability.measureLabelCollisions(),
          suppressed: Number(document.querySelector('#model-graph-svg').dataset.suppressedLabelCount || 0),
          algorithmOverlaps: Number(document.querySelector('#model-graph-svg').dataset.labelOverlapCount || 0),
          objects: document.querySelectorAll('#model-graph-svg [data-object-id]').length,
          wires: document.querySelectorAll('#model-graph-svg [data-wire-id]').length,
          frameBadges: [...document.querySelectorAll('.vi-structure-frame-badge')].map(node => node.textContent.trim()).filter(Boolean),
          tunnels: document.querySelectorAll('.is-structure-tunnel').length,
          bidirectionalTunnels: document.querySelectorAll('.is-structure-tunnel[data-tunnel-direction="bidirectional"]').length,
        })"""
    )
    require(block["objects"] > 0, f"{key}: real block diagram has no objects", diagnostics)
    require(block["wires"] > 0, f"{key}: real block diagram has no wires", diagnostics)
    require(block["metrics"]["overlaps"] <= 4, f"{key}: real diagram retains excessive visible label collisions", diagnostics)

    selected_node = choose_node(payload["vi"])
    page.evaluate(
        "id => window.VISemanticEditor.select(id, false)",
        selected_node["id"],
    )
    page.wait_for_timeout(140)
    page.evaluate("() => window.VIReadability.decorate()")
    selection = page.evaluate(
        """id => {
          const node = document.querySelector(`[data-object-id="${CSS.escape(id)}"]`);
          const selectedLabel = node?.querySelector('.vi-object-label');
          return {
            primary: node?.classList.contains('is-readability-primary'),
            relatedObjects: document.querySelectorAll('.vi-object.is-readability-related').length,
            relatedWires: document.querySelectorAll('.vi-wire-group.is-readability-related,.vi-wire-group.is-readability-primary').length,
            mutedObjects: document.querySelectorAll('.vi-object.is-readability-muted').length,
            selectedLabelSuppressed: Boolean(selectedLabel?.classList.contains('is-label-suppressed')),
          };
        }""",
        selected_node["id"],
    )
    require(selection["primary"], f"{key}: selected real node is not primary", diagnostics)
    require(selection["relatedWires"] > 0, f"{key}: selected real node exposes no related wire", diagnostics)
    require(not selection["selectedLabelSuppressed"], f"{key}: selected real node label was suppressed", diagnostics)

    branching = choose_branching_wire(payload["vi"])
    network: dict[str, Any] | None = None
    if branching:
        page.evaluate(
            "id => window.VISemanticEditor.select(id, false)",
            branching["id"],
        )
        page.wait_for_timeout(120)
        page.evaluate("() => window.VIReadability.decorate()")
        network = page.evaluate(
            """([wireId, netId]) => {
              const groups = [...document.querySelectorAll(`[data-wire-id="${CSS.escape(wireId)}"]`)]
              const siblings = [...document.querySelectorAll('#model-graph-svg [data-wire-id]')]
                .filter(node => node.dataset.netId === netId && node.dataset.wireId !== wireId);
              return {
                primary: groups.length > 0 && groups.every(node => node.classList.contains('is-readability-primary')),
                siblingCount: siblings.length,
                relatedSiblingCount: siblings.filter(node => node.classList.contains('is-readability-related')).length,
              };
            }""",
            [branching["id"], str(branching["net_id"])],
        )
        require(network["primary"], f"{key}: selected real wire is not primary", diagnostics)
        require(network["siblingCount"] > 0, f"{key}: branching real net has no rendered sibling", diagnostics)
        require(
            network["relatedSiblingCount"] == network["siblingCount"],
            f"{key}: not all real net branches are highlighted",
            diagnostics,
        )

    page.evaluate(
        """() => {
          window.VISemanticEditor.S.selected = null;
          window.VISemanticEditor.renderAll(false);
        }"""
    )
    page.locator('[data-vi-surface="front-panel"]').click()
    page.evaluate("() => window.VICanvasDensity.fit('readable')")
    page.wait_for_timeout(220)
    page.evaluate("() => window.VIReadability.decorate()")
    front = page.evaluate(
        """() => ({
          lod: document.querySelector('#vi-editor-shell')?.dataset.viLod,
          scale: window.VICanvasDensity.runtime.currentScale,
          metrics: window.VIReadability.measureLabelCollisions(),
          suppressed: Number(document.querySelector('#model-graph-svg').dataset.suppressedLabelCount || 0),
          objects: document.querySelectorAll('#model-graph-svg [data-object-id]').length,
          clusters: document.querySelectorAll('.is-cluster-container').length,
        })"""
    )
    require(front["objects"] > 0, f"{key}: real front panel has no objects", diagnostics)
    require(front["metrics"]["overlaps"] <= 4, f"{key}: real front panel retains excessive visible label collisions", diagnostics)

    diagnostics["viewports"][key] = {
        "block_diagram": block,
        "selected_node": {
            "id": selected_node["id"],
            "name": selected_node.get("name"),
            **selection,
        },
        "network": network,
        "front_panel": front,
    }
    page.screenshot(
        path=str(ARTIFACTS / f"real-readability-{key}.png"),
        full_page=False,
    )
    context.close()


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    payload = build_payload()
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".sandbox-real-readability-jobs"),
        }
    )
    process = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    diagnostics: dict[str, Any] = {
        "source": {
            "repository": SOURCE_REPOSITORY,
            "commit": SOURCE_COMMIT,
            "path": SOURCE_PATH,
        },
        "semantic": {
            "nodes": payload["vi"].get("summary", {}).get("block_diagram_nodes"),
            "wires": payload["vi"].get("summary", {}).get("wires"),
            "nets": payload["vi"].get("summary", {}).get("wire_nets"),
            "front_panel_objects": payload["vi"].get("summary", {}).get("front_panel_objects"),
        },
        "failures": [],
        "console_errors": [],
        "page_errors": [],
        "viewports": {},
    }
    try:
        wait_for_server(process)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            for size in VIEWPORTS:
                audit_viewport(browser, size, payload, diagnostics)
            browser.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
        if process.stdout:
            output = process.stdout.read()
            if output:
                print("REAL_READABILITY_APPLICATION_LOG=" + output[-4000:].replace("\n", "\\n"))

    (ARTIFACTS / "real-vi-readability.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "REAL_VI_READABILITY_JSON="
        + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
    )
    if diagnostics["failures"] or diagnostics["console_errors"] or diagnostics["page_errors"]:
        print("REAL_VI_READABILITY_TEST_FAILED")
        return 1
    print("REAL_VI_READABILITY_TEST_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
