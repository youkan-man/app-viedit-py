from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "scripts" / "semantic_ui_feedback_test.py"
spec = importlib.util.spec_from_file_location("semantic_feedback_target", TARGET)
if spec is None or spec.loader is None:
    raise RuntimeError(f"unable to load {TARGET}")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

original = module.audit_drag_and_save


def wrapped(page, payload, calls, diagnostics):
    page.set_default_timeout(8000)
    try:
        return original(page, payload, calls, diagnostics)
    except Exception as error:
        browser_state = page.evaluate(
            """() => {
              const S = window.VISemanticEditor?.S;
              const selected = S?.objects?.get(S.selected);
              const toastNodes = [...document.querySelectorAll(
                '#toast-container *, [role="alert"], .toast, .notification, .alert'
              )];
              return {
                persistenceReady: window.VIPersistence?.ready,
                persistenceSaving: window.VIPersistence?.runtime?.saving,
                runtimeSaving: S?.saving,
                selected: S?.selected,
                dirty: [...(S?.dirty || [])],
                local: [...(S?.local || new Map()).entries()],
                selectedBounds: selected
                  ? (window.VISemanticEditor.effectiveBounds?.(selected)
                    || window.VISemanticEditor.getBounds?.(selected))
                  : null,
                revision: S?.revision,
                jobModified: S?.job?.component_modified_at,
                modelObjectCount: S?.objects?.size,
                notices: [...new Set(
                  toastNodes.map(node => node.textContent?.trim()).filter(Boolean)
                )],
              };
            }"""
        )
        print(
            "SAVE_DIAGNOSTIC_JSON="
            + json.dumps(
                {
                    "exception": repr(error),
                    "state": browser_state,
                    "calls": calls,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        raise


module.audit_drag_and_save = wrapped
raise SystemExit(module.main())
