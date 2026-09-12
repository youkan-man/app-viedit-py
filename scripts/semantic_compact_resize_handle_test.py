from __future__ import annotations

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

from semantic_component_projection_test import job, payload  # noqa: E402

PORT = int(os.getenv("VI_COMPACT_RESIZE_HANDLE_PORT", "8098"))
BASE_URL = f"http://127.0.0.1:{PORT}"
ARTIFACTS = Path(
    os.getenv(
        "BUILD_ARTIFACT_DIR",
        str(ROOT / "artifacts" / "semantic-compact-resize-handles"),
    )
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


def route_payload(page: Page, value: dict[str, Any]) -> None:
    def model_route(route: Route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(value, ensure_ascii=False),
        )

    page.route("**/api/jobs/component-projection/model*", model_route)


def require(condition: bool, message: str, diagnostics: dict[str, Any]) -> None:
    if not condition:
        diagnostics["failures"].append(message)


def snapshot(page: Page, object_id: str) -> dict[str, Any]:
    return page.evaluate(
        """id => {
          const E = window.VISemanticEditor;
          const S = E.S;
          const group = document.querySelector(
            `[data-object-id="${CSS.escape(id)}"]`
          );
          const visual = group?.querySelector(':scope > .vi-resize-handle');
          const hit = group?.querySelector(':scope > .vi-resize-hit-target');
          const body = group?.querySelector(
            ':scope > .vi-component-geometry .vi-front-panel-body,' +
            ':scope > .vi-component-geometry .vi-block-node-body,' +
            ':scope > .vi-front-panel-body,' +
            ':scope > .vi-block-node-body'
          );
          const rect = element => {
            if (!element) return null;
            const value = element.getBoundingClientRect();
            return {
              x: value.x,
              y: value.y,
              width: value.width,
              height: value.height,
              right: value.right,
              bottom: value.bottom,
            };
          };
          const item = S.objects.get(id);
          return {
            objectId: id,
            selected: S.selected,
            surface: S.surface,
            bounds: item ? {...E.effectiveBounds(item)} : null,
            nativeBounds: item ? {...item.bounds} : null,
            visual: rect(visual),
            hit: rect(hit),
            body: rect(body),
            visualVisibility: visual ? getComputedStyle(visual).visibility : null,
            visualDisplay: visual ? getComputedStyle(visual).display : null,
            hitDisplay: hit ? getComputedStyle(hit).display : null,
            visualDataResize: visual?.dataset.resize || null,
            hitDataResize: hit?.dataset.resize || null,
            localKeys: [...S.local.keys()].sort(),
            dirtyKeys: [...S.dirty].sort(),
            ready: window.VICompactResizeHandles?.ready === true,
            sizes: {
              visual: window.VICompactResizeHandles?.visualSizePx || null,
              hit: window.VICompactResizeHandles?.hitSizePx || null,
            },
          };
        }""",
        object_id,
    )


def near(value: float, expected: float, tolerance: float = 1.25) -> bool:
    return abs(float(value) - expected) <= tolerance


def validate_sizes(value: dict[str, Any], label: str, diagnostics: dict[str, Any]) -> None:
    require(value["ready"], f"{label}: compact handle runtime is not ready", diagnostics)
    require(bool(value["visual"]), f"{label}: visible handle is missing", diagnostics)
    require(bool(value["hit"]), f"{label}: resize hit target is missing", diagnostics)
    if value["visual"]:
        require(
            near(value["visual"]["width"], 5)
            and near(value["visual"]["height"], 5),
            f"{label}: visible handle is not approximately 5px",
            diagnostics,
        )
    if value["hit"]:
        require(
            near(value["hit"]["width"], 14)
            and near(value["hit"]["height"], 14),
            f"{label}: hit target is not approximately 14px",
            diagnostics,
        )
    if value["visual"] and value["body"]:
        require(
            value["visual"]["x"] >= value["body"]["right"] - 1.5
            and value["visual"]["y"] >= value["body"]["bottom"] - 1.5,
            f"{label}: visible handle still covers the component body",
            diagnostics,
        )
    require(
        value["visualDataResize"] is None and value["hitDataResize"] == "true",
        f"{label}: resize behavior is not isolated to the hit target",
        diagnostics,
    )


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    value = payload()
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".compact-resize-handle-jobs"),
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
            page.set_default_timeout(15_000)
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
                  && window.VICompactResizeHandles?.ready
                  && window.VIMultiSelectionPolish?.ready
                  && window.VISemanticEditor?.S?.vi
                )"""
            )
            page.evaluate(
                "() => window.VISemanticEditor.select('projection-front-numeric', false)"
            )
            page.wait_for_timeout(250)

            initial = snapshot(page, "projection-front-numeric")
            diagnostics["initial"] = initial
            validate_sizes(initial, "initial", diagnostics)
            require(
                initial["localKeys"] == [] and initial["dirtyKeys"] == [],
                "initial decoration changed geometry state",
                diagnostics,
            )

            page.locator("#model-graph-zoom-in").click()
            page.locator("#model-graph-zoom-in").click()
            page.wait_for_timeout(250)
            zoomed = snapshot(page, "projection-front-numeric")
            diagnostics["zoomed"] = zoomed
            validate_sizes(zoomed, "zoomed", diagnostics)

            hit = page.locator(
                '[data-object-id="projection-front-numeric"] > .vi-resize-hit-target'
            )
            hit_box = hit.bounding_box()
            before_resize = snapshot(page, "projection-front-numeric")
            if hit_box:
                x = hit_box["x"] + hit_box["width"] / 2
                y = hit_box["y"] + hit_box["height"] / 2
                page.mouse.move(x, y)
                page.mouse.down()
                page.mouse.move(x + 32, y + 24, steps=6)
                page.mouse.up()
                page.wait_for_timeout(260)
            else:
                require(False, "resize hit target has no screen bounds", diagnostics)

            resized = snapshot(page, "projection-front-numeric")
            diagnostics["resized"] = resized
            validate_sizes(resized, "resized", diagnostics)
            require(
                resized["bounds"]["width"] > before_resize["bounds"]["width"]
                and resized["bounds"]["height"] > before_resize["bounds"]["height"],
                "dragging the transparent hit target did not resize the component",
                diagnostics,
            )
            require(
                resized["localKeys"] == ["projection-front-numeric"]
                and resized["dirtyKeys"] == ["projection-front-numeric"],
                "resize modified unexpected object geometry",
                diagnostics,
            )
            require(
                resized["nativeBounds"] == initial["nativeBounds"],
                "display handle or resize changed native source bounds",
                diagnostics,
            )

            page.evaluate(
                """() => window.VIMultiSelection.setSelection(
                  ['projection-front-boolean', 'projection-front-numeric'],
                  'projection-front-numeric'
                )"""
            )
            page.wait_for_timeout(220)
            multiple = snapshot(page, "projection-front-numeric")
            diagnostics["multiple"] = multiple
            require(
                multiple["hit"] is None
                and multiple["visualDisplay"] == "none",
                "multi-selection still exposes an active resize handle",
                diagnostics,
            )

            page.evaluate("() => window.VIMultiSelection.clearSelection()")
            page.locator('[data-vi-surface="block-diagram"]').click()
            page.wait_for_timeout(180)
            page.evaluate(
                "() => window.VISemanticEditor.select('projection-source-terminal', false)"
            )
            page.wait_for_timeout(180)
            terminal = snapshot(page, "projection-source-terminal")
            diagnostics["terminal"] = terminal
            require(
                terminal["visual"] is None and terminal["hit"] is None,
                "terminal incorrectly exposes a resize handle",
                diagnostics,
            )

            page.screenshot(
                path=str(ARTIFACTS / "compact-resize-handles-1440x900.png"),
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

    (ARTIFACTS / "semantic-compact-resize-handles.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "SEMANTIC_COMPACT_RESIZE_HANDLES_JSON="
        + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
    )
    failed = bool(
        diagnostics["failures"]
        or diagnostics["console_errors"]
        or diagnostics["page_errors"]
    )
    print(
        "SEMANTIC_COMPACT_RESIZE_HANDLES_TEST_FAILED"
        if failed
        else "SEMANTIC_COMPACT_RESIZE_HANDLES_TEST_OK"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
