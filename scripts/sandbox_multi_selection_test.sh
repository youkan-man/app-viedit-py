#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$0")/.."

PYTHON="${ISSUE30_PYTHON:-${ISSUE19_PYTHON:-/home/deploy/.issue19-venv/bin/python}}"
export PYTHONPATH="${PYTHONPATH:-$PWD}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/home/deploy/.issue19-browsers}"
ROOT="${BUILD_ARTIFACT_DIR:-$PWD/artifacts/issue30-multi-selection}"
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
  printf 'ISSUE30_MULTI_SELECTION_STAGE=%s EXIT=%s\n' "$stage" "$code"
  exit "$code"
}
trap finish EXIT

run_stage() {
  stage="$1"
  shift
  local log="$ROOT/$stage.log"
  local status
  set +e
  "$@" >"$log" 2>&1
  status="$?"
  set -e
  printf 'ISSUE30_STAGE=%s STATUS=%s\n' "$stage" "$status"
  if [[ "$status" -ne 0 ]]; then
    tail -n 220 "$log" || true
    return "$status"
  fi
  grep -E '(_TEST_OK|_AUDIT_OK|passed|_OK$)' "$log" | tail -n 16 || tail -n 10 "$log"
}

[[ -x "$PYTHON" ]] || {
  printf 'Python runtime is missing: %s\n' "$PYTHON" >&2
  exit 2
}

cat .sandbox-source.json 2>/dev/null || true

run_stage syntax bash -lc '
  node --check app/static/pages.js &&
  node --check app/static/vi-editor-runtime-fixes.js &&
  node --check app/static/vi-editor-multi-selection.js &&
  node --check app/static/vi-editor-navigation.js &&
  node --check app/static/vi-editor-navigation-workflow.js &&
  node --check app/static/vi-editor-navigation-keyboard-guard.js &&
  node --check app/static/vi-editor-navigation-history-stability.js
'

run_stage compile "$PYTHON" -m compileall -q \
  app \
  scripts/semantic_multi_selection_test.py \
  scripts/semantic_navigation_workflow_test.py \
  scripts/semantic_navigation_history_stability_test.py \
  scripts/semantic_component_projection_test.py \
  scripts/semantic_ui_density_test.py \
  scripts/semantic_ui_density_memory_test.py \
  scripts/semantic_ui_readability_test.py \
  scripts/semantic_authoritative_browser_test.py

run_stage ruff-app "$PYTHON" -m ruff check app tests
run_stage ruff-scripts "$PYTHON" -m ruff check \
  scripts/semantic_multi_selection_test.py \
  scripts/semantic_navigation_workflow_test.py \
  scripts/semantic_navigation_history_stability_test.py \
  scripts/semantic_component_projection_test.py \
  scripts/semantic_ui_density_test.py \
  scripts/semantic_ui_density_memory_test.py \
  scripts/semantic_ui_readability_test.py \
  scripts/semantic_authoritative_browser_test.py \
  --ignore E501

run_stage pytest "$PYTHON" -m pytest -q

export BUILD_ARTIFACT_DIR="$ROOT/multi-selection"
run_stage multi-selection "$PYTHON" scripts/semantic_multi_selection_test.py

export BUILD_ARTIFACT_DIR="$ROOT/navigation-workflow"
run_stage navigation-workflow "$PYTHON" scripts/semantic_navigation_workflow_test.py

export BUILD_ARTIFACT_DIR="$ROOT/navigation-history"
run_stage navigation-history "$PYTHON" scripts/semantic_navigation_history_stability_test.py

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
    root / "multi-selection" / "semantic-multi-selection.json",
    root / "multi-selection" / "multi-selection-1365x768.png",
    root / "multi-selection" / "multi-selection-1440x900.png",
    root / "multi-selection" / "multi-selection-1920x1080.png",
]
missing = [
    str(path)
    for path in required
    if not path.is_file() or path.stat().st_size == 0
]
if missing:
    raise SystemExit("missing multi-selection artifacts: " + ", ".join(missing))

payload = json.loads(required[0].read_text(encoding="utf-8"))
problems = [
    *(payload.get("failures") or []),
    *(payload.get("console_errors") or []),
    *(payload.get("page_errors") or []),
]
if problems:
    raise SystemExit("multi-selection diagnostics contain failures: " + repr(problems))
if int(payload.get("fixture_object_count") or 0) < 300:
    raise SystemExit("multi-selection fixture contains fewer than 300 objects")
viewports = payload.get("viewports") or {}
expected = {"1365x768", "1440x900", "1920x1080"}
if set(viewports) != expected:
    raise SystemExit(f"unexpected viewport artifacts: {sorted(viewports)}")

summary = {
    "fixture_object_count": payload.get("fixture_object_count"),
    "viewports": sorted(viewports),
    "sizes": {
        str(path.relative_to(root)): path.stat().st_size
        for path in required
    },
    "selection_counts": {
        key: len((value.get("selected") or {}).get("selectedIds") or [])
        for key, value in viewports.items()
    },
    "history_entries": {
        key: ((value.get("after_drag") or {}).get("historyTop") or {}).get("entries")
        for key, value in viewports.items()
    },
}
(root / "artifact-summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print(
    "ISSUE30_ARTIFACT_SUMMARY="
    + json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
)
PY

stage="complete"
write_status 0
trap - EXIT
printf '%s\n' 'ISSUE30_MULTI_SELECTION_SUITE_OK'
