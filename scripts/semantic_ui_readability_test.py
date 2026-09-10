from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, Route, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.semantic_ui_browser_test import make_payload  # noqa: E402

PORT = int(os.getenv("VI_UI_READABILITY_PORT", "8088"))
BASE_URL = f"http://127.0.0.1:{PORT}"
ARTIFACTS = Path(
    os.getenv("BUILD_ARTIFACT_DIR", str(ROOT / "artifacts" / "semantic-readability"))
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


def clone_object(template: dict[str, Any], object_id: str, **changes: Any) -> dict[str, Any]:
    item = copy.deepcopy(template)
    item.update(
        {
            "id": object_id,
            "component_id": object_id,
            "uid": object_id,
            "terminal_ids": [],
            "linked_terminal_ids": [],
            "wire_ids": [],
            "parent_object_id": None,
            "child_object_ids": [],
            "nesting_depth": 0,
            "movable": False,
            "resizable": False,
            "semantic_source": "readability-browser-fixture",
            **changes,
        }
    )
    return item


def dense_payload() -> dict[str, Any]:
    payload = copy.deepcopy(make_payload())
    vi = payload["vi"]
    objects = vi["objects"]
    node_template = next(
        item
        for item in objects
        if item.get("surface") == "block-diagram"
        and item.get("category") == "node"
    )
    terminal_template = next(
        item for item in objects if item.get("category") == "terminal"
    )
    control_template = next(
        item
        for item in objects
        if item.get("surface") == "front-panel"
        and item.get("category") == "control"
    )

    additions: list[dict[str, Any]] = []
    for index in range(14):
        additions.append(
            clone_object(
                node_template,
                f"dense-node-{index}",
                surface="block-diagram",
                category="node",
                kind="add" if index % 3 == 0 else "subvi",
                visual_kind="arithmetic" if index % 3 == 0 else "subvi",
                name=f"Dense operation {index + 1} with overlapping label",
                symbol="+" if index % 3 == 0 else "VI",
                bounds={
                    "x": 170 + (index % 7) * 46,
                    "y": 155 + (index // 7) * 45,
                    "width": 38,
                    "height": 30,
                },
                positioned=True,
            )
        )

    source_node = clone_object(
        node_template,
        "read-source-node",
        surface="block-diagram",
        category="node",
        kind="subvi",
        visual_kind="subvi",
        name="Selected source operation",
        symbol="VI",
        bounds={"x": 90, "y": 360, "width": 72, "height": 54},
        positioned=True,
        terminal_ids=["read-source-terminal"],
        wire_ids=["read-wire-a", "read-wire-b"],
    )
    target_a = clone_object(
        node_template,
        "read-target-a",
        surface="block-diagram",
        category="node",
        kind="subvi",
        visual_kind="subvi",
        name="Directly connected target A",
        symbol="VI",
        bounds={"x": 350, "y": 320, "width": 72, "height": 54},
        positioned=True,
        terminal_ids=["read-target-terminal-a"],
        wire_ids=["read-wire-a"],
    )
    target_b = clone_object(
        node_template,
        "read-target-b",
        surface="block-diagram",
        category="node",
        kind="subvi",
        visual_kind="subvi",
        name="Same network target B",
        symbol="VI",
        bounds={"x": 350, "y": 420, "width": 72, "height": 54},
        positioned=True,
        terminal_ids=["read-target-terminal-b"],
        wire_ids=["read-wire-b"],
    )
    unrelated = clone_object(
        node_template,
        "read-unrelated-node",
        surface="block-diagram",
        category="node",
        kind="subvi",
        visual_kind="subvi",
        name="Unrelated operation",
        symbol="VI",
        bounds={"x": 610, "y": 370, "width": 72, "height": 54},
        positioned=True,
    )
    structure = clone_object(
        node_template,
        "read-case-structure",
        surface="block-diagram",
        category="node",
        kind="structure-case",
        visual_kind="structure",
        name="Case Structure",
        symbol="▣",
        active_frame_index=1,
        active_frame_label="True",
        bounds={"x": 760, "y": 270, "width": 260, "height": 230},
        positioned=True,
        terminal_ids=["read-structure-tunnel"],
    )
    source_terminal = clone_object(
        terminal_template,
        "read-source-terminal",
        surface="block-diagram",
        category="terminal",
        kind="terminal",
        visual_kind="terminal",
        name="result",
        direction="source",
        owner_object_id=source_node["id"],
        bounds={"x": 154, "y": 382, "width": 8, "height": 8},
        positioned=True,
        wire_ids=["read-wire-a", "read-wire-b"],
    )
    target_terminal_a = clone_object(
        terminal_template,
        "read-target-terminal-a",
        surface="block-diagram",
        category="terminal",
        kind="terminal",
        visual_kind="terminal",
        name="input A",
        direction="sink",
        owner_object_id=target_a["id"],
        bounds={"x": 350, "y": 342, "width": 8, "height": 8},
        positioned=True,
        wire_ids=["read-wire-a"],
    )
    target_terminal_b = clone_object(
        terminal_template,
        "read-target-terminal-b",
        surface="block-diagram",
        category="terminal",
        kind="terminal",
        visual_kind="terminal",
        name="input B",
        direction="sink",
        owner_object_id=target_b["id"],
        bounds={"x": 350, "y": 442, "width": 8, "height": 8},
        positioned=True,
        wire_ids=["read-wire-b"],
    )
    tunnel = clone_object(
        terminal_template,
        "read-structure-tunnel",
        surface="block-diagram",
        category="terminal",
        kind="terminal",
        visual_kind="terminal",
        name="data tunnel",
        direction="bidirectional",
        owner_object_id=structure["id"],
        bounds={"x": 756, "y": 376, "width": 10, "height": 10},
        positioned=True,
        wire_roles=["source", "sink"],
    )
    additions.extend(
        [
            source_node,
            target_a,
            target_b,
            unrelated,
            structure,
            source_terminal,
            target_terminal_a,
            target_terminal_b,
            tunnel,
        ]
    )

    cluster = clone_object(
        control_template,
        "read-front-cluster",
        surface="front-panel",
        category="control",
        kind="cluster-control",
        visual_kind="cluster",
        data_type="cluster",
        name="Configuration cluster",
        bounds={"x": 120, "y": 120, "width": 300, "height": 180},
        positioned=True,
        child_object_ids=["read-front-child-a", "read-front-child-b", "read-front-child-c"],
    )
    for index, name in enumerate(
        (
            "Very long gain setting label",
            "Very long threshold setting label",
            "Very long timeout setting label",
        )
    ):
        additions.append(
            clone_object(
                control_template,
                f"read-front-child-{chr(97 + index)}",
                surface="front-panel",
                category="control",
                kind="numeric-control",
                visual_kind="numeric",
                data_type="numeric",
                name=name,
                parent_object_id=cluster["id"],
                nesting_depth=1,
                bounds={
                    "x": 145 + index * 45,
                    "y": 185 + index * 5,
                    "width": 82,
                    "height": 38,
                },
                positioned=True,
            )
        )
    additions.append(cluster)
    objects.extend(additions)

    vi["wires"].extend(
        [
            {
                "id": "read-wire-a",
                "name": "Selected source → target A",
                "surface": "block-diagram",
                "source_terminal_id": source_terminal["id"],
                "target_terminal_ids": [target_terminal_a["id"]],
                "terminal_ids": [source_terminal["id"], target_terminal_a["id"]],
                "source_object_id": source_node["id"],
                "target_object_ids": [target_a["id"]],
                "endpoint_object_ids": [source_node["id"], target_a["id"]],
                "route_points": [
                    {"x": 158, "y": 386},
                    {"x": 245, "y": 386},
                    {"x": 245, "y": 346},
                    {"x": 354, "y": 346},
                ],
                "resolved": True,
                "direction_confidence": "signal-term-list",
                "native_uid": "read-net-1",
                "native_signal_uid": "read-net-1",
                "net_id": "read-net",
                "branch_index": 0,
                "branch_count": 2,
                "data_type": "numeric",
            },
            {
                "id": "read-wire-b",
                "name": "Selected source → target B",
                "surface": "block-diagram",
                "source_terminal_id": source_terminal["id"],
                "target_terminal_ids": [target_terminal_b["id"]],
                "terminal_ids": [source_terminal["id"], target_terminal_b["id"]],
                "source_object_id": source_node["id"],
                "target_object_ids": [target_b["id"]],
                "endpoint_object_ids": [source_node["id"], target_b["id"]],
                "route_points": [
                    {"x": 158, "y": 386},
                    {"x": 245, "y": 386},
                    {"x": 245, "y": 446},
                    {"x": 354, "y": 446},
                ],
                "resolved": True,
                "direction_confidence": "signal-term-list",
                "native_uid": "read-net-1_1",
                "native_signal_uid": "read-net-1",
                "net_id": "read-net",
                "branch_index": 1,
                "branch_count": 2,
                "data_type": "numeric",
            },
        ]
    )
    vi["nets"] = list(vi.get("nets") or []) + [
        {
            "id": "read-net",
            "native_signal_uid": "read-net-1",
            "source_terminal_id": source_terminal["id"],
            "target_terminal_ids": [target_terminal_a["id"], target_terminal_b["id"]],
            "branch_ids": ["read-wire-a", "read-wire-b"],
            "branch_count": 2,
            "data_type": "numeric",
        }
    ]
    vi["surfaces"]["front-panel"] = [
        item["id"] for item in objects if item.get("surface") == "front-panel"
    ]
    vi["surfaces"]["block-diagram"] = [
        item["id"] for item in objects if item.get("surface") == "block-diagram"
    ]
    vi["summary"]["block_diagram_nodes"] = sum(
        item.get("surface") == "block-diagram" and item.get("category") == "node"
        for item in objects
    )
    vi["summary"]["wires"] = len(vi["wires"])
    vi["summary"]["resolved_wires"] = len(vi["wires"])
    vi["summary"]["wire_nets"] = len(vi["nets"])
    return payload


def job() -> dict[str, Any]:
    return {
        "job_id": "readability-ui",
        "status": "ready",
        "component_modified_at": "2026-09-10T12:10:00Z",
        "xml_modified_at": "2026-09-10T12:10:00Z",
        "files": [],
    }


def route_payload(page: Page, payload: dict[str, Any]) -> None:
    def model_route(route: Route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload, ensure_ascii=False),
        )

    page.route("**/api/jobs/readability-ui/model*", model_route)


def require(condition: bool, message: str, diagnostics: dict[str, Any]) -> None:
    if not condition:
        diagnostics["failures"].append(message)


def audit_viewport(browser, size: dict[str, int], payload: dict[str, Any], diagnostics: dict[str, Any]) -> None:
    context = browser.new_context(viewport=size)
    page = context.new_page()
    key = f"{size['width']}x{size['height']}"
    page.on(
        "console",
        lambda message: diagnostics["console_errors"].append(f"{key}: {message.text}")
        if message.type == "error"
        else None,
    )
    page.on(
        "pageerror",
        lambda error: diagnostics["page_errors"].append(f"{key}: {error}"),
    )
    route_payload(page, payload)
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_function("() => Boolean(window.viPages && window.viModelGraph)")
    page.evaluate("value => window.viPages.setJob(value, {openModel: true})", job())
    page.evaluate("async value => { await window.viModelGraph.setJob(value); }", job())
    page.wait_for_function("() => window.VIReadability?.ready === true")
    page.locator('[data-vi-surface="block-diagram"]').click()
    page.wait_for_function(
        "() => document.querySelectorAll('#model-graph-svg [data-object-id]').length > 10"
    )
    page.evaluate(
        """() => {
          const shell = document.querySelector('#vi-editor-shell');
          shell.dataset.viLod = 'normal';
          window.VIReadability.decorate();
        }"""
    )
    page.wait_for_timeout(180)

    initial = page.evaluate(
        """() => ({
          metrics: window.VIReadability.measureLabelCollisions(),
          suppressed: Number(document.querySelector('#model-graph-svg').dataset.suppressedLabelCount || 0),
          visible: Number(document.querySelector('#model-graph-svg').dataset.visibleLabelCount || 0),
          overlaps: Number(document.querySelector('#model-graph-svg').dataset.labelOverlapCount || 0),
        })"""
    )
    require(initial["suppressed"] > 0, f"{key}: dense labels were not suppressed", diagnostics)
    require(initial["overlaps"] <= 1, f"{key}: visible labels still overlap excessively", diagnostics)

    page.evaluate("() => window.VISemanticEditor.select('read-source-node', false)")
    page.evaluate("() => window.VIReadability.decorate()")
    page.wait_for_timeout(100)
    selection = page.evaluate(
        """() => ({
          primary: document.querySelector('[data-object-id="read-source-node"]')?.classList.contains('is-readability-primary'),
          targetA: document.querySelector('[data-object-id="read-target-a"]')?.classList.contains('is-readability-related'),
          targetB: document.querySelector('[data-object-id="read-target-b"]')?.classList.contains('is-readability-related'),
          unrelated: document.querySelector('[data-object-id="read-unrelated-node"]')?.classList.contains('is-readability-muted'),
          selectedLabelSuppressed: document.querySelector('[data-object-id="read-source-node"] .vi-object-label')?.classList.contains('is-label-suppressed'),
        })"""
    )
    require(selection["primary"], f"{key}: selected node is not primary", diagnostics)
    require(selection["targetA"] and selection["targetB"], f"{key}: direct targets are not related", diagnostics)
    require(selection["unrelated"], f"{key}: unrelated node is not muted", diagnostics)
    require(not selection["selectedLabelSuppressed"], f"{key}: selected label was suppressed", diagnostics)

    page.evaluate("() => window.VISemanticEditor.select('read-wire-a', false)")
    page.evaluate("() => window.VIReadability.decorate()")
    page.wait_for_timeout(100)
    network = page.evaluate(
        """() => ({
          primary: [...document.querySelectorAll('[data-wire-id="read-wire-a"]')].every(node => node.classList.contains('is-readability-primary')),
          sibling: [...document.querySelectorAll('[data-wire-id="read-wire-b"]')].every(node => node.classList.contains('is-readability-related')),
          netIds: [...document.querySelectorAll('[data-wire-id="read-wire-a"],[data-wire-id="read-wire-b"]')].map(node => node.dataset.netId),
        })"""
    )
    require(network["primary"], f"{key}: selected wire branch is not primary", diagnostics)
    require(network["sibling"], f"{key}: sibling branch in the same net is not related", diagnostics)

    structure = page.evaluate(
        """() => ({
          badge: document.querySelector('[data-object-id="read-case-structure"] .vi-structure-frame-badge')?.textContent,
          activeFrame: document.querySelector('[data-object-id="read-case-structure"]')?.dataset.activeFrameLabel,
          tunnel: document.querySelector('[data-object-id="read-structure-tunnel"]')?.classList.contains('is-structure-tunnel'),
          direction: document.querySelector('[data-object-id="read-structure-tunnel"]')?.dataset.tunnelDirection,
          mark: Boolean(document.querySelector('[data-object-id="read-structure-tunnel"] .vi-tunnel-direction')),
        })"""
    )
    require(structure["badge"] == "True", f"{key}: active Structure frame label is missing", diagnostics)
    require(structure["tunnel"], f"{key}: Structure terminal is not marked as a tunnel", diagnostics)
    require(structure["direction"] == "bidirectional", f"{key}: tunnel direction is wrong", diagnostics)
    require(structure["mark"], f"{key}: tunnel direction mark is missing", diagnostics)

    page.evaluate("() => { window.VISemanticEditor.S.selected = null; window.VISemanticEditor.renderAll(false); }")
    page.wait_for_timeout(100)
    page.locator('[data-vi-surface="front-panel"]').click()
    page.evaluate(
        """() => {
          document.querySelector('#vi-editor-shell').dataset.viLod = 'compact';
          window.VIReadability.decorate();
        }"""
    )
    page.wait_for_timeout(160)
    front = page.evaluate(
        """() => ({
          suppressedChildren: [...document.querySelectorAll(
            '[data-object-id="read-front-child-a"] .vi-object-label,' +
            '[data-object-id="read-front-child-b"] .vi-object-label,' +
            '[data-object-id="read-front-child-c"] .vi-object-label'
          )].filter(node => node.classList.contains('is-label-suppressed')).length,
          clusterSuppressed: document.querySelector('[data-object-id="read-front-cluster"] .vi-object-label')?.classList.contains('is-label-suppressed'),
          metrics: window.VIReadability.measureLabelCollisions(),
        })"""
    )
    require(front["suppressedChildren"] >= 1, f"{key}: overlapping cluster child labels were not reduced", diagnostics)
    require(not front["clusterSuppressed"], f"{key}: parent cluster label lost priority", diagnostics)

    diagnostics["viewports"][key] = {
        "initial": initial,
        "selection": selection,
        "network": network,
        "structure": structure,
        "front_panel": front,
    }
    page.screenshot(path=str(ARTIFACTS / f"readability-{key}.png"), full_page=False)
    context.close()


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    payload = dense_payload()
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".sandbox-readability-jobs"),
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
                print("READABILITY_APPLICATION_LOG=" + output[-4000:].replace("\n", "\\n"))

    output = ARTIFACTS / "semantic-ui-readability.json"
    output.write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "SEMANTIC_UI_READABILITY_JSON="
        + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
    )
    if diagnostics["failures"] or diagnostics["console_errors"] or diagnostics["page_errors"]:
        print("SEMANTIC_UI_READABILITY_TEST_FAILED")
        return 1
    print("SEMANTIC_UI_READABILITY_TEST_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
