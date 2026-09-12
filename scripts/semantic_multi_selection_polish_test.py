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

from semantic_multi_selection_test import (  # noqa: E402
    BASE_URL,
    PORT,
    fixture,
    job,
    route_payload,
    wait_for_server,
)

ARTIFACTS = Path(
    os.getenv(
        "BUILD_ARTIFACT_DIR",
        str(ROOT / "artifacts" / "semantic-multi-selection-polish"),
    )
)


def require(condition: bool, message: str, diagnostics: dict[str, Any]) -> None:
    if not condition:
        diagnostics["failures"].append(message)


def snapshot(page: Page) -> dict[str, Any]:
    return page.evaluate(
        """() => {
          const E = window.VISemanticEditor;
          const S = E.S;
          const M = window.VIMultiSelection;
          const selected = [...M.runtime.selectedIds].sort();
          const outlineCount = document.querySelectorAll(
            '#model-graph-svg .vi-multi-selection-item-outline'
          ).length;
          const geometry = document.querySelector('#vi-geometry-editor');
          return {
            surface: S.surface,
            selectedIds: selected,
            primaryId: M.runtime.primaryId,
            selected: S.selected,
            localKeys: [...S.local.keys()].sort(),
            dirtyKeys: [...S.dirty].sort(),
            outlineCount,
            geometryDisplay: geometry ? getComputedStyle(geometry).display : null,
            polishReady: window.VIMultiSelectionPolish?.ready === true,
            moduleLoaded: window.VIRuntimeFixes?.modules?.includes(
              'vi-editor-multi-selection-polish'
            ) === true,
          };
        }"""
    )


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    value = fixture()
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".semantic-multi-selection-polish-jobs"),
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
            page.set_default_timeout(20_000)
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
            route_payload(page, value)
            page.goto(BASE_URL, wait_until="networkidle")
            page.wait_for_function("() => Boolean(window.viPages && window.viModelGraph)")
            active_job = job()
            page.evaluate(
                "value => window.viPages.setJob(value, {openModel: true})",
                active_job,
            )
            page.evaluate(
                "async value => { await window.viModelGraph.setJob(value); }",
                active_job,
            )
            page.wait_for_function(
                """() => Boolean(
                  window.VIRuntimeFixes?.ready
                  && window.VINavigationHistoryStability?.ready
                  && window.VIMultiSelection?.ready
                  && window.VIMultiSelectionPolish?.ready
                  && window.VIComponentFit?.ready
                )"""
            )
            page.locator('[data-vi-surface="block-diagram"]').click()
            page.wait_for_timeout(300)

            initial = snapshot(page)
            diagnostics["initial"] = initial
            require(initial["polishReady"], "polish runtime is not ready", diagnostics)
            require(initial["moduleLoaded"], "polish module is absent from runtime manifest", diagnostics)

            page.keyboard.press("Control+A")
            page.wait_for_timeout(180)
            select_all = snapshot(page)
            diagnostics["select_all"] = select_all
            require(
                len(select_all["selectedIds"]) >= 150,
                "Ctrl+A did not select the visible block-diagram objects",
                diagnostics,
            )
            require(
                "multi-source-terminal" not in select_all["selectedIds"]
                and "multi-target-terminal" not in select_all["selectedIds"],
                "Ctrl+A selected owner-bound terminal records",
                diagnostics,
            )
            require(
                select_all["localKeys"] == [] and select_all["dirtyKeys"] == [],
                "Ctrl+A modified geometry state",
                diagnostics,
            )

            page.evaluate(
                """() => window.VIMultiSelection.setSelection(
                  ['multi-node-a', 'multi-node-b'],
                  'multi-node-b'
                )"""
            )
            page.wait_for_timeout(150)
            before_primary = snapshot(page)
            box = page.locator('[data-object-id="multi-node-a"]').bounding_box()
            if box:
                page.mouse.click(
                    box["x"] + box["width"] / 2,
                    box["y"] + box["height"] / 2,
                )
                page.wait_for_timeout(180)
            else:
                require(False, "primary-switch target is not rendered", diagnostics)
            primary = snapshot(page)
            diagnostics["primary"] = primary
            require(
                primary["selectedIds"] == ["multi-node-a", "multi-node-b"],
                "clicking a selected object collapsed the group",
                diagnostics,
            )
            require(
                primary["primaryId"] == "multi-node-a"
                and primary["selected"] == "multi-node-a",
                "clicking a selected object did not make it primary",
                diagnostics,
            )
            require(
                primary["outlineCount"] >= 2,
                "per-item multi-selection outlines are missing",
                diagnostics,
            )
            require(
                primary["geometryDisplay"] == "none",
                "single-object geometry editor remained visible for a group",
                diagnostics,
            )
            require(
                primary["localKeys"] == before_primary["localKeys"]
                and primary["dirtyKeys"] == before_primary["dirtyKeys"],
                "primary switching modified geometry",
                diagnostics,
            )

            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(160)
            moved = snapshot(page)
            diagnostics["keyboard_moved"] = moved
            require(
                moved["dirtyKeys"] == ["multi-node-a", "multi-node-b"],
                "early keyboard guard did not move the selected group",
                diagnostics,
            )

            page.locator('[data-vi-surface="front-panel"]').click()
            page.wait_for_timeout(220)
            surface = snapshot(page)
            diagnostics["surface"] = surface
            require(
                surface["surface"] == "front-panel",
                "surface switch did not reach the front panel",
                diagnostics,
            )
            require(
                surface["selectedIds"] == [] and surface["selected"] is None,
                "selection from the block diagram leaked into the front panel",
                diagnostics,
            )

            page.locator('[data-vi-surface="block-diagram"]').click()
            page.wait_for_timeout(180)
            page.evaluate(
                """() => window.VIMultiSelection.setSelection(
                  ['multi-node-a', 'multi-node-b'],
                  'multi-node-a'
                )"""
            )
            page.wait_for_timeout(100)
            page.keyboard.press("Escape")
            page.wait_for_timeout(150)
            escaped = snapshot(page)
            diagnostics["escaped"] = escaped
            require(
                escaped["selectedIds"] == [] and escaped["selected"] is None,
                "early Escape guard did not clear the group",
                diagnostics,
            )

            page.screenshot(
                path=str(ARTIFACTS / "multi-selection-polish-1440x900.png"),
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
                diagnostics["application_log_tail"] = output[-4000:]

    (ARTIFACTS / "semantic-multi-selection-polish.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "SEMANTIC_MULTI_SELECTION_POLISH_JSON="
        + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
    )
    failed = bool(
        diagnostics["failures"]
        or diagnostics["console_errors"]
        or diagnostics["page_errors"]
    )
    print(
        "SEMANTIC_MULTI_SELECTION_POLISH_TEST_FAILED"
        if failed
        else "SEMANTIC_MULTI_SELECTION_POLISH_TEST_OK"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
