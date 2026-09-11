from __future__ import annotations

import json
import traceback

from semantic_structure_workflow_test import main


def run() -> int:
    try:
        return main()
    except Exception as error:
        frames = [
            frame
            for frame in traceback.extract_tb(error.__traceback__)
            if "/workspace/" in frame.filename
            and "/site-packages/" not in frame.filename
        ]
        payload = {
            "type": type(error).__name__,
            "message": str(error),
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
            "STRUCTURE_WORKFLOW_UNCAUGHT_JSON="
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            flush=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
