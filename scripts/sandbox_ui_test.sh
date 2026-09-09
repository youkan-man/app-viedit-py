#!/usr/bin/env bash
set -Eeuo pipefail

cd /workspace
export PLAYWRIGHT_BROWSERS_PATH=/opt/vi-ui-browsers
export PYTHONUNBUFFERED=1

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
python -m compileall -q app scripts/semantic_ui_browser_test.py
node --check app/static/graph.js
node --check app/static/vi-editor-list.js
node --check app/static/vi-editor-canvas.js
python -m ruff check app tests scripts/semantic_ui_browser_test.py
printf '%s\n' '--- unit tests'
python -m pytest -q
printf '%s\n' '--- browser interaction and screenshot audit'
python scripts/semantic_ui_browser_test.py
