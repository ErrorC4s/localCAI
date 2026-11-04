"""Smoke test of a packaged localCAI (the Windows exe in CI), run from outside the source tree:
start it, prepare the browser extension, import an extension export, check the exported character card
and chat are in the formats SillyTavern reads, then quit cleanly.

    python tests/exe_smoke.py dist/localCAI.exe        # or: python tests/exe_smoke.py -m localcai.desktop
"""
import json, os, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "extension_export.lcai.json"
PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"


def call(path, data=None, headers=None):
    h = {"X-LocalCAI": "1", "Host": f"127.0.0.1:{PORT}", **(headers or {})}
    req = urllib.request.Request(BASE + path, data=data, headers=h, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
        return json.loads(body) if r.headers.get("Content-Type", "").startswith("application/json") else body


def main() -> None:
    cmd = [sys.executable, *sys.argv[1:]] if sys.argv[1:2] == ["-m"] else [str(Path(sys.argv[1]).resolve())]
    home = tempfile.mkdtemp(prefix="lcai-smoke-")
    env = {**os.environ, "LOCALCAI_HOME": home, "LOCALCAI_NO_WINDOW": "1"}
    if cmd[0] == sys.executable:                       # from source: find the package without the cwd
        env["PYTHONPATH"] = str(ROOT)
    proc = subprocess.Popen(cmd, env=env, cwd=tempfile.gettempdir())   # not the source tree
    try:
        for _ in range(120):
            try:
                st = call("/api/state"); break
            except OSError:
                time.sleep(0.5)
        else:
            raise SystemExit("the app never came up")
        print("started, version", st.get("version"))
        for browser in ("chromium", "firefox"):
            r = call("/api/extractor/setup", json.dumps({"browser": browser}).encode(), {"Content-Type": "application/json"})
            assert Path(r["manifest"]).exists(), r
        print("extension prepared for Chrome/Edge and Firefox")
        rep = call("/api/import", FIXTURE.read_bytes(), {"X-Filename": FIXTURE.name})
        assert rep["characters"] and rep["chats"], rep
        print(f"imported {len(rep['characters'])} characters, {len(rep['chats'])} chats")
        # SillyTavern formats: Character Card V2 inside the PNG, chat as .jsonl (metadata line + messages)
        sys.path.insert(0, str(ROOT))
        from localcai.importers.sillytavern import card_from_png
        stem = Path(rep["characters"][0]["card_json"]).name.removesuffix(".card.json")
        png = call(f"/api/card/{urllib.request.quote(stem)}.png")
        png_path = Path(home) / "exported.card.png"
        png_path.write_bytes(png)
        card = card_from_png(png_path)
        assert card and (card.get("spec") == "chara_card_v2" or "data" in card), card
        lines = [json.loads(l) for l in Path(rep["chats"][0]["path"]).read_text("utf-8").splitlines() if l.strip()]
        assert "user_name" in lines[0] and "character_name" in lines[0], lines[0]
        assert all({"name", "is_user", "mes", "send_date"} <= set(m) for m in lines[1:]), "message fields"
        print(f"card + chat ({len(lines) - 1} messages) in SillyTavern formats")
        call("/api/quit", b"{}", {"Content-Type": "application/json"})
        proc.wait(timeout=30)
        print("quit cleanly, exit code", proc.returncode)
        print("EXE SMOKE PASS")
    finally:
        if proc.poll() is None:
            proc.kill()


if __name__ == "__main__":
    main()
