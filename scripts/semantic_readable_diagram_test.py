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

PORT = int(os.getenv("VI_READABLE_DIAGRAM_PORT", "8092"))
BASE_URL = f"http://127.0.0.1:{PORT}"
ARTIFACTS = Path(
    os.getenv(
        "BUILD_ARTIFACT_DIR",
        str(ROOT / "artifacts" / "readable-diagram-density"),
    )
)
VIEWPORTS = (
    {"width": 1365, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1920, "height": 1080},
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


def clone_node_fixture(
    payload: dict[str, Any],
    *,
    rows: int,
    columns: int,
    step_x: float,
    step_y: float,
    origin_x: float,
    origin_y: float,
    prefix: str,
) -> dict[str, Any]:
    value = copy.deepcopy(payload)
    vi = value["vi"]
    template = next(
        item
        for item in vi["objects"]
        if item["surface"] == "block-diagram"
        and item["category"] == "node"
        and item.get("kind") == "add"
    )
    additions: list[dict[str, Any]] = []
    for row in range(rows):
        for column in range(columns):
            node = copy.deepcopy(template)
            node_id = f"{prefix}-node-{row:02d}-{column:02d}"
            node["id"] = node_id
            node["component_id"] = node_id
            node["uid"] = f"{prefix}-{row:02d}-{column:02d}"
            node["name"] = f"Stage {column + 1}.{row + 1}"
            node["terminal_ids"] = []
            node["linked_terminal_ids"] = []
            node["wire_ids"] = []
            node["child_object_ids"] = []
            node["owner_object_id"] = None
            node["bounds"] = {
                **(node.get("bounds") or {}),
                "x": origin_x + column * step_x,
                "y": origin_y + row * step_y,
                "width": 40,
                "height": 40,
                "source_property_id": None,
            }
            node["movable"] = False
            node["resizable"] = False
            additions.append(node)

    vi["objects"].extend(additions)
    vi["surfaces"]["block-diagram"] = [
        item["id"]
        for item in vi["objects"]
        if item["surface"] == "block-diagram"
    ]
    vi["summary"]["block_diagram_nodes"] = sum(
        item["surface"] == "block-diagram" and item["category"] == "node"
        for item in vi["objects"]
    )
    return value


def route_payload(page: Page, job_id: str, payload: dict[str, Any]) -> None:
    def route_model(route: Route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload, ensure_ascii=False),
        )

    page.route(f"**/api/jobs/{job_id}/model*", route_model)


def job(job_id: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "status": "ready",
        "component_modified_at": "2026-09-13T00:00:00Z",
        "xml_modified_at": "2026-09-13T00:00:00Z",
        "files": [],
    }


def load_job(page: Page, job_id: str) -> None:
    value = job(job_id)
    page.evaluate("job => window.viPages.setJob(job, {openModel: true})", value)
    page.evaluate("async job => { await window.viModelGraph.setJob(job); }", value)
    page.wait_for_function(
        """() => Boolean(
          window.VIRuntimeFixes?.ready
          && window.VICanvasDensity?.ready
          && window.VIComponentProjection?.ready
          && window.VIComponentFit?.ready
          && window.VISemanticEditor?.S?.vi
        )"""
    )
    page.wait_for_timeout(360)


def switch_to_block_diagram(page: Page) -> None:
    page.locator('[data-vi-surface="block-diagram"]').click()
    page.wait_for_timeout(360)


def state_fingerprint(page: Page) -> dict[str, Any]:
    return page.evaluate(
        """() => {
          const S = window.VISemanticEditor.S;
          return {
            bounds: [...S.objects.values()]
              .map(item => [item.id, JSON.stringify(item.bounds || null)])
              .sort((a, b) => a[0].localeCompare(b[0])),
            local: [...S.local.entries()]
              .map(([id, value]) => [id, JSON.stringify(value)])
              .sort((a, b) => a[0].localeCompare(b[0])),
            dirty: [...S.dirty].sort(),
          };
        }"""
    )


def snapshot(page: Page) -> dict[str, Any]:
    return page.evaluate(
        """() => {
          const S = window.VISemanticEditor.S;
          const fit = window.VIComponentFit;
          const viewport = S.el.modelGraphViewport.getBoundingClientRect();
          const scale = Math.min(
            viewport.width / S.box.width,
            viewport.height / S.box.height,
          );
          const content = fit.projectedContentBounds({
            includeWires: true,
            includeLabels: true,
          });
          const metrics = fit.readabilityMetrics();
          const representative = fit.representativeRecords();
          const add = representative.find(record => record.item.kind === 'add');
          const terminals = fit.currentRecords()
            .filter(record => record.item.category === 'terminal');
          const left = add
            ? terminals.filter(record => record.right <= add.x)
            : [];
          const right = add
            ? terminals.filter(record => record.x >= add.right)
            : [];
          const leftGap = add && left.length
            ? add.x - Math.max(...left.map(record => record.right))
            : null;
          const rightGap = add && right.length
            ? Math.min(...right.map(record => record.x)) - add.right
            : null;
          return {
            viewport: {
              width: viewport.width,
              height: viewport.height,
            },
            box: {...S.box},
            content,
            scale,
            mode: S.el.viEditorShell.dataset.viViewMode,
            lod: S.el.viEditorShell.dataset.viLod,
            reason: S.el.viEditorShell.dataset.viFitReason,
            requestedScale: Number(
              S.el.viEditorShell.dataset.viFitRequestedScale || '0',
            ),
            representativeCount: representative.length,
            metrics,
            leftGapPixels: leftGap == null ? null : leftGap * scale,
            rightGapPixels: rightGap == null ? null : rightGap * scale,
            bendPixels: metrics.bends.medianBendRun == null
              ? null
              : metrics.bends.medianBendRun * scale,
            contentWidthPixels: content ? content.width * scale : null,
            contentHeightPixels: content ? content.height * scale : null,
          };
        }"""
    )


def box_contains(
    box: dict[str, float],
    bounds: dict[str, float],
    tolerance: float = 2,
) -> bool:
    return (
        box["x"] <= bounds["x"] + tolerance
        and box["y"] <= bounds["y"] + tolerance
        and box["x"] + box["width"]
        >= bounds["x"] + bounds["width"] - tolerance
        and box["y"] + box["height"]
        >= bounds["y"] + bounds["height"] - tolerance
    )


def require(condition: bool, message: str, diagnostics: dict[str, Any]) -> None:
    if not condition:
        diagnostics["failures"].append(message)


def exercise_modes(page: Page) -> dict[str, Any]:
    before = state_fingerprint(page)
    readable = snapshot(page)

    page.locator("#model-graph-overview").click()
    page.wait_for_timeout(320)
    overview = snapshot(page)

    page.locator("#model-graph-fit").click()
    page.wait_for_timeout(320)
    restored = snapshot(page)

    selected_id = page.evaluate(
        """() => window.VIComponentFit.representativeRecords()
          .find(record => record.item.kind === 'add')?.item.id
          || window.VIComponentFit.representativeRecords()[0]?.item.id"""
    )
    if selected_id:
        page.evaluate(
            "id => window.VISemanticEditor.select(id, false)",
            selected_id,
        )
        page.wait_for_timeout(120)
        page.locator("#model-graph-focus").click()
        page.wait_for_timeout(320)
    focus = snapshot(page)
    selected_context = page.evaluate(
        """() => {
          const value = window.VIComponentFit.selectedContext();
          return {records: value.records.length, routes: value.routes.length};
        }"""
    )
    page.locator("#model-graph-fit").click()
    page.wait_for_timeout(320)
    final_readable = snapshot(page)
    after = state_fingerprint(page)
    return {
        "before": before,
        "readable": readable,
        "overview": overview,
        "restored": restored,
        "focus": focus,
        "final_readable": final_readable,
        "selected_context": selected_context,
        "after": after,
    }


def audit_viewport(
    browser,
    viewport_size: dict[str, int],
    basic_payload: dict[str, Any],
    medium_payload: dict[str, Any],
    huge_payload: dict[str, Any],
    diagnostics: dict[str, Any],
) -> None:
    key = f"{viewport_size['width']}x{viewport_size['height']}"
    context = browser.new_context(viewport=viewport_size)
    page = context.new_page()
    page.on(
        "console",
        lambda message: diagnostics["console_errors"].append(
            f"{key}: {message.text}"
        )
        if message.type == "error"
        else None,
    )
    page.on(
        "pageerror",
        lambda error: diagnostics["page_errors"].append(f"{key}: {error}"),
    )
    route_payload(page, "readable-basic", basic_payload)
    route_payload(page, "readable-medium", medium_payload)
    route_payload(page, "readable-huge", huge_payload)
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_function("() => Boolean(window.viPages && window.viModelGraph)")

    load_job(page, "readable-basic")
    switch_to_block_diagram(page)
    basic = exercise_modes(page)
    diagnostics["viewports"][key] = {"basic": basic}
    basic_readable = basic["readable"]
    require(
        1.55 <= basic_readable["scale"] <= 1.83,
        f"{key}: basic VI readable scale is outside the bounded policy",
        diagnostics,
    )
    require(
        basic_readable["mode"] == "readable",
        f"{key}: basic VI did not start in readable mode",
        diagnostics,
    )
    basic_gaps = [
        value
        for value in (
            basic_readable["leftGapPixels"],
            basic_readable["rightGapPixels"],
        )
        if value is not None
    ]
    require(
        bool(basic_gaps) and min(basic_gaps) >= 36,
        f"{key}: basic VI node-to-terminal gap is still cramped",
        diagnostics,
    )
    if basic_readable["bendPixels"] is not None:
        require(
            basic_readable["bendPixels"] >= 18,
            f"{key}: basic VI wire bends have too little screen clearance",
            diagnostics,
        )
    require(
        basic["selected_context"]["records"] >= 3,
        f"{key}: focus did not include connected flow records",
        diagnostics,
    )
    require(
        basic["selected_context"]["routes"] >= 1,
        f"{key}: focus did not include connected wire routes",
        diagnostics,
    )
    require(
        basic["before"] == basic["after"],
        f"{key}: density modes changed VI bounds or edit state",
        diagnostics,
    )
    page.screenshot(
        path=str(ARTIFACTS / f"readable-basic-{key}.png"),
        full_page=False,
    )

    load_job(page, "readable-medium")
    switch_to_block_diagram(page)
    medium = snapshot(page)
    diagnostics["viewports"][key]["medium"] = medium
    require(
        10 <= medium["representativeCount"] <= 30,
        f"{key}: medium fixture is outside the 10-30 node acceptance range",
        diagnostics,
    )
    require(
        medium["scale"] >= 1.55,
        f"{key}: medium diagram remains visually compressed",
        diagnostics,
    )
    require(
        (
            medium["contentWidthPixels"] >= medium["viewport"]["width"] * 0.50
            or medium["contentHeightPixels"] >= medium["viewport"]["height"] * 0.42
        ),
        f"{key}: medium diagram still appears as a central blob",
        diagnostics,
    )
    horizontal_gap = medium["metrics"]["spacing"]["medianHorizontalGap"]
    if horizontal_gap is not None:
        require(
            horizontal_gap * medium["scale"] >= 38,
            f"{key}: medium node spacing is below the readable target",
            diagnostics,
        )
    page.screenshot(
        path=str(ARTIFACTS / f"readable-medium-{key}.png"),
        full_page=False,
    )

    load_job(page, "readable-huge")
    switch_to_block_diagram(page)
    huge_readable = snapshot(page)
    page.locator("#model-graph-overview").click()
    page.wait_for_timeout(360)
    huge_overview = snapshot(page)
    diagnostics["viewports"][key]["huge"] = {
        "readable": huge_readable,
        "overview": huge_overview,
    }
    require(
        huge_readable["representativeCount"] >= 300,
        f"{key}: huge fixture did not exercise 300+ objects",
        diagnostics,
    )
    require(
        bool(huge_readable["content"])
        and (
            huge_readable["content"]["width"] > huge_readable["box"]["width"]
            or huge_readable["content"]["height"] > huge_readable["box"]["height"]
        ),
        f"{key}: readable forced the 300+ object diagram into one screen",
        diagnostics,
    )
    require(
        huge_overview["scale"] < huge_readable["scale"] * 0.65,
        f"{key}: overview is not materially different for the huge diagram",
        diagnostics,
    )
    require(
        bool(huge_overview["content"])
        and box_contains(huge_overview["box"], huge_overview["content"]),
        f"{key}: overview does not contain the whole huge diagram",
        diagnostics,
    )
    require(
        huge_overview["mode"] == "overview"
        and huge_readable["mode"] == "readable",
        f"{key}: view modes were not recorded distinctly",
        diagnostics,
    )
    page.screenshot(
        path=str(ARTIFACTS / f"readable-huge-overview-{key}.png"),
        full_page=False,
    )
    context.close()


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    basic_payload = make_payload()
    medium_payload = clone_node_fixture(
        basic_payload,
        rows=3,
        columns=6,
        step_x=48,
        step_y=46,
        origin_x=84,
        origin_y=48,
        prefix="medium",
    )
    huge_payload = clone_node_fixture(
        basic_payload,
        rows=20,
        columns=16,
        step_x=58,
        step_y=48,
        origin_x=60,
        origin_y=44,
        prefix="huge",
    )
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".sandbox-readable-diagram-jobs"),
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
            for viewport_size in VIEWPORTS:
                audit_viewport(
                    browser,
                    viewport_size,
                    basic_payload,
                    medium_payload,
                    huge_payload,
                    diagnostics,
                )
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
                    "READABLE_DIAGRAM_APPLICATION_LOG="
                    + output[-5000:].replace("\n", "\\n")
                )

    output = ARTIFACTS / "semantic-readable-diagram.json"
    output.write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "SEMANTIC_READABLE_DIAGRAM_JSON="
        + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
    )
    if (
        diagnostics["failures"]
        or diagnostics["console_errors"]
        or diagnostics["page_errors"]
    ):
        print("SEMANTIC_READABLE_DIAGRAM_TEST_FAILED")
        return 1
    print("SEMANTIC_READABLE_DIAGRAM_TEST_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
