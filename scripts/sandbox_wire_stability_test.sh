#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$0")/.."

PYTHON="${ISSUE34_PYTHON:-${ISSUE19_PYTHON:-/home/deploy/.issue19-venv/bin/python}}"
export PYTHONPATH="${PYTHONPATH:-$PWD}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/home/deploy/.issue19-browsers}"
ROOT="${BUILD_ARTIFACT_DIR:-$PWD/artifacts/issue34-wire-stability}"
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
  printf 'ISSUE34_WIRE_STABILITY_STAGE=%s EXIT=%s\n' "$stage" "$code"
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
  printf 'ISSUE34_STAGE=%s STATUS=%s\n' "$stage" "$status"
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
  node --check app/static/vi-editor-wire-stability.js &&
  node --check app/static/vi-editor-component-coordinate-space.js &&
  node --check app/static/vi-editor-integrity.js &&
  node --check app/static/vi-editor-canvas.js
'

run_stage compile "$PYTHON" -m compileall -q \
  app \
  scripts/semantic_wire_stability_test.py \
  scripts/semantic_compact_resize_handle_test.py \
  scripts/semantic_component_projection_test.py \
  scripts/semantic_multi_selection_test.py \
  scripts/semantic_authoritative_browser_test.py \
  scripts/semantic_ui_readability_test.py

run_stage ruff-app "$PYTHON" -m ruff check app tests
run_stage ruff-scripts "$PYTHON" -m ruff check \
  scripts/semantic_wire_stability_test.py \
  scripts/semantic_compact_resize_handle_test.py \
  scripts/semantic_component_projection_test.py \
  scripts/semantic_multi_selection_test.py \
  scripts/semantic_authoritative_browser_test.py \
  scripts/semantic_ui_readability_test.py \
  --ignore E501
run_stage pytest "$PYTHON" -m pytest -q

export BUILD_ARTIFACT_DIR="$ROOT/wire-stability"
run_stage wire-stability "$PYTHON" scripts/semantic_wire_stability_test.py

export BUILD_ARTIFACT_DIR="$ROOT/resize-handles"
run_stage resize-handles "$PYTHON" scripts/semantic_compact_resize_handle_test.py

export BUILD_ARTIFACT_DIR="$ROOT/component-projection"
run_stage component-projection "$PYTHON" scripts/semantic_component_projection_test.py

export BUILD_ARTIFACT_DIR="$ROOT/multi-selection"
run_stage multi-selection "$PYTHON" scripts/semantic_multi_selection_test.py

export BUILD_ARTIFACT_DIR="$ROOT/authoritative"
run_stage authoritative "$PYTHON" scripts/semantic_authoritative_browser_test.py

export BUILD_ARTIFACT_DIR="$ROOT/readability"
run_stage readability "$PYTHON" scripts/semantic_ui_readability_test.py

stage="artifact-verification"
STATUS_ROOT="$ROOT" "$PYTHON" - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path

root = Path(os.environ["STATUS_ROOT"])
required = [
    root / "wire-stability" / "semantic-wire-stability.json",
    root / "wire-stability" / "wire-stability-1365x768.png",
    root / "wire-stability" / "wire-stability-1440x900.png",
    root / "wire-stability" / "wire-stability-1920x1080.png",
]
missing = [
    str(path)
    for path in required
    if not path.is_file() or path.stat().st_size == 0
]
if missing:
    raise SystemExit("missing wire-stability artifacts: " + ", ".join(missing))

payload = json.loads(required[0].read_text(encoding="utf-8"))
problems = [
    *(payload.get("failures") or []),
    *(payload.get("console_errors") or []),
    *(payload.get("page_errors") or []),
]
if problems:
    raise SystemExit("wire-stability diagnostics contain failures: " + repr(problems))

viewports = payload.get("viewports") or {}
expected = {"1365x768", "1440x900", "1920x1080"}
if set(viewports) != expected:
    raise SystemExit(f"unexpected viewport artifacts: {sorted(viewports)}")
required_stages = {
    "initial",
    "repeated-render",
    "readable-fit",
    "overview",
    "focus",
    "zoom-pan",
    "surface-roundtrip",
    "node-move",
    "group-move",
    "group-undo",
    "group-redo",
    "legacy-reroute-repair",
}
for key, value in viewports.items():
    stages = value.get("stages") or {}
    missing_stages = required_stages - set(stages)
    if missing_stages:
        raise SystemExit(f"{key} missing stages: {sorted(missing_stages)}")
    final = value.get("final") or {}
    if len(final.get("records") or []) != 3:
        raise SystemExit(f"{key} did not preserve three wire branches")

summary = {
    "viewports": {},
    "sizes": {
        str(path.relative_to(root)): path.stat().st_size
        for path in required
    },
}
for key, value in viewports.items():
    final = value.get("final") or {}
    summary["viewports"][key] = {
        "branch_count": len(final.get("records") or []),
        "paths": [
            {
                "key": record.get("key"),
                "point_count": record.get("pointCount"),
                "source_error": record.get("sourceError"),
                "target_error": record.get("targetError"),
            }
            for record in final.get("records") or []
        ],
        "local_keys": final.get("localKeys"),
        "dirty_keys": final.get("dirtyKeys"),
    }

(root / "artifact-summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print(
    "ISSUE34_ARTIFACT_SUMMARY="
    + json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
)
PY

stage="complete"
write_status 0
trap - EXIT
printf '%s\n' 'ISSUE34_WIRE_STABILITY_SUITE_OK'
