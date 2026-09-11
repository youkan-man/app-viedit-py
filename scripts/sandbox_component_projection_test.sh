#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$0")/.."

PYTHON="${ISSUE19_PYTHON:-/home/deploy/.issue19-venv/bin/python}"
export PYTHONPATH="${PYTHONPATH:-$PWD}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/home/deploy/.issue19-browsers}"
ROOT="${BUILD_ARTIFACT_DIR:-$PWD/artifacts/issue19-component-projection}"
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
  printf 'ISSUE19_COMPONENT_PROJECTION_STAGE=%s EXIT=%s\n' "$stage" "$code"
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
  printf 'ISSUE19_STAGE=%s STATUS=%s\n' "$stage" "$status"
  if [[ "$status" -ne 0 ]]; then
    tail -n 180 "$log" || true
    return "$status"
  fi
  grep -E '(_TEST_OK|_AUDIT_OK|passed|_OK$)' "$log" | tail -n 12 || tail -n 8 "$log"
}

[[ -x "$PYTHON" ]] || {
  printf 'Python runtime is missing: %s\n' "$PYTHON" >&2
  exit 2
}

cat .sandbox-source.json 2>/dev/null || true

run_stage syntax bash -lc '
  node --check app/static/pages.js &&
  node --check app/static/vi-editor-runtime-fixes.js &&
  node --check app/static/vi-editor-component-primer.js &&
  node --check app/static/vi-editor-component-projection.js &&
  node --check app/static/vi-editor-component-anchor.js &&
  node --check app/static/vi-editor-component-coordinate-space.js &&
  node --check app/static/vi-editor-component-terminal-visual.js &&
  node --check app/static/vi-editor-component-fit.js &&
  node --check app/static/vi-editor-navigation.js
'

run_stage compile "$PYTHON" -m compileall -q \
  app \
  scripts/semantic_component_projection_test.py \
  scripts/semantic_component_coordinate_space_test.py \
  scripts/semantic_component_terminal_visual_test.py \
  scripts/real_vi_component_projection_audit.py \
  scripts/real_vi_component_projection_probe.py \
  scripts/semantic_ui_density_test.py \
  scripts/semantic_ui_density_memory_test.py \
  scripts/semantic_ui_readability_test.py \
  scripts/semantic_authoritative_browser_test.py

run_stage ruff-app "$PYTHON" -m ruff check app tests
run_stage ruff-scripts "$PYTHON" -m ruff check \
  scripts/semantic_component_projection_test.py \
  scripts/semantic_component_coordinate_space_test.py \
  scripts/semantic_component_terminal_visual_test.py \
  scripts/real_vi_component_projection_audit.py \
  scripts/real_vi_component_projection_probe.py \
  scripts/semantic_ui_density_test.py \
  scripts/semantic_ui_density_memory_test.py \
  scripts/semantic_ui_readability_test.py \
  scripts/semantic_authoritative_browser_test.py \
  --ignore E501
run_stage pytest "$PYTHON" -m pytest -q

export BUILD_ARTIFACT_DIR="$ROOT/synthetic"
run_stage synthetic "$PYTHON" scripts/semantic_component_projection_test.py

export BUILD_ARTIFACT_DIR="$ROOT/coordinate-space"
run_stage coordinate-space "$PYTHON" scripts/semantic_component_coordinate_space_test.py

export BUILD_ARTIFACT_DIR="$ROOT/terminal-visual"
run_stage terminal-visual "$PYTHON" scripts/semantic_component_terminal_visual_test.py

export BUILD_ARTIFACT_DIR="$ROOT/real-vi"
run_stage real-vi "$PYTHON" scripts/real_vi_component_projection_audit.py

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
    root / "synthetic" / "semantic-component-projection.json",
    root / "synthetic" / "component-projection-1365x768.png",
    root / "synthetic" / "component-projection-1440x900.png",
    root / "synthetic" / "component-projection-1920x1080.png",
    root / "coordinate-space" / "semantic-component-coordinate-space.json",
    root / "coordinate-space" / "component-coordinate-space-1440x900.png",
    root / "terminal-visual" / "semantic-component-terminal-visual.json",
    root / "terminal-visual" / "component-terminal-visual-1440x900.png",
    root / "real-vi" / "real-component-projection.json",
]
missing = [
    str(path)
    for path in required
    if not path.is_file() or path.stat().st_size == 0
]
if missing:
    raise SystemExit("missing artifacts: " + ", ".join(missing))

synthetic = json.loads(required[0].read_text(encoding="utf-8"))
coordinate = json.loads(required[4].read_text(encoding="utf-8"))
terminal_visual = json.loads(required[6].read_text(encoding="utf-8"))
real = json.loads(required[-1].read_text(encoding="utf-8"))
for name, payload in (
    ("synthetic", synthetic),
    ("coordinate-space", coordinate),
    ("terminal-visual", terminal_visual),
    ("real", real),
):
    problems = [
        *(payload.get("failures") or []),
        *(payload.get("console_errors") or []),
        *(payload.get("page_errors") or []),
    ]
    if problems:
        raise SystemExit(f"{name} diagnostics contain failures: {problems}")

summary: dict[str, object] = {
    "required": [str(path.relative_to(root)) for path in required],
    "sizes": {
        str(path.relative_to(root)): path.stat().st_size for path in required
    },
    "synthetic_viewports": {},
    "coordinate_space": {
        "initial": coordinate.get("initial"),
        "moved": coordinate.get("moved"),
    },
    "terminal_visual": {
        "initial": terminal_visual.get("initial"),
        "moved": terminal_visual.get("moved"),
    },
    "real_viewports": {},
}
for key, viewport in (synthetic.get("viewports") or {}).items():
    front = viewport.get("front") or {}
    block = viewport.get("block") or {}
    summary["synthetic_viewports"][key] = {
        "front_scale": front.get("scale"),
        "block_scale": block.get("scale"),
        "front_ui": front.get("ui"),
        "block_ui": block.get("ui"),
        "front_projection": front.get("projection"),
        "block_projection": block.get("projection"),
        "wire_endpoint_errors": (viewport.get("wire_before") or {}).get(
            "errors"
        ),
    }
for key, viewport in (real.get("viewports") or {}).items():
    front = viewport.get("front_panel") or {}
    block = viewport.get("block_diagram") or {}
    summary["real_viewports"][key] = {
        "front_scale": front.get("scale"),
        "block_scale": block.get("scale"),
        "front_summary": front.get("summary"),
        "block_summary": block.get("summary"),
        "endpoint_errors": block.get("endpoint_errors"),
    }

(root / "artifact-summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print(
    "ISSUE19_ARTIFACT_SUMMARY="
    + json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
)
PY

stage="complete"
write_status 0
trap - EXIT
printf '%s\n' 'ISSUE19_COMPONENT_PROJECTION_SUITE_OK'
