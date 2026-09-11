#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="${PYTHONPATH:-$PWD}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/opt/vi-ui-browsers}"
export BUILD_ARTIFACT_DIR="${BUILD_ARTIFACT_DIR:-$PWD/artifacts/structure-workflow}"
mkdir -p "$BUILD_ARTIFACT_DIR"

python -m compileall -q \
  app \
  scripts/semantic_structure_net_scenario.py \
  scripts/semantic_structure_workflow_test.py \
  scripts/semantic_structure_frame_audit.py \
  scripts/semantic_authoritative_browser_test.py
node --check app/static/pages.js
node --check app/static/vi-editor-runtime-fixes.js
node --check app/static/vi-editor-structure-workflow.js
python -m ruff check app tests
python -m ruff check \
  scripts/semantic_structure_net_scenario.py \
  scripts/semantic_structure_workflow_test.py \
  scripts/semantic_structure_frame_audit.py \
  scripts/semantic_authoritative_browser_test.py \
  --ignore E501
python -m pytest -q
python scripts/semantic_structure_frame_audit.py
python scripts/semantic_structure_workflow_test.py
python scripts/semantic_authoritative_browser_test.py
python scripts/semantic_ui_density_test.py
python scripts/semantic_ui_density_memory_test.py
python scripts/semantic_ui_readability_test.py
printf '%s\n' 'VI_STRUCTURE_WORKFLOW_SANDBOX_SUITE_OK'
