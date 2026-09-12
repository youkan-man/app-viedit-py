from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, Route, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.semantic_readable_diagram_test import (  # noqa: E402
    ARTIFACTS,
    BASE_URL,
    VIEWPORTS,
    box_contains,
    job,
    load_job,
    require,
    state_fingerprint,
    switch_to_block_diagram,
    wait_for_server,
)
from scripts.semantic_ui_browser_test import make_payload  # noqa: E402

PORT = int(os.getenv("VI_READABLE_DIAGRAM_PORT", "8092"))


def connected_flow_payload(node_count: int = 12) -> dict[str, Any]:
    payload = copy.deepcopy(make_payload())
    vi = payload["vi"]
    template = next(
        item
        for item in vi["objects"]
        if item["surface"] == "block-diagram"
        and item["category"] == "node"
        and item.get("kind") == "add"
    )
    retained = [
        item for item in vi["objects"] if item["surface"] != "block-diagram"
    ]
    nodes: list[dict[str, Any]] = []
    for index in range(node_count):
        node = copy.deepcopy(template)
        node_id = f"flow-node-{index:02d}"
        x = 58 + index * 76
        y = 92 + (index % 2) * 76
        node.update(
            {
                "id": node_id,
                "component_id": node_id,
                "uid": f"flow-{index:02d}",
                "name": f"Flow stage {index + 1}",
                "terminal_ids": [],
                "linked_terminal_ids": [],
                "wire_ids": [],
                "child_object_ids": [],
                "owner_object_id": None,
                "movable": False,
                "resizable": False,
            }
        )
        node["bounds"] = {
            **(node.get("bounds") or {}),
            "x": x,
            "y": y,
            "width": 40,
            "height": 40,
            "source_property_id": None,
        }
        nodes.append(node)

    wires: list[dict[str, Any]] = []
    for index, (source, target) in enumerate(zip(nodes, nodes[1:])):
        source_bounds = source["bounds"]
        target_bounds = target["bounds"]
        source_center = {
            "x": source_bounds["x"] + source_bounds["width"] / 2,
            "y": source_bounds["y"] + source_bounds["height"] / 2,
        }
        target_center = {
            "x": target_bounds["x"] + target_bounds["width"] / 2,
            "y": target_bounds["y"] + target_bounds["height"] / 2,
        }
        middle_x = (source_center["x"] + target_center["x"]) / 2
        wire_id = f"flow-wire-{index:02d}"
        wire = {
            "id": wire_id,
            "name": f"Stage {index + 1} to {index + 2}",
            "data_type": "Numeric",
            "resolved": True,
            "source_terminal_id": None,
            "source_object_id": source["id"],
            "target_terminal_ids": [],
            "target_object_ids": [target["id"]],
            "terminal_ids": [],
            "route_points": [
                source_center,
                {"x": middle_x, "y": source_center["y"]},
                {"x": middle_x, "y": target_center["y"]},
                target_center,
            ],
        }
        source["wire_ids"].append(wire_id)
        target["wire_ids"].append(wire_id)
        wires.append(wire)

    vi["objects"] = retained + nodes
    vi["wires"] = wires
    vi["surfaces"]["block-diagram"] = [node["id"] for node in nodes]
    vi["summary"]["block_diagram_nodes"] = len(nodes)
    vi["summary"]["wires"] = len(wires)
    return payload


def route_payload(page: Page, job_id: str, payload: dict[str, Any]) -> None:
    def route_model(route: Route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload, ensure_ascii=False),
        )

    page.route(f"**/api/jobs/{job_id}/model*", route_model)


def flow_snapshot(page: Page) -> dict[str, Any]:
    return page.evaluate(
        """() => {
          const S = window.VISemanticEditor.S;
          const fit = window.VIComponentFit;
          const viewport = S.el.modelGraphViewport.getBoundingClientRect();
          const scale = Math.min(
            viewport.width / S.box.width,
            viewport.height / S.box.height,
          );
          const records = fit.representativeRecords()
            .slice()
            .sort((first, second) => first.centerX - second.centerX);
          const metrics = fit.readabilityMetrics();
          const content = fit.projectedContentBounds({
            includeWires: true,
            includeLabels: true,
          });
          const source = records[0] || null;
          const sink = records.at(-1) || null;
          return {
            viewport: {width: viewport.width, height: viewport.height},
            box: {...S.box},
            scale,
            mode: S.el.viEditorShell.dataset.viViewMode,
            lod: S.el.viEditorShell.dataset.viLod,
            reason: S.el.viEditorShell.dataset.viFitReason,
            datasetDirectionality: Number(
              S.el.viEditorShell.dataset.viFlowDirectionality || '0',
            ),
            content,
            recordCount: records.length,
            wireCount: S.wires.size,
            renderedWireCount: document.querySelectorAll(
              '#model-graph-svg .vi-wire-group',
            ).length,
            metrics,
            sourceViewportRatio: source
              ? (source.centerX - S.box.x) / S.box.width
              : null,
            sinkViewportRatio: sink
              ? (sink.centerX - S.box.x) / S.box.width
              : null,
            horizontalGapPixels:
              metrics.spacing.medianHorizontalGap == null
                ? null
                : metrics.spacing.medianHorizontalGap * scale,
            bendRunPixels:
              metrics.bends.medianBendRun == null
                ? null
                : metrics.bends.medianBendRun * scale,
          };
        }"""
    )


def audit_viewport(
    browser,
    viewport_size: dict[str, int],
    payload: dict[str, Any],
    diagnostics: dict[str, Any],
) -> None:
    key = f"{viewport_size['width']}x{viewport_size['height']}"
    job_id = f"readable-flow-{key}"
    context = browser.new_context(viewport=viewport_size)
    page = context.new_page()
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
    route_payload(page, job_id, payload)
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_function("() => Boolean(window.viPages && window.viModelGraph)")
    load_job(page, job_id)
    switch_to_block_diagram(page)
    page.evaluate("() => window.VIComponentFit.fit('readable')")
    page.wait_for_timeout(220)

    before = state_fingerprint(page)
    readable = flow_snapshot(page)
    diagnostics["viewports"][key] = {"readable": readable}
    flow = readable["metrics"]["flow"]
    require(
        readable["recordCount"] == 12,
        f"{key}: connected flow fixture did not contain 12 nodes",
        diagnostics,
    )
    require(
        readable["wireCount"] == 11 and readable["renderedWireCount"] == 11,
        f"{key}: connected flow fixture did not render all 11 wires",
        diagnostics,
    )
    require(
        flow["forwardEdges"] == 11
        and flow["backwardEdges"] == 0
        and flow["directionality"] >= 0.99,
        f"{key}: left-to-right flow direction was not detected",
        diagnostics,
    )
    require(
        readable["datasetDirectionality"] >= 0.99,
        f"{key}: flow directionality was not published to the editor shell",
        diagnostics,
    )
    require(
        1.55 <= readable["scale"] <= 1.83,
        f"{key}: connected flow readable scale is outside policy",
        diagnostics,
    )
    require(
        readable["sourceViewportRatio"] is not None
        and 0.08 <= readable["sourceViewportRatio"] <= 0.30,
        f"{key}: upstream node was not retained near the left reading margin",
        diagnostics,
    )
    require(
        readable["sinkViewportRatio"] is not None
        and readable["sinkViewportRatio"] > 0.78,
        f"{key}: downstream flow did not extend across the readable viewport",
        diagnostics,
    )
    require(
        bool(readable["content"])
        and readable["content"]["width"] > readable["box"]["width"],
        f"{key}: connected flow was squeezed into one readable viewport",
        diagnostics,
    )
    require(
        readable["horizontalGapPixels"] is not None
        and readable["horizontalGapPixels"] >= 40,
        f"{key}: connected nodes have insufficient horizontal screen gap",
        diagnostics,
    )
    require(
        readable["bendRunPixels"] is not None
        and readable["bendRunPixels"] >= 18,
        f"{key}: connected wires have insufficient bend clearance",
        diagnostics,
    )

    page.evaluate(
        """() => {
          const records = window.VIComponentFit.representativeRecords()
            .slice()
            .sort((first, second) => first.centerX - second.centerX);
          window.VISemanticEditor.select(records[5].item.id, false);
        }"""
    )
    page.wait_for_timeout(100)
    page.locator("#model-graph-focus").click()
    page.wait_for_timeout(220)
    focus = flow_snapshot(page)
    context_counts = page.evaluate(
        """() => {
          const selected = window.VIComponentFit.selectedContext();
          return {records: selected.records.length, routes: selected.routes.length};
        }"""
    )
    diagnostics["viewports"][key]["focus"] = focus
    diagnostics["viewports"][key]["focus_context"] = context_counts
    require(
        focus["mode"] == "focus"
        and context_counts["records"] >= 3
        and context_counts["routes"] >= 2,
        f"{key}: focus did not follow the selected connected system",
        diagnostics,
    )

    page.locator("#model-graph-overview").click()
    page.wait_for_timeout(220)
    overview = flow_snapshot(page)
    diagnostics["viewports"][key]["overview"] = overview
    require(
        overview["mode"] == "overview"
        and overview["scale"] < readable["scale"] * 0.80,
        f"{key}: overview was not materially distinct from readable flow",
        diagnostics,
    )
    require(
        bool(overview["content"])
        and box_contains(overview["box"], overview["content"]),
        f"{key}: overview did not contain the complete connected flow",
        diagnostics,
    )

    page.locator("#model-graph-fit").click()
    page.wait_for_timeout(220)
    after = state_fingerprint(page)
    require(
        before == after,
        f"{key}: flow view modes changed VI bounds or edit state",
        diagnostics,
    )
    page.screenshot(
        path=str(ARTIFACTS / f"readable-flow-{key}.png"),
        full_page=False,
    )
    context.close()


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    payload = connected_flow_payload()
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".sandbox-readable-flow-jobs"),
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
        "failures": [],
        "console_errors": [],
        "page_errors": [],
        "viewports": {},
    }
    try:
        wait_for_server(process)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            for viewport_size in VIEWPORTS:
                audit_viewport(browser, viewport_size, payload, diagnostics)
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
                print(
                    "READABLE_FLOW_APPLICATION_LOG="
                    + output[-5000:].replace("\n", "\\n")
                )

    output = ARTIFACTS / "semantic-readable-flow.json"
    output.write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "SEMANTIC_READABLE_FLOW_JSON="
        + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
    )
    if (
        diagnostics["failures"]
        or diagnostics["console_errors"]
        or diagnostics["page_errors"]
    ):
        print("SEMANTIC_READABLE_FLOW_TEST_FAILED")
        return 1
    print("SEMANTIC_READABLE_FLOW_TEST_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
