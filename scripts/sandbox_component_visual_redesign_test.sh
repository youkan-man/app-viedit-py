#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$0")/.."

PYTHON="${ISSUE35_PYTHON:-${ISSUE19_PYTHON:-/home/deploy/.issue19-venv/bin/python}}"
export PYTHONPATH="${PYTHONPATH:-$PWD}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/home/deploy/.issue19-browsers}"
ROOT="${BUILD_ARTIFACT_DIR:-$PWD/artifacts/issue35-component-visuals}"
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
  printf 'ISSUE35_COMPONENT_VISUAL_STAGE=%s EXIT=%s\n' "$stage" "$code"
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
  printf 'ISSUE35_STAGE=%s STATUS=%s\n' "$stage" "$status"
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
  node --check app/static/vi-editor-realism.js &&
  node --check app/static/vi-editor-component-visuals.js &&
  node --check app/static/vi-editor-component-primer.js &&
  node --check app/static/vi-editor-component-projection.js &&
  node --check app/static/vi-editor-compact-resize-handles.js &&
  node --check app/static/vi-editor-wire-stability.js
'

run_stage compile "$PYTHON" -m compileall -q \
  app \
  scripts/semantic_component_visual_redesign_test.py \
  scripts/semantic_component_projection_test.py \
  scripts/semantic_compact_resize_handle_test.py \
  scripts/semantic_wire_stability_test.py \
  scripts/real_vi_component_projection_audit.py \
  scripts/semantic_ui_density_test.py \
  scripts/semantic_ui_readability_test.py \
  scripts/semantic_authoritative_browser_test.py

run_stage ruff-app "$PYTHON" -m ruff check app tests
run_stage ruff-scripts "$PYTHON" -m ruff check \
  scripts/semantic_component_visual_redesign_test.py \
  scripts/semantic_component_projection_test.py \
  scripts/semantic_compact_resize_handle_test.py \
  scripts/semantic_wire_stability_test.py \
  scripts/real_vi_component_projection_audit.py \
  scripts/semantic_ui_density_test.py \
  scripts/semantic_ui_readability_test.py \
  scripts/semantic_authoritative_browser_test.py \
  --ignore E501

run_stage pytest "$PYTHON" -m pytest -q

export BUILD_ARTIFACT_DIR="$ROOT/component-visuals"
run_stage component-visuals "$PYTHON" scripts/semantic_component_visual_redesign_test.py

export BUILD_ARTIFACT_DIR="$ROOT/component-projection"
run_stage component-projection "$PYTHON" scripts/semantic_component_projection_test.py

export BUILD_ARTIFACT_DIR="$ROOT/compact-handles"
run_stage compact-handles "$PYTHON" scripts/semantic_compact_resize_handle_test.py

export BUILD_ARTIFACT_DIR="$ROOT/wire-stability"
run_stage wire-stability "$PYTHON" scripts/semantic_wire_stability_test.py

export BUILD_ARTIFACT_DIR="$ROOT/real-vi"
run_stage real-vi "$PYTHON" scripts/real_vi_component_projection_audit.py

export BUILD_ARTIFACT_DIR="$ROOT/density"
run_stage density "$PYTHON" scripts/semantic_ui_density_test.py

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
    root / "component-visuals" / "semantic-component-visual-redesign.json",
    root / "component-visuals" / "component-visuals-front-1365x768.png",
    root / "component-visuals" / "component-visuals-block-1365x768.png",
    root / "component-visuals" / "component-visuals-front-1440x900.png",
    root / "component-visuals" / "component-visuals-block-1440x900.png",
    root / "component-visuals" / "component-visuals-front-1920x1080.png",
    root / "component-visuals" / "component-visuals-block-1920x1080.png",
    root / "real-vi" / "real-component-projection.json",
]
missing = [
    str(path)
    for path in required
    if not path.is_file() or path.stat().st_size == 0
]
if missing:
    raise SystemExit("missing component visual artifacts: " + ", ".join(missing))

visuals = json.loads(required[0].read_text(encoding="utf-8"))
real = json.loads(required[-1].read_text(encoding="utf-8"))
for name, diagnostics in (("component-visuals", visuals), ("real-vi", real)):
    problems = [
        *(diagnostics.get("failures") or []),
        *(diagnostics.get("console_errors") or []),
        *(diagnostics.get("page_errors") or []),
    ]
    if problems:
        raise SystemExit(f"{name} diagnostics contain failures: {problems!r}")

viewports = visuals.get("viewports") or {}
expected = {"1365x768", "1440x900", "1920x1080"}
if set(viewports) != expected:
    raise SystemExit(f"unexpected component visual viewports: {sorted(viewports)}")

summary = {
    "viewports": sorted(viewports),
    "sizes": {
        str(path.relative_to(root)): path.stat().st_size for path in required
    },
    "front_signatures": {
        key: {
            object_id: record.get("signature")
            for object_id, record in ((value.get("front") or {}).get("records") or {}).items()
        }
        for key, value in viewports.items()
    },
    "block_visuals": {
        key: {
            object_id: record.get("visual")
            for object_id, record in ((value.get("block") or {}).get("records") or {}).items()
        }
        for key, value in viewports.items()
    },
}
(root / "artifact-summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print(
    "ISSUE35_ARTIFACT_SUMMARY="
    + json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
)
PY

stage="complete"
write_status 0
trap - EXIT
printf '%s\n' 'ISSUE35_COMPONENT_VISUAL_SUITE_OK'
