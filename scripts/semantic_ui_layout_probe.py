from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from playwright.sync_api import Route, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.semantic_ui_browser_test import make_payload  # noqa: E402

PORT = int(os.getenv("VI_UI_LAYOUT_PROBE_PORT", "8084"))
BASE_URL = f"http://127.0.0.1:{PORT}"
ARTIFACT_DIR = Path(
    os.getenv("BUILD_ARTIFACT_DIR", str(ROOT / "artifacts" / "semantic-ui-layout"))
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


def capture(page) -> dict[str, Any]:
    return page.evaluate(
        """() => {
          const describe = selector => {
            const element = document.querySelector(selector);
            if (!element) return null;
            const rect = element.getBoundingClientRect();
            const style = getComputedStyle(element);
            return {
              selector,
              rect: {
                x: rect.x, y: rect.y, width: rect.width, height: rect.height,
                right: rect.right, bottom: rect.bottom
              },
              display: style.display,
              position: style.position,
              height: style.height,
              minHeight: style.minHeight,
              maxHeight: style.maxHeight,
              overflow: style.overflow,
              gridTemplateRows: style.gridTemplateRows,
              gridTemplateColumns: style.gridTemplateColumns,
              alignSelf: style.alignSelf,
              visibility: style.visibility,
              hidden: Boolean(element.hidden),
              open: 'open' in element ? Boolean(element.open) : null,
              childCount: element.children.length
            };
          };
          const shell = document.querySelector('#vi-editor-shell');
          return {
            readyState: document.readyState,
            activePage: document.body.dataset.activePage,
            selected: window.VISemanticEditor?.S?.selected || null,
            surface: window.VISemanticEditor?.S?.surface || null,
            criticalStyle: Boolean(document.querySelector('style[data-vi-critical-layout]')),
            stylesheets: [...document.styleSheets].map(sheet => sheet.href || 'inline'),
            shellChildren: shell ? [...shell.children].map(child => ({
              tag: child.tagName,
              id: child.id,
              className: child.className,
              rect: (() => {
                const r = child.getBoundingClientRect();
                return {x: r.x, y: r.y, width: r.width, height: r.height, bottom: r.bottom};
              })(),
              display: getComputedStyle(child).display
            })) : [],
            elements: [
              '.azure-application-shell',
              '.azure-content-stage',
              '#page-stack',
              '#page-model',
              '#vi-editor-shell',
              '.vi-editor-header',
              '.vi-summary',
              '.vi-diagnostics',
              '.vi-editor-layout',
              '.vi-object-pane',
              '.vi-canvas-pane',
              '.vi-canvas-toolbar',
              '#model-graph-viewport',
              '.vi-canvas-statusbar',
              '#vi-source-debug',
              '#vi-source-debug .vi-source-debug-grid',
              '#model-context-section',
              '#model-inspector',
              '#model-inspector-empty'
            ].map(describe),
            document: {
              innerWidth,
              innerHeight,
              scrollWidth: document.documentElement.scrollWidth,
              scrollHeight: document.documentElement.scrollHeight
            }
          };
        }"""
    )


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    payload = make_payload()
    job = {
        "job_id": "layout-probe",
        "status": "ready",
        "component_modified_at": "2026-09-10T00:00:00Z",
        "xml_modified_at": "2026-09-10T00:00:00Z",
        "files": [
            {"path": "sum_FPHb.xml", "size": 1024},
            {"path": "sum_BDHb.xml", "size": 2048},
        ],
    }
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".sandbox-ui-layout-probe-jobs"),
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
    result: dict[str, Any] = {}
    try:
        wait_for_server(process)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1365, "height": 860})
            page = context.new_page()

            def model_route(route: Route) -> None:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(payload, ensure_ascii=False),
                )

            page.route("**/api/jobs/layout-probe/model*", model_route)
            page.goto(BASE_URL, wait_until="networkidle")
            page.wait_for_function("() => Boolean(window.viPages && window.viModelGraph)")
            page.evaluate("job => window.viPages.setJob(job, {openModel: true})", job)
            page.evaluate("async job => { await window.viModelGraph.setJob(job); }", job)
            page.wait_for_function(
                "() => document.querySelectorAll('#model-graph-svg .vi-object').length === 3"
            )
            page.wait_for_timeout(350)
            result["selected_front_panel"] = capture(page)

            page.evaluate(
                """() => {
                  window.VISemanticEditor.S.selected = null;
                  window.VISemanticEditor.renderAll(false);
                }"""
            )
            page.wait_for_timeout(120)
            result["cleared_front_panel"] = capture(page)

            first_id = payload["vi"]["surfaces"]["front-panel"][0]
            page.evaluate("id => window.VISemanticEditor.select(id, false)", first_id)
            page.wait_for_timeout(120)
            result["reselected_front_panel"] = capture(page)

            page.evaluate(
                """() => {
                  const details = document.querySelector('#vi-source-debug');
                  if (details) details.open = true;
                }"""
            )
            page.wait_for_timeout(120)
            result["debug_open_front_panel"] = capture(page)

            page.evaluate(
                """() => {
                  const details = document.querySelector('#vi-source-debug');
                  if (details) details.open = false;
                }"""
            )
            page.wait_for_timeout(120)
            result["debug_closed_front_panel"] = capture(page)

            page.locator('[data-vi-surface="block-diagram"]').click()
            page.wait_for_timeout(180)
            result["block_diagram"] = capture(page)
            browser.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()

    output = ARTIFACT_DIR / "layout-probe.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SEMANTIC_LAYOUT_PROBE=" + json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
