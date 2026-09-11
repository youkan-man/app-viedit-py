from __future__ import annotations

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

from semantic_structure_workflow_test import job, workflow_model  # noqa: E402
from semantic_structure_net_scenario import BASE_URL, PORT, wait_for_server  # noqa: E402

ARTIFACTS = Path(
    os.getenv(
        "BUILD_ARTIFACT_DIR",
        str(ROOT / "artifacts" / "structure-workflow-probe"),
    )
)


def route_model(page: Page, model: dict[str, Any]) -> None:
    def model_route(route: Route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(model, ensure_ascii=False),
        )

    page.route("**/api/jobs/structure-net/model*", model_route)


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".sandbox-structure-workflow-probe-jobs"),
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
    }
    try:
        wait_for_server(process)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()
            page.set_default_timeout(10_000)
            page.on(
                "console",
                lambda message: diagnostics["console_errors"].append(message.text)
                if message.type == "error"
                else None,
            )
            page.on(
                "pageerror",
                lambda error: diagnostics["page_errors"].append(str(error)),
            )
            route_model(page, workflow_model())
            value = job()
            page.goto(BASE_URL, wait_until="networkidle")
            page.wait_for_function("() => Boolean(window.viPages && window.viModelGraph)")
            page.evaluate("job => window.viPages.setJob(job, {openModel: true})", value)
            page.evaluate("async job => { await window.viModelGraph.setJob(job); }", value)
            page.wait_for_function("() => window.VIStructureWorkflow?.ready === true")
            page.add_script_tag(
                url="/static/vi-editor-structure-workflow-catalog-fix.js?v=1"
            )
            page.wait_for_function(
                "() => window.VIStructureWorkflowCatalogFix?.ready === true"
            )
            page.add_script_tag(
                url="/static/vi-editor-structure-workflow-probe.js?v=1"
            )
            page.wait_for_function(
                "() => window.VIStructureWorkflowProbe?.ready === true"
            )
            page.locator('[data-vi-surface="block-diagram"]').click()
            page.evaluate("() => window.VISemanticEditor.select('case', true)")
            page.evaluate("() => window.VIStructureWorkflow.switchFrame('case', 1)")
            page.wait_for_timeout(250)
            diagnostics["report"] = page.evaluate(
                "() => window.VIStructureWorkflowProbe.report()"
            )
            diagnostics["state"] = page.evaluate(
                """() => ({
                  wires: [...window.VISemanticEditor.S.wires.keys()].sort(),
                  viWires: window.VISemanticEditor.S.vi.wires.map(wire => wire.id).sort(),
                  nets: window.VISemanticEditor.S.vi.nets.map(net => ({
                    id: net.id,
                    branchCount: net.branch_count,
                  })),
                  selected: window.VISemanticEditor.S.selected,
                })"""
            )
            expected = ["wire-true-a", "wire-true-b"]
            if diagnostics["state"]["wires"] != expected:
                diagnostics["failures"].append(
                    "normalized catalog did not restore the True-frame wires"
                )
            page.screenshot(
                path=str(ARTIFACTS / "structure-workflow-probe.png"),
                full_page=False,
            )
            context.close()
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
                print("STRUCTURE_WORKFLOW_PROBE_APP_LOG=" + output[-2500:].replace("\n", "\\n"))

    print(
        "STRUCTURE_WORKFLOW_PROBE_JSON="
        + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
    )
    failed = bool(
        diagnostics["failures"]
        or diagnostics["console_errors"]
        or diagnostics["page_errors"]
    )
    print("STRUCTURE_WORKFLOW_PROBE_FAILED" if failed else "STRUCTURE_WORKFLOW_PROBE_OK")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
