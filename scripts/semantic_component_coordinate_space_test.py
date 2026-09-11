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

PORT = int(os.getenv("VI_COMPONENT_COORDINATE_SPACE_PORT", "8094"))
BASE_URL = f"http://127.0.0.1:{PORT}"
ARTIFACTS = Path(
    os.getenv(
        "BUILD_ARTIFACT_DIR",
        str(ROOT / "artifacts" / "semantic-component-coordinate-space"),
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
        "x": source["bounds"]["x"] + source["bounds"]["width"] - 12,
        "y": source["bounds"]["y"] + 6,
        "width": 24,
        "height": 24,
        "relative_to_object_id": source["id"],
        "source_coordinate_space": "absolute-owner-anchored",
        "anchor_x": 1.0,
        "anchor_y": 0.25,
    }
    target_terminal["bounds"] = {
        "x": target["bounds"]["x"] - 12,
        "y": target["bounds"]["y"] + target["bounds"]["height"] - 30,
        "width": 24,
        "height": 24,
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
        {"x": 285, "y": 338},
        {"x": 285, "y": 370},
        {
            "x": target["bounds"]["x"],
            "y": target["bounds"]["y"] + target["bounds"]["height"] * 0.75,
        },
    ]
    return value


def job() -> dict[str, Any]:
    return {
        "job_id": "component-coordinate-space",
        "status": "ready",
        "component_modified_at": "2026-09-11T13:00:00Z",
        "xml_modified_at": "2026-09-11T13:00:00Z",
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

    page.route("**/api/jobs/component-coordinate-space/model*", model_route)


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
            return {
              logical: {...logical},
              projected: {...projected},
              center: P.projectedCenter(id),
              source: projected.source,
              nativeBounds: {...item.bounds},
            };
          };
          const wire = S.wires.get('projection-wire');
          const path = document.querySelector(
            '[data-wire-id="projection-wire"] .vi-wire'
          );
          const length = path?.getTotalLength?.() || 0;
          const pointAt = offset => {
            const point = path?.getPointAtLength?.(offset);
            return point ? {x: point.x, y: point.y} : null;
          };
          return {
            runtimeReady: window.VIRuntimeFixes?.ready === true,
            modules: window.VIRuntimeFixes?.modules || [],
            coordinateReady: window.VIComponentCoordinateSpace?.ready === true,
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
              start: length ? pointAt(0) : null,
              end: length ? pointAt(length) : null,
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
    source_owner = value["sourceOwner"]["projected"]
    target_owner = value["targetOwner"]["projected"]
    expected_source = {
        "x": source_owner["x"] + source_owner["width"],
        "y": source_owner["y"] + source_owner["height"] * 0.25,
    }
    expected_target = {
        "x": target_owner["x"],
        "y": target_owner["y"] + target_owner["height"] * 0.75,
    }
    require(value["runtimeReady"], f"{label}: runtime manifest is not ready", diagnostics)
    require(value["coordinateReady"], f"{label}: coordinate-space module is not ready", diagnostics)
    require(
        "vi-editor-component-coordinate-space" in value["modules"],
        f"{label}: coordinate-space module is missing from the manifest",
        diagnostics,
    )
    require(
        value["sourceTerminal"]["source"].endswith("semantic-anchor"),
        f"{label}: source terminal ignored its semantic anchor",
        diagnostics,
    )
    require(
        value["targetTerminal"]["source"].endswith("semantic-anchor"),
        f"{label}: target terminal ignored its semantic anchor",
        diagnostics,
    )
    require(
        close(value["sourceTerminal"]["center"], expected_source),
        f"{label}: source terminal did not follow the owner boundary",
        diagnostics,
    )
    require(
        close(value["targetTerminal"]["center"], expected_target),
        f"{label}: target terminal did not follow the owner boundary",
        diagnostics,
    )
    require(
        close(value["path"]["start"], value["sourceTerminal"]["center"]),
        f"{label}: wire start is detached from the projected source terminal",
        diagnostics,
    )
    require(
        close(value["path"]["end"], value["targetTerminal"]["center"]),
        f"{label}: wire end is detached from the projected target terminal",
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
            "WORK_ROOT": str(ROOT / ".component-coordinate-space-jobs"),
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
                  && window.VIComponentCoordinateSpace?.ready
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
                    x: 185,
                    y: 250,
                    width: 108,
                    height: 92,
                  });
                  S.local.set('projection-target', {
                    x: 500,
                    y: 370,
                    width: 84,
                    height: 96,
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
                "source terminal native bounds changed during display projection",
                diagnostics,
            )
            require(
                moved["targetTerminal"]["nativeBounds"] == native_target_terminal,
                "target terminal native bounds changed during display projection",
                diagnostics,
            )
            require(
                moved["localKeys"] == ["projection-source", "projection-target"],
                "display projection created unexpected local geometry",
                diagnostics,
            )
            require(
                moved["dirtyKeys"] == ["projection-source", "projection-target"],
                "display projection dirtied terminal records",
                diagnostics,
            )
            page.screenshot(
                path=str(ARTIFACTS / "component-coordinate-space-1440x900.png"),
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

    (ARTIFACTS / "semantic-component-coordinate-space.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "SEMANTIC_COMPONENT_COORDINATE_SPACE_JSON="
        + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
    )
    failed = bool(
        diagnostics["failures"]
        or diagnostics["console_errors"]
        or diagnostics["page_errors"]
    )
    print(
        "SEMANTIC_COMPONENT_COORDINATE_SPACE_TEST_FAILED"
        if failed
        else "SEMANTIC_COMPONENT_COORDINATE_SPACE_TEST_OK"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
