#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="${PYTHONPATH:-$PWD}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/opt/vi-ui-browsers}"
export BUILD_ARTIFACT_DIR="${BUILD_ARTIFACT_DIR:-$PWD/artifacts/component-scale}"
mkdir -p "$BUILD_ARTIFACT_DIR"

python -m compileall -q \
  app \
  scripts/semantic_component_scale_browser_test.py \
  scripts/semantic_ui_density_memory_test.py \
  scripts/semantic_ui_feedback_diagnostic.py \
  scripts/semantic_authoritative_browser_test.py \
  scripts/semantic_ui_readability_test.py
node --check app/static/pages.js
node --check app/static/vi-editor-runtime-fixes.js
node --check app/static/vi-editor-component-scale.js
python -m ruff check app tests
python -m ruff check \
  scripts/semantic_component_scale_browser_test.py \
  scripts/semantic_ui_density_memory_test.py \
  scripts/semantic_ui_feedback_diagnostic.py \
  scripts/semantic_authoritative_browser_test.py \
  scripts/semantic_ui_readability_test.py \
  --ignore E501
python -m pytest -q
python scripts/semantic_component_scale_browser_test.py
python scripts/semantic_ui_density_memory_test.py
python scripts/semantic_ui_feedback_diagnostic.py
python scripts/semantic_authoritative_browser_test.py
python scripts/semantic_ui_readability_test.py
printf '%s\n' 'VI_COMPONENT_SCALE_SANDBOX_SUITE_OK'
