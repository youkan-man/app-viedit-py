#!/usr/bin/env bash
set -Eeuo pipefail

cd /workspace
export PLAYWRIGHT_BROWSERS_PATH=/opt/vi-ui-browsers
export PYTHONUNBUFFERED=1
export PYTHONPATH=/workspace
export WORK_ROOT=/workspace/.sandbox-ui-jobs
export BUILD_ARTIFACT_DIR="${BUILD_ARTIFACT_DIR:-/workspace/artifacts/manual}"
mkdir -p "$WORK_ROOT" "$BUILD_ARTIFACT_DIR"
trap 'printf "%s\n" "--- compact layout probe artifact"; cat "$BUILD_ARTIFACT_DIR/layout-probe-summary.json" 2>/dev/null || true' EXIT

python3 -m venv .sandbox-ui-venv
. .sandbox-ui-venv/bin/activate
python -m pip install --upgrade pip
python -m pip install \
  fastapi==0.128.2 \
  uvicorn==0.48.0 \
  python-multipart==0.0.29 \
  defusedxml==0.7.1 \
  httpx==0.28.1 \
  pytest \
  ruff \
  playwright==1.55.0 \
  Pillow

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
printf '%s\n' '--- unit tests'
python -m pytest -q
printf '%s\n' '--- semantic workspace layout probe'
python scripts/semantic_ui_layout_probe.py
python - <<'PY'
import json
import os
from pathlib import Path

artifact_dir = Path(os.environ["BUILD_ARTIFACT_DIR"])
source = json.loads((artifact_dir / "layout-probe.json").read_text(encoding="utf-8"))
selectors = {
    "shell": "#vi-editor-shell",
    "layout": ".vi-editor-layout",
    "canvas_pane": ".vi-canvas-pane",
    "canvas": "#model-graph-viewport",
    "debug": "#vi-source-debug",
    "debug_grid": "#vi-source-debug .vi-source-debug-grid",
    "context": "#model-context-section",
    "inspector": "#model-inspector",
    "inspector_empty": "#model-inspector-empty",
}
summary = {}
for state_name, state in source.items():
    by_selector = {
        item["selector"]: item for item in state.get("elements", []) if item
    }
    row = {
        "selected": state.get("selected"),
        "surface": state.get("surface"),
        "critical_style": state.get("criticalStyle"),
    }
    for name, selector in selectors.items():
        item = by_selector.get(selector)
        if item:
            row[name] = {
                "rect": item.get("rect"),
                "display": item.get("display"),
                "height": item.get("height"),
                "min_height": item.get("minHeight"),
                "max_height": item.get("maxHeight"),
                "overflow": item.get("overflow"),
                "grid_rows": item.get("gridTemplateRows"),
                "hidden": item.get("hidden"),
                "open": item.get("open"),
            }
    summary[state_name] = row
output = artifact_dir / "layout-probe-summary.json"
output.write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
print("SEMANTIC_LAYOUT_PROBE_SUMMARY=" + json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
PY
printf '%s\n' '--- browser layout and screenshot audit'
python scripts/semantic_ui_browser_test.py
printf '%s\n' '--- native route, navigation, and save persistence audit'
python scripts/semantic_ui_interaction_test.py
printf '%s\n' '--- semantic inspector, history, data-type, and responsive audit'
python scripts/semantic_ui_round2_test.py
