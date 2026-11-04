"""Local web app: `localcai` opens this in your browser.

Standard library only. Binds to 127.0.0.1 and rejects requests whose Host header
isn't localhost (DNS-rebinding protection); state-changing requests need an
X-LocalCAI header, which other websites can't send without a CORS preflight we never grant.
"""
from __future__ import annotations

import atexit
import json
import mimetypes
import os
import subprocess
import sys
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
from ..engine import ENGINE, models_dir
from .. import analyze
from .. import facts as factmem
from ..recall import recall
from ..library import delete_character, import_into, list_library
from ..runtime import BACKENDS, build_messages, list_models, resolve_base_url, stream_chat
from ..runtime.guard import check_reply, same_reply, spoken_part
from ..runtime.scene import build_state, save_state, state_for
from ..runtime.client import ContextTooLong, other_speakers, strip_markers, strip_meta, strip_name_prefix, trim_to_sentence
from ..runtime.prompt import PRONOUN_CHOICES, reply_words_for
from ..safety import HELPLINES, load_config, looks_like_crisis, save_config

STATIC = Path(__file__).parent / "static"
MAX_UPLOAD = 200 * 1024 * 1024
GUARD_MARK = "\x1e"  # sent after the streamed reply while the OOC guard checks it
CHARS_PER_TOKEN: dict[str, float] = {}  # learned per model when the server says a prompt didn't fit
STALE_MARK = "\x1d"  # end of a reply that wasn't saved because the chat changed meanwhile

SETTINGS_KEYS = {"backend", "model", "persona", "user_name", "temperature", "max_tokens", "age_confirmed",
                 "engine_variant", "ctx_size", "gpu_layers", "recall", "gpu_device", "reply_length", "pacing", "user_pronouns", "persona_pronouns", "initiative", "ooc_guard", "kv_cache", "scene_state", "auto_facts"}
DEFAULTS = {"backend": "builtin", "model": "", "persona": "", "user_name": "",
            "temperature": 0.8, "max_tokens": 512, "age_confirmed": False,
            "engine_variant": "auto", "ctx_size": 8192, "gpu_layers": 999, "recall": True,
            "gpu_device": "auto", "kv_cache": "auto", "scene_state": True, "auto_facts": True, "reply_length": "auto", "pacing": True, "user_pronouns": "",
            "persona_pronouns": {}, "initiative": "auto", "ooc_guard": True}

# Background jobs (history analysis). One at a time; the UI polls /api/job.
JOB: dict = {}
JOB_LOCK = threading.Lock()


def model_url() -> str:
    """URL of the configured model, starting the built-in engine if needed (raises RuntimeError)."""
    s = settings()
    if not s["model"]:
        raise RuntimeError("Pick a model first (top bar).")
    if s["backend"] == "builtin":
        ENGINE.start(s["model"], int(s["ctx_size"]), int(s["gpu_layers"]), device=s["gpu_device"],
                     kv=s.get("kv_cache", "auto"))
        return ENGINE.base_url
    return resolve_base_url(s["backend"])
def extension_source() -> Path | None:
    """The browser extension's files. They live inside the package (localcai/extension), so the same
    lookup works from source, a pip install (package data) and the Windows exe (bundled at the same path)."""
    src = Path(__file__).resolve().parents[1] / "extension"
    return src if (src / "manifest.json").exists() else None


def setup_extractor(browser: str) -> dict:
    """Put a ready-to-load copy of the extension in ~/.localcai/extractor/<browser> and open that folder,
    so "Load unpacked" only needs the user to pick the folder that just opened."""
    import shutil
    from ..library import home
    src = extension_source()
    if src is None:
        raise FileNotFoundError("The extension isn't bundled here. Download it from the localCAI releases page.")
    kind = "firefox" if browser == "firefox" else "chromium"
    dest = home() / "extractor" / kind
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("README.md", ".DS_Store"))
    manifest = json.loads((dest / "manifest.json").read_text("utf-8"))
    if kind == "chromium":
        manifest.pop("browser_specific_settings", None)  # Firefox-only key: Chrome would show a warning
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), "utf-8")
    opened = True
    try:
        if sys.platform == "win32":
            os.startfile(str(dest))  # noqa: S606 - Explorer on the user's own machine
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(dest)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        opened = False
    return {"path": str(dest), "manifest": str(dest / "manifest.json"), "version": manifest.get("version"),
            "opened": opened}


IMPORT_EXT = {".json", ".jsonl", ".png", ".zip"}
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}


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
                                           "settings": settings(),
                                           "backends": {"builtin": "built-in llama.cpp", **BACKENDS},
                                           "helplines": HELPLINES, "library_path": str(app.lib)})
                if u.path == "/api/job":
                    return self.send_json(dict(JOB))
                if u.path == "/api/engine":
                    s = settings()
                    return self.send_json({**ENGINE.status(), "fits": ENGINE.fits(int(s["ctx_size"]), s["gpu_device"])})
                if u.path == "/api/engine/devices":
                    return self.send_json({"devices": ENGINE.devices()})
                if u.path == "/api/models":
                    if (q.get("backend") or settings()["backend"]) == "builtin":
                        st = ENGINE.status()
                        err = "" if st["installed"] else "The built-in engine isn't installed yet. Click 🧠 to set it up."
                        if st["installed"] and not st["models"]:
                            err = "No models yet. Click 🧠 to download one, or drop a .gguf into the models folder."
                        return self.send_json({"models": [m["name"] for m in st["models"]], "error": err,
                                               "builtin": True})
                    url = resolve_base_url(q.get("backend") or settings()["backend"])
                    try:
                        return self.send_json({"models": list_models(url)})
                    except OSError as e:
                        return self.send_json({"models": [], "error": f"No model runner found at {url}. Start Ollama / LM Studio / llama.cpp, or pick another backend."})
                if u.path == "/api/facts":
                    card = app.card(q["character"])
                    p = app.safe_file("chats", q["chat"], "")
                    with app.lock:
                        meta, rows = chatlog.load(p)
                        got = factmem.chat_facts(meta, card)
                        if factmem.KEY not in (meta.get("chat_metadata") or {}):
                            # an older import (facts only on the card): give the chat its own list now,
                            # so the ids the dialog uses are the ones that are saved
                            factmem.set_facts(meta, got)
                            chatlog.save(p, meta, rows)
                    return self.send_json(self.facts_info(got))
                if u.path == "/api/chat":
                    card = app.card(q["character"])
                    meta, rows = chatlog.load(app.safe_file("chats", q["chat"], ""))
                    return self.send_json({"meta": meta, "rows": rows, "card": card.get("data", card)})
                m = re.fullmatch(r"/api/avatar/(.+)\.png", u.path)
                if m:  # the card PNG doubles as the avatar image
                    p = app.safe_file("characters", unquote(m.group(1)), ".card.png")
                    return self.raw(p.read_bytes(), "image/png", cache=True)
                m = re.fullmatch(r"/api/image/(characters|chats|personas)/([^/]+)", u.path)
                if m:
                    name = unquote(m.group(2)).split("?")[0]
                    ctype = IMAGE_TYPES.get(Path(name).suffix.lower())
                    if not ctype:
                        raise FileNotFoundError(name)
                    p = app.safe_file(m.group(1), name.split("?")[0], "")
                    return self.raw(p.read_bytes(), ctype, cache=True)
                m = re.fullmatch(r"/api/card/(.+)\.png", u.path)
                if m:
                    p = app.safe_file("characters", unquote(m.group(1)), ".card.png")
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

        def raw(self, data: bytes, ctype: str, download: str | None = None, cache: bool = False):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "max-age=60" if cache else "no-store")
            if download:
                self.send_header("Content-Disposition", f'attachment; filename="{download}"')
            else:
                self.send_header("Content-Security-Policy",
                                 "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'")
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
                if path == "/api/quit":  # a newer localCAI is starting and takes over
                    self.send_json({"ok": True})
                    hook = getattr(self.server, "quit_hook", None) or self.server.shutdown
                    threading.Thread(target=hook, daemon=True).start()
                    return
                if path.startswith("/api/engine/"):
                    return self.engine_action(path.rsplit("/", 1)[1], self.body_json())
                if path == "/api/extractor/setup":
                    return self.send_json(setup_extractor(str(self.body_json().get("browser") or "chromium")))
                if path == "/api/character/delete":
                    with app.lock:
                        n = delete_character(app.lib, self.body_json()["character"])
                    return self.send_json({"moved": n})
                if path == "/api/chat/background":
                    return self.chat_background_upload()
                if path == "/api/character/background-remove":
                    stem = app.safe_file("characters", self.body_json()["character"], ".card.json").name.removesuffix(".card.json")
                    with app.lock:
                        for f in (app.lib / "characters").glob(f"{stem}.custom-bg.*"):
                            f.unlink()
                    return self.send_json({"ok": True})
                if path in ("/api/chat/edit", "/api/chat/delete", "/api/chat/pin", "/api/chat/swipe",
                            "/api/chat/background-remove", "/api/chat/background-style"):
                    return self.chat_edit(path.rsplit("/", 1)[1], self.body_json())
                if path in ("/api/analyze/style", "/api/analyze/story"):
                    return self.start_job(path.rsplit("/", 1)[1], self.body_json())
                if path == "/api/job/stop":
                    JOB["stop"] = True
                    return self.send_json(dict(JOB))
                if path == "/api/story/save":
                    body = self.body_json()
                    p = app.safe_file("chats", body["chat"], "")
                    with app.lock:
                        meta, rows = chatlog.load(p)
                        meta.setdefault("chat_metadata", {})["localcai_story"] = str(body.get("text", "")).strip()
                        chatlog.save(p, meta, rows)
                    return self.send_json({"ok": True})
                if path == "/api/character/save":
                    return self.character_save(self.body_json())
                if path == "/api/facts":
                    body = self.body_json()
                    card = app.card(body["character"])
                    p = app.safe_file("chats", body["chat"], "")
                    with app.lock:
                        meta, rows = chatlog.load(p)
                        new = factmem.apply_to_chat(meta, card, str(body.get("op", "")), body)
                        chatlog.save(p, meta, rows)
                    return self.send_json(self.facts_info(new))
                if path in ("/api/chat/new", "/api/chat/send", "/api/chat/regenerate"):
                    if not settings()["age_confirmed"]:
                        return self.send_json({"error": "Please confirm you are 18 or older first."}, 403)
                    if path == "/api/chat/new":
                        return self.chat_new(self.body_json())
                    return self.chat_reply(self.body_json(), regenerate=path.endswith("regenerate"))
                self.send_json({"error": "not found"}, 404)
            except (FileNotFoundError, KeyError, ValueError) as e:
                self.send_json({"error": str(e)}, 400)

        def facts_info(self, facts: list[dict]) -> dict:
            return {"facts": facts, "used": factmem.used(facts), "limit": factmem.LIMIT}

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

        def engine_action(self, action: str, body: dict):
            s = settings()
            if action == "install":
                ok = ENGINE.install_async(body.get("variant") or s["engine_variant"])
            elif action == "download":
                ok = ENGINE.download_model_async(body.get("model", ""))
            elif action == "start":
                if not body.get("model"):
                    raise ValueError("model required")
                ENGINE.start_async(body["model"], int(s["ctx_size"]), int(s["gpu_layers"]), s["gpu_device"],
                                   s.get("kv_cache", "auto"))
                ok = True
            elif action == "stop":
                ENGINE.stop()
                ok = True
            elif action == "open-folder":
                folder = str(models_dir())
                if sys.platform == "win32":
                    os.startfile(folder)  # noqa: S606 - opens Explorer on the user's own machine
                else:
                    subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", folder])
                ok = True
            else:
                return self.send_json({"error": "unknown action"}, 404)
            if not ok:
                return self.send_json({"error": "Another download is still running."}, 409)
            return self.send_json(ENGINE.status())

        def chat_edit(self, action: str, body: dict):
            path = app.safe_file("chats", body["chat"], "")
            with app.lock:
                meta, rows = chatlog.load(path)
                if action == "background-remove":
                    for f in (app.lib / "chats").glob(f"{path.stem}.background.*"):
                        f.unlink()
                    return self.send_json({"ok": True})
                if action == "background-style":
                    style = {"dim": max(0, min(90, int(body.get("dim", 45)))),
                             "blur": max(0, min(20, int(body.get("blur", 0)))),
                             "off": bool(body.get("off", False))}
                    meta.setdefault("chat_metadata", {})["localcai_bg"] = style
                    chatlog.save(path, meta, rows)
                    return self.send_json({"ok": True, "style": style})
                i = int(body["index"])
                if not 0 <= i < len(rows):
                    raise ValueError("message index out of range")
                # guard against editing a different message than the one on screen
                if "expect" in body and rows[i].get("mes", "")[:200] != str(body["expect"])[:200]:
                    return self.send_json({"error": "The chat changed. Reload and try again."}, 409)
                row = rows[i]
                if action == "edit":
                    text = str(body.get("text", "")).strip()
                    if not text:
                        raise ValueError("empty message")
                    row["mes"] = text
                    if row.get("swipes"):
                        row["swipes"][row.get("swipe_id", 0)] = text
                    row.setdefault("extra", {})["edited"] = True
                elif action == "delete":
                    rows = rows[:i] + ([] if body.get("from_here") else rows[i + 1:])
                elif action == "pin":
                    row.setdefault("extra", {})["pinned"] = bool(body.get("pinned"))
                elif action == "swipe":
                    chatlog.set_swipe(row, int(body["to"]))
                chatlog.save(path, meta, rows)
            return self.send_json({"rows": rows})

        def chat_background_upload(self):
            from ..images import looks_like, ext_for
            character = unquote(self.headers.get("X-Character", ""))
            if character:  # for every chat with this character
                card = app.safe_file("characters", character, ".card.json")
                folder, stem = app.lib / "characters", card.name.removesuffix(".card.json") + ".custom-bg"
            else:
                path = app.safe_file("chats", unquote(self.headers.get("X-Chat", "")), "")
                folder, stem = app.lib / "chats", f"{path.stem}.background"
            n = int(self.headers.get("Content-Length") or 0)
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if not 0 < n <= 15 * 1024 * 1024:
                return self.send_json({"error": "Image missing or larger than 15 MB."}, 400)
            data = self.rfile.read(n)
            if ctype not in ("image/png", "image/jpeg", "image/webp", "image/gif") or not looks_like(ctype, data):
                return self.send_json({"error": "Please use a PNG, JPEG, WebP or GIF image."}, 400)
            with app.lock:
                for f in folder.glob(f"{stem}.*"):
                    f.unlink()
                (folder / f"{stem}.{ext_for(ctype)}").write_bytes(data)
            return self.send_json({"ok": True})

        def character_save(self, body: dict):
            editable = {"description", "personality", "scenario", "first_mes", "mes_example",
                        "creator_notes", "system_prompt"}
            jp = app.safe_file("characters", body["character"], ".card.json")
            pp = app.safe_file("characters", body["character"], ".card.png")
            with app.lock:
                card = json.loads(jp.read_text("utf-8"))
                d = card.setdefault("data", {})
                for k, v in (body.get("data") or {}).items():
                    if k in editable and isinstance(v, str):
                        d[k] = v
                if "rules" in body:
                    rules = [str(r).strip()[:300] for r in (body.get("rules") or []) if str(r).strip()][:30]
                    d.setdefault("extensions", {}).setdefault("localcai", {})["rules"] = rules
                if "pronouns" in body:
                    pr = str(body["pronouns"] or "")
                    if pr and pr not in PRONOUN_CHOICES:
                        raise ValueError("unknown pronouns")
                    d.setdefault("extensions", {}).setdefault("localcai", {})["pronouns"] = pr
                jp.write_text(json.dumps(card, ensure_ascii=False, indent=2), "utf-8")
                from ..exporters import embed_card_in_png
                pp.write_bytes(embed_card_in_png(pp.read_bytes(), card))  # keep the PNG card in sync
            return self.send_json({"ok": True, "card": d})

        def start_job(self, kind: str, body: dict):
            if not settings()["age_confirmed"]:
                return self.send_json({"error": "Please confirm you are 18 or older first."}, 403)
            with JOB_LOCK:
                if JOB and not JOB.get("done"):
                    return self.send_json({"error": "Another analysis is still running."}, 409)
                JOB.clear()
                JOB.update(kind=kind, done=False, error="", message="Starting…", progress=0.0, stop=False)
            character, chat = body["character"], body["chat"]
            card_path = app.safe_file("characters", character, ".card.json")
            chat_path = app.safe_file("chats", chat, "")
            scope = int(body.get("scope") or 0)

            def run():
                try:
                    card = json.loads(card_path.read_text("utf-8"))
                    d = card.setdefault("data", {})
                    char = d.get("name", "Character")
                    _, user = app.persona()
                    meta, rows = chatlog.load(chat_path)
                    JOB["message"] = "Loading the model…"
                    url, model = model_url(), settings()["model"]
                    ask = lambda prompt, sys_="": analyze.complete(url, model, prompt, sys_)
                    if kind == "style":
                        JOB.update(message="Reading her replies…", progress=0.2)
                        notes = analyze.style_notes(rows, char, user, lambda p: ask(p, analyze.STYLE_SYSTEM))
                        JOB.update(message="Picking example dialogues…", progress=0.9)
                        examples = analyze.pick_examples(rows, user, char)
                        auto = d.setdefault("extensions", {}).setdefault(analyze.AUTO_MARK, {})
                        if not d.get("personality") or auto.get("personality"):
                            d["personality"] = notes
                            auto["personality"] = True
                        else:
                            d["personality"] = d["personality"].rstrip() + "\n\n[Style notes from your chats]\n" + notes
                        if examples and (not d.get("mes_example") or auto.get("mes_example")):
                            d["mes_example"] = examples
                            auto["mes_example"] = True
                        with app.lock:
                            card_path.write_text(json.dumps(card, ensure_ascii=False, indent=2), "utf-8")
                            pp = card_path.with_name(card_path.name.replace(".card.json", ".card.png"))
                            if pp.exists():
                                from ..exporters import embed_card_in_png
                                pp.write_bytes(embed_card_in_png(pp.read_bytes(), card))
                        JOB.update(message="Learned her style.", progress=1.0)
                    else:
                        part = rows[-scope:] if scope else rows
                        def prog(done, total):
                            JOB.update(progress=done / max(total, 1),
                                       message=f"Reading part {min(done + 1, total)} of {total}…")
                        story = analyze.story_summary(part, char, user, lambda p: ask(p, analyze.STORY_SYSTEM),
                                                      prog, lambda: JOB.get("stop"))
                        if story:
                            with app.lock:
                                meta2, rows2 = chatlog.load(chat_path)
                                meta2.setdefault("chat_metadata", {})["localcai_story"] = story
                                chatlog.save(chat_path, meta2, rows2)
                        JOB.update(message="Stopped. Saved what was read so far." if JOB.get("stop")
                                   else "The story so far is ready.", progress=1.0, story=story)
                except Exception as e:  # report to the UI
                    JOB.update(error=str(e) or e.__class__.__name__, message="Failed")
                finally:
                    JOB["done"] = True

            threading.Thread(target=run, daemon=True).start()
            return self.send_json(dict(JOB))

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
            base = chatlog.snapshot(rows)  # what this reply is based on: checked again before saving
            crisis = False
            swipe_row = None
            if regenerate:
                if rows and not rows[-1].get("is_user"):
                    swipe_row = rows.pop()  # generate a new alternative for this reply
            else:
                text = str(body.get("text", "")).strip()
                if not text:
                    return self.send_json({"error": "empty message"}, 400)
                crisis = looks_like_crisis(text)
                rows.append(chatlog.row(user, True, text, datetime.now().isoformat()))
            if not s["model"]:
                return self.send_json({"error": "Pick a model first (top bar)."}, 400)

            try:
                url = model_url()
            except RuntimeError as e:
                return self.send_json({"error": str(e)}, 502)
            story = (meta.get("chat_metadata") or {}).get("localcai_story", "")
            recalled = []
            if s.get("recall", True) and len(rows) > 45:
                query = " ".join(r.get("mes", "") for r in rows[-2:])
                recalled = recall(rows, query, exclude_last=40, cache_key=str(path))
            # the engine may run with less context than asked (it shrinks it to fit free VRAM)
            ctx = ENGINE.ctx if s["backend"] == "builtin" and ENGINE.ctx else int(s["ctx_size"])
            # characters per token differ by model and text; start from what this model showed so far
            ratio = CHARS_PER_TOKEN.get(s["model"], 3.2)
            budget = max(2000, int((ctx - int(s["max_tokens"])) * ratio))
            history = chatlog.to_history(rows)
            target_words = reply_words_for(str(s.get("reply_length", "auto")), history, card)
            instruction = str(body.get("instruction") or "")[:600]
            use_scene = s.get("scene_state", True) is not False
            facts_now = factmem.chat_facts(meta, card)
            scene_now = ""
            if use_scene and history and history[-1]["role"] == "user":
                last_bot = max((i for i, m in enumerate(history[:-1]) if m["role"] == "assistant"), default=-1)
                scene_now = state_for(path, history[:last_bot + 1]) if last_bot >= 0 else ""

            def make_msgs(instruction: str = "", rewrite_of: str = "") -> list[dict]:
                return build_messages(
                    card, history, user, max_chars=budget, persona=persona,
                    memories=chatlog.pinned_memories(rows + ([swipe_row] if swipe_row else [])),
                    story=story, recalled=recalled, reply_words=target_words,
                    pacing=s.get("pacing", True) is not False,
                    user_pronouns=str((s.get("persona_pronouns") or {}).get(s.get("persona") or "", "")
                                      or s.get("user_pronouns") or ""),
                    initiative=str(s.get("initiative") or "auto"),
                    instruction=instruction, rewrite_of=rewrite_of,
                    avoid=(swipe_row.get("swipes") or [swipe_row.get("mes", "")]) if swipe_row and not instruction else None,
                    scene=scene_now, facts=facts_now)

            msgs = make_msgs(instruction, (swipe_row or {}).get("mes", "") if instruction else "")
            info: dict = {}
            # Built-in engine: sampler settings that keep small models from rambling and looping.
            sampler = ({"top_p": 0.9, "top_k": 40, "min_p": 0.05, "repeat_penalty": 1.08}
                       if s["backend"] == "builtin" else {})
            extra = dict(sampler)
            # never let the model write the user's turn in chat-log style ("Sam: …")
            extra = {**extra, "stop": [f"\n{user}:", f"\n**{user}:**", f"\n{user}：", "<|im_end|>", "<|im_start|>"]}
            temp = float(s["temperature"])
            if swipe_row is not None and not instruction:
                temp = min(1.3, temp + 0.15)  # another version: a little more variety
            def start(msgs: list[dict]):
                return strip_name_prefix(stream_chat(url, s["model"], msgs, temperature=temp,
                                                     max_tokens=int(s["max_tokens"]), info=info, extra=extra), char, info)
            gen = start(msgs)
            try:
                try:
                    first = next(gen, "")
                except ContextTooLong as e:
                    # The estimate was off for this text: the server said how many tokens the prompt really had.
                    # Learn this model's ratio, keep less history so it fits with room for the reply, retry once.
                    chars = sum(len(m["content"]) for m in msgs)
                    ratio = max(1.2, min(ratio, chars / e.n_prompt) * 0.95)
                    CHARS_PER_TOKEN[s["model"]] = ratio
                    budget = max(1000, int((e.n_ctx - int(s["max_tokens"]) - 64) * ratio))
                    msgs = make_msgs(instruction, (swipe_row or {}).get("mes", "") if instruction else "")
                    gen = start(msgs)
                    try:
                        first = next(gen, "")
                    except ContextTooLong as e2:
                        return self.send_json({"error": (
                            f"The character's setup and memory alone are too long for this model's context "
                            f"({e2.n_prompt} tokens, {e2.n_ctx} fit). Raise Context size in Settings, or shorten "
                            f"the memory (facts, pinned messages, the story so far).")}, 502)
            except OSError as e:
                return self.send_json({"error": f"Couldn't reach the model at {url}: {e}"}, 502)

            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-LocalCAI-Crisis", "1" if crisis else "0")
            self.end_headers()
            reply = [first]
            stopped = False
            try:
                self.wfile.write(first.encode("utf-8"))
                self.wfile.flush()
                for tok in gen:
                    reply.append(tok)
                    self.wfile.write(tok.encode("utf-8"))
                    self.wfile.flush()
            except BrokenPipeError:
                stopped = True  # client hit Stop: keep what we have
            except OSError as e:  # the model failed mid-reply: tell the user in the chat
                try:
                    self.wfile.write(f"\n\n[localCAI: the model stopped with an error: {e}]".encode("utf-8"))
                except OSError:
                    pass
            text_out = strip_meta(strip_markers("".join(reply))).strip()
            if info.get("finish_reason") == "length":
                text_out = trim_to_sentence(text_out)  # hit max_tokens: don't save half a sentence
            if info.get("name_prefix") and other_speakers(text_out, char):
                # a group scene: keep the opening "Bram:" so every line says who is talking
                text_out = info["name_prefix"].strip() + " " + text_out
            fixed, fix_reason = "", ""
            if (text_out and not stopped and not instruction and not crisis
                    and s.get("ooc_guard", True) is not False):
                # OOC guard: a second look; if the reply breaks character, rewrite it once
                try:
                    self.wfile.write(GUARD_MARK.encode("utf-8"))  # tells the UI "checking…"
                    self.wfile.flush()
                except OSError:
                    pass

                def ask(system: str, prompt: str) -> str:
                    return "".join(stream_chat(url, s["model"], [{"role": "system", "content": system},
                                                                 {"role": "user", "content": prompt}],
                                               temperature=0.1, max_tokens=80, extra=sampler or None))

                last_user = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
                fix_reason = check_reply(ask, card, user, last_user, text_out, target_words)
                if fix_reason:
                    try:
                        info2: dict = {}
                        out = "".join(strip_name_prefix(stream_chat(
                            url, s["model"], make_msgs(fix_reason, text_out), temperature=float(s["temperature"]),
                            max_tokens=int(s["max_tokens"]), info=info2, extra=extra), char, info2))
                        fixed = strip_meta(strip_markers(out)).strip()
                        if info2.get("finish_reason") == "length":
                            fixed = trim_to_sentence(fixed)
                        if same_reply(fixed, text_out) or same_reply(spoken_part(fixed), spoken_part(text_out)):
                            # nothing really changed (or only the *actions* moved, which aren't reviewed):
                            # keep one version, no "auto-fixed" badge
                            fixed = ""
                    except OSError:
                        fixed = ""
            with app.lock:
                # The chat may have been edited, rewound, swiped or answered in another window while this
                # reply was being written. Save onto the chat as it is *now*, and only if the messages the
                # reply was based on are unchanged; otherwise drop the reply instead of undoing those changes.
                meta_now, now = chatlog.load(path)
                stale = not chatlog.same_messages(now, base)
                if not stale:
                    if swipe_row is not None:
                        target = now[-1]
                        if text_out:
                            chatlog.add_swipe(target, text_out)
                    else:
                        if len(rows) > len(base):
                            now.append(rows[len(base)])  # the user's new message (none when regenerating)
                        target = None
                        if text_out:
                            target = chatlog.row(char, False, text_out, datetime.now().isoformat())
                            now.append(target)
                    if fixed and target is not None:
                        chatlog.add_swipe(target, fixed)  # the in-character version is shown; the first try stays a swipe
                        target.setdefault("extra", {})["ooc_fixed"] = fix_reason[:300]
                    chatlog.save(path, meta_now, now)
            if stale:
                try:
                    self.wfile.write(STALE_MARK.encode("utf-8"))  # tells the UI the reply wasn't saved
                    self.wfile.flush()
                except OSError:
                    pass
                return
            final = fixed or text_out
            if not final or stopped or crisis:
                return
            done_history = history + [{"role": "assistant", "content": final}]
            replies = sum(1 for m in done_history if m["role"] == "assistant")
            want_facts = s.get("auto_facts", True) is not False and replies % factmem.AUTO_EVERY == 0
            if not use_scene and not want_facts:
                return

            # Made in the background so this reply isn't held up: the scene note for the next turn and,
            # every few replies, new lasting facts for the chat's memory. One after the other (one GPU).
            def ask(system: str, prompt: str, n: int) -> str:
                return "".join(stream_chat(
                    url, s["model"], [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                    temperature=0.1, max_tokens=n, extra=sampler or None))

            def background() -> None:
                if use_scene:
                    state = build_state(lambda a, b: ask(a, b, 110), done_history, char, user, prev=scene_now)
                    if state:
                        with app.lock:
                            try:
                                # only if the chat still is what the note describes (not edited meanwhile)
                                _, rows_now = chatlog.load(path)
                                if chatlog.to_history(rows_now) == done_history:
                                    save_state(path, done_history, state)
                            except (OSError, ValueError):
                                pass
                if want_facts and factmem.used(facts_now) < factmem.LIMIT * factmem.AUTO_STOP:
                    found = factmem.find_new(lambda a, b: ask(a, b, 160), done_history, char, user, facts_now)
                    if found:
                        with app.lock:
                            try:
                                meta_now, rows_now = chatlog.load(path)
                                if chatlog.to_history(rows_now)[:len(done_history)] != done_history:
                                    return  # edited or rewound meanwhile: what was read may no longer be true
                                cur = factmem.chat_facts(meta_now, card)
                                merged = factmem.merge_auto(cur, found)
                                if merged != cur:
                                    factmem.set_facts(meta_now, merged)
                                    chatlog.save(path, meta_now, rows_now)
                            except (OSError, ValueError):
                                pass
            threading.Thread(target=background, daemon=True).start()

    return H


def create_server(port: int = 8765, library: Path | None = None) -> ThreadingHTTPServer:
    from ..library import default_library
    lib = Path(library or default_library())
    for sub in ("characters", "chats", "personas"):
        (lib / sub).mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(App(lib), port))
    httpd.library = lib
    from ..engine import kill_orphan
    kill_orphan()  # free the GPU from an engine a previous run left behind
    atexit.register(ENGINE.stop)  # never leave a model running in the background
    return httpd


def serve(port: int = 8765, open_browser: bool = True, library: Path | None = None) -> int:
    httpd = create_server(port, library)
    url = f"http://127.0.0.1:{port}/"
    print(f"localCAI is running at {url}  (library: {httpd.library})\nPress Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nBye!")
    finally:
        httpd.server_close()
        ENGINE.stop()
    return 0
