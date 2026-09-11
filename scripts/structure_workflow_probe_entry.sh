#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="${PYTHONPATH:-$PWD}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/opt/vi-ui-browsers}"
export BUILD_ARTIFACT_DIR="${BUILD_ARTIFACT_DIR:-$PWD/artifacts/structure-workflow-probe}"
mkdir -p "$BUILD_ARTIFACT_DIR"
node --check app/static/vi-editor-structure-workflow.js
node --check app/static/vi-editor-structure-workflow-catalog-fix.js
node --check app/static/vi-editor-structure-workflow-probe.js
python -m ruff check \
  scripts/semantic_structure_net_scenario.py \
  scripts/semantic_structure_workflow_test.py \
  scripts/semantic_structure_workflow_probe_test.py \
  --ignore E501
python scripts/semantic_structure_workflow_probe_test.py
