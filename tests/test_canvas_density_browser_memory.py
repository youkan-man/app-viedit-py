from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_surface_view_memory_in_browser(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "BUILD_ARTIFACT_DIR": str(tmp_path / "artifacts"),
            "WORK_ROOT": str(tmp_path / "jobs"),
            "VI_UI_DENSITY_MEMORY_PORT": "18087",
            "PYTHONPATH": str(ROOT),
        }
    )
    completed = subprocess.run(
        [sys.executable, "scripts/semantic_ui_density_memory_test.py"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=150,
        check=False,
    )

    output = completed.stdout + "\n" + completed.stderr
    assert completed.returncode == 0, output[-12_000:]
    assert "SEMANTIC_UI_DENSITY_MEMORY_TEST_OK" in output
