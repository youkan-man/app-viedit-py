#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="${PYTHONPATH:-$PWD}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/opt/vi-ui-browsers}"
export BUILD_ARTIFACT_DIR="${BUILD_ARTIFACT_DIR:-$PWD/artifacts/readability}"
mkdir -p "$BUILD_ARTIFACT_DIR"

node --check app/static/vi-editor-readability-loader.js
node --check app/static/vi-editor-readability.js
node --check app/static/vi-editor-runtime-fixes.js
python -m ruff check tests/test_readability_contract.py
python -m ruff check \
  scripts/semantic_ui_readability_test.py \
  scripts/real_vi_readability_browser_test.py \
  --ignore E501
python -m pytest -q \
  tests/test_readability_contract.py \
  tests/test_canvas_density_contract.py \
  tests/test_canvas_density_browser_memory.py \
  tests/test_canvas_density_collapse_browser.py
python scripts/semantic_ui_density_test.py
python scripts/semantic_ui_density_memory_test.py
python scripts/semantic_ui_readability_test.py
python scripts/real_vi_readability_browser_test.py
printf '%s\n' 'VI_READABILITY_SANDBOX_SUITE_OK'
