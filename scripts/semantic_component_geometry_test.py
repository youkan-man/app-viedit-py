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

from scripts.semantic_ui_browser_test import make_payload  # noqa: E402

PORT = int(os.getenv("VI_COMPONENT_GEOMETRY_PORT", "8092"))
BASE_URL = f"http://127.0.0.1:{PORT}"
ARTIFACTS = Path(
    os.getenv(
        "BUILD_ARTIFACT_DIR",
        str(ROOT / "artifacts" / "semantic-component-geometry"),
    )
)
VIEWPORTS = (
    {"width": 1365, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1920, "height": 1080},
)
EXPECTED = {
    "geometry-front-boolean": {"width": 28, "height": 28},
    "geometry-front-text": {"width": 116, "height": 30},
    "geometry-block-primitive": {"width": 28, "height": 28},
    "geometry-block-subvi": {"width": 36, "height": 36},
    "geometry-terminal": {"width": 8, "height": 8},
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


def object_record(
    object_id: str,
    *,
    surface: str,
    category: str,
    kind: str,
    visual_kind: str,
    name: str,
    owner_object_id: str | None = None,
) -> dict[str, Any]:
    return {
        "id": object_id,
        "component_id": object_id,
        "uid": object_id,
        "surface": surface,
        "category": category,
        "kind": kind,
        "visual_kind": visual_kind,
        "name": name,
        "symbol": "+" if "primitive" in kind else "VI",
        "class_name": kind,
        "bounds": None,
        "positioned": False,
        "movable": False,
        "resizable": False,
        "terminal_ids": [],
        "linked_terminal_ids": [],
        "wire_ids": [],
        "parent_object_id": None,
        "owner_object_id": owner_object_id,
        "child_object_ids": [],
        "data_type": "boolean" if "boolean" in kind else "numeric",
        "semantic_source": "component-geometry-browser-fixture",
        "source": {
            "file": "component-geometry-fixture.xml",
            "xml_path": f"/{object_id}",
        },
    }


def payload() -> dict[str, Any]:
    value = copy.deepcopy(make_payload())
    vi = value["vi"]
    additions = [
        object_record(
            "geometry-front-boolean",
            surface="front-panel",
            category="control",
            kind="boolean-control",
            visual_kind="boolean",
            name="Fallback Boolean",
        ),
        object_record(
            "geometry-front-text",
            surface="front-panel",
            category="control",
            kind="string-control",
            visual_kind="string",
            name="Fallback Text",
        ),
        object_record(
            "geometry-block-primitive",
            surface="block-diagram",
            category="node",
            kind="primitive-add",
            visual_kind="primitive",
            name="Fallback Add",
        ),
        object_record(
            "geometry-block-subvi",
            surface="block-diagram",
            category="node",
            kind="subvi",
            visual_kind="subvi",
            name="Fallback SubVI",
        ),
        object_record(
            "geometry-terminal",
            surface="block-diagram",
            category="terminal",
            kind="terminal",
            visual_kind="terminal",
            name="Fallback Terminal",
            owner_object_id="geometry-block-subvi",
        ),
    ]
    next(item for item in additions if item["id"] == "geometry-block-subvi")[
        "terminal_ids"
    ] = ["geometry-terminal"]
    vi["objects"].extend(additions)
    vi["surfaces"]["front-panel"].extend(
        ["geometry-front-boolean", "geometry-front-text"]
    )
    vi["surfaces"]["block-diagram"].extend(
        [
            "geometry-block-primitive",
            "geometry-block-subvi",
            "geometry-terminal",
        ]
    )
    vi["summary"]["front_panel_objects"] += 2
    vi["summary"]["block_diagram_nodes"] += 2
    vi["summary"]["terminals"] += 1
    return value


def job() -> dict[str, Any]:
    return {
        "job_id": "component-geometry",
        "status": "ready",
        "component_modified_at": "2026-09-11T05:00:00Z",
        "xml_modified_at": "2026-09-11T05:00:00Z",
        "files": [],
    }


def route_payload(page: Page, model: dict[str, Any]) -> None:
    def model_route(route: Route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(model, ensure_ascii=False),
        )

    page.route("**/api/jobs/component-geometry/model*", model_route)


def require(condition: bool, message: str, diagnostics: dict[str, Any]) -> None:
    if not condition:
        diagnostics["failures"].append(message)


def close(first: float, second: float, tolerance: float = 0.01) -> bool:
    return abs(float(first) - float(second)) <= tolerance


def snapshot(page: Page) -> dict[str, Any]:
    return page.evaluate(
        """ids => {
          const rect = selector => {
            const element = document.querySelector(selector);
            if (!element) return null;
            const value = element.getBoundingClientRect();
            return {width: value.width, height: value.height};
          };
          const font = selector => {
            const element = document.querySelector(selector);
            return element ? Number.parseFloat(getComputedStyle(element).fontSize) : null;
          };
          const E = window.VISemanticEditor;
          const S = E.S;
          return {
            commandbar: rect('.azure-command-bar'),
            navigation: rect('.azure-navigation'),
            context: rect('.azure-context-pane'),
            objectPane: rect('.vi-object-pane'),
            canvas: rect('#model-graph-viewport'),
            fonts: {
              brand: font('.azure-command-bar .brand-copy strong'),
              navigation: font('.navigation-item strong'),
              objectList: font('.vi-list-copy strong'),
              inspector: font('.model-inspector-grid dd'),
              toolbar: font('.vi-canvas-actions .secondary-action'),
            },
            effective: Object.fromEntries(ids.map(id => {
              const item = S.objects.get(id);
              return [id, item ? E.effectiveBounds(item) : null];
            })),
            fallbacks: Object.fromEntries(ids.map(id => [id, S.fallback.get(id) || null])),
            localCount: S.local.size,
            dirtyCount: S.dirty.size,
            report: window.VIComponentGeometry.report(),
            viewport: {width: innerWidth, height: innerHeight},
          };
        }""",
        list(EXPECTED),
    )


def audit_viewport(
    browser,
    viewport: dict[str, int],
    model: dict[str, Any],
    diagnostics: dict[str, Any],
) -> None:
    key = f"{viewport['width']}x{viewport['height']}"
    context = browser.new_context(viewport=viewport)
    page = context.new_page()
    page.on(
        "console",
        lambda message: diagnostics["console_errors"].append(f"{key}: {message.text}")
        if message.type == "error"
        else None,
    )
    page.on(
        "pageerror",
        lambda error: diagnostics["page_errors"].append(f"{key}: {error}"),
    )
    route_payload(page, model)
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_function("() => Boolean(window.viPages && window.viModelGraph)")
    value = job()
    page.evaluate("job => window.viPages.setJob(job, {openModel: true})", value)
    page.evaluate("async job => { await window.viModelGraph.setJob(job); }", value)
    page.wait_for_function(
        """() => Boolean(
          window.VIComponentGeometry?.ready
          && window.VICanvasDensity?.ready
          && window.VISemanticEditor?.S?.vi
        )"""
    )
    page.wait_for_timeout(240)

    front = snapshot(page)
    page.locator('[data-vi-surface="block-diagram"]').click()
    page.wait_for_timeout(220)
    block = snapshot(page)
    diagnostics["viewports"][key] = {"front": front, "block": block}

    require(
        close(front["commandbar"]["height"], 48, 1),
        f"{key}: normal command bar was not restored",
        diagnostics,
    )
    require(
        close(front["navigation"]["width"], 216, 2),
        f"{key}: normal navigation width was not restored",
        diagnostics,
    )
    require(
        close(front["context"]["width"], 292, 2),
        f"{key}: normal context width was not restored",
        diagnostics,
    )
    require(
        close(front["objectPane"]["width"], 224, 2),
        f"{key}: normal object pane width was not restored",
        diagnostics,
    )
    for name, size in front["fonts"].items():
        require(
            size is None or size >= 9,
            f"{key}: {name} UI font is still miniature ({size}px)",
            diagnostics,
        )

    combined = {**front["effective"], **block["effective"]}
    fallbacks = {**front["fallbacks"], **block["fallbacks"]}
    for object_id, expected in EXPECTED.items():
        actual = combined.get(object_id)
        fallback = fallbacks.get(object_id)
        require(actual is not None, f"{key}: {object_id} has no bounds", diagnostics)
        if actual:
            require(
                close(actual["width"], expected["width"])
                and close(actual["height"], expected["height"]),
                f"{key}: {object_id} uses {actual['width']}x{actual['height']} instead of {expected['width']}x{expected['height']}",
                diagnostics,
            )
        require(
            fallback is not None
            and fallback.get("geometry_source") == "kind-specific-fallback",
            f"{key}: {object_id} did not use the safe display-only fallback",
            diagnostics,
        )

    require(
        front["localCount"] == 0
        and front["dirtyCount"] == 0
        and block["localCount"] == 0
        and block["dirtyCount"] == 0,
        f"{key}: geometry audit modified editable VI state",
        diagnostics,
    )
    require(
        front["report"]["profiles"].get("front-boolean", {}).get("fallback", 0) >= 1,
        f"{key}: front Boolean fallback was not audited",
        diagnostics,
    )
    require(
        block["report"]["profiles"].get("block-subvi", {}).get("fallback", 0) >= 1,
        f"{key}: block SubVI fallback was not audited",
        diagnostics,
    )

    page.screenshot(
        path=str(ARTIFACTS / f"component-geometry-{key}.png"),
        full_page=False,
    )
    context.close()


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    model = payload()
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".sandbox-component-geometry-jobs"),
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
        "viewports": {},
    }
    try:
        wait_for_server(process)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            for viewport in VIEWPORTS:
                audit_viewport(browser, viewport, model, diagnostics)
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
                print("COMPONENT_GEOMETRY_APP_LOG=" + output[-4000:].replace("\n", "\\n"))

    (ARTIFACTS / "semantic-component-geometry.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "SEMANTIC_COMPONENT_GEOMETRY_JSON="
        + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
    )
    failed = bool(
        diagnostics["failures"]
        or diagnostics["console_errors"]
        or diagnostics["page_errors"]
    )
    print(
        "SEMANTIC_COMPONENT_GEOMETRY_TEST_FAILED"
        if failed
        else "SEMANTIC_COMPONENT_GEOMETRY_TEST_OK"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
