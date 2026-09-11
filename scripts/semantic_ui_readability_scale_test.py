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

from scripts.semantic_ui_readability_test import dense_payload  # noqa: E402

PORT = int(os.getenv("VI_UI_READABILITY_SCALE_PORT", "8090"))
BASE_URL = f"http://127.0.0.1:{PORT}"
ARTIFACTS = Path(
    os.getenv(
        "BUILD_ARTIFACT_DIR",
        str(ROOT / "artifacts" / "semantic-readability-scale"),
    )
)
STRESS_COLUMNS = 36
STRESS_ROWS = 20
STRESS_COUNT = STRESS_COLUMNS * STRESS_ROWS


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


def stress_payload() -> dict[str, Any]:
    payload = copy.deepcopy(dense_payload())
    vi = payload["vi"]
    objects = vi["objects"]
    template = next(
        item
        for item in objects
        if item.get("surface") == "block-diagram"
        and item.get("category") == "node"
    )
    stress_objects = []
    for index in range(STRESS_COUNT):
        column = index % STRESS_COLUMNS
        row = index // STRESS_COLUMNS
        item = copy.deepcopy(template)
        item.update(
            {
                "id": f"stress-node-{index}",
                "component_id": f"stress-node-{index}",
                "uid": f"stress-node-{index}",
                "surface": "block-diagram",
                "category": "node",
                "kind": "subvi",
                "visual_kind": "subvi",
                "name": f"Stress operation {index + 1} with a deliberately long label",
                "symbol": "VI",
                "bounds": {
                    "x": 4200 + column * 48,
                    "y": 90 + row * 42,
                    "width": 38,
                    "height": 28,
                },
                "positioned": True,
                "movable": False,
                "resizable": False,
                "terminal_ids": [],
                "linked_terminal_ids": [],
                "wire_ids": [],
                "parent_object_id": None,
                "child_object_ids": [],
                "nesting_depth": 0,
                "semantic_source": "readability-scale-fixture",
            }
        )
        stress_objects.append(item)
    objects.extend(stress_objects)
    vi["surfaces"]["block-diagram"] = [
        item["id"]
        for item in objects
        if item.get("surface") == "block-diagram"
    ]
    vi["summary"]["block_diagram_nodes"] = sum(
        item.get("surface") == "block-diagram"
        and item.get("category") == "node"
        for item in objects
    )
    return payload


def job() -> dict[str, Any]:
    return {
        "job_id": "readability-scale",
        "status": "ready",
        "component_modified_at": "2026-09-11T00:30:00Z",
        "xml_modified_at": "2026-09-11T00:30:00Z",
        "files": [],
    }


def route_payload(page: Page, payload: dict[str, Any]) -> None:
    def model_route(route: Route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload, ensure_ascii=False),
        )

    page.route("**/api/jobs/readability-scale/model*", model_route)


def apply_view(page: Page, box: dict[str, float]) -> None:
    page.evaluate(
        """box => {
          const S = window.VISemanticEditor.S;
          S.box = {...box};
          S.el.modelGraphSvg.setAttribute(
            'viewBox',
            `${box.x} ${box.y} ${box.width} ${box.height}`,
          );
          const shell = document.querySelector('#vi-editor-shell');
          shell.dataset.viLod = 'normal';
          window.VIReadability.decorate();
        }""",
        box,
    )
    page.wait_for_timeout(120)


def require(condition: bool, message: str, diagnostics: dict[str, Any]) -> None:
    if not condition:
        diagnostics["failures"].append(message)


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    payload = stress_payload()
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".sandbox-readability-scale-jobs"),
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
        "stress_objects": STRESS_COUNT,
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
            route_payload(page, payload)
            page.goto(BASE_URL, wait_until="networkidle")
            page.wait_for_function("() => Boolean(window.viPages && window.viModelGraph)")
            page.evaluate("value => window.viPages.setJob(value, {openModel: true})", job())
            page.evaluate("async value => { await window.viModelGraph.setJob(value); }", job())
            page.wait_for_function("() => window.VIReadability?.ready === true")
            page.locator('[data-vi-surface="block-diagram"]').click()
            page.wait_for_function(
                f"() => document.querySelectorAll('#model-graph-svg [data-object-id]').length > {STRESS_COUNT}"
            )

            apply_view(
                page,
                {"x": 0, "y": 0, "width": 1200, "height": 700},
            )
            viewport_culling = page.evaluate(
                """() => ({
                  metrics: {...window.VIReadability.runtime.metrics},
                  renderedObjects: document.querySelectorAll(
                    '#model-graph-svg [data-object-id]'
                  ).length,
                })"""
            )
            diagnostics["viewport_culling"] = viewport_culling
            culling_metrics = viewport_culling["metrics"]
            require(
                culling_metrics["total"] > STRESS_COUNT,
                "stress labels were not rendered",
                diagnostics,
            )
            require(
                culling_metrics["candidates"] < culling_metrics["total"] / 4,
                "off-screen labels still participate in collision work",
                diagnostics,
            )

            apply_view(
                page,
                {"x": 4140, "y": 20, "width": 1900, "height": 920},
            )
            stress = page.evaluate(
                """() => ({
                  metrics: {...window.VIReadability.runtime.metrics},
                  visibleCollisions: window.VIReadability.measureLabelCollisions(),
                  scheduled: window.VIReadability.runtime.scheduled,
                })"""
            )
            diagnostics["stress_region"] = stress
            metrics = stress["metrics"]
            pairwise = metrics["candidates"] * (metrics["candidates"] - 1) / 2
            require(
                metrics["candidates"] >= 300,
                "stress region did not expose enough visible labels",
                diagnostics,
            )
            require(
                metrics["collisionChecks"] < pairwise * 0.2,
                "collision work regressed toward a quadratic scan",
                diagnostics,
            )
            require(
                metrics["indexCells"] > 10,
                "spatial collision index was not populated",
                diagnostics,
            )
            require(
                stress["visibleCollisions"]["overlaps"] <= 4,
                "stress region retains excessive visible label overlap",
                diagnostics,
            )

            page.evaluate("() => window.VISemanticEditor.select('stress-node-0', false)")
            page.evaluate("() => window.VIReadability.decorate()")
            page.wait_for_timeout(120)
            selection = page.evaluate(
                """() => {
                  const group = document.querySelector(
                    '[data-object-id="stress-node-0"]'
                  );
                  return {
                    primary: group?.classList.contains('is-readability-primary'),
                    labelSuppressed: group?.querySelector('.vi-object-label')
                      ?.classList.contains('is-label-suppressed'),
                    scheduled: window.VIReadability.runtime.scheduled,
                  };
                }"""
            )
            diagnostics["stress_selection"] = selection
            require(selection["primary"], "stress selection is not primary", diagnostics)
            require(
                not selection["labelSuppressed"],
                "selected stress label was suppressed",
                diagnostics,
            )

            page.wait_for_timeout(350)
            diagnostics["settled"] = page.evaluate(
                """() => ({
                  scheduled: window.VIReadability.runtime.scheduled,
                  decorating: window.VIReadability.runtime.decorating,
                })"""
            )
            require(
                not diagnostics["settled"]["scheduled"]
                and not diagnostics["settled"]["decorating"],
                "readability decoration did not settle",
                diagnostics,
            )
            page.screenshot(
                path=str(ARTIFACTS / "readability-scale-1440x900.png"),
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
                print("READABILITY_SCALE_APPLICATION_LOG=" + output[-4000:].replace("\n", "\\n"))

    (ARTIFACTS / "semantic-ui-readability-scale.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "SEMANTIC_UI_READABILITY_SCALE_JSON="
        + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
    )
    if diagnostics["failures"] or diagnostics["console_errors"] or diagnostics["page_errors"]:
        print("SEMANTIC_UI_READABILITY_SCALE_TEST_FAILED")
        return 1
    print("SEMANTIC_UI_READABILITY_SCALE_TEST_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
