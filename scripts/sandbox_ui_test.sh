#!/usr/bin/env bash
set -Eeuo pipefail

cd /workspace
export PLAYWRIGHT_BROWSERS_PATH=/opt/vi-ui-browsers
export PYTHONUNBUFFERED=1
export PYTHONPATH=/workspace
export WORK_ROOT=/workspace/.sandbox-ui-jobs
export BUILD_ARTIFACT_DIR="${BUILD_ARTIFACT_DIR:-/workspace/artifacts/manual}"
mkdir -p "$WORK_ROOT" "$BUILD_ARTIFACT_DIR"

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
    tail -n 180 "$log"
    return "$status"
  fi
  printf 'PASSED_STAGE=%s\n' "$name"
  grep -E '(_TEST_OK|_JSON=|passed|PASSED_STAGE=)' "$log" \
    | grep -v '_B64_' \
    | tail -n 12 \
    || true
}

python3 -m venv .sandbox-ui-venv
. .sandbox-ui-venv/bin/activate
python -m pip install --upgrade pip >/dev/null
python -m pip install \
  fastapi==0.128.2 \
  uvicorn==0.48.0 \
  python-multipart==0.0.29 \
  defusedxml==0.7.1 \
  httpx==0.28.1 \
  pytest \
  ruff \
  playwright==1.55.0 \
  Pillow >/dev/null

printf '%s\n' '--- source marker'
cat .sandbox-source.json 2>/dev/null || true
printf '%s\n' '--- static and Python checks'
python -m compileall -q \
  app \
  scripts/semantic_ui_browser_test.py \
  scripts/semantic_ui_interaction_test.py \
  scripts/semantic_ui_layout_probe.py \
  scripts/semantic_ui_round2_test.py
node --check app/static/graph.js
node --check app/static/vi-editor-list.js
node --check app/static/vi-editor-canvas.js
node --check app/static/vi-editor-enhancements.js
node --check app/static/pages.js
python -m ruff check app tests
python -m ruff check \
  scripts/semantic_ui_browser_test.py \
  scripts/semantic_ui_interaction_test.py \
  scripts/semantic_ui_layout_probe.py \
  scripts/semantic_ui_round2_test.py \
  --ignore E501

run_logged unit-tests python -m pytest -q
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

printf '%s\n' 'SANDBOX_UI_SUITE_OK'
