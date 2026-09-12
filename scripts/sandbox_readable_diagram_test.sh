#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

PYTHON_BIN=${PYTHON_BIN:-python}
RUFF_BIN=${RUFF_BIN:-ruff}
PYTEST_BIN=${PYTEST_BIN:-pytest}

node --check app/static/pages.js
node --check app/static/vi-editor-component-fit.js
node --check app/static/vi-editor-runtime-fixes.js
"$PYTHON_BIN" -m py_compile \
  scripts/semantic_ui_density_test.py \
  scripts/semantic_readable_diagram_test.py \
  scripts/semantic_readable_flow_test.py \
  scripts/readable_diagram_contact_sheet.py \
  tests/test_readable_diagram_density_contract.py \
  tests/test_component_projection_contract.py
"$RUFF_BIN" check \
  scripts/semantic_ui_density_test.py \
  scripts/semantic_readable_diagram_test.py \
  scripts/semantic_readable_flow_test.py \
  scripts/readable_diagram_contact_sheet.py \
  tests/test_readable_diagram_density_contract.py \
  tests/test_component_projection_contract.py
"$PYTEST_BIN" -q
"$PYTHON_BIN" scripts/semantic_ui_density_test.py
"$PYTHON_BIN" scripts/semantic_readable_diagram_test.py
"$PYTHON_BIN" scripts/semantic_readable_flow_test.py
"$PYTHON_BIN" scripts/readable_diagram_contact_sheet.py

printf '%s\n' 'SANDBOX_READABLE_DIAGRAM_TEST_OK'
