from __future__ import annotations

import json
import traceback
from typing import Any

from playwright.sync_api import Page

_ORIGINAL_WAIT_FOR_FUNCTION = Page.wait_for_function


def _diagnostic_wait_for_function(
    page: Page,
    expression: str,
    *args: Any,
    **kwargs: Any,
):
    try:
        return _ORIGINAL_WAIT_FOR_FUNCTION(page, expression, *args, **kwargs)
    except Exception:
        try:
            browser_state = page.evaluate(
                """expression => {
                  const E = window.VISemanticEditor;
                  const S = E?.S;
                  const workflow = window.VIStructureWorkflow;
                  const ids = [
                    'case',
                    'nested-case',
                    'source',
                    'source-term',
                    'node-false',
                    'false-term',
                    'node-true-a',
                    'true-a-term',
                    'node-true-b',
                    'true-b-term',
                    'nested-a',
                    'nested-b',
                  ];
                  const wireRecord = ([id, wire]) => ({
                    id,
                    netId: wire.net_id || null,
                    sourceTerminalId: wire.source_terminal_id || null,
                    targetTerminalIds: [...(wire.target_terminal_ids || [])],
                    terminalIds: [...(wire.terminal_ids || [])],
                    sourceObjectId: wire.source_object_id || null,
                    targetObjectIds: [...(wire.target_object_ids || [])],
                    endpointObjectIds: [...(wire.endpoint_object_ids || [])],
                    routePointCount: (wire.route_points || []).length,
                    hidden: Boolean(wire.hidden_by_structure_frame),
                  });
                  return {
                    expression,
                    surface: S?.surface || null,
                    selected: S?.selected || null,
                    hiddenIds: workflow
                      ? [...workflow.hiddenObjectIds()].sort()
                      : [],
                    wires: S ? [...S.wires.entries()].map(wireRecord) : [],
                    viWires: (S?.vi?.wires || []).map(
                      wire => wireRecord([wire.id, wire])
                    ),
                    inactiveWires: (
                      S?.vi?.inactive_structure_frame_wires || []
                    ).map(wire => wireRecord([wire.id, wire])),
                    allFrameWires: (
                      S?.vi?.all_structure_frame_wires || []
                    ).map(wire => wireRecord([wire.id, wire])),
                    catalogWires: workflow
                      ? [...workflow.runtime.wireCatalog.entries()].map(wireRecord)
                      : [],
                    frames: ids.map(id => {
                      const item = S?.objects.get(id);
                      return item ? {
                        id,
                        surface: item.surface,
                        nativeSurface: item.native_surface || null,
                        parentObjectId: item.parent_object_id || null,
                        ownerObjectId: item.owner_object_id || null,
                        linkedObjectId: item.linked_object_id || null,
                        relativeToObjectId:
                          item.bounds?.relative_to_object_id || null,
                        activeFrameIndex: item.active_frame_index ?? null,
                        hidden: Boolean(item.hidden_by_structure_frame),
                      } : {id, missing: true};
                    }),
                    integrity: S?.vi?.integrity?.structure_frame_runtime || null,
                    summary: S?.vi?.summary || null,
                    renderedWires: [...document.querySelectorAll(
                      '#model-graph-svg [data-wire-id]'
                    )].map(node => node.dataset.wireId),
                  };
                }""",
                expression,
            )
        except Exception as state_error:
            browser_state = {
                "state_error": f"{type(state_error).__name__}: {state_error}"
            }
        print(
            "STRUCTURE_WORKFLOW_WAIT_FAILED_JSON="
            + json.dumps(browser_state, ensure_ascii=False, separators=(",", ":")),
            flush=True,
        )
        raise


Page.wait_for_function = _diagnostic_wait_for_function

from semantic_structure_workflow_test import main  # noqa: E402


def run() -> int:
    try:
        return main()
    except Exception as error:
        frames = [
            frame
            for frame in traceback.extract_tb(error.__traceback__)
            if "/workspace/" in frame.filename
            and "/site-packages/" not in frame.filename
        ]
        payload = {
            "type": type(error).__name__,
            "message": str(error),
            "frames": [
                {
                    "file": frame.filename,
                    "line": frame.lineno,
                    "function": frame.name,
                    "source": frame.line,
                }
                for frame in frames[-12:]
            ],
        }
        print(
            "STRUCTURE_WORKFLOW_UNCAUGHT_JSON="
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            flush=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
