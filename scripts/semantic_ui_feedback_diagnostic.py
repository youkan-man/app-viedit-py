from __future__ import annotations

import importlib.util
import json
import re
import sys
import urllib.parse
from pathlib import Path

from playwright.sync_api import Request, Route

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "scripts" / "semantic_ui_feedback_test.py"
spec = importlib.util.spec_from_file_location("semantic_feedback_target", TARGET)
if spec is None or spec.loader is None:
    raise RuntimeError(f"unable to load {TARGET}")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

original_audit = module.audit_drag_and_save
original_install_routes = module.install_routes


def install_routes(page, payload, job, calls):
    original_install_routes(page, payload, job, calls)

    def components_route(route: Route, request: Request) -> None:
        parsed = urllib.parse.urlparse(request.url)
        suffix = parsed.path.split("/components", 1)[1].strip("/")
        if not suffix:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "job_id": job["job_id"],
                        "total": 0,
                        "offset": 0,
                        "limit": 200,
                        "items": [],
                    }
                ),
            )
            return

        component_id = urllib.parse.unquote(suffix)
        detail = module.detail_for(payload, component_id)
        if request.method == "GET":
            calls["component_get"] += 1
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(detail, ensure_ascii=False),
            )
            return
        if request.method != "PATCH":
            route.fulfill(status=405, body="unsupported")
            return

        body = request.post_data_json
        calls["patches"].append(body)
        item = next(
            record
            for record in payload["vi"]["objects"]
            if record.get("component_id") == component_id
        )
        updated_ids = []
        for update in body.get("updates", []):
            updated_ids.append(update["property_id"])
            if update["property_id"] == detail["bounds"]["property_id"]:
                module.update_object_bounds(item, update["value"])
            elif update["property_id"] == module.property_id(component_id, "label"):
                item["name"] = update["value"]
        calls["revision"] += 1
        job["component_modified_at"] = (
            f"2026-09-10T02:00:{calls['revision']:02d}Z"
        )
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "job": job,
                    "component": module.detail_for(payload, component_id),
                    "updated_properties": updated_ids,
                },
                ensure_ascii=False,
            ),
        )

    page.route(
        re.compile(
            r".*/api/jobs/ui-feedback/components(?:/[^?]+)?(?:\?.*)?$"
        ),
        components_route,
    )


def wrapped(page, payload, calls, diagnostics):
    page.set_default_timeout(8000)
    try:
        return original_audit(page, payload, calls, diagnostics)
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
                selectedModelBounds: selected?.bounds || null,
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


module.install_routes = install_routes
module.audit_drag_and_save = wrapped
raise SystemExit(module.main())
