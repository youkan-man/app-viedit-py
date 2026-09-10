#!/usr/bin/env bash
set -Eeuo pipefail

cd /workspace
export PLAYWRIGHT_BROWSERS_PATH=/opt/vi-ui-browsers
export PYTHONUNBUFFERED=1
export PYTHONPATH=/workspace
export WORK_ROOT=/workspace/.sandbox-ui-jobs
export BUILD_ARTIFACT_DIR="${BUILD_ARTIFACT_DIR:-/workspace/artifacts/manual}"
mkdir -p "$WORK_ROOT" "$BUILD_ARTIFACT_DIR"

print_failure_summary() {
  local name="$1"
  local log="$2"
  python - "$name" "$log" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

name = sys.argv[1]
path = Path(sys.argv[2])
text = path.read_text(encoding="utf-8", errors="replace")
records = []
for line in text.splitlines():
    if "_JSON=" not in line:
        continue
    _, value = line.split("=", 1)
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        continue
    if isinstance(payload, dict):
        records.append(payload)

payload = records[-1] if records else {}
front = payload.get("front_panel") or payload.get("cluster") or {}
block = payload.get("block_diagram") or {}
responsive = payload.get("responsive") or {}
summary = {
    "stage": name,
    "failures": payload.get("failures") or [],
    "console_errors": payload.get("console_errors") or [],
    "page_errors": payload.get("page_errors") or [],
    "front_canvas": front.get("canvas"),
    "block_canvas": block.get("canvas"),
    "responsive_canvas": responsive.get("canvas"),
    "drag_and_save": payload.get("drag_and_save"),
    "inline_and_actions": payload.get("inline_and_actions"),
    "parser": payload.get("parser"),
    "wire_endpoint_errors": payload.get("wire_endpoint_errors"),
}
print(
    "FAILED_STAGE_DIAGNOSTIC_JSON="
    + json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
)
PY
}

run_logged() {
  local name="$1"
  shift
  local log="$BUILD_ARTIFACT_DIR/${name}.log"
  printf '%s\n' "--- ${name}"
  set +e
  "$@" >"$log" 2>&1
  local status=$?
  set -e
  if (( status != 0 )); then
    printf 'FAILED_STAGE=%s STATUS=%s\n' "$name" "$status"
    grep -vE '(_B64_|_JSON=)' "$log" | tail -n 180 || true
    grep -E 'SAVE_DIAGNOSTIC_JSON=' "$log" | tail -n 1 || true
    print_failure_summary "$name" "$log"
    return "$status"
  fi
  printf 'PASSED_STAGE=%s\n' "$name"
  grep -E '(_TEST_OK|passed|LVKIT_IMPORT_OK)' "$log" \
    | grep -v '_B64_' \
    | tail -n 12 \
    || true
}

python3 -m venv .sandbox-ui-venv
. .sandbox-ui-venv/bin/activate
python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements.txt >/dev/null
python -m pip install \
  httpx==0.28.1 \
  pytest \
  ruff \
  playwright==1.55.0 \
  Pillow >/dev/null

python - <<'PY'
from lvkit.parser import parse_vi
print("LVKIT_IMPORT_OK", parse_vi.__module__)
PY

printf '%s\n' '--- source marker'
cat .sandbox-source.json 2>/dev/null || true
printf '%s\n' '--- static and Python checks'
python -m compileall -q \
  app \
  scripts/semantic_ui_browser_test.py \
  scripts/semantic_ui_interaction_test.py \
  scripts/semantic_ui_layout_probe.py \
  scripts/semantic_ui_round2_test.py \
  scripts/semantic_ui_feedback_test.py \
  scripts/semantic_ui_feedback_diagnostic.py \
  scripts/semantic_authoritative_browser_test.py \
  scripts/real_vi_authoritative_smoke.py
node --check app/static/graph.js
node --check app/static/vi-editor-list.js
node --check app/static/vi-editor-canvas.js
node --check app/static/vi-editor-navigation.js
node --check app/static/vi-editor-enhancements.js
node --check app/static/vi-editor-runtime-fixes.js
node --check app/static/vi-editor-realism.js
node --check app/static/vi-editor-persistence.js
node --check app/static/vi-editor-actions.js
node --check app/static/vi-editor-inline-properties.js
node --check app/static/vi-editor-ui-labels.js
node --check app/static/vi-editor-type-definitions.js
node --check app/static/component-properties-semantic.js
node --check app/static/pages.js
python -m ruff check app tests
python -m ruff check \
  scripts/semantic_ui_browser_test.py \
  scripts/semantic_ui_interaction_test.py \
  scripts/semantic_ui_layout_probe.py \
  scripts/semantic_ui_round2_test.py \
  scripts/semantic_ui_feedback_test.py \
  scripts/semantic_ui_feedback_diagnostic.py \
  scripts/semantic_authoritative_browser_test.py \
  scripts/real_vi_authoritative_smoke.py \
  --ignore E501

run_logged unit-tests python -m pytest -q
run_logged real-vi-authoritative python scripts/real_vi_authoritative_smoke.py
run_logged layout-probe python scripts/semantic_ui_layout_probe.py

python - <<'PY'
import json
import os
from pathlib import Path

artifact_dir = Path(os.environ["BUILD_ARTIFACT_DIR"])
source = json.loads((artifact_dir / "layout-probe.json").read_text(encoding="utf-8"))
summary = {}
for state_name, state in source.items():
    by_selector = {
        item["selector"]: item for item in state.get("elements", []) if item
    }
    summary[state_name] = {
        "surface": state.get("surface"),
        "selected": bool(state.get("selected")),
        "canvas_height": by_selector.get("#model-graph-viewport", {})
        .get("rect", {})
        .get("height"),
        "layout_height": by_selector.get(".vi-editor-layout", {})
        .get("rect", {})
        .get("height"),
        "debug_height": by_selector.get("#vi-source-debug", {})
        .get("rect", {})
        .get("height"),
        "debug_open": by_selector.get("#vi-source-debug", {}).get("open"),
        "debug_body_display": by_selector.get(
            "#vi-source-debug .vi-source-debug-grid", {}
        ).get("display"),
    }
output = artifact_dir / "layout-probe-summary.json"
output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print("SEMANTIC_LAYOUT_PROBE_SUMMARY=" + json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
PY

run_logged browser-layout python scripts/semantic_ui_browser_test.py
run_logged native-interaction python scripts/semantic_ui_interaction_test.py
run_logged semantic-round2 python scripts/semantic_ui_round2_test.py
run_logged reported-feedback python scripts/semantic_ui_feedback_diagnostic.py
run_logged authoritative-graph-typedef python scripts/semantic_authoritative_browser_test.py

python - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path

root = Path(os.environ["BUILD_ARTIFACT_DIR"])

def read_payload(path: Path, marker: str) -> dict:
    for line in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        if line.startswith(marker):
            return json.loads(line.split("=", 1)[1])
    return {}

real = read_payload(root / "real-vi-authoritative.log", "REAL_VI_AUTHORITATIVE_JSON=")
browser = read_payload(root / "authoritative-graph-typedef.log", "AUTHORITATIVE_UI_FINAL_JSON=")
summary = {
    "real_vi": {
        "source": real.get("source"),
        "parser": real.get("parser"),
        "editor": real.get("editor"),
        "sample_wire_endpoints": real.get("sample_wire_endpoints", [])[:4],
        "failures": real.get("failures"),
    },
    "browser": {
        "parser": browser.get("parser"),
        "summary": browser.get("summary"),
        "wire_endpoint_errors": browser.get("wire_endpoint_errors"),
        "type_title": browser.get("type_title"),
        "type_fields": browser.get("type_fields"),
        "failures": browser.get("failures"),
        "console_errors": browser.get("console_errors"),
        "page_errors": browser.get("page_errors"),
    },
}
print("FINAL_SEMANTIC_GRAPH_SUMMARY=" + json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
PY

printf '%s\n' 'SANDBOX_UI_SUITE_OK'
