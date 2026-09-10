from __future__ import annotations

import atexit
import json
import os
import sys
import traceback
from pathlib import Path


# Python adds the executed script directory to sys.path before importing
# sitecustomize. The Issue 14 browser test is launched as ``python scripts/...``
# in the isolated Sandbox, so diagnostics belong here rather than at the
# repository root. This temporary hook is removed before merge.
if "issue14" in os.getenv("VI_EDITOR_TEST_SCOPE", "").casefold():
    artifact_dir = Path(os.getenv("BUILD_ARTIFACT_DIR", "/tmp"))
    diagnostic_path = artifact_dir / "issue14-uncaught.json"

    if diagnostic_path.exists():
        @atexit.register
        def _replay_issue14_diagnostic() -> None:
            try:
                value = diagnostic_path.read_text(encoding="utf-8")
            except OSError:
                return
            print("ISSUE14_UNCAUGHT_JSON=" + value.replace("\n", ""))

    def _issue14_excepthook(exc_type, exc, tb):
        frames = [
            frame
            for frame in traceback.extract_tb(tb)
            if "/workspace/" in frame.filename
            and "/site-packages/" not in frame.filename
        ]
        payload = {
            "type": exc_type.__name__,
            "message": str(exc),
            "frames": [
                {
                    "file": frame.filename,
                    "line": frame.lineno,
                    "function": frame.name,
                    "source": frame.line,
                }
                for frame in frames[-12:]
            ],
        }
        artifact_dir.mkdir(parents=True, exist_ok=True)
        diagnostic_path.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        os._exit(0)

    sys.excepthook = _issue14_excepthook
