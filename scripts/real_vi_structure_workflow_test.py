from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from real_vi_structure_workflow_scenario import (  # noqa: E402
    ARTIFACTS,
    BASE_URL,
    PORT,
    box_close,
    build_candidate,
    frame_state,
    job,
    route_payload,
    stale_wire_endpoints,
    visible_frame_pairs,
    wait_for_server,
)


def require(condition: bool, message: str, diagnostics: dict[str, Any]) -> None:
    if not condition:
        diagnostics["failures"].append(message)


def switch_frame(page: Page, structure_id: str, frame_index: int) -> None:
    page.evaluate(
        "([id, index]) => window.VIStructureWorkflow.switchFrame(id, index)",
        [structure_id, frame_index],
    )
    page.wait_for_function(
        """([id, index]) => (
          window.VISemanticEditor.S.objects.get(id)?.active_frame_index === index
        )""",
        arg=[structure_id, frame_index],
    )
    page.wait_for_timeout(150)


def set_frame_session(
    page: Page,
    object_id: str,
    box: dict[str, float],
) -> None:
    page.evaluate(
        "box => window.VICanvasDensity.applyBox(box, 'manual', {remember: true})",
        box,
    )
    page.evaluate(
        "id => window.VISemanticEditor.select(id, false)",
        object_id,
    )
    page.wait_for_timeout(80)


def validate_frame(
    page: Page,
    structure_id: str,
    own_exclusive_id: str,
    other_exclusive_ids: list[str],
    label: str,
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    current = frame_state(page, structure_id)
    diagnostics[label] = current
    require(
        own_exclusive_id in current["activeVisible"],
        f"{label}: exclusive object is not rendered",
        diagnostics,
    )
    require(
        not set(other_exclusive_ids) & set(current["inactiveVisible"]),
        f"{label}: inactive-frame objects leaked into the canvas",
        diagnostics,
    )
    require(
        not stale_wire_endpoints(page),
        f"{label}: stale wire endpoints remain after switching",
        diagnostics,
    )
    return current


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    payload, source = build_candidate()
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".sandbox-real-structure-workflow-jobs"),
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
        "source": source,
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
            page.set_default_timeout(12_000)
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
            value = job()
            page.goto(BASE_URL, wait_until="networkidle")
            page.wait_for_function(
                "() => Boolean(window.viPages && window.viModelGraph)"
            )
            page.evaluate(
                "job => window.viPages.setJob(job, {openModel: true})",
                value,
            )
            page.evaluate(
                "async job => { await window.viModelGraph.setJob(job); }",
                value,
            )
            page.wait_for_function(
                """() => Boolean(
                  window.VIStructureWorkflow?.ready
                  && window.VIReadability?.ready
                  && window.VICanvasDensity?.ready
                )"""
            )
            page.locator('[data-vi-surface="block-diagram"]').click()
            structure_id = str(source["structure_id"])
            page.evaluate(
                "id => window.VISemanticEditor.select(id, true)",
                structure_id,
            )
            page.wait_for_selector("#vi-structure-frame-workflow:not([hidden])")
            pairs = visible_frame_pairs(page, structure_id)
            diagnostics["frames"] = pairs
            require(
                len(pairs) == 2,
                "real Structure has no distinct populated frame pair",
                diagnostics,
            )

            if len(pairs) == 2:
                first, second = pairs
                first_id = str(first["exclusive"][0])
                second_id = str(second["exclusive"][0])
                first_view = {
                    "x": 20.0,
                    "y": 20.0,
                    "width": 920.0,
                    "height": 620.0,
                }
                second_view = {
                    "x": 130.0,
                    "y": 70.0,
                    "width": 780.0,
                    "height": 540.0,
                }

                switch_frame(page, structure_id, int(first["index"]))
                set_frame_session(page, first_id, first_view)
                validate_frame(
                    page,
                    structure_id,
                    first_id,
                    [str(value) for value in second["exclusive"]],
                    "first",
                    diagnostics,
                )

                switch_frame(page, structure_id, int(second["index"]))
                set_frame_session(page, second_id, second_view)
                validate_frame(
                    page,
                    structure_id,
                    second_id,
                    [str(value) for value in first["exclusive"]],
                    "second",
                    diagnostics,
                )

                switch_frame(page, structure_id, int(first["index"]))
                first_restored = frame_state(page, structure_id)
                diagnostics["first_restored"] = first_restored
                require(
                    first_restored["selected"] == first_id,
                    "real first-frame selection was not restored",
                    diagnostics,
                )
                require(
                    box_close(first_restored["box"], first_view),
                    "real first-frame view was not restored",
                    diagnostics,
                )

                switch_frame(page, structure_id, int(second["index"]))
                second_restored = frame_state(page, structure_id)
                diagnostics["second_restored"] = second_restored
                require(
                    second_restored["selected"] == second_id,
                    "real second-frame selection was not restored",
                    diagnostics,
                )
                require(
                    box_close(second_restored["box"], second_view),
                    "real second-frame view was not restored",
                    diagnostics,
                )

            page.screenshot(
                path=str(ARTIFACTS / "real-structure-workflow-1440x900.png"),
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
                print(
                    "REAL_STRUCTURE_WORKFLOW_APPLICATION_LOG="
                    + output[-4000:].replace("\n", "\\n")
                )

    (ARTIFACTS / "real-structure-workflow.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "REAL_STRUCTURE_WORKFLOW_JSON="
        + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
    )
    failed = bool(
        diagnostics["failures"]
        or diagnostics["console_errors"]
        or diagnostics["page_errors"]
    )
    print(
        "REAL_STRUCTURE_WORKFLOW_TEST_FAILED"
        if failed
        else "REAL_STRUCTURE_WORKFLOW_TEST_OK"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
