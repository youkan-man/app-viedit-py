from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Route, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.semantic_ui_browser_test import make_payload  # noqa: E402

PORT = int(os.getenv("VI_UI_DENSITY_MEMORY_PORT", "8087"))
BASE_URL = f"http://127.0.0.1:{PORT}"
ARTIFACTS = Path(
    os.getenv("BUILD_ARTIFACT_DIR", str(ROOT / "artifacts" / "semantic-density-memory"))
)


def wait_for_server(process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output, _ = process.communicate(timeout=3)
            raise RuntimeError(f"application exited before ready:\n{output}")
        try:
            import urllib.request

            with urllib.request.urlopen(f"{BASE_URL}/api/health", timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("application did not become ready")


def close(first: dict[str, float], second: dict[str, float], tolerance: float = 0.75) -> bool:
    return all(abs(first[key] - second[key]) <= tolerance for key in ("x", "y", "width", "height"))


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    payload = make_payload()
    job: dict[str, Any] = {
        "job_id": "density-memory",
        "status": "ready",
        "component_modified_at": "2026-09-10T08:00:00Z",
        "xml_modified_at": "2026-09-10T08:00:00Z",
        "files": [],
    }
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(PORT),
            "HOST": "127.0.0.1",
            "WORK_ROOT": str(ROOT / ".sandbox-density-memory-jobs"),
        }
    )
    process = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    diagnostics: dict[str, Any] = {
        "failures": [],
        "console_errors": [],
        "page_errors": [],
    }
    try:
        wait_for_server(process)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()
            page.on(
                "console",
                lambda message: diagnostics["console_errors"].append(message.text)
                if message.type == "error"
                else None,
            )
            page.on("pageerror", lambda error: diagnostics["page_errors"].append(str(error)))

            def model_route(route: Route) -> None:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(payload, ensure_ascii=False),
                )

            page.route("**/api/jobs/density-memory/model*", model_route)
            page.goto(BASE_URL, wait_until="networkidle")
            page.wait_for_function("() => Boolean(window.viPages && window.viModelGraph)")
            page.wait_for_function(
                "() => Boolean(window.VICanvasDensity?.ready && window.VICanvasDensityMemory?.ready)"
            )
            page.evaluate("job => window.viPages.setJob(job, {openModel: true})", job)
            page.evaluate("async job => { await window.viModelGraph.setJob(job); }", job)
            page.wait_for_function("() => Boolean(window.VISemanticEditor.S.vi)")
            page.wait_for_timeout(250)

            page.evaluate("() => window.VICanvasDensity.zoomAt(1.25)")
            page.wait_for_timeout(100)
            front_box = page.evaluate("() => ({...window.VISemanticEditor.S.box})")
            front_scale = page.evaluate("() => window.VICanvasDensity.runtime.currentScale")

            page.locator('[data-vi-surface="block-diagram"]').click()
            page.wait_for_timeout(180)
            page.evaluate("() => window.VICanvasDensity.zoomAt(0.82)")
            page.wait_for_timeout(100)
            block_box = page.evaluate("() => ({...window.VISemanticEditor.S.box})")
            block_scale = page.evaluate("() => window.VICanvasDensity.runtime.currentScale")

            page.locator('[data-vi-surface="front-panel"]').click()
            page.wait_for_timeout(180)
            restored_front = page.evaluate("() => ({...window.VISemanticEditor.S.box})")
            restored_front_scale = page.evaluate(
                "() => window.VICanvasDensity.runtime.currentScale"
            )

            page.locator('[data-vi-surface="block-diagram"]').click()
            page.wait_for_timeout(180)
            restored_block = page.evaluate("() => ({...window.VISemanticEditor.S.box})")
            restored_block_scale = page.evaluate(
                "() => window.VICanvasDensity.runtime.currentScale"
            )

            if not close(front_box, restored_front):
                diagnostics["failures"].append("front-panel view was not restored")
            if not close(block_box, restored_block):
                diagnostics["failures"].append("block-diagram view was not restored")
            if abs(front_scale - restored_front_scale) > 0.02:
                diagnostics["failures"].append("front-panel scale changed after round trip")
            if abs(block_scale - restored_block_scale) > 0.02:
                diagnostics["failures"].append("block-diagram scale changed after round trip")

            diagnostics.update(
                {
                    "front": {
                        "box": front_box,
                        "restored": restored_front,
                        "scale": front_scale,
                        "restored_scale": restored_front_scale,
                    },
                    "block": {
                        "box": block_box,
                        "restored": restored_block,
                        "scale": block_scale,
                        "restored_scale": restored_block_scale,
                    },
                }
            )
            page.screenshot(
                path=str(ARTIFACTS / "density-surface-memory.png"),
                full_page=False,
            )
            browser.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
        if process.stdout:
            output = process.stdout.read()
            if output:
                print("DENSITY_MEMORY_APP_LOG=" + output[-4000:].replace("\n", "\\n"))

    print(
        "SEMANTIC_UI_DENSITY_MEMORY_JSON="
        + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
    )
    if diagnostics["failures"] or diagnostics["console_errors"] or diagnostics["page_errors"]:
        print("SEMANTIC_UI_DENSITY_MEMORY_TEST_FAILED")
        return 1
    print("SEMANTIC_UI_DENSITY_MEMORY_TEST_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
