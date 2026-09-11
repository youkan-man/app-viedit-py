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

from real_vi_component_projection_audit import (  # noqa: E402
    BASE_URL,
    PORT,
    build_candidate,
    job,
    route_payload,
    wait_for_server,
)

ARTIFACTS = Path(
    os.getenv(
        "BUILD_ARTIFACT_DIR",
        str(ROOT / "artifacts" / "real-component-projection-probe"),
    )
)


def load_editor(page: Page, model: dict[str, Any]) -> None:
    route_payload(page, model)
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_function("() => Boolean(window.viPages && window.viModelGraph)")
    value = job()
    page.evaluate("value => window.viPages.setJob(value, {openModel: true})", value)
    page.evaluate("async value => { await window.viModelGraph.setJob(value); }", value)
    page.wait_for_function(
        """() => Boolean(
          window.VIComponentProjection?.ready
          && window.VIComponentAnchors?.ready
          && window.VIComponentFit?.ready
        )"""
    )
    page.locator('[data-vi-surface="block-diagram"]').click()
    page.wait_for_timeout(500)


def capture_coordinates(page: Page) -> dict[str, Any]:
    return page.evaluate(
        """() => {
          const E = window.VISemanticEditor;
          const S = E.S;
          const P = window.VIComponentProjection;
          const A = window.VIComponentAnchors;
          const rect = value => value ? {
            x: value.x,
            y: value.y,
            width: value.width,
            height: value.height,
          } : null;
          const itemRecord = id => {
            const item = S.objects.get(id);
            if (!item) return {id, missing: true};
            const logical = E.effectiveBounds(item);
            const projected = P.projectBounds(item, logical);
            const group = document.querySelector(
              `[data-object-id="${CSS.escape(id)}"]`
            );
            const wrapper = group?.querySelector(
              ':scope > .vi-component-geometry'
            );
            const body = group?.querySelector(
              '.vi-terminal-body,.vi-block-node-body,.vi-front-panel-body'
            );
            return {
              id,
              name: item.name,
              category: item.category,
              kind: item.kind,
              visualKind: item.visual_kind,
              direction: item.direction,
              ownerObjectId: item.owner_object_id || null,
              linkedObjectId: item.linked_object_id || null,
              parentObjectId: item.parent_object_id || null,
              relativeToObjectId: item.bounds?.relative_to_object_id || null,
              sourceCoordinateSpace:
                item.bounds?.source_coordinate_space
                || item.source_coordinate_space
                || null,
              rawBounds: item.bounds || null,
              logical,
              projected,
              projectedCenter: P.projectedCenter(id),
              anchorCenter: A?.projectedCenter?.(id) || null,
              groupTransform: group?.getAttribute('transform') || null,
              wrapperTransform: wrapper?.getAttribute('transform') || null,
              groupData: group ? {...group.dataset} : null,
              bodyBBox: body?.getBBox ? rect(body.getBBox()) : null,
            };
          };
          const logicalCenter = id => {
            const item = S.objects.get(id);
            const bounds = item && E.effectiveBounds(item);
            return bounds ? {
              x: bounds.x + bounds.width / 2,
              y: bounds.y + bounds.height / 2,
            } : null;
          };
          const wires = [];
          for (const [id, wire] of S.wires) {
            const groups = [...document.querySelectorAll(
              `[data-wire-id="${CSS.escape(id)}"]`
            )];
            groups.forEach((group, branchIndex) => {
              const path = group.querySelector('.vi-wire');
              const targetTerminalId = group.dataset.targetTerminalId
                || wire.target_terminal_ids?.[branchIndex]
                || null;
              const sourceId = wire.source_terminal_id || wire.source_object_id;
              const targetId = targetTerminalId
                || wire.target_object_ids?.[branchIndex]
                || null;
              const length = path?.getTotalLength?.() || 0;
              const sourceItem = S.objects.get(sourceId);
              const targetItem = S.objects.get(targetId);
              const sourceOwnerId = sourceItem?.owner_object_id
                || sourceItem?.bounds?.relative_to_object_id
                || sourceItem?.parent_object_id
                || sourceItem?.linked_object_id
                || null;
              const targetOwnerId = targetItem?.owner_object_id
                || targetItem?.bounds?.relative_to_object_id
                || targetItem?.parent_object_id
                || targetItem?.linked_object_id
                || null;
              wires.push({
                id,
                branchIndex,
                targetTerminalId,
                sourceId,
                targetId,
                wire: {
                  sourceTerminalId: wire.source_terminal_id,
                  targetTerminalIds: wire.target_terminal_ids,
                  sourceObjectId: wire.source_object_id,
                  targetObjectIds: wire.target_object_ids,
                  routePoints: wire.route_points,
                },
                groupData: {...group.dataset},
                pathD: path?.getAttribute('d') || null,
                start: length ? path.getPointAtLength(0) : null,
                end: length ? path.getPointAtLength(length) : null,
                sourceProjected: P.projectedCenter(sourceId),
                targetProjected: P.projectedCenter(targetId),
                sourceLogical: logicalCenter(sourceId),
                targetLogical: logicalCenter(targetId),
                source: itemRecord(sourceId),
                target: itemRecord(targetId),
                sourceOwner: itemRecord(sourceOwnerId),
                targetOwner: itemRecord(targetOwnerId),
              });
            });
          }
          return {
            modules: window.VIRuntimeFixes?.modules || [],
            anchorReady: A?.ready === true,
            rootData: {...S.el.modelGraphSvg.dataset},
            wires,
          };
        }"""
    )


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    model, source_meta = build_candidate()
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".real-component-projection-probe-jobs"),
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
    payload: dict[str, Any] = {"source": source_meta}
    try:
        wait_for_server(process)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()
            page.set_default_timeout(15_000)
            load_editor(page, model)
            payload.update(capture_coordinates(page))
            page.screenshot(
                path=str(ARTIFACTS / "real-component-projection-probe.png"),
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
                payload["applicationLogTail"] = output[-2000:]

    output = ARTIFACTS / "real-component-projection-probe.json"
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        "ISSUE19_REAL_COORDINATES="
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )
    print("ISSUE19_REAL_COORDINATE_PROBE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
