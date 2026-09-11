from __future__ import annotations

import json
import os
import sys
import traceback

# Python imports sitecustomize after the standard site initialization. The
# application and its browser-test harnesses start from the repository root,
# so this is the earliest common point at which the authoritative semantic
# projector can be normalized before service_graph imports its build function.
from app.deep_audit_runtime_patch import install

install()


if "issue14" in os.getenv("VI_EDITOR_TEST_SCOPE", "").casefold():
    _default_excepthook = sys.excepthook

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
        print(
            "ISSUE14_UNCAUGHT_JSON="
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            file=sys.stderr,
            flush=True,
        )
        _default_excepthook(exc_type, exc, tb)

    sys.excepthook = _issue14_excepthook
