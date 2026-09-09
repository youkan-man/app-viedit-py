"""Capture real VI imports on a disposable runner; never execute VI code."""
from __future__ import annotations

import base64
import collections
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import urllib.request
import zipfile

from playwright.sync_api import sync_playwright

OUT = Path(os.environ.get("AUDIT_OUT", "audit-evidence"))
BASE = "http://127.0.0.1:8080"
SAMPLES = [
    ("empty", "mefistotelis/pylabview", "examples/lv14f1/empty_vifile.vi", "e5a2d6fabc3af4a074c563bb53eaa64ef915c5f8", "MIT", "shift_jis"),
    ("modbus", "AppliedMotionProducts/LabVIEW", "AMP_Modbus_TCP.vi", "32ee3edc1e4d64db79b42cc7c3340bd89c9f1c94", "Apache-2.0", "shift_jis"),
    ("modbus-cp1252", "AppliedMotionProducts/LabVIEW", "AMP_Modbus_TCP.vi", "32ee3edc1e4d64db79b42cc7c3340bd89c9f1c94", "Apache-2.0", "cp1252"),
    ("systemlink", "ni/systemlink-labview-examples", "Asset Management/Asset Utilization Example.vi", "71b54e6f518bbadc2c1188ac30da5c0692cc8d63", "MIT", "shift_jis"),
]


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def read_url(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "VI-GUI-Audit/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def snap(page, folder: Path, name: str) -> dict:
    page.screenshot(path=str(folder / f"{name}.png"), full_page=True)
    data = page.evaluate("""() => {
      const r = e => {const b=e.getBoundingClientRect(); return {x:b.x,y:b.y,width:b.width,height:b.height};};
      const svg = document.querySelector('#model-graph-svg');
      return {
        viewport: {width:innerWidth,height:innerHeight},
        bodyWidth:document.body.scrollWidth,
        graphRect:svg ? r(svg) : null,
        viewBox:svg?.getAttribute('viewBox'),
        layer:document.querySelector('#model-graph-layer')?.value,
        nodes:[...document.querySelectorAll('.model-node')].map(e=>({
          id:e.dataset.modelId, cls:e.getAttribute('class'), rect:r(e),
          shape:e.querySelector('rect') ? r(e.querySelector('rect')) : null,
          label:e.querySelector('text')?.textContent,
          labelRect:e.querySelector('text') ? r(e.querySelector('text')) : null
        })),
        edges:document.querySelectorAll('.model-edge').length,
        text:document.body.innerText
      };
    }""")
    write_json(folder / f"{name}.dom.json", data)
    if page.locator("#model-graph-svg").count():
        (folder / f"{name}.svg").write_text(page.locator("#model-graph-svg").evaluate("e=>e.outerHTML"), encoding="utf-8")
    return {"name": name, "nodes": len(data["nodes"]), "edges": data["edges"], "layer": data["layer"], "viewport": data["viewport"], "graphRect": data["graphRect"]}


def audit(browser, sample: tuple) -> dict:
    key, repo, source_path, blob, license_name, encoding = sample
    folder = OUT / key
    folder.mkdir(parents=True, exist_ok=True)
    result = {"sample": key, "repository": repo, "source_path": source_path, "git_blob": blob, "license": license_name, "encoding": encoding, "screens": []}
    context = browser.new_context(viewport={"width": 1440, "height": 1000}, locale="ja-JP", device_scale_factor=1)
    page = context.new_page()
    page.set_default_timeout(30000)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        source_url = f"https://api.github.com/repos/{repo}/git/blobs/{blob}"
        source = json.loads(read_url(source_url))
        raw = base64.b64decode(source["content"])
        digest = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
        if digest != blob:
            raise ValueError("Immutable sample blob verification failed")
        filename = folder / Path(source_path).name
        filename.write_bytes(raw)
        result.update({"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "download_url": source_url})
        license_file = json.loads(read_url(f"https://api.github.com/repos/{repo}/contents/LICENSE"))
        (folder / "SOURCE-LICENSE.txt").write_bytes(base64.b64decode(license_file["content"]))
        result["license_blob"] = license_file["sha"]
        page.goto(BASE, wait_until="networkidle")
        if key == "empty":
            result["screens"].append(snap(page, folder, "00-unloaded"))
        page.locator("#header-open").click()
        page.locator("#open-file").set_input_files(str(filename.resolve()))
        page.locator("#open-verify").check()
        page.locator("#open-encoding").select_option(encoding)
        if key == "modbus":
            result["screens"].append(snap(page, folder, "01-upload-dialog"))
        with page.expect_response(lambda response: "/api/convert/vi-to-xml" in response.url, timeout=300000) as pending:
            page.locator("#open-submit").click()
        response = pending.value
        result["http_status"] = response.status
        job = response.json()
        write_json(folder / "job.json", job)
        if response.status != 200:
            raise RuntimeError(f"Upload returned HTTP {response.status}: {job}")
        page.locator("#open-dialog").wait_for(state="hidden", timeout=180000)
        page.locator("#page-stack").wait_for(state="visible")
        page.wait_for_timeout(400)
        result["job_id"] = job["job_id"]
        result["verification"] = job.get("verification")
        model = json.loads(read_url(f"{BASE}/api/jobs/{job['job_id']}/model"))
        write_json(folder / "model.json", model)
        graph = model.get("graph", {})
        result["model_summary"] = model.get("summary")
        result["graph_summary"] = graph.get("summary")
        result["class_counts"] = dict(collections.Counter(m.get("class_name", "") for m in graph.get("models", [])))
        result["screens"].append(snap(page, folder, "02-default-model"))
        for link_name in ["dataset", "main_xml", "roundtrip"]:
            url = job.get("urls", {}).get(link_name)
            if url:
                content = read_url(url if url.startswith("http") else BASE + url)
                suffix = {"dataset": ".zip", "main_xml": ".xml", "roundtrip": ".vi"}[link_name]
                (folder / (link_name + suffix)).write_bytes(content)
        if (folder / "dataset.zip").exists():
            with zipfile.ZipFile(folder / "dataset.zip") as archive:
                result["dataset_files"] = [{"name": i.filename, "bytes": i.file_size} for i in archive.infolist()]
        components = json.loads(read_url(f"{BASE}/api/jobs/{job['job_id']}/components?limit=200&offset=0"))
        write_json(folder / "components-page1.json", components)
        layers = page.locator("#model-graph-layer option").evaluate_all("es=>es.map(e=>e.value).filter(Boolean)")
        for layer in layers:
            page.locator("#model-graph-layer").select_option(layer)
            page.locator("#model-graph-fit").click()
            result["screens"].append(snap(page, folder, "03-" + layer))
        if "front-panel" in layers:
            page.locator("#model-graph-layer").select_option("front-panel")
        nodes = page.locator(".model-node")
        if nodes.count():
            nodes.first.focus()
            nodes.first.press("Enter")
            result["screens"].append(snap(page, folder, "04-selected-model"))
        page.set_viewport_size({"width": 1366, "height": 768})
        result["screens"].append(snap(page, folder, "05-laptop-model"))
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.locator('[data-app-page="properties"]').click()
        page.locator("#component-model-card").wait_for(state="visible")
        page.wait_for_timeout(600)
        result["screens"].append(snap(page, folder, "06-properties"))
        kinds = page.locator("#component-kind-filter option").evaluate_all("es=>es.map(e=>e.value)")
        if "control" in kinds:
            page.locator("#component-kind-filter").select_option("control")
            page.wait_for_timeout(400)
        rows = page.locator("#component-list-body tr")
        if rows.count():
            rows.first.click()
            page.wait_for_timeout(500)
            result["screens"].append(snap(page, folder, "07-control-properties"))
        (folder / "properties.html").write_text(page.content(), encoding="utf-8")
        page.set_viewport_size({"width": 1366, "height": 768})
        result["screens"].append(snap(page, folder, "08-laptop-properties"))
        result["capture_completed"] = True
    except Exception as error:
        result["error"] = str(error)
        result["traceback"] = traceback.format_exc()
        try:
            result["screens"].append(snap(page, folder, "99-error"))
        except Exception:
            pass
    finally:
        result["page_errors"] = errors
        write_json(folder / "result.json", result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        context.close()
    return result


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["WORK_ROOT"] = str((OUT / "jobs").resolve())
    env["PORT"] = "8080"
    env["HOST"] = "127.0.0.1"
    log = (OUT / "server.log").open("w", encoding="utf-8")
    server = subprocess.Popen([sys.executable, "main.py"], env=env, stdout=log, stderr=subprocess.STDOUT)
    results = []
    try:
        for _ in range(90):
            try:
                health = json.loads(read_url(BASE + "/api/health"))
                if health.get("pylabview", {}).get("available"):
                    write_json(OUT / "health.json", health)
                    break
            except Exception:
                pass
            if server.poll() is not None:
                raise RuntimeError("Application exited before health check")
            time.sleep(1)
        else:
            raise RuntimeError("Application was not healthy")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for sample in SAMPLES:
                results.append(audit(browser, sample))
            browser.close()
        write_json(OUT / "results.json", results)
        return 0 if all(r.get("capture_completed") for r in results) else 1
    finally:
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
        log.close()


if __name__ == "__main__":
    raise SystemExit(main())
