from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, Page, Route, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_structure_net_scenario import (  # noqa: E402
    BASE_URL,
    PORT,
    _node,
    make_model,
    wait_for_server,
)

ARTIFACTS = Path(
    os.getenv(
        "BUILD_ARTIFACT_DIR",
        str(ROOT / "artifacts" / "semantic-structure-workflow"),
    )
)
VIEWPORTS = (
    {"width": 1365, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1920, "height": 1080},
)


def workflow_model() -> dict[str, Any]:
    model = make_model()
    vi = model["vi"]
    objects = vi["objects"]
    by_id = {item["id"]: item for item in objects}

    parent = by_id["case"]
    parent["structure_frames"][1]["object_ids"].append("nested-case")
    parent["structure_frames"][1]["node_uids"].append("nested-case")

    nested = _node(
        "nested-case",
        "Nested Case",
        570,
        135,
        kind="structure-case",
        parent_id="case",
        surface="block-diagram-inactive",
        visual_kind="structure",
    )
    nested["bounds"] = {"x": 570, "y": 135, "width": 190, "height": 220}
    nested["active_frame_index"] = 0
    nested["active_frame_label"] = "A"
    nested["structure_frames"] = [
        {
            "index": 0,
            "label": "A",
            "is_active": True,
            "object_ids": ["nested-a"],
            "node_uids": ["nested-a"],
        },
        {
            "index": 1,
            "label": "B",
            "is_active": False,
            "object_ids": ["nested-b"],
            "node_uids": ["nested-b"],
        },
    ]
    nested_a = _node(
        "nested-a",
        "Nested A",
        620,
        205,
        parent_id="nested-case",
        surface="block-diagram-inactive",
    )
    nested_b = _node(
        "nested-b",
        "Nested B",
        620,
        285,
        parent_id="nested-case",
        surface="block-diagram-inactive",
    )
    nested_a["nesting_depth"] = 2
    nested_b["nesting_depth"] = 2
    objects.extend([nested, nested_a, nested_b])

    for wire in vi["all_structure_frame_wires"]:
        if wire["id"].startswith("wire-true"):
            wire["type_definition_id"] = "workflow-number-type"
    for wire in vi["inactive_structure_frame_wires"]:
        if wire["id"].startswith("wire-true"):
            wire["type_definition_id"] = "workflow-number-type"
    vi["type_definitions"] = [
        {
            "id": "workflow-number-type",
            "name": "Workflow Numeric",
            "kind": "primitive",
            "available": True,
            "definition": {
                "kind": "primitive",
                "name": "DBL",
                "display": "DBL",
            },
            "source_object_ids": ["true-a-term", "true-b-term"],
            "source": "structure-workflow-browser-fixture",
        }
    ]
    vi["summary"]["hidden_structure_frame_objects"] = 7
    vi["integrity"]["structure_frames"] = {
        "active_frame_only": True,
        "inactive_object_count": 7,
        "inactive_wire_count": 2,
    }
    return model


def job() -> dict[str, Any]:
    return {
        "job_id": "structure-net",
        "status": "ready",
        "component_modified_at": "2026-09-11T02:00:00Z",
        "xml_modified_at": "2026-09-11T02:00:00Z",
        "files": [],
    }


def require(condition: bool, message: str, diagnostics: dict[str, Any]) -> None:
    if not condition:
        diagnostics["failures"].append(message)


def box_close(
    first: dict[str, float] | None,
    second: dict[str, float] | None,
    tolerance: float = 1.0,
) -> bool:
    if not first or not second:
        return False
    return all(
        abs(float(first[key]) - float(second[key])) <= tolerance
        for key in ("x", "y", "width", "height")
    )


def route_model(page: Page, model: dict[str, Any]) -> None:
    def model_route(route: Route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(model, ensure_ascii=False),
        )

    page.route("**/api/jobs/structure-net/model*", model_route)


def load_editor(page: Page) -> None:
    value = job()
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_function("() => Boolean(window.viPages && window.viModelGraph)")
    page.evaluate("job => window.viPages.setJob(job, {openModel: true})", value)
    page.evaluate("async job => { await window.viModelGraph.setJob(job); }", value)
    page.wait_for_function(
        """() => Boolean(
          window.VIStructureWorkflow?.ready
          && window.VIReadability?.ready
          && window.VICanvasDensity?.ready
          && window.VITypeDefinitions?.ready
        )"""
    )
    page.locator('[data-vi-surface="block-diagram"]').click()
    page.wait_for_function("() => Boolean(window.VISemanticEditor.S.box)")


def snapshot(page: Page) -> dict[str, Any]:
    return page.evaluate(
        """() => ({
          frameOwner: document.querySelector('#vi-frame-select')
            ?.dataset.structureId || null,
          frame: document.querySelector('#vi-frame-select')?.value || null,
          frameOptions: document.querySelector('#vi-frame-select')?.options.length || 0,
          falseVisible: Boolean(document.querySelector('[data-object-id="node-false"]')),
          trueAVisible: Boolean(document.querySelector('[data-object-id="node-true-a"]')),
          trueBVisible: Boolean(document.querySelector('[data-object-id="node-true-b"]')),
          nestedVisible: Boolean(document.querySelector('[data-object-id="nested-case"]')),
          nestedAVisible: Boolean(document.querySelector('[data-object-id="nested-a"]')),
          nestedBVisible: Boolean(document.querySelector('[data-object-id="nested-b"]')),
          wires: [...window.VISemanticEditor.S.wires.keys()].sort(),
          catalog: [...window.VIStructureWorkflow.runtime.wireCatalog.keys()].sort(),
          nets: (window.VISemanticEditor.S.vi.nets || []).map(net => ({
            id: net.id,
            branchCount: net.branch_count,
            wireCount: net.wire_record_count,
          })),
          selected: window.VISemanticEditor.S.selected,
          box: window.VISemanticEditor.S.box
            ? {...window.VISemanticEditor.S.box}
            : null,
          dirty: window.VISemanticEditor.S.dirty.has('node-false'),
          local: window.VISemanticEditor.S.local.get('node-false') || null,
        })"""
    )


def set_view(page: Page, box: dict[str, float]) -> None:
    page.evaluate(
        "box => window.VICanvasDensity.applyBox(box, 'manual', {remember: true})",
        box,
    )
    page.wait_for_timeout(80)


def wire_endpoint_errors(page: Page) -> list[dict[str, Any]]:
    return page.evaluate(
        """() => {
          const E = window.VISemanticEditor;
          const S = E.S;
          const errors = [];
          for (const [id, wire] of S.wires) {
            const path = document.querySelector(
              `[data-wire-id="${CSS.escape(id)}"] .vi-wire`
            );
            const source = S.objects.get(wire.source_terminal_id);
            const target = S.objects.get(wire.target_terminal_ids?.[0]);
            if (!path?.getTotalLength || !source || !target) {
              errors.push({id, reason: 'missing-rendered-endpoint'});
              continue;
            }
            const sourceBox = E.effectiveBounds(source);
            const targetBox = E.effectiveBounds(target);
            const start = path.getPointAtLength(0);
            const end = path.getPointAtLength(path.getTotalLength());
            const expectedStart = {
              x: sourceBox.x + sourceBox.width / 2,
              y: sourceBox.y + sourceBox.height / 2,
            };
            const expectedEnd = {
              x: targetBox.x + targetBox.width / 2,
              y: targetBox.y + targetBox.height / 2,
            };
            const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
            const direct = distance(start, expectedStart) + distance(end, expectedEnd);
            const reverse = distance(start, expectedEnd) + distance(end, expectedStart);
            if (Math.min(direct, reverse) > 2.5) {
              errors.push({id, direct, reverse});
            }
          }
          return errors;
        }"""
    )


def run_scenario(
    browser: Browser,
    size: dict[str, int],
    model: dict[str, Any],
    diagnostics: dict[str, Any],
) -> None:
    key = f"{size['width']}x{size['height']}"
    context = browser.new_context(viewport=size)
    page = context.new_page()
    page.set_default_timeout(10_000)
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
    route_model(page, model)
    load_editor(page)

    page.evaluate("() => window.VISemanticEditor.select('case', true)")
    page.wait_for_selector("#vi-structure-frame-workflow:not([hidden])")
    initial = snapshot(page)
    false_view = {"x": 10.0, "y": 12.0, "width": 850.0, "height": 560.0}
    set_view(page, false_view)
    page.evaluate(
        """() => {
          const S = window.VISemanticEditor.S;
          S.local.set('node-false', {x: 438, y: 182, width: 84, height: 48});
          S.dirty.add('node-false');
          window.VISemanticEditor.select('node-false', false);
        }"""
    )
    require(initial["frameOwner"] == "case", f"{key}: wrong initial Structure", diagnostics)
    require(initial["frame"] == "0", f"{key}: initial frame is not False", diagnostics)
    require(initial["frameOptions"] == 2, f"{key}: frame options are incomplete", diagnostics)
    require(initial["falseVisible"] and not initial["trueAVisible"], f"{key}: initial visibility is wrong", diagnostics)
    require(initial["wires"] == ["wire-false"], f"{key}: initial wire set is wrong", diagnostics)
    require(
        initial["catalog"] == ["wire-false", "wire-true-a", "wire-true-b"],
        f"{key}: immutable wire catalog is incomplete",
        diagnostics,
    )

    page.locator("#vi-frame-select").select_option("1")
    page.wait_for_selector('[data-object-id="node-true-a"]')
    page.wait_for_selector('[data-object-id="nested-a"]')
    page.wait_for_function("() => window.VISemanticEditor.S.wires.size === 2")
    page.wait_for_timeout(120)
    true_frame = snapshot(page)
    require(not true_frame["falseVisible"], f"{key}: False node leaked", diagnostics)
    require(
        true_frame["trueAVisible"]
        and true_frame["trueBVisible"]
        and true_frame["nestedVisible"]
        and true_frame["nestedAVisible"]
        and not true_frame["nestedBVisible"],
        f"{key}: True/nested visibility is wrong",
        diagnostics,
    )
    require(
        true_frame["wires"] == ["wire-true-a", "wire-true-b"],
        f"{key}: True wire set is incomplete",
        diagnostics,
    )
    require(
        true_frame["nets"] == [
            {"id": "net-true", "branchCount": 2, "wireCount": 2}
        ],
        f"{key}: True branches were not rebuilt as one net",
        diagnostics,
    )
    require(true_frame["selected"] == "case", f"{key}: hidden selection did not fall back", diagnostics)
    require(true_frame["dirty"] and true_frame["local"], f"{key}: local edit was lost", diagnostics)
    require(box_close(false_view, true_frame["box"]), f"{key}: first switch reset view", diagnostics)

    page.evaluate("() => window.VISemanticEditor.select('nested-case', false)")
    page.wait_for_function(
        "() => document.querySelector('#vi-frame-select')?.dataset.structureId === 'nested-case'"
    )
    page.locator("#vi-frame-select").select_option("1")
    page.wait_for_selector('[data-object-id="nested-b"]')
    page.wait_for_function(
        """() => !document.querySelector('[data-object-id="nested-a"]')"""
    )
    true_view = {"x": 180.0, "y": 70.0, "width": 720.0, "height": 500.0}
    set_view(page, true_view)
    page.evaluate("() => window.VISemanticEditor.select('nested-b', false)")
    page.evaluate("() => window.VIStructureWorkflow.switchFrame('case', 0)")
    page.wait_for_selector('[data-object-id="node-false"]')
    page.wait_for_timeout(120)
    false_restored = snapshot(page)
    require(false_restored["selected"] == "node-false", f"{key}: False selection was not restored", diagnostics)
    require(box_close(false_view, false_restored["box"]), f"{key}: False view was not restored", diagnostics)
    require(
        not false_restored["nestedVisible"]
        and not false_restored["nestedAVisible"]
        and not false_restored["nestedBVisible"],
        f"{key}: inactive nested descendants leaked",
        diagnostics,
    )

    page.evaluate("() => window.VIStructureWorkflow.switchFrame('case', 1)")
    page.wait_for_selector('[data-object-id="nested-b"]')
    page.wait_for_timeout(120)
    true_restored = snapshot(page)
    require(true_restored["selected"] == "nested-b", f"{key}: True selection was not restored", diagnostics)
    require(box_close(true_view, true_restored["box"]), f"{key}: True view was not restored", diagnostics)
    require(
        true_restored["nestedBVisible"] and not true_restored["nestedAVisible"],
        f"{key}: nested frame choice was not retained",
        diagnostics,
    )
    require(
        true_restored["local"] == {"x": 438, "y": 182, "width": 84, "height": 48},
        f"{key}: local geometry did not survive the round trip",
        diagnostics,
    )

    page.evaluate("() => window.VISemanticEditor.select('wire-true-a', true)")
    page.wait_for_selector("#vi-net-workflow:not([hidden])")
    page.wait_for_function(
        """() => document.querySelectorAll(
          '#model-graph-svg .vi-wire-group.is-workflow-net'
        ).length === 2"""
    )
    net = page.evaluate(
        """() => ({
          id: window.VIStructureWorkflow.selectedNet()?.id || null,
          targets: document.querySelector('#vi-net-target-count')?.textContent,
          branches: document.querySelector('#vi-net-branch-count')?.textContent,
          wires: document.querySelector('#vi-net-wire-count')?.textContent,
          branchButtons: document.querySelectorAll('#vi-net-branch-list .vi-net-branch').length,
          endpointButtons: document.querySelectorAll('#vi-net-endpoints .vi-net-endpoint').length,
          highlighted: document.querySelectorAll('.vi-wire-group.is-workflow-net').length,
          sources: document.querySelectorAll('.is-workflow-net-source').length,
          sinks: document.querySelectorAll('.is-workflow-net-sink').length,
          typeAction: Boolean(document.querySelector('#vi-net-open-type:not([hidden])')),
        })"""
    )
    require(net["id"] == "net-true", f"{key}: wrong net selected", diagnostics)
    require(net["targets"] == "2" and net["branches"] == "2", f"{key}: net counts are wrong", diagnostics)
    require(net["wires"] == "2" and net["branchButtons"] == 2, f"{key}: net records are incomplete", diagnostics)
    require(net["endpointButtons"] == 3, f"{key}: endpoint list is incomplete", diagnostics)
    require(net["highlighted"] == 2, f"{key}: whole net is not highlighted", diagnostics)
    require(net["sources"] >= 1 and net["sinks"] >= 2, f"{key}: endpoints are not marked", diagnostics)
    require(net["typeAction"], f"{key}: type-definition action is hidden", diagnostics)

    page.locator("#vi-net-open-type").click()
    page.wait_for_selector("#vi-type-definition-panel:not([hidden])")
    require(
        page.locator("#vi-type-definition-title").text_content() == "Workflow Numeric",
        f"{key}: wrong type definition opened",
        diagnostics,
    )
    page.locator("#vi-net-next-endpoint").click()
    page.wait_for_function("() => window.VISemanticEditor.S.selected !== 'wire-true-a'")
    endpoint_selection = page.evaluate("() => window.VISemanticEditor.S.selected")
    require(
        endpoint_selection in {"source", "node-true-a", "node-true-b"},
        f"{key}: endpoint navigation selected an unrelated object",
        diagnostics,
    )
    page.evaluate("() => window.VISemanticEditor.select('wire-true-a', false)")
    page.locator("#vi-net-focus").click()
    page.wait_for_function("() => window.VICanvasDensity.runtime.currentMode === 'focus'")
    endpoint_errors = wire_endpoint_errors(page)
    require(not endpoint_errors, f"{key}: wire endpoints left terminal centers", diagnostics)

    page.locator('[data-vi-surface="front-panel"]').click()
    page.wait_for_selector('[data-object-id="front-input"]')
    front = page.evaluate(
        """() => ({
          surface: window.VISemanticEditor.S.surface,
          dirty: window.VISemanticEditor.S.dirty.has('node-false'),
          framePanelHidden: document.querySelector('#vi-structure-frame-workflow')?.hidden,
          netPanelHidden: document.querySelector('#vi-net-workflow')?.hidden,
        })"""
    )
    require(front["surface"] == "front-panel", f"{key}: front panel was damaged", diagnostics)
    require(front["dirty"], f"{key}: surface switch discarded frame edit", diagnostics)
    require(front["framePanelHidden"] and front["netPanelHidden"], f"{key}: workflow panels leaked to front panel", diagnostics)

    diagnostics["viewports"][key] = {
        "initial": initial,
        "true_frame": true_frame,
        "false_restored": false_restored,
        "true_restored": true_restored,
        "net": net,
        "endpoint_selection": endpoint_selection,
        "endpoint_errors": endpoint_errors,
        "front_panel": front,
    }
    page.screenshot(
        path=str(ARTIFACTS / f"structure-workflow-{key}.png"),
        full_page=False,
    )
    context.close()


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    model = workflow_model()
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".sandbox-structure-workflow-jobs"),
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
                run_scenario(browser, size, model, diagnostics)
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
                print("STRUCTURE_WORKFLOW_APPLICATION_LOG=" + output[-4000:].replace("\n", "\\n"))

    (ARTIFACTS / "semantic-structure-workflow.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "SEMANTIC_STRUCTURE_WORKFLOW_JSON="
        + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
    )
    failed = bool(
        diagnostics["failures"]
        or diagnostics["console_errors"]
        or diagnostics["page_errors"]
    )
    print(
        "SEMANTIC_STRUCTURE_WORKFLOW_TEST_FAILED"
        if failed
        else "SEMANTIC_STRUCTURE_WORKFLOW_TEST_OK"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
