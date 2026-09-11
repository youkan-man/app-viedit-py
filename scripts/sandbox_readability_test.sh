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

printf '%s\n' 'READABILITY_STAGE_RESULTS_BEGIN'
cat "$stage_results"
printf '%s\n' 'READABILITY_STAGE_RESULTS_END'
printf '%s\n' 'VI_READABILITY_SANDBOX_SUITE_OK'
