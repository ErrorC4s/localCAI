"""Built-in engine, end to end, with no real internet:
a fake GitHub release (serving a fake llama-server), a fake Hugging Face, and the real app.

Run: python tests/e2e_ui/test_engine.py   (Linux/macOS; needs playwright)
"""
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
FAKE_SERVER = (Path(__file__).parent / "fake_llama_server.py").read_bytes()
UI_PORT, CDN_PORT = 8797, 8796
REPO = "lmstudio-community/Qwen3-4B-Instruct-2507-GGUF"
MODEL = "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"


def make_tarball() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for name, data, mode in [("llama-b9999/llama-server", FAKE_SERVER, 0o644),  # not executable on purpose
                                 ("llama-b9999/libggml-base.so", b"\0" * 64, 0o644)]:
            ti = tarfile.TarInfo(name); ti.size = len(data); ti.mode = mode
            t.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


TARBALL = make_tarball()
GGUF = b"GGUF" + b"\0" * 300_000


class CDN(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send(self, body: bytes, ctype="application/octet-stream"):
        self.send_response(200); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        base = f"http://127.0.0.1:{CDN_PORT}"
        if self.path == "/release":
            assets = [{"name": n, "browser_download_url": f"{base}/dl/{n}"} for n in (
                "llama-b9999-bin-win-vulkan-x64.zip", "llama-b9999-bin-ubuntu-x64.tar.gz",
                "llama-b9999-bin-ubuntu-vulkan-x64.tar.gz", "llama-b9999-bin-macos-arm64.tar.gz")]
            return self.send(json.dumps({"tag_name": "b9999", "assets": assets}).encode(), "application/json")
        if self.path.startswith("/dl/"):
            return self.send(TARBALL)
        if self.path == f"/hf/api/models/{REPO}":
            sib = [{"rfilename": f} for f in ("README.md", "Qwen3-4B-Instruct-2507-Q8_0.gguf", MODEL)]
            return self.send(json.dumps({"siblings": sib}).encode(), "application/json")
        if self.path == f"/hf/{REPO}/resolve/main/{MODEL}":
            return self.send(GGUF)
        self.send_response(404); self.end_headers()


def main():
    cdn = ThreadingHTTPServer(("127.0.0.1", CDN_PORT), CDN)
    threading.Thread(target=cdn.serve_forever, daemon=True).start()
    home = tempfile.mkdtemp(prefix="lcai-engine-")
    env = {**os.environ, "LOCALCAI_HOME": home, "PYTHONPATH": str(ROOT),
           "LOCALCAI_LLAMA_RELEASE_API": f"http://127.0.0.1:{CDN_PORT}/release",
           "LOCALCAI_HF_BASE": f"http://127.0.0.1:{CDN_PORT}/hf"}
    ui = subprocess.Popen([sys.executable, "-m", "localcai", "ui", "--no-browser", "--port", str(UI_PORT)], env=env, cwd=home)
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{UI_PORT}/", timeout=1); break
            except OSError:
                time.sleep(0.1)
        with sync_playwright() as p:
            page = p.chromium.launch().new_page(viewport={"width": 1280, "height": 820})
            page.on("pageerror", lambda e: print("PAGEERROR", e))
            page.goto(f"http://127.0.0.1:{UI_PORT}/")
            expect(page.locator("#backend")).to_have_value("builtin")          # default for new users
            expect(page.locator("#engine-chip")).to_contain_text("not installed")

            # picking a model before installing must not hang on "loading…"
            Path(home, "models").mkdir(parents=True, exist_ok=True)
            Path(home, "models", "early.gguf").write_bytes(GGUF)
            page.click("#refresh-models")
            page.select_option("#model", "early.gguf")
            expect(page.locator("#engine-chip")).to_contain_text("not installed")
            for _ in range(30):
                st = json.load(urllib.request.urlopen(f"http://127.0.0.1:{UI_PORT}/api/engine"))
                if st["error"]:
                    break
                time.sleep(0.2)
            assert st["state"] != "starting" and "isn't installed" in st["error"], st

            page.click("#open-engine")
            expect(page.locator("#eng-status")).to_contain_text("Not installed")
            page.click("#eng-install")
            expect(page.locator("#eng-status")).to_contain_text("llama-b9999-bin-ubuntu-vulkan-x64.tar.gz", timeout=20000)
            page.click("#eng-download")
            expect(page.locator("#eng-models li", has_text=MODEL)).to_have_count(1, timeout=20000)
            page.click("#eng-close")

            expect(page.locator(f"#model option[value='{MODEL}']")).to_have_count(1)
            page.select_option("#model", MODEL)
            expect(page.locator("#engine-chip")).to_have_text("● ready", timeout=20000)

            page.set_input_files("#file-input", str(ROOT / "tests" / "fixtures" / "extension_export.lcai.json"))
            page.click(".char-item:has-text('Luna')")
            n = page.locator(".msg").count()
            page.fill("#input", "hi")
            page.keyboard.press("Enter")
            page.click("#age-yes")
            expect(page.locator(".msg")).to_have_count(n + 2, timeout=15000)
            last = page.locator(".msg").last
            expect(last).to_contain_text(f"Hello from {MODEL}")
            expect(last).not_to_contain_text("let me think")                  # <think> stripped

            st = json.load(urllib.request.urlopen(f"http://127.0.0.1:{UI_PORT}/api/engine"))
            assert st["state"] == "ready" and st["model"] == MODEL
            page.click("#open-engine"); page.click("#eng-stop"); page.click("#eng-close")
            expect(page.locator("#engine-chip")).to_have_text("● engine off")
        server = Path(home, "engine", "b9999", "llama-b9999", "llama-server")
        assert os.access(server, os.X_OK), "llama-server must be made executable"
        assert (Path(home) / "models" / MODEL).read_bytes()[:4] == b"GGUF"
        print("ENGINE E2E PASS")
    finally:
        ui.terminate(); ui.wait(10)
        cdn.shutdown()
    out = subprocess.run(["pgrep", "-f", "fake llama-server|llama-b9999"], capture_output=True, text=True).stdout.strip()
    assert not out, "engine process left running after the app quit: " + out


if __name__ == "__main__":
    main()
