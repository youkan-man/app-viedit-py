from __future__ import annotations

import atexit
import json
import os
import sys
import traceback
from pathlib import Path

# Python imports sitecustomize after the standard site initialization. The
# application and its browser-test harnesses start from the repository root,
# so this is the earliest common point at which the authoritative semantic
# projector can be normalized before service_graph imports its build function.
from app.deep_audit_runtime_patch import install

install()


# The isolated Issue 14 build can generate a large Playwright/application log.
# Emit one compact final line with the semantic workflow state so the relay log
# tail identifies the failed stage without modifying any other test program or
# turning a genuine failure into a successful process exit.
if "issue14" in os.getenv("VI_EDITOR_TEST_SCOPE", "").casefold():
    artifact_dir = Path(os.getenv("BUILD_ARTIFACT_DIR", "/tmp"))

    @atexit.register
    def _replay_issue14_browser_result() -> None:
        path = artifact_dir / "semantic-structure-net.json"
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        concise = {
            "stage": payload.get("stage"),
            "failures": payload.get("failures") or [],
            "console_errors": payload.get("console_errors") or [],
            "page_errors": payload.get("page_errors") or [],
            "initial": payload.get("initial"),
            "true_frame": payload.get("true_frame"),
            "net": payload.get("net"),
            "restored": payload.get("restored"),
            "browser_state": payload.get("browser_state"),
        }
        print(
            "ISSUE14_BROWSER_RESULT="
            + json.dumps(concise, ensure_ascii=False, separators=(",", ":")),
            flush=True,
        )

    _default_excepthook = sys.excepthook

    def _issue14_excepthook(exc_type, exc, tb):
        frames = [
            frame
            for frame in traceback.extract_tb(tb)
            if "/workspace/" in frame.filename
            and "/site-packages/" not in frame.filename
        ]
        concise = {
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
        print(
            "ISSUE14_UNCAUGHT_JSON="
            + json.dumps(concise, ensure_ascii=False, separators=(",", ":")),
            file=sys.stderr,
            flush=True,
        )
        _default_excepthook(exc_type, exc, tb)

    sys.excepthook = _issue14_excepthook
