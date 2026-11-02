"""Local web app: `localcai` opens this in your browser.

Standard library only. Binds to 127.0.0.1 and rejects requests whose Host header
isn't localhost (DNS-rebinding protection); state-changing requests need an
X-LocalCAI header, which other websites can't send without a CORS preflight we never grant.
"""
from __future__ import annotations

import json
import mimetypes
import re
import shutil
import tempfile
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .. import __version__, chatlog
from ..library import import_into, list_library
from ..runtime import BACKENDS, build_messages, list_models, resolve_base_url, stream_chat
from ..safety import HELPLINES, load_config, looks_like_crisis, save_config

STATIC = Path(__file__).parent / "static"
MAX_UPLOAD = 200 * 1024 * 1024
SETTINGS_KEYS = {"backend", "model", "persona", "user_name", "temperature", "max_tokens", "age_confirmed"}
DEFAULTS = {"backend": "ollama", "model": "", "persona": "", "user_name": "",
            "temperature": 0.8, "max_tokens": 512, "age_confirmed": False}
IMPORT_EXT = {".json", ".jsonl", ".png", ".zip"}


def settings() -> dict:
    cfg = load_config()
    return {k: cfg.get(k, v) for k, v in DEFAULTS.items()}


class App:
    def __init__(self, library: Path):
        self.lib = library
        self.lock = threading.Lock()  # one writer at a time for chat files

    def safe_file(self, sub: str, name: str, suffix: str) -> Path:
        if not name or "/" in name or "\\" in name or name.startswith("."):
            raise ValueError("bad name")
        p = (self.lib / sub / (name + suffix)).resolve()
        if p.parent != (self.lib / sub).resolve() or not p.exists():
            raise FileNotFoundError(name)
        return p

    def card(self, character: str) -> dict:
        return json.loads(self.safe_file("characters", character, ".card.json").read_text("utf-8"))

    def persona(self) -> tuple[str, str]:
        s = settings()
        pfile = self.lib / "personas" / "personas.json"
        if s["persona"] and pfile.exists():
            for p in json.loads(pfile.read_text("utf-8")):
                if p.get("name") == s["persona"]:
                    return p.get("description", ""), p["name"]
        return "", s["user_name"] or "User"


def make_handler(app: App, port: int):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class H(BaseHTTPRequestHandler):
        server_version = f"localCAI/{__version__}"

        def log_message(self, *a):  # quiet
            pass

        # ── helpers ──────────────────────────────────────────────
        def send_json(self, obj, code=200):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def body_json(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}") if n else {}

        def guard(self, write: bool) -> bool:
            if self.headers.get("Host") not in allowed_hosts:
                self.send_json({"error": "forbidden host"}, 403)
                return False
            if write and self.headers.get("X-LocalCAI") != "1":
                self.send_json({"error": "missing X-LocalCAI header"}, 403)
                return False
            return True

        # ── GET ──────────────────────────────────────────────────
        def do_GET(self):
            if not self.guard(False):
                return
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            try:
                if u.path in ("/", "/index.html"):
                    return self.static("index.html")
                if u.path.startswith("/static/"):
                    return self.static(u.path[len("/static/"):])
                if u.path == "/api/state":
                    return self.send_json({"version": __version__, "library": list_library(app.lib),
                                           "settings": settings(), "backends": BACKENDS,
                                           "helplines": HELPLINES, "library_path": str(app.lib)})
                if u.path == "/api/models":
                    url = resolve_base_url(q.get("backend") or settings()["backend"])
                    try:
                        return self.send_json({"models": list_models(url)})
                    except OSError as e:
                        return self.send_json({"models": [], "error": f"No model runner found at {url}. Start Ollama / LM Studio / llama.cpp, or pick another backend."})
                if u.path == "/api/chat":
                    card = app.card(q["character"])
                    meta, rows = chatlog.load(app.safe_file("chats", q["chat"], ""))
                    return self.send_json({"meta": meta, "rows": rows, "card": card.get("data", card)})
                m = re.fullmatch(r"/api/card/(.+)\.png", u.path)
                if m:
                    p = app.safe_file("characters", m.group(1), ".card.png")
                    return self.raw(p.read_bytes(), "image/png", download=p.name)
                self.send_json({"error": "not found"}, 404)
            except (FileNotFoundError, KeyError, ValueError) as e:
                self.send_json({"error": f"not found: {e}"}, 404)

        def static(self, name: str):
            p = (STATIC / name).resolve()
            if p.parent != STATIC.resolve() or not p.is_file():
                return self.send_json({"error": "not found"}, 404)
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            self.raw(p.read_bytes(), ctype + ("; charset=utf-8" if ctype.startswith("text/") or "javascript" in ctype else ""))

        def raw(self, data: bytes, ctype: str, download: str | None = None):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            if download:
                self.send_header("Content-Disposition", f'attachment; filename="{download}"')
            else:
                self.send_header("Content-Security-Policy",
                                 "default-src 'self'; img-src 'self' https: data:; style-src 'self' 'unsafe-inline'")
            self.end_headers()
            self.wfile.write(data)

        # ── POST ─────────────────────────────────────────────────
        def do_POST(self):
            if not self.guard(True):
                return
            path = urlparse(self.path).path
            try:
                if path == "/api/settings":
                    cfg = load_config()
                    cfg.update({k: v for k, v in self.body_json().items() if k in SETTINGS_KEYS})
                    save_config(cfg)
                    return self.send_json(settings())
                if path == "/api/import":
                    return self.do_import()
                if path in ("/api/chat/new", "/api/chat/send", "/api/chat/regenerate"):
                    if not settings()["age_confirmed"]:
                        return self.send_json({"error": "Please confirm you are 18 or older first."}, 403)
                    if path == "/api/chat/new":
                        return self.chat_new(self.body_json())
                    return self.chat_reply(self.body_json(), regenerate=path.endswith("regenerate"))
                self.send_json({"error": "not found"}, 404)
            except (FileNotFoundError, KeyError, ValueError) as e:
                self.send_json({"error": str(e)}, 400)

        def do_import(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0 or n > MAX_UPLOAD:
                return self.send_json({"error": "file missing or too large"}, 400)
            name = Path(unquote(self.headers.get("X-Filename", "upload.json"))).name
            if Path(name).suffix.lower() not in IMPORT_EXT:
                return self.send_json({"error": f"unsupported file type: {name}"}, 400)
            tmp = Path(tempfile.mkdtemp(prefix="localcai-import-"))
            try:
                f = tmp / name
                with f.open("wb") as fh:
                    left = n
                    while left:
                        chunk = self.rfile.read(min(left, 1 << 20))
                        if not chunk:
                            break
                        fh.write(chunk)
                        left -= len(chunk)
                try:
                    rep = import_into(f, app.lib)
                except (ValueError, KeyError) as e:
                    return self.send_json({"error": f"Couldn't read {name}: {e}"}, 400)
                return self.send_json({"characters": rep.characters, "chats": rep.chats,
                                       "personas": rep.personas, "warnings": rep.warnings})
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

        def chat_new(self, body: dict):
            card = app.card(body["character"])
            d = card.get("data", card)
            char = d.get("name", "Character")
            _, user = app.persona()
            rows = []
            if d.get("first_mes"):
                rows.append(chatlog.row(char, False, d["first_mes"].replace("{{char}}", char).replace("{{user}}", user),
                                        datetime.now().isoformat()))
            name = f"{body['character']}.{datetime.now():%Y%m%d-%H%M%S}.jsonl"
            with app.lock:
                chatlog.save(app.lib / "chats" / name, {"user_name": user, "character_name": char}, rows)
            return self.send_json({"chat": name})

        def chat_reply(self, body: dict, regenerate: bool):
            card = app.card(body["character"])
            d = card.get("data", card)
            char = d.get("name", "Character")
            path = app.safe_file("chats", body["chat"], "")
            persona, user = app.persona()
            s = settings()
            with app.lock:
                meta, rows = chatlog.load(path)
            crisis = False
            if regenerate:
                if rows and not rows[-1].get("is_user"):
                    rows.pop()
            else:
                text = str(body.get("text", "")).strip()
                if not text:
                    return self.send_json({"error": "empty message"}, 400)
                crisis = looks_like_crisis(text)
                rows.append(chatlog.row(user, True, text, datetime.now().isoformat()))
            if not s["model"]:
                return self.send_json({"error": "Pick a model first (top bar)."}, 400)

            url = resolve_base_url(s["backend"])
            msgs = build_messages(card, chatlog.to_history(rows), user, persona=persona)
            gen = stream_chat(url, s["model"], msgs, temperature=float(s["temperature"]),
                              max_tokens=int(s["max_tokens"]))
            try:
                first = next(gen, "")
            except OSError as e:
                return self.send_json({"error": f"Couldn't reach the model at {url}: {e}"}, 502)

            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-LocalCAI-Crisis", "1" if crisis else "0")
            self.end_headers()
            reply = [first]
            try:
                self.wfile.write(first.encode("utf-8"))
                self.wfile.flush()
                for tok in gen:
                    reply.append(tok)
                    self.wfile.write(tok.encode("utf-8"))
                    self.wfile.flush()
            except (OSError, BrokenPipeError):
                pass  # client hit Stop: keep what we have
            text_out = "".join(reply).strip()
            if text_out:
                rows.append(chatlog.row(char, False, text_out, datetime.now().isoformat()))
            with app.lock:
                chatlog.save(path, meta, rows)

    return H


def serve(port: int = 8765, open_browser: bool = True, library: Path | None = None) -> int:
    from ..library import default_library
    lib = Path(library or default_library())
    for sub in ("characters", "chats", "personas"):
        (lib / sub).mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(App(lib), port))
    url = f"http://127.0.0.1:{port}/"
    print(f"localCAI is running at {url}  (library: {lib})\nPress Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nBye!")
    finally:
        httpd.server_close()
    return 0
