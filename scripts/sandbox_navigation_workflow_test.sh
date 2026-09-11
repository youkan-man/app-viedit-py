#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$0")/.."

PYTHON="${ISSUE27_PYTHON:-/home/deploy/.issue19-venv/bin/python}"
export PYTHONPATH="${PYTHONPATH:-$PWD}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/home/deploy/.issue19-browsers}"
ROOT="${BUILD_ARTIFACT_DIR:-$PWD/artifacts/issue27-navigation-workflow}"
STATUS="$ROOT/status.json"
rm -rf "$ROOT"
mkdir -p "$ROOT"

stage="setup"
write_status() {
  local code="$1"
  STATUS_FILE="$STATUS" STAGE_NAME="$stage" EXIT_CODE="$code" "$PYTHON" - <<'PY'
import json
import os
from pathlib import Path

Path(os.environ["STATUS_FILE"]).write_text(
    json.dumps(
        {
            "status": "passed" if os.environ["EXIT_CODE"] == "0" else "failed",
            "stage": os.environ["STAGE_NAME"],
            "exit_code": int(os.environ["EXIT_CODE"]),
        },
        separators=(",", ":"),
    ),
    encoding="utf-8",
)
PY
}

finish() {
  local code="$?"
  if [[ "$stage" != "complete" || "$code" -ne 0 ]]; then
    write_status "$code"
  fi
  printf 'ISSUE27_NAVIGATION_STAGE=%s EXIT=%s\n' "$stage" "$code"
  exit "$code"
}
trap finish EXIT

run_stage() {
  stage="$1"
  shift
  local log="$ROOT/$stage.log"
  local code
  set +e
  "$@" >"$log" 2>&1
  code="$?"
  set -e
  printf 'ISSUE27_STAGE=%s STATUS=%s\n' "$stage" "$code"
  if [[ "$code" -ne 0 ]]; then
    tail -n 200 "$log" || true
    return "$code"
  fi
  grep -E '(_TEST_OK|_AUDIT_OK|passed|_OK$)' "$log" | tail -n 14 || tail -n 10 "$log"
}

[[ -x "$PYTHON" ]] || {
  printf 'Python runtime is missing: %s\n' "$PYTHON" >&2
  exit 2
}

cat .sandbox-source.json 2>/dev/null || true

run_stage syntax bash -lc '
  node --check app/static/pages.js &&
  node --check app/static/vi-editor-runtime-fixes.js &&
  node --check app/static/vi-editor-navigation-workflow.js &&
  node --check app/static/vi-editor-navigation-keyboard-guard.js
'

run_stage compile "$PYTHON" -m compileall -q \
  app \
  scripts/semantic_navigation_workflow_test.py

run_stage ruff-app "$PYTHON" -m ruff check app tests
run_stage ruff-scripts "$PYTHON" -m ruff check \
  scripts/semantic_navigation_workflow_test.py \
  --ignore E501
run_stage pytest "$PYTHON" -m pytest -q

export BUILD_ARTIFACT_DIR="$ROOT/navigation"
run_stage navigation "$PYTHON" scripts/semantic_navigation_workflow_test.py

export BUILD_ARTIFACT_DIR="$ROOT/component-projection"
run_stage component-projection "$PYTHON" scripts/semantic_component_projection_test.py

export BUILD_ARTIFACT_DIR="$ROOT/density"
run_stage density "$PYTHON" scripts/semantic_ui_density_test.py

export BUILD_ARTIFACT_DIR="$ROOT/density-memory"
run_stage density-memory "$PYTHON" scripts/semantic_ui_density_memory_test.py

export BUILD_ARTIFACT_DIR="$ROOT/readability"
run_stage readability "$PYTHON" scripts/semantic_ui_readability_test.py

export BUILD_ARTIFACT_DIR="$ROOT/authoritative"
run_stage authoritative "$PYTHON" scripts/semantic_authoritative_browser_test.py

stage="artifact-verification"
STATUS_ROOT="$ROOT" "$PYTHON" - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path

root = Path(os.environ["STATUS_ROOT"])
required = [
    root / "navigation" / "semantic-navigation-workflow.json",
    root / "navigation" / "navigation-workflow-1365x768.png",
    root / "navigation" / "navigation-workflow-1440x900.png",
    root / "navigation" / "navigation-workflow-1920x1080.png",
]
missing = [
    str(path)
    for path in required
    if not path.is_file() or path.stat().st_size == 0
]
if missing:
    raise SystemExit("missing navigation artifacts: " + ", ".join(missing))

navigation = json.loads(required[0].read_text(encoding="utf-8"))
problems = [
    *(navigation.get("failures") or []),
    *(navigation.get("console_errors") or []),
    *(navigation.get("page_errors") or []),
]
if problems:
    raise SystemExit("navigation diagnostics contain failures: " + repr(problems))

summary = {
    "required": [str(path.relative_to(root)) for path in required],
    "sizes": {
        str(path.relative_to(root)): path.stat().st_size for path in required
    },
    "viewports": {
        key: {
            "record_count": value.get("record_count"),
            "selected": (value.get("navigated") or {}).get("selected"),
            "surface": (value.get("navigated") or {}).get("surface"),
            "history_length": len((value.get("history_before") or {}).get("history") or []),
            "back_selected": (value.get("back_b") or {}).get("selected"),
            "forward_selected": (value.get("forward_b") or {}).get("selected"),
            "local_keys": (value.get("final") or {}).get("localKeys"),
            "dirty_keys": (value.get("final") or {}).get("dirtyKeys"),
        }
        for key, value in (navigation.get("viewports") or {}).items()
    },
}
(root / "artifact-summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print(
    "ISSUE27_ARTIFACT_SUMMARY="
    + json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
)
PY

stage="complete"
write_status 0
trap - EXIT
printf '%s\n' 'ISSUE27_NAVIGATION_WORKFLOW_SUITE_OK'
