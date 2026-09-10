from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def test_structure_net_runtime_has_valid_javascript_syntax() -> None:
    node = shutil.which("node")
    assert node is not None, "node is required for frontend contract tests"

    for name in (
        "vi-editor-structure-net-v2.js",
        "vi-editor-runtime-fixes.js",
        "pages.js",
    ):
        result = subprocess.run(
            [node, "--check", str(STATIC / name)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"{name} failed node --check:\n{result.stdout}\n{result.stderr}"
        )
