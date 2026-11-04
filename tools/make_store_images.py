"""Render store screenshots (1280×800) and the promo tile (440×280) from the real UI, with demo data.

Needs: pip install playwright. Usage: python tools/make_store_images.py
Uses only the synthetic test fixture (Luna); never real chats.
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "store"
LOGO = (ROOT / "assets" / "logo.svg").read_text("utf-8")
FIXTURE = ROOT / "tests" / "fixtures" / "extension_export.lcai.json"

STUB = """
window.chrome = {
  runtime: { getManifest: () => ({ version: "%s" }) },
  tabs: {
    query: async () => [{ id: 1 }],
    sendMessage: async (_id, msg) => msg.type === "stats"
      ? { captures: 412, characters: 1, chats: 1, turns: 18432, pinned: 12, version: "%s",
          job: { running: false, done: true, message: "Reached the first message. 18,432 messages loaded." } }
      : { ok: true },
  },
};
"""

SLIDE = """<!doctype html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box} body{margin:0;width:1280px;height:800px;font-family:'Segoe UI',system-ui,sans-serif;
background:radial-gradient(1200px 700px at 85%% 20%%,#2b2560 0%%,#15161d 60%%);color:#e8e8ef;display:flex;align-items:center;gap:56px;padding:0 70px;overflow:hidden}
.text{width:430px;flex:none} .brand{display:flex;align-items:center;gap:12px;font-size:22px;margin-bottom:34px}
.brand svg{width:44px;height:44px} .brand b{color:#8b7dff}
h1{font-size:44px;line-height:1.12;margin:0 0 18px} p{font-size:20px;line-height:1.5;color:#b9bad0;margin:0}
ul{margin:22px 0 0;padding:0;list-style:none;font-size:18px;color:#d6d7e6} li{margin:10px 0} li::before{content:"✓  ";color:#8b7dff;font-weight:700}
.shot{flex:1;display:flex;justify-content:center} .shot img{max-width:100%%;max-height:680px;border-radius:14px;box-shadow:0 30px 80px rgba(0,0,0,.55)}
</style></head><body><div class="text"><div class="brand">%s<span>local<b>CAI</b></span></div>
<h1>%s</h1><p>%s</p><ul>%s</ul></div><div class="shot"><img src="data:image/png;base64,%s"></div></body></html>"""


def slide(page, title, sub, bullets, png: bytes, name: str):
    html = SLIDE % (LOGO, title, sub, "".join(f"<li>{b}</li>" for b in bullets), base64.b64encode(png).decode())
    page.set_viewport_size({"width": 1280, "height": 800})
    page.set_content(html)
    page.screenshot(path=str(OUT / "screenshots" / name))


def main():
    (OUT / "screenshots").mkdir(parents=True, exist_ok=True)
    version = json.loads((ROOT / "localcai" / "extension" / "manifest.json").read_text())["version"]
    home = tempfile.mkdtemp(prefix="lcai-store-")
    Path(home, "config.json").write_text(json.dumps({"age_confirmed": True, "backend": "builtin",
                                                     "model": "Qwen3-4B-Instruct-2507-Q4_K_M.gguf", "persona": "Alex"}))
    env = {**os.environ, "LOCALCAI_HOME": home, "PYTHONPATH": str(ROOT)}
    subprocess.run([sys.executable, "-m", "localcai", "import", str(FIXTURE)], env=env, check=True, capture_output=True)
    # a few more demo lines so the screenshot shows a real conversation
    chat = next(Path(home, "library", "chats").glob("Luna.*.jsonl"))
    demo = [("Alex", True, "Long day... can we just sit by the window for a bit?"),
            ("Luna", False, "*She pats the cushion beside her and pours a second cup.* \"Of course. "
             "The moon's extra bright tonight. **Oolong**, the way you like it.\""),
            ("Alex", True, "You remembered."),
            ("Luna", False, "*A sleepy smile.* \"I always do, silly. Now drink before it gets cold~\"")]
    with chat.open("a", encoding="utf-8") as f:
        for name, is_user, text in demo:
            f.write(json.dumps({"name": name, "is_user": is_user, "mes": text, "extra": {}}) + "\n")
    ui = subprocess.Popen([sys.executable, "-m", "localcai", "ui", "--no-browser", "--port", "8791"], env=env)
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen("http://127.0.0.1:8791/", timeout=1); break
            except OSError:
                time.sleep(0.1)
        with sync_playwright() as p:
            b = p.chromium.launch()
            # popup, rendered from the real extension files with a stubbed browser API
            pop = b.new_page(viewport={"width": 300, "height": 520}, device_scale_factor=2)
            pop.add_init_script(STUB % (version, version))
            pop.goto((ROOT / "localcai" / "extension" / "popup" / "popup.html").as_uri())
            pop.wait_for_timeout(400)
            popup_png = pop.locator("body").screenshot()
            # the app
            app = b.new_page(viewport={"width": 1180, "height": 760}, device_scale_factor=2)
            app.goto("http://127.0.0.1:8791/")
            app.click(".char-item:has-text('Luna')")
            app.wait_for_timeout(600)
            # demo environment has no engine installed: hide those notices for the screenshot
            app.add_style_tag(content=".toast,#engine-chip{display:none!important}")
            app.wait_for_timeout(200)
            app_png = app.screenshot()
            canvas = b.new_page()
            slide(canvas, "Your chats are yours.", "Save your own Character.AI chats to an open file in one click.",
                  ["Full history, even tens of thousands of messages", "Pins, chat memory, personas, avatars",
                   "Everything stays on your computer"], popup_png, "1-extract.png")
            slide(canvas, "Keep chatting, locally.", "Drop the file into the free localCAI app and continue on a local AI.",
                  ["Built-in engine, no extra installs", "Swipes, edits, pins, backgrounds",
                   "Learns your character's style from your history"], app_png, "2-app.png")
            # promo tile 440×280
            canvas.set_viewport_size({"width": 440, "height": 280})
            canvas.set_content(f"""<!doctype html><html><body style="margin:0;width:440px;height:280px;display:flex;
              flex-direction:column;align-items:center;justify-content:center;gap:14px;font-family:'Segoe UI',system-ui,sans-serif;
              background:radial-gradient(400px 260px at 70% 20%,#2b2560,#15161d);color:#e8e8ef">
              <div style="width:96px;height:96px">{LOGO.replace('width="128" height="128"', 'width="96" height="96"')}</div>
              <div style="font-size:34px">local<b style="color:#8b7dff">CAI</b></div>
              <div style="font-size:16px;color:#b9bad0">Bring your characters home.</div></body></html>""")
            canvas.screenshot(path=str(OUT / "promo-440x280.png"))
            b.close()
    finally:
        ui.terminate()
    for f in sorted(OUT.rglob("*.png")):
        print(f.relative_to(ROOT))


if __name__ == "__main__":
    main()
