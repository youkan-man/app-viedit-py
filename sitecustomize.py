from __future__ import annotations

import os
import sys
import traceback

# Python imports sitecustomize after the standard site initialization.  The
# application and its browser-test harnesses start from the repository root,
# so this is the earliest common point at which the authoritative semantic
# projector can be normalized before service_graph imports its build function.
from app.deep_audit_runtime_patch import install

install()


# The isolated Issue 14 Sandbox uses a long shell build command whose broker
# tail can hide the first frames of a Playwright timeout. Emit one compact line
# with the relevant repository frames; this is inactive in normal application
# and test runs.
if "issue14" in os.getenv("VI_EDITOR_TEST_SCOPE", "").casefold():
    _default_excepthook = sys.excepthook

    def _issue14_excepthook(exc_type, exc, tb):
        frames = [
            frame
            for frame in traceback.extract_tb(tb)
            if "/workspace/" in frame.filename
            and "/site-packages/" not in frame.filename
        ]
        compact = " | ".join(
            f"{frame.filename}:{frame.lineno}:{frame.name}"
            for frame in frames[-8:]
        )
        print(
            "ISSUE14_UNCAUGHT="
            f"{exc_type.__name__}:{exc};frames={compact}",
            file=sys.stderr,
        )
        _default_excepthook(exc_type, exc, tb)

    sys.excepthook = _issue14_excepthook
