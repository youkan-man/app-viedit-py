from __future__ import annotations

import json
import os
import runpy
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

ARTIFACTS = Path(
    os.getenv(
        "BUILD_ARTIFACT_DIR",
        str(ROOT / "artifacts" / "semantic-authoritative"),
    )
)
PORT = int(os.getenv("VI_UI_AUTHORITATIVE_PORT", "8085"))
BASE_URL = f"http://127.0.0.1:{PORT}"


def payload_from_fixture() -> dict[str, Any]:
    fixture = runpy.run_path(str(ROOT / "tests" / "test_lvkit_semantic.py"))
    with tempfile.TemporaryDirectory(prefix="authoritative-ui-") as directory:
        vi = fixture["_project"](Path(directory))
    return {
        "summary": {"failed_files": 0},
        "warnings": [],
        "graph": {
            "version": 1,
            "models": [],
            "connections": [],
            "nets": [],
            "unresolved": [],
            "documents": [],
        },
        "vi": vi,
    }


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


def require(condition: bool, message: str, diagnostics: dict[str, Any]) -> None:
    if not condition:
        diagnostics["failures"].append(message)


def install_route(page: Page, payload: dict[str, Any]) -> None:
    def model_route(route: Route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload, ensure_ascii=False),
        )

    page.route("**/api/jobs/authoritative-ui/model*", model_route)


def open_editor(page: Page, payload: dict[str, Any]) -> None:
    job = {
        "job_id": "authoritative-ui",
        "status": "ready",
        "component_modified_at": "2026-09-10T03:20:00Z",
        "xml_modified_at": "2026-09-10T03:20:00Z",
        "source": {"name": "sum.vi"},
        "files": [],
    }
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_function("() => Boolean(window.viPages && window.viModelGraph)")
    page.evaluate("job => window.viPages.setJob(job, {openModel: true})", job)
    page.evaluate("async job => { await window.viModelGraph.setJob(job); }", job)
    page.wait_for_function(
        "expected => window.VISemanticEditor?.S?.vi?.version === expected",
        arg=payload["vi"]["version"],
    )
    page.wait_for_function("() => window.VITypeDefinitions?.ready === true")
    page.wait_for_timeout(300)


def endpoint_error(page: Page, wire_id: str, target_terminal_id: str) -> dict[str, float]:
    return page.evaluate(
        """([wireId, targetId]) => {
          const escape = value => CSS.escape(value);
          const group = document.querySelector(
            `[data-wire-id="${escape(wireId)}"][data-target-terminal-id="${escape(targetId)}"]`
          );
          const path = group?.querySelector('.vi-wire');
          const target = document.querySelector(`[data-object-id="${escape(targetId)}"]`);
          const sourceId = window.VISemanticEditor.S.wires.get(wireId).source_terminal_id;
          const source = document.querySelector(`[data-object-id="${escape(sourceId)}"]`);
          if (!path || !source || !target) return {source: 9999, target: 9999};

          const screenPoint = (element, point) => {
            const matrix = element.getCTM();
            const svg = document.querySelector('#model-graph-svg');
            const candidate = svg.createSVGPoint();
            candidate.x = point.x;
            candidate.y = point.y;
            return candidate.matrixTransform(matrix);
          };
          const terminalCenter = element => {
            const box = element.getBBox();
            return screenPoint(element, {
              x: box.x + box.width / 2,
              y: box.y + box.height / 2,
            });
          };
          const start = screenPoint(path, path.getPointAtLength(0));
          const end = screenPoint(path, path.getPointAtLength(path.getTotalLength()));
          const sourceCenter = terminalCenter(source);
          const targetCenter = terminalCenter(target);
          const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
          return {
            source: distance(start, sourceCenter),
            target: distance(end, targetCenter),
          };
        }""",
        [wire_id, target_terminal_id],
    )


def audit(payload: dict[str, Any]) -> dict[str, Any]:
    vi = payload["vi"]
    objects = {item["id"]: item for item in vi["objects"]}
    input_control = next(item for item in vi["objects"] if item["name"] == "Input")
    definition_id = input_control["type_definition_id"]
    diagnostics: dict[str, Any] = {
        "failures": [],
        "console_errors": [],
        "page_errors": [],
        "parser": vi["parser"],
        "summary": vi["summary"],
        "wire_endpoint_errors": [],
    }

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page.on(
            "console",
            lambda message: diagnostics["console_errors"].append(message.text)
            if message.type == "error"
            else None,
        )
        page.on("pageerror", lambda error: diagnostics["page_errors"].append(str(error)))
        install_route(page, payload)
        open_editor(page, payload)

        require(
            vi["parser"]["mode"] == "authoritative",
            "editor payload is not authoritative",
            diagnostics,
        )
        require(
            not vi["debug"]["generic_graph_used_for_block_diagram"],
            "generic XML graph still drives block diagram",
            diagnostics,
        )

        page.locator('[data-vi-surface="block-diagram"]').click()
        page.wait_for_function(
            "expected => document.querySelectorAll('#model-graph-svg .vi-wire-group').length === expected",
            arg=len(vi["wires"]),
        )
        page.wait_for_timeout(250)

        rendered_node_ids = page.locator(
            "#model-graph-svg .vi-object.is-node:not(.is-terminal)"
        ).evaluate_all("nodes => nodes.map(node => node.dataset.objectId)")
        expected_node_ids = [
            item["id"]
            for item in vi["objects"]
            if item["surface"] == "block-diagram" and item["category"] == "node"
        ]
        require(
            sorted(rendered_node_ids) == sorted(expected_node_ids),
            "rendered component set differs from parsed LabVIEW nodes",
            diagnostics,
        )
        require(
            all(objects[object_id]["uid"] != "999" for object_id in rendered_node_ids),
            "internal DCO was rendered as a component",
            diagnostics,
        )

        for wire in vi["wires"]:
            target_id = wire["target_terminal_ids"][0]
            error = endpoint_error(page, wire["id"], target_id)
            diagnostics["wire_endpoint_errors"].append(
                {
                    "wire_id": wire["id"],
                    "source_uid": objects[wire["source_terminal_id"]]["uid"],
                    "target_uid": objects[target_id]["uid"],
                    **error,
                }
            )
            require(
                error["source"] <= 1.5 and error["target"] <= 1.5,
                f"wire {wire['id']} does not terminate on terminal centers",
                diagnostics,
            )
            require(
                wire["direction_confidence"] == "signal-term-list",
                f"wire {wire['id']} direction is not derived from signal term order",
                diagnostics,
            )

        input_terminal_id = input_control["linked_terminal_ids"][0]
        page.locator(f'[data-object-id="{input_terminal_id}"]').click()
        page.wait_for_timeout(300)
        require(
            page.locator("#vi-open-type-definition").is_visible(),
            "type definition action is hidden for typed terminal",
            diagnostics,
        )
        page.locator("#vi-open-type-definition").click()
        page.wait_for_selector("#vi-type-definition-panel:not([hidden])")
        require(
            page.locator("#vi-type-definition-title").inner_text() == "Settings.ctl",
            "wrong type definition opened",
            diagnostics,
        )
        require(
            page.locator("#vi-type-definition-tree").get_by_text("Gain", exact=True).count()
            == 1,
            "typedef field Gain is not visible",
            diagnostics,
        )
        active_definition = page.evaluate(
            "() => window.VITypeDefinitions.runtime.activeDefinitionId"
        )
        require(
            active_definition == definition_id,
            "selected terminal did not open its attached typedef",
            diagnostics,
        )

        typed_wire = next(
            wire for wire in vi["wires"] if wire.get("type_definition_id") == definition_id
        )
        page.locator(f'[data-wire-id="{typed_wire["id"]}"]').first.click()
        page.wait_for_timeout(250)
        wire_definition_ids = page.evaluate(
            "() => window.VITypeDefinitions.selectedDefinitionIds()"
        )
        require(
            definition_id in wire_definition_ids,
            "typed wire does not expose the same typedef",
            diagnostics,
        )

        diagnostics.update(
            {
                "rendered_node_ids": rendered_node_ids,
                "expected_node_ids": expected_node_ids,
                "opened_definition_id": active_definition,
                "typed_wire_definition_ids": wire_definition_ids,
                "type_title": page.locator("#vi-type-definition-title").inner_text(),
                "type_fields": page.locator(
                    "#vi-type-definition-tree .vi-type-node-heading strong"
                ).all_inner_texts(),
            }
        )
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(
            path=str(ARTIFACTS / "authoritative-graph-and-typedef.png"),
            full_page=False,
        )
        browser.close()

    return diagnostics


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    payload = payload_from_fixture()
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".sandbox-authoritative-ui-jobs"),
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
    diagnostics: dict[str, Any] | None = None
    try:
        wait_for_server(process)
        diagnostics = audit(payload)
        print(
            "AUTHORITATIVE_UI_JSON="
            + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
        )
        if (
            diagnostics["failures"]
            or diagnostics["console_errors"]
            or diagnostics["page_errors"]
        ):
            print("AUTHORITATIVE_UI_TEST_FAILED")
            return 1
        print("AUTHORITATIVE_UI_TEST_OK")
        return 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
        if process.stdout:
            output = process.stdout.read()
            if output:
                print("AUTHORITATIVE_UI_APP_LOG=" + output[-4000:].replace("\n", "\\n"))
        if diagnostics is not None:
            print(
                "AUTHORITATIVE_UI_FINAL_JSON="
                + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
            )


if __name__ == "__main__":
    raise SystemExit(main())
