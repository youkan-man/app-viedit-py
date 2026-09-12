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

from semantic_component_projection_test import (  # noqa: E402
    object_record,
    payload as projection_payload,
)

PORT = int(os.getenv("VI_WIRE_STABILITY_PORT", "8098"))
BASE_URL = f"http://127.0.0.1:{PORT}"
ARTIFACTS = Path(
    os.getenv(
        "BUILD_ARTIFACT_DIR",
        str(ROOT / "artifacts" / "semantic-wire-stability"),
    )
)
VIEWPORTS = (
    {"width": 1365, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1920, "height": 1080},
)


def payload() -> dict[str, Any]:
    value = copy.deepcopy(projection_payload())
    vi = value["vi"]
    objects = vi["objects"]
    by_id = {item["id"]: item for item in objects}
    source = by_id["projection-source"]
    source_terminal = by_id["projection-source-terminal"]
    target_a = by_id["projection-target"]
    target_a_terminal = by_id["projection-target-terminal"]

    target_b = object_record(
        "wire-target-b",
        surface="block-diagram",
        category="node",
        kind="primitive-multiply",
        visual_kind="primitive",
        name="Multiply",
        bounds={"x": 430, "y": 500, "width": 64, "height": 64},
        symbol="×",
        terminal_ids=["wire-target-b-terminal"],
        wire_ids=["wire-multisink"],
    )
    target_b_terminal = object_record(
        "wire-target-b-terminal",
        surface="block-diagram",
        category="terminal",
        kind="terminal",
        visual_kind="terminal",
        name="input B",
        bounds={
            "x": 418,
            "y": 520,
            "width": 24,
            "height": 24,
            "relative_to_object_id": target_b["id"],
            "source_coordinate_space": "absolute-owner-anchored",
            "anchor_x": 0.0,
            "anchor_y": 0.5,
        },
        owner_object_id=target_b["id"],
        wire_ids=["wire-multisink"],
        direction="sink",
        wire_roles=["sink"],
        movable=False,
        resizable=False,
        symbol="",
    )
    structure = object_record(
        "wire-structure",
        surface="block-diagram",
        category="node",
        kind="structure-case",
        visual_kind="structure",
        name="Wire Case",
        bounds={"x": 700, "y": 285, "width": 240, "height": 190},
        symbol="▣",
        terminal_ids=["wire-structure-tunnel"],
        wire_ids=["wire-multisink"],
        structure_frames=[
            {
                "index": 0,
                "label": "True",
                "is_active": True,
                "object_ids": [],
                "node_uids": [],
            },
            {
                "index": 1,
                "label": "False",
                "is_active": False,
                "object_ids": [],
                "node_uids": [],
            },
        ],
        active_frame_index=0,
        active_frame_label="True",
    )
    tunnel = object_record(
        "wire-structure-tunnel",
        surface="block-diagram",
        category="terminal",
        kind="terminal",
        visual_kind="terminal",
        name="Case tunnel",
        bounds={
            "x": 688,
            "y": 380,
            "width": 24,
            "height": 24,
            "relative_to_object_id": structure["id"],
            "source_coordinate_space": "absolute-owner-anchored",
            "anchor_x": 0.0,
            "anchor_y": 0.55,
        },
        owner_object_id=structure["id"],
        wire_ids=["wire-multisink"],
        direction="sink",
        wire_roles=["sink"],
        movable=False,
        resizable=False,
        symbol="",
        is_structure_tunnel=True,
    )

    source["wire_ids"] = ["wire-multisink"]
    source_terminal["wire_ids"] = ["wire-multisink"]
    source_terminal["bounds"].update(
        {
            "relative_to_object_id": source["id"],
            "source_coordinate_space": "absolute-owner-anchored",
            "anchor_x": 1.0,
            "anchor_y": 0.5,
        }
    )
    target_a["wire_ids"] = ["wire-multisink"]
    target_a_terminal["wire_ids"] = ["wire-multisink"]
    target_a_terminal["bounds"].update(
        {
            "relative_to_object_id": target_a["id"],
            "source_coordinate_space": "absolute-owner-anchored",
            "anchor_x": 0.0,
            "anchor_y": 0.5,
        }
    )

    wire = {
        "id": "wire-multisink",
        "name": "Source → three sinks",
        "surface": "block-diagram",
        "source_terminal_id": source_terminal["id"],
        "target_terminal_ids": [
            target_a_terminal["id"],
            target_b_terminal["id"],
            tunnel["id"],
        ],
        "terminal_ids": [
            source_terminal["id"],
            target_a_terminal["id"],
            target_b_terminal["id"],
            tunnel["id"],
        ],
        "source_object_id": source["id"],
        "target_object_ids": [target_a["id"], target_b["id"], structure["id"]],
        "endpoint_object_ids": [
            source["id"],
            target_a["id"],
            target_b["id"],
            structure["id"],
        ],
        # Deliberately malformed-looking legacy points: duplicates, a reversal,
        # near-endpoint values, and diagonal transitions. The display pass must
        # canonicalize these without changing the stored model record.
        "route_points": [
            {"x": 180, "y": 356},
            {"x": 250, "y": 356},
            {"x": 250, "y": 356},
            {"x": 320, "y": 356},
            {"x": 275, "y": 356},
            {"x": 315, "y": 430},
            {"x": 315, "y": 430},
            {"x": 390, "y": 355},
        ],
        "resolved": True,
        "direction_confidence": "wire-stability-fixture",
        "native_uid": "wire-multisink",
        "native_signal_uid": "wire-multisink",
        "net_id": "wire-stability-net",
        "branch_count": 3,
        "target_terminal_count": 3,
        "data_type": "numeric",
        "semantic_source": "wire-stability-browser-fixture",
    }

    objects.extend([target_b, target_b_terminal, structure, tunnel])
    vi["wires"] = [wire]
    vi["nets"] = [
        {
            "id": "wire-stability-net",
            "source_terminal_id": source_terminal["id"],
            "source_object_id": source["id"],
            "target_terminal_ids": list(wire["target_terminal_ids"]),
            "target_object_ids": list(wire["target_object_ids"]),
            "branch_ids": [wire["id"]],
            "branch_count": 3,
            "data_type": "numeric",
        }
    ]
    vi["surfaces"]["block-diagram"] = [
        item["id"] for item in objects if item["surface"] == "block-diagram"
    ]
    vi["summary"].update(
        {
            "block_diagram_nodes": sum(
                item["surface"] == "block-diagram" and item["category"] == "node"
                for item in objects
            ),
            "terminals": sum(item["category"] == "terminal" for item in objects),
            "wires": 1,
            "resolved_wires": 1,
            "wire_nets": 1,
        }
    )
    vi["integrity"] = {"version": 3, "wire_nets": 1, "type_conflicts": 0}
    return value


def job() -> dict[str, Any]:
    return {
        "job_id": "wire-stability",
        "status": "ready",
        "component_modified_at": "2026-09-12T03:50:00Z",
        "xml_modified_at": "2026-09-12T03:50:00Z",
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

    page.route("**/api/jobs/wire-stability/model*", model_route)


def require(condition: bool, message: str, diagnostics: dict[str, Any]) -> None:
    if not condition:
        diagnostics["failures"].append(message)


def close_point(
    first: dict[str, float] | None,
    second: dict[str, float] | None,
    tolerance: float = 1,
) -> bool:
    if not first or not second:
        return False
    return (
        abs(float(first["x"]) - float(second["x"])) <= tolerance
        and abs(float(first["y"]) - float(second["y"])) <= tolerance
    )


def install_audit(page: Page) -> None:
    page.evaluate(
        """() => {
          const point = value => value ? {x: value.x, y: value.y} : null;
          const distance = (a, b) => !a || !b
            ? Number.POSITIVE_INFINITY
            : Math.hypot(a.x - b.x, a.y - b.y);
          const keyFor = group => [
            group.dataset.wireId || '',
            group.dataset.branchIndex || '0',
            group.dataset.targetTerminalId || '',
          ].join('::');
          const inspect = () => {
            const S = window.VISemanticEditor.S;
            const P = window.VIComponentProjection;
            const W = window.VIWireStability;
            const groups = [...document.querySelectorAll(
              '#model-graph-svg .vi-wire-group[data-wire-id]'
            )];
            const records = groups.map(group => {
              const wire = S.wires.get(group.dataset.wireId);
              const branchIndex = Math.max(
                0,
                Number.parseInt(group.dataset.branchIndex || '0', 10) || 0,
              );
              const targetTerminalId = group.dataset.targetTerminalId
                || wire?.target_terminal_ids?.[branchIndex]
                || null;
              const targetObjectId = wire?.target_object_ids?.[branchIndex] || null;
              const points = W.projectedWirePoints(
                wire,
                targetTerminalId,
                targetObjectId,
              );
              const visible = [...group.querySelectorAll(':scope > .vi-wire')];
              const hits = [...group.querySelectorAll(':scope > .vi-wire-hit')];
              const path = visible[0] || null;
              const length = path?.getTotalLength?.() || 0;
              const start = length ? point(path.getPointAtLength(0)) : null;
              const end = length ? point(path.getPointAtLength(length)) : null;
              const source = P.projectedCenter(
                wire?.source_terminal_id || wire?.source_object_id,
              );
              const target = P.projectedCenter(targetTerminalId || targetObjectId);
              const zeroSegments = points.slice(1).filter(
                (value, index) => distance(points[index], value) <= 0.01,
              ).length;
              const diagonalSegments = points.slice(1).filter((value, index) => {
                const previous = points[index];
                return Math.abs(previous.x - value.x) > 0.01
                  && Math.abs(previous.y - value.y) > 0.01;
              }).length;
              const repeatedVertices = points.filter((value, index) => (
                points.slice(0, index).some(previous => distance(previous, value) <= 0.01)
              )).length;
              const immediateBacktracks = points.slice(2).filter((value, index) => {
                const first = points[index];
                const middle = points[index + 1];
                const horizontal = Math.abs(first.y - middle.y) <= 0.01
                  && Math.abs(middle.y - value.y) <= 0.01;
                const vertical = Math.abs(first.x - middle.x) <= 0.01
                  && Math.abs(middle.x - value.x) <= 0.01;
                if (!horizontal && !vertical) return false;
                const firstDelta = horizontal
                  ? middle.x - first.x
                  : middle.y - first.y;
                const secondDelta = horizontal
                  ? value.x - middle.x
                  : value.y - middle.y;
                return firstDelta * secondDelta <= 0;
              }).length;
              return {
                key: keyFor(group),
                branchIndex,
                targetTerminalId,
                visibleCount: visible.length,
                hitCount: hits.length,
                visibleD: visible[0]?.getAttribute('d') || '',
                hitD: hits[0]?.getAttribute('d') || '',
                pointCount: points.length,
                points,
                start,
                end,
                source: point(source),
                target: point(target),
                sourceError: distance(start, source),
                targetError: distance(end, target),
                zeroSegments,
                diagonalSegments,
                repeatedVertices,
                immediateBacktracks,
                stable: group.dataset.wireStable || null,
                stablePointCount: Number(group.dataset.stablePointCount || 0),
                hidden: group.getAttribute('visibility') === 'hidden',
              };
            });
            const keys = records.map(record => record.key);
            return {
              runtimeReady: window.VIRuntimeFixes?.ready === true,
              wireReady: W?.ready === true,
              moduleLoaded: window.VIRuntimeFixes?.modules?.includes(
                'vi-editor-wire-stability'
              ) === true,
              surface: S.surface,
              records,
              duplicateKeys: keys.filter((value, index) => keys.indexOf(value) !== index),
              signature: records.map(record => `${record.key}:${record.visibleD}`).join('|'),
              localKeys: [...S.local.keys()].sort(),
              dirtyKeys: [...S.dirty].sort(),
              storedRoutePoints: (S.wires.get('wire-multisink')?.route_points || [])
                .map(value => ({...value})),
            };
          };
          const frames = async count => {
            const values = [];
            for (let index = 0; index < count; index += 1) {
              await new Promise(resolve => requestAnimationFrame(resolve));
              values.push(inspect());
            }
            return values;
          };
          window.__wireStabilityAudit = {inspect, frames};
        }"""
    )


def validate_snapshot(
    value: dict[str, Any],
    stage: str,
    diagnostics: dict[str, Any],
) -> None:
    require(value["runtimeReady"], f"{stage}: runtime manifest is not ready", diagnostics)
    require(value["wireReady"], f"{stage}: wire stability runtime is not ready", diagnostics)
    require(value["moduleLoaded"], f"{stage}: wire stability module is absent", diagnostics)
    require(value["surface"] == "block-diagram", f"{stage}: wrong surface", diagnostics)
    require(len(value["records"]) == 3, f"{stage}: expected three wire branches", diagnostics)
    require(not value["duplicateKeys"], f"{stage}: duplicate branch groups remain", diagnostics)
    for record in value["records"]:
        prefix = f"{stage} branch {record['branchIndex']}"
        require(record["visibleCount"] == 1, f"{prefix}: visible path count is wrong", diagnostics)
        require(record["hitCount"] == 1, f"{prefix}: hit path count is wrong", diagnostics)
        require(record["visibleD"] == record["hitD"], f"{prefix}: visible/hit paths differ", diagnostics)
        require(bool(record["visibleD"]), f"{prefix}: path is empty", diagnostics)
        require("NaN" not in record["visibleD"], f"{prefix}: path contains NaN", diagnostics)
        require(" L " not in f" {record['visibleD']} ", f"{prefix}: path is diagonal", diagnostics)
        require(record["pointCount"] >= 2, f"{prefix}: too few points", diagnostics)
        require(record["stable"] == "true", f"{prefix}: stable marker is missing", diagnostics)
        require(not record["hidden"], f"{prefix}: valid route is hidden", diagnostics)
        require(record["zeroSegments"] == 0, f"{prefix}: zero segment remains", diagnostics)
        require(record["diagonalSegments"] == 0, f"{prefix}: diagonal segment remains", diagnostics)
        require(record["repeatedVertices"] == 0, f"{prefix}: repeated vertex remains", diagnostics)
        require(record["immediateBacktracks"] == 0, f"{prefix}: backtracking remains", diagnostics)
        require(record["sourceError"] <= 1, f"{prefix}: source endpoint detached", diagnostics)
        require(record["targetError"] <= 1, f"{prefix}: target endpoint detached", diagnostics)
        require(
            close_point(record["start"], record["source"])
            and close_point(record["end"], record["target"]),
            f"{prefix}: SVG endpoints do not match projected terminals",
            diagnostics,
        )


def validate_frames(
    frames: list[dict[str, Any]],
    stage: str,
    diagnostics: dict[str, Any],
) -> None:
    require(bool(frames), f"{stage}: no animation-frame samples", diagnostics)
    for index, frame in enumerate(frames):
        validate_snapshot(frame, f"{stage}/frame-{index}", diagnostics)
    signatures = {frame["signature"] for frame in frames}
    require(
        len(signatures) == 1,
        f"{stage}: path changed across consecutive painted frames",
        diagnostics,
    )


def capture_stage(
    page: Page,
    name: str,
    diagnostics: dict[str, Any],
    expression: str | None = None,
    *,
    immediate: bool = True,
) -> dict[str, Any]:
    if expression:
        first = page.evaluate(
            f"""() => {{
              {expression}
              return window.__wireStabilityAudit.inspect();
            }}"""
        )
    else:
        first = page.evaluate("() => window.__wireStabilityAudit.inspect()")
    if immediate:
        validate_snapshot(first, f"{name}/immediate", diagnostics)
    frames = page.evaluate("async () => window.__wireStabilityAudit.frames(5)")
    validate_frames(frames, name, diagnostics)
    result = {"immediate": first, "frames": frames}
    diagnostics["stages"][name] = result
    return result


def run_viewport(
    browser,
    viewport: dict[str, int],
    value: dict[str, Any],
    diagnostics: dict[str, Any],
) -> None:
    key = f"{viewport['width']}x{viewport['height']}"
    context = browser.new_context(viewport=viewport)
    page = context.new_page()
    page.set_default_timeout(20_000)
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
    route_payload(page, value)
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_function("() => Boolean(window.viPages && window.viModelGraph)")
    active_job = job()
    page.evaluate("value => window.viPages.setJob(value, {openModel: true})", active_job)
    page.evaluate("async value => { await window.viModelGraph.setJob(value); }", active_job)
    page.wait_for_function(
        """() => Boolean(
          window.VIRuntimeFixes?.ready
          && window.VIWireStability?.ready
          && window.VICompactResizeHandles?.ready
          && window.VIMultiSelection?.ready
          && window.VIComponentFit?.ready
          && window.VISemanticEditor?.S?.vi
        )"""
    )
    page.locator('[data-vi-surface="block-diagram"]').click()
    page.wait_for_timeout(300)
    install_audit(page)

    viewport_diagnostics: dict[str, Any] = {"stages": {}}
    diagnostics["viewports"][key] = viewport_diagnostics
    original_route_points = copy.deepcopy(value["vi"]["wires"][0]["route_points"])

    capture_stage(page, "initial", viewport_diagnostics)
    capture_stage(
        page,
        "repeated-render",
        viewport_diagnostics,
        """
          const E = window.VISemanticEditor;
          E.renderCanvas();
          E.renderCanvas();
          E.renderAll(false);
        """,
    )
    capture_stage(
        page,
        "readable-fit",
        viewport_diagnostics,
        "window.VICanvasDensity.fit('readable');",
    )
    capture_stage(
        page,
        "overview",
        viewport_diagnostics,
        "window.VICanvasDensity.fit('overview');",
    )
    capture_stage(
        page,
        "focus",
        viewport_diagnostics,
        """
          window.VISemanticEditor.select('projection-source', true);
          window.VICanvasDensity.fit('focus');
        """,
    )
    before_zoom = page.evaluate("() => window.__wireStabilityAudit.inspect()")
    zoom = capture_stage(
        page,
        "zoom-pan",
        viewport_diagnostics,
        """
          const D = window.VICanvasDensity;
          const S = window.VISemanticEditor.S;
          D.zoomAt(1.25);
          D.applyBox({
            x: S.box.x + 28,
            y: S.box.y + 17,
            width: S.box.width,
            height: S.box.height,
          }, 'manual');
        """,
    )
    require(
        before_zoom["signature"] == zoom["immediate"]["signature"],
        f"{key}: Zoom/Pan changed world-coordinate wire geometry",
        diagnostics,
    )

    page.locator('[data-vi-surface="front-panel"]').click()
    page.wait_for_timeout(180)
    page.locator('[data-vi-surface="block-diagram"]').click()
    page.wait_for_timeout(260)
    install_audit(page)
    capture_stage(page, "surface-roundtrip", viewport_diagnostics)

    moved = capture_stage(
        page,
        "node-move",
        viewport_diagnostics,
        """
          const E = window.VISemanticEditor;
          const S = E.S;
          const set = (id, x, y, width, height) => {
            S.local.set(id, {x, y, width, height});
            S.dirty.add(id);
          };
          set('projection-source', 175, 345, 82, 76);
          set('projection-target', 465, 335, 66, 64);
          set('wire-target-b', 470, 525, 70, 68);
          E.renderCanvas();
        """,
    )
    require(
        moved["immediate"]["localKeys"] == [
            "projection-source",
            "projection-target",
            "wire-target-b",
        ],
        f"{key}: node move created unexpected local geometry",
        diagnostics,
    )

    capture_stage(
        page,
        "group-move",
        viewport_diagnostics,
        """
          window.VIMultiSelection.setSelection(
            ['projection-source', 'projection-target', 'wire-target-b'],
            'wire-target-b'
          );
          window.VIMultiSelection.moveSelectionBy(22, 14, 'wire stability group move');
          window.VISemanticEditor.renderCanvas();
        """,
    )
    capture_stage(
        page,
        "group-undo",
        viewport_diagnostics,
        """
          window.VIMultiSelection.undo();
          window.VISemanticEditor.renderCanvas();
        """,
    )
    capture_stage(
        page,
        "group-redo",
        viewport_diagnostics,
        """
          window.VIMultiSelection.redo();
          window.VISemanticEditor.renderCanvas();
        """,
    )

    page.evaluate(
        """() => {
          document.querySelectorAll(
            '#model-graph-svg .vi-wire-group[data-wire-id]'
          ).forEach(group => {
            group.querySelector(':scope > .vi-wire')
              ?.setAttribute('d', 'M 0 0 L 10 10');
            group.querySelector(':scope > .vi-wire-hit')
              ?.setAttribute('d', 'M 20 20 L 30 30');
          });
        }"""
    )
    legacy_frames = page.evaluate("async () => window.__wireStabilityAudit.frames(5)")
    validate_frames(legacy_frames, "legacy-reroute-repair", viewport_diagnostics)
    viewport_diagnostics["stages"]["legacy-reroute-repair"] = {
        "frames": legacy_frames
    }

    final = page.evaluate("() => window.__wireStabilityAudit.inspect()")
    require(
        final["storedRoutePoints"] == original_route_points,
        f"{key}: display routing changed stored route_points",
        diagnostics,
    )
    require(
        set(final["localKeys"])
        == {"projection-source", "projection-target", "wire-target-b"},
        f"{key}: routing created unexpected local geometry",
        diagnostics,
    )
    require(
        set(final["dirtyKeys"])
        == {"projection-source", "projection-target", "wire-target-b"},
        f"{key}: routing dirtied non-moved records",
        diagnostics,
    )
    viewport_diagnostics["final"] = final
    page.screenshot(
        path=str(ARTIFACTS / f"wire-stability-{key}.png"),
        full_page=False,
    )
    context.close()


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    value = payload()
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".wire-stability-jobs"),
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
                run_viewport(browser, viewport, value, diagnostics)
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

    output = ARTIFACTS / "semantic-wire-stability.json"
    output.write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "SEMANTIC_WIRE_STABILITY_JSON="
        + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
    )
    failed = bool(
        diagnostics["failures"]
        or diagnostics["console_errors"]
        or diagnostics["page_errors"]
    )
    print(
        "SEMANTIC_WIRE_STABILITY_TEST_FAILED"
        if failed
        else "SEMANTIC_WIRE_STABILITY_TEST_OK"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
