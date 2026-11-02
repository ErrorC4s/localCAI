"""localCAI command line.

  localcai                                       Open the app in its own window (`localcai desktop`)
  localcai ui                                    Open the app in your browser instead
  localcai import <file-or-folder> [-o DIR]      Convert exports into cards + chats (default: your library)
  localcai models [--backend ollama]             List models your local runner has
  localcai chat <card> --model NAME [...]        Chat in the terminal
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from . import __version__, chatlog
from .importers.sillytavern import card_from_png
from .library import default_library, import_into
from .runtime import build_messages, list_models, resolve_base_url, stream_chat, BACKENDS
from .safety import RESOURCES, age_gate, looks_like_crisis


def cmd_import(a: argparse.Namespace) -> int:
    out = Path(a.output) if a.output else default_library()
    rep = import_into(a.path, out, swap_roles=a.swap_roles, user_name=a.user_name)
    for c in rep.characters:
        print(f"  ✓ character  {c['name']}  ({c['memories']} memories)  → {c['card_json']}")
    for c in rep.chats:
        print(f"  ✓ chat       {c['character']}  {c['messages']} msgs, {c['pinned']} pinned, "
              f"{c['memories']} memories  → {c['path']}")
    if rep.personas:
        print(f"  ✓ personas   {', '.join(rep.personas)}  → {out / 'personas' / 'personas.json'}")
    for w in rep.warnings:
        print(f"  ! {w}", file=sys.stderr)
    if rep.empty:
        return 1
    print(f"\nDone. Run `localcai` to open the app, or import {out / 'characters'} into SillyTavern.")
    return 0


def cmd_models(a: argparse.Namespace) -> int:
    url = resolve_base_url(a.backend)
    try:
        for m in list_models(url):
            print(m)
    except OSError as e:
        print(f"Could not reach {url} ({e}). Is your local runner started?", file=sys.stderr)
        return 1
    return 0


def _load_card(path: Path) -> dict:
    return card_from_png(path) if path.suffix.lower() == ".png" else json.loads(path.read_text("utf-8"))


def load_persona(spec: str | None, name: str | None) -> tuple[str, str | None]:
    """Returns (description, persona_name). spec = personas.json path or plain text."""
    if not spec:
        return "", None
    p = Path(spec)
    if p.exists():
        items = json.loads(p.read_text("utf-8"))
        items = items if isinstance(items, list) else [items]
        chosen = next((x for x in items if x.get("name") == name), items[0] if items else None)
        return (chosen.get("description", ""), chosen.get("name")) if chosen else ("", None)
    return spec, None


def cmd_chat(a: argparse.Namespace) -> int:
    if not age_gate():
        print("Sorry, chat is for adults only.")
        return 1
    card = _load_card(Path(a.card))
    d = card.get("data", card)
    char = d.get("name", "Character")
    persona, persona_name = load_persona(a.persona, a.persona_name)
    user = a.user_name or persona_name or "User"
    url = resolve_base_url(a.backend)

    if a.resume:
        save = Path(a.resume)
        meta, rows = chatlog.load(save)
    else:
        save = Path(a.save_dir) / f"{char}.{datetime.now():%Y%m%d-%H%M%S}.jsonl"
        meta, rows = {"user_name": user, "character_name": char}, []
        if d.get("first_mes"):
            rows.append(chatlog.row(char, False, d["first_mes"].replace("{{char}}", char).replace("{{user}}", user)))

    print(f"── {char} · {a.model} @ {url} · /quit to exit ──")
    if persona:
        print(f"(playing as {user}; persona loaded)")
    print()
    for r in rows[-6:]:
        print(f"{r.get('name')}: {r.get('mes')}\n")
    while True:
        try:
            text = input(f"{user}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text in ("/quit", "/exit"):
            break
        if looks_like_crisis(text):
            print(RESOURCES)
        rows.append(chatlog.row(user, True, text, datetime.now().isoformat()))
        print(f"\n{char}: ", end="", flush=True)
        reply = []
        try:
            for tok in stream_chat(url, a.model, build_messages(card, chatlog.to_history(rows), user, persona=persona),
                                   temperature=a.temperature, max_tokens=a.max_tokens):
                print(tok, end="", flush=True)
                reply.append(tok)
        except OSError as e:
            print(f"\n[error talking to {url}: {e}]")
            rows.pop()
            continue
        print("\n")
        rows.append(chatlog.row(char, False, "".join(reply), datetime.now().isoformat()))
        chatlog.save(save, meta, rows)
    print(f"Chat saved to {save}")
    return 0


def cmd_ui(a: argparse.Namespace) -> int:
    from .webui.server import serve
    return serve(port=a.port, open_browser=not a.no_browser,
                 library=Path(a.library) if a.library else default_library())


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        argv = ["desktop"]
    p = argparse.ArgumentParser(prog="localcai", description="Bring your characters home.")
    p.add_argument("--version", action="version", version=f"localCAI {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    pd = sub.add_parser("desktop", help="open the app in its own window (default)")
    pd.set_defaults(fn=lambda a: __import__("localcai.desktop", fromlist=["main"]).main())

    pu = sub.add_parser("ui", help="open the app in your browser")
    pu.add_argument("--port", type=int, default=8765)
    pu.add_argument("--no-browser", action="store_true")
    pu.add_argument("--library", help="library folder (default: ~/.localcai/library)")
    pu.set_defaults(fn=cmd_ui)

    pi = sub.add_parser("import", help="convert exported chats/characters")
    pi.add_argument("path")
    pi.add_argument("-o", "--output", help="output folder (default: your library)")
    pi.add_argument("--swap-roles", action="store_true", help="fix chats where user/character are swapped")
    pi.add_argument("--user-name", help="your display name in the converted chats")
    pi.set_defaults(fn=cmd_import)

    backend_help = "backend preset (" + ", ".join(BACKENDS) + ") or a full base URL"
    pm = sub.add_parser("models", help="list models on your local runner")
    pm.add_argument("--backend", default="ollama", help=backend_help)
    pm.set_defaults(fn=cmd_models)

    pc = sub.add_parser("chat", help="chat in the terminal")
    pc.add_argument("card")
    pc.add_argument("--model", required=True)
    pc.add_argument("--backend", default="ollama", help=backend_help)
    pc.add_argument("--user-name")
    pc.add_argument("--persona", help="personas.json from an import, or a plain-text description of you")
    pc.add_argument("--persona-name", help="which persona to use if the file has several")
    pc.add_argument("--resume", help="continue an existing .jsonl chat")
    pc.add_argument("--save-dir", default="localcai_chats")
    pc.add_argument("--temperature", type=float, default=0.8)
    pc.add_argument("--max-tokens", type=int, default=512)
    pc.set_defaults(fn=cmd_chat)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
