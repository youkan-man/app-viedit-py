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

from semantic_component_projection_test import payload  # noqa: E402

PORT = int(os.getenv("VI_COMPONENT_TERMINAL_VISUAL_PORT", "8095"))
BASE_URL = f"http://127.0.0.1:{PORT}"
ARTIFACTS = Path(
    os.getenv(
        "BUILD_ARTIFACT_DIR",
        str(ROOT / "artifacts" / "semantic-component-terminal-visual"),
    )
)


def model() -> dict[str, Any]:
    value = copy.deepcopy(payload())
    by_id = {item["id"]: item for item in value["vi"]["objects"]}
    source = by_id["projection-source"]
    target = by_id["projection-target"]
    source_terminal = by_id["projection-source-terminal"]
    target_terminal = by_id["projection-target-terminal"]

    source_terminal["bounds"] = {
        "x": source["bounds"]["x"] + 6,
        "y": source["bounds"]["y"] + 18,
        "width": 227,
        "height": 19,
        "relative_to_object_id": source["id"],
        "source_coordinate_space": "absolute-owner-anchored",
        "anchor_x": 1.0,
        "anchor_y": 0.25,
    }
    target_terminal["bounds"] = {
        "x": target["bounds"]["x"] - 120,
        "y": target["bounds"]["y"] + 42,
        "width": 159,
        "height": 19,
        "relative_to_object_id": target["id"],
        "source_coordinate_space": "absolute-owner-anchored",
        "anchor_x": 0.0,
        "anchor_y": 0.75,
    }
    value["vi"]["wires"][0]["route_points"] = [
        {
            "x": source["bounds"]["x"] + source["bounds"]["width"],
            "y": source["bounds"]["y"] + source["bounds"]["height"] * 0.25,
        },
        {"x": 300, "y": 330},
        {"x": 300, "y": 390},
        {
            "x": target["bounds"]["x"],
            "y": target["bounds"]["y"] + target["bounds"]["height"] * 0.75,
        },
    ]
    return value


def job() -> dict[str, Any]:
    return {
        "job_id": "component-terminal-visual",
        "status": "ready",
        "component_modified_at": "2026-09-11T13:30:00Z",
        "xml_modified_at": "2026-09-11T13:30:00Z",
        "files": [],
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


def route_payload(page: Page, value: dict[str, Any]) -> None:
    def model_route(route: Route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(value, ensure_ascii=False),
        )

    page.route("**/api/jobs/component-terminal-visual/model*", model_route)


def close(first: dict[str, float], second: dict[str, float], tolerance: float = 0.8) -> bool:
    return (
        abs(float(first["x"]) - float(second["x"])) <= tolerance
        and abs(float(first["y"]) - float(second["y"])) <= tolerance
    )


def snapshot(page: Page) -> dict[str, Any]:
    return page.evaluate(
        """() => {
          const E = window.VISemanticEditor;
          const S = E.S;
          const P = window.VIComponentProjection;
          const record = id => {
            const item = S.objects.get(id);
            const logical = E.effectiveBounds(item);
            const projected = P.projectBounds(item, logical);
            const group = document.querySelector(
              `[data-object-id="${CSS.escape(id)}"]`
            );
            const hit = group?.querySelector(':scope > .vi-component-hit-target');
            return {
              logical: {...logical},
              projected: {...projected},
              center: P.projectedCenter(id),
              source: projected.source,
              nativeBounds: {...item.bounds},
              terminalVisualSize: group?.dataset.terminalVisualSize || null,
              hitTarget: hit ? {
                x: Number(hit.getAttribute('x')),
                y: Number(hit.getAttribute('y')),
                width: Number(hit.getAttribute('width')),
                height: Number(hit.getAttribute('height')),
                mode: hit.dataset.projectedBodyTarget || null,
              } : null,
            };
          };
          const wire = S.wires.get('projection-wire');
          const path = document.querySelector(
            '[data-wire-id="projection-wire"] .vi-wire'
          );
          const length = path?.getTotalLength?.() || 0;
          return {
            runtimeReady: window.VIRuntimeFixes?.ready === true,
            terminalVisualReady:
              window.VIComponentTerminalVisual?.ready === true,
            modules: window.VIRuntimeFixes?.modules || [],
            sourceOwner: record('projection-source'),
            targetOwner: record('projection-target'),
            sourceTerminal: record('projection-source-terminal'),
            targetTerminal: record('projection-target-terminal'),
            projectedWirePoints: P.projectedWirePoints(
              wire,
              'projection-target-terminal',
              'projection-target',
            ),
            path: {
              d: path?.getAttribute('d') || null,
              start: length ? path.getPointAtLength(0) : null,
              end: length ? path.getPointAtLength(length) : null,
            },
            localKeys: [...S.local.keys()].sort(),
            dirtyKeys: [...S.dirty].sort(),
          };
        }"""
    )


def require(condition: bool, message: str, diagnostics: dict[str, Any]) -> None:
    if not condition:
        diagnostics["failures"].append(message)


def validate(value: dict[str, Any], label: str, diagnostics: dict[str, Any]) -> None:
    require(value["runtimeReady"], f"{label}: runtime manifest is not ready", diagnostics)
    require(
        value["terminalVisualReady"],
        f"{label}: compact terminal visual is not ready",
        diagnostics,
    )
    require(
        "vi-editor-component-terminal-visual" in value["modules"],
        f"{label}: compact terminal module is missing from the manifest",
        diagnostics,
    )
    for name in ("sourceTerminal", "targetTerminal"):
        terminal = value[name]
        projected = terminal["projected"]
        require(
            projected["width"] == 8 and projected["height"] == 8,
            f"{label}: {name} envelope was not reduced to an 8x8 port",
            diagnostics,
        )
        require(
            terminal["terminalVisualSize"] == "8",
            f"{label}: {name} DOM size marker is wrong",
            diagnostics,
        )
        require(
            terminal["source"].endswith("compact-port"),
            f"{label}: {name} did not use compact-port projection",
            diagnostics,
        )
        require(
            terminal["hitTarget"]
            and terminal["hitTarget"]["width"] >= 16
            and terminal["hitTarget"]["height"] >= 16,
            f"{label}: {name} lost its minimum hit target",
            diagnostics,
        )
    require(
        close(value["path"]["start"], value["sourceTerminal"]["center"]),
        f"{label}: wire start is detached from the compact source port",
        diagnostics,
    )
    require(
        close(value["path"]["end"], value["targetTerminal"]["center"]),
        f"{label}: wire end is detached from the compact target port",
        diagnostics,
    )


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    value = model()
    native_source_terminal = copy.deepcopy(
        next(
            item["bounds"]
            for item in value["vi"]["objects"]
            if item["id"] == "projection-source-terminal"
        )
    )
    native_target_terminal = copy.deepcopy(
        next(
            item["bounds"]
            for item in value["vi"]["objects"]
            if item["id"] == "projection-target-terminal"
        )
    )
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".component-terminal-visual-jobs"),
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
            page.evaluate("value => window.viPages.setJob(value, {openModel: true})", job())
            page.evaluate("async value => { await window.viModelGraph.setJob(value); }", job())
            page.wait_for_function(
                """() => Boolean(
                  window.VIRuntimeFixes?.ready
                  && window.VIComponentTerminalVisual?.ready
                  && window.VIComponentFit?.ready
                )"""
            )
            page.locator('[data-vi-surface="block-diagram"]').click()
            page.wait_for_timeout(300)
            initial = snapshot(page)
            diagnostics["initial"] = initial
            validate(initial, "initial", diagnostics)

            page.evaluate(
                """() => {
                  const S = window.VISemanticEditor.S;
                  S.local.set('projection-source', {
                    x: 190,
                    y: 250,
                    width: 112,
                    height: 96,
                  });
                  S.local.set('projection-target', {
                    x: 505,
                    y: 372,
                    width: 88,
                    height: 100,
                  });
                  S.dirty.add('projection-source');
                  S.dirty.add('projection-target');
                  window.VISemanticEditor.renderCanvas();
                }"""
            )
            page.wait_for_timeout(300)
            moved = snapshot(page)
            diagnostics["moved"] = moved
            validate(moved, "moved", diagnostics)
            require(
                moved["sourceTerminal"]["nativeBounds"] == native_source_terminal,
                "source terminal native envelope changed",
                diagnostics,
            )
            require(
                moved["targetTerminal"]["nativeBounds"] == native_target_terminal,
                "target terminal native envelope changed",
                diagnostics,
            )
            require(
                moved["localKeys"] == ["projection-source", "projection-target"],
                "compact terminal projection created unexpected local geometry",
                diagnostics,
            )
            require(
                moved["dirtyKeys"] == ["projection-source", "projection-target"],
                "compact terminal projection dirtied terminal records",
                diagnostics,
            )
            page.screenshot(
                path=str(ARTIFACTS / "component-terminal-visual-1440x900.png"),
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
                diagnostics["application_log_tail"] = output[-3000:]

    (ARTIFACTS / "semantic-component-terminal-visual.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "SEMANTIC_COMPONENT_TERMINAL_VISUAL_JSON="
        + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
    )
    failed = bool(
        diagnostics["failures"]
        or diagnostics["console_errors"]
        or diagnostics["page_errors"]
    )
    print(
        "SEMANTIC_COMPONENT_TERMINAL_VISUAL_TEST_FAILED"
        if failed
        else "SEMANTIC_COMPONENT_TERMINAL_VISUAL_TEST_OK"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
