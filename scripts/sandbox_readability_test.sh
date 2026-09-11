#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="${PYTHONPATH:-$PWD}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/opt/vi-ui-browsers}"
export BUILD_ARTIFACT_DIR="${BUILD_ARTIFACT_DIR:-$PWD/artifacts/readability}"
mkdir -p "$BUILD_ARTIFACT_DIR"

stage_results="$BUILD_ARTIFACT_DIR/readability-stage-results.tsv"
: >"$stage_results"

run_stage() {
  local name="$1"
  shift
  local log="$BUILD_ARTIFACT_DIR/stage-${name}.log"
  printf 'READABILITY_STAGE_START=%s\n' "$name"
  set +e
  "$@" >"$log" 2>&1
  local status=$?
  set -e
  printf '%s\t%s\t%s\n' "$name" "$status" "$log" >>"$stage_results"
  if (( status != 0 )); then
    printf 'READABILITY_STAGE_FAILED=%s STATUS=%s LOG=%s\n' \
      "$name" "$status" "$log" >&2
    tail -n 140 "$log" >&2 || true
    exit "$status"
  fi
  printf 'READABILITY_STAGE_OK=%s\n' "$name"
  grep -E '(_TEST_OK|passed|VI_READABILITY_|LVKIT_|AUTHORITATIVE_)' "$log" \
    | tail -n 12 \
    || true
}

run_stage compile-python python -m compileall -q \
  app \
  scripts/semantic_ui_readability_test.py \
  scripts/semantic_ui_readability_scale_test.py \
  scripts/real_vi_readability_browser_test.py
run_stage syntax-pages node --check app/static/pages.js
run_stage syntax-runtime node --check app/static/vi-editor-runtime-fixes.js
run_stage syntax-readability node --check app/static/vi-editor-readability.js
run_stage ruff-project python -m ruff check app tests
run_stage ruff-readability-scripts python -m ruff check \
  scripts/semantic_ui_readability_test.py \
  scripts/semantic_ui_readability_scale_test.py \
  scripts/real_vi_readability_browser_test.py \
  --ignore E501
run_stage pytest python -m pytest -q
run_stage density python scripts/semantic_ui_density_test.py
run_stage density-memory python scripts/semantic_ui_density_memory_test.py
run_stage readability-synthetic python scripts/semantic_ui_readability_test.py
run_stage readability-scale python scripts/semantic_ui_readability_scale_test.py
run_stage authoritative-browser python scripts/semantic_authoritative_browser_test.py
run_stage readability-real-vi python scripts/real_vi_readability_browser_test.py

python - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path

root = Path(os.environ["BUILD_ARTIFACT_DIR"])
synthetic = json.loads(
    (root / "semantic-ui-readability.json").read_text(encoding="utf-8")
)
scale = json.loads(
    (root / "semantic-ui-readability-scale.json").read_text(encoding="utf-8")
)
real = json.loads((root / "real-vi-readability.json").read_text(encoding="utf-8"))
for name, payload in (("synthetic", synthetic), ("scale", scale), ("real", real)):
    errors = [
        *(payload.get("failures") or []),
        *(payload.get("console_errors") or []),
        *(payload.get("page_errors") or []),
    ]
    if errors:
        raise SystemExit(f"{name} diagnostics contain errors: {errors}")

summary = {
    "pytest": "passed",
    "synthetic_viewports": sorted((synthetic.get("viewports") or {}).keys()),
    "synthetic": {
        key: {
            "suppressed": (value.get("initial") or {}).get("suppressed"),
            "visible_overlaps": (
                (value.get("initial") or {}).get("metrics") or {}
            ).get("overlaps"),
        }
        for key, value in (synthetic.get("viewports") or {}).items()
    },
    "scale": {
        "stress_objects": scale.get("stress_objects"),
        "viewport_culling": scale.get("viewport_culling"),
        "stress_region": scale.get("stress_region"),
        "settled": scale.get("settled"),
    },
    "real_vi": {
        "source": real.get("source"),
        "semantic": real.get("semantic"),
        "viewports": {
            key: {
                "block_overlaps": (
                    (value.get("block_diagram") or {}).get("metrics") or {}
                ).get("overlaps"),
                "block_suppressed": (
                    value.get("block_diagram") or {}
                ).get("suppressed"),
                "network": value.get("network"),
                "front_overlaps": (
                    (value.get("front_panel") or {}).get("metrics") or {}
                ).get("overlaps"),
            }
            for key, value in (real.get("viewports") or {}).items()
        },
    },
}
print(
    "READABILITY_FINAL_SUMMARY="
    + json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
)
PY

printf '%s\n' 'READABILITY_STAGE_RESULTS_BEGIN'
cat "$stage_results"
printf '%s\n' 'READABILITY_STAGE_RESULTS_END'
printf '%s\n' 'VI_READABILITY_SANDBOX_SUITE_OK'
