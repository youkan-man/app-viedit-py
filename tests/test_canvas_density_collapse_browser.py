from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import Route, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def _wait_for_server(process: subprocess.Popen[str], base_url: str) -> None:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output, _ = process.communicate(timeout=3)
            raise AssertionError(f"application exited before ready:\n{output}")
        try:
            with urllib.request.urlopen(f"{base_url}/api/health", timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.2)
    raise AssertionError("application did not become ready")


def _layout_snapshot(page) -> dict:
    return page.evaluate(
        """() => {
          const inspect = selector => {
            const element = document.querySelector(selector);
            if (!element) return null;
            const rect = element.getBoundingClientRect();
            const style = getComputedStyle(element);
            return {
              selector,
              tag: element.tagName,
              classes: element.className,
              parent: element.parentElement?.className || element.parentElement?.id || null,
              rect: {
                x: rect.x,
                y: rect.y,
                width: rect.width,
                height: rect.height,
                right: rect.right,
                bottom: rect.bottom,
              },
              display: style.display,
              position: style.position,
              width: style.width,
              minWidth: style.minWidth,
              maxWidth: style.maxWidth,
              height: style.height,
              minHeight: style.minHeight,
              overflow: style.overflow,
              overflowX: style.overflowX,
              overflowY: style.overflowY,
              gridTemplateColumns: style.gridTemplateColumns,
              gridTemplateRows: style.gridTemplateRows,
              gridColumn: style.gridColumn,
              gridRow: style.gridRow,
              justifySelf: style.justifySelf,
              alignSelf: style.alignSelf,
              contain: style.contain,
              transform: style.transform,
            };
          };
          return {
            viewport: {width: innerWidth, height: innerHeight},
            bodyClasses: document.body.className,
            activePage: document.body.dataset.activePage,
            elements: [
              'body',
              '.azure-application-shell',
              '.azure-navigation',
              '.azure-content-stage',
              '#page-stack',
              '#page-model',
              '#vi-editor-shell',
              '.vi-editor-layout',
              '.vi-object-pane',
              '.vi-canvas-pane',
              '.vi-canvas-toolbar',
              '.vi-canvas-actions',
              '#model-graph-viewport',
              '.azure-context-pane',
            ].map(inspect),
          };
        }"""
    )


def _compact(snapshot: dict) -> dict:
    return {
        "viewport": snapshot["viewport"],
        "bodyClasses": snapshot["bodyClasses"],
        "activePage": snapshot["activePage"],
        "elements": {
            item["selector"]: {
                "rect": item["rect"],
                "display": item["display"],
                "position": item["position"],
                "width": item["width"],
                "minWidth": item["minWidth"],
                "maxWidth": item["maxWidth"],
                "overflow": item["overflow"],
                "gridTemplateColumns": item["gridTemplateColumns"],
                "gridColumn": item["gridColumn"],
                "justifySelf": item["justifySelf"],
                "parent": item["parent"],
            }
            for item in snapshot["elements"]
            if item is not None
        },
    }


def test_collapsing_both_panes_keeps_canvas_full_width(tmp_path: Path) -> None:
    port = 18088
    base_url = f"http://127.0.0.1:{port}"
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(port),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(tmp_path / "jobs"),
            "PYTHONPATH": str(ROOT),
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
    try:
        _wait_for_server(process, base_url)
        fixture = __import__(
            "scripts.semantic_ui_browser_test",
            fromlist=["make_payload"],
        )
        payload = fixture.make_payload()
        job = {
            "job_id": "density-collapse",
            "status": "ready",
            "component_modified_at": "2026-09-10T09:00:00Z",
            "xml_modified_at": "2026-09-10T09:00:00Z",
            "files": [],
        }
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1920, "height": 1080})
            page = context.new_page()

            def model_route(route: Route) -> None:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(payload, ensure_ascii=False),
                )

            page.route("**/api/jobs/density-collapse/model*", model_route)
            page.goto(base_url, wait_until="networkidle")
            page.wait_for_function(
                "() => Boolean(window.viPages && window.viModelGraph && window.VICanvasDensityToolbar?.ready)"
            )
            page.evaluate("job => window.viPages.setJob(job, {openModel: true})", job)
            page.evaluate("async job => { await window.viModelGraph.setJob(job); }", job)
            page.wait_for_function("() => Boolean(window.VISemanticEditor.S.vi)")
            page.wait_for_timeout(250)
            before = _layout_snapshot(page)

            page.locator("#vi-toggle-object-pane").click()
            page.locator("#vi-toggle-context-pane").click()
            page.wait_for_timeout(250)
            collapsed = _layout_snapshot(page)

            page.set_viewport_size({"width": 2040, "height": 1120})
            page.wait_for_timeout(250)
            resized = _layout_snapshot(page)
            browser.close()

        report = {
            "before": _compact(before),
            "collapsed": _compact(collapsed),
            "resized": _compact(resized),
        }
        artifact_root = Path(os.getenv("BUILD_ARTIFACT_DIR", str(tmp_path)))
        artifact_root.mkdir(parents=True, exist_ok=True)
        (artifact_root / "collapse-layout-diagnostic.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        by_selector = {
            item["selector"]: item
            for item in collapsed["elements"]
            if item is not None
        }
        resized_by_selector = {
            item["selector"]: item
            for item in resized["elements"]
            if item is not None
        }
        widths = {
            "collapsed": {
                selector: item["rect"]["width"]
                for selector, item in by_selector.items()
            },
            "resized": {
                selector: item["rect"]["width"]
                for selector, item in resized_by_selector.items()
            },
            "bodyClasses": collapsed["bodyClasses"],
            "activePage": collapsed["activePage"],
        }
        diagnostic = json.dumps(widths, ensure_ascii=False, separators=(",", ":"))
        assert by_selector[".azure-content-stage"]["rect"]["width"] >= 1500, diagnostic
        assert by_selector["#vi-editor-shell"]["rect"]["width"] >= 1500, diagnostic
        assert by_selector[".vi-editor-layout"]["rect"]["width"] >= 1500, diagnostic
        assert by_selector[".vi-canvas-pane"]["rect"]["width"] >= 1500, diagnostic
        assert by_selector["#model-graph-viewport"]["rect"]["width"] >= 1500, diagnostic
        assert resized_by_selector["#model-graph-viewport"]["rect"]["width"] >= 1600, diagnostic
    finally:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
