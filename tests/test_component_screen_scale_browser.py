from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_component_screen_scale_in_browser(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "BUILD_ARTIFACT_DIR": str(tmp_path / "artifacts"),
            "WORK_ROOT": str(tmp_path / "jobs"),
            "VI_COMPONENT_SCALE_PORT": "18094",
            "PYTHONPATH": str(ROOT),
        }
    )
    completed = subprocess.run(
        [sys.executable, "scripts/component_screen_scale_regression.py"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=210,
        check=False,
    )

    output = completed.stdout + "\n" + completed.stderr
    assert completed.returncode == 0, output[-20_000:]
    assert "COMPONENT_SCREEN_SCALE_OK" in output
