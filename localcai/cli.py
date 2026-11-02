"""localCAI command line.

  localcai import <file-or-folder> [-o out/]      Convert exports into cards + chats
  localcai models [--backend ollama]              List models your local runner has
  localcai chat <card> --model NAME [--backend …] Chat with a card on a local model
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from . import __version__
from .exporters import write_card, write_chat
from .importers import import_path
from .importers.sillytavern import card_from_png, import_chat_jsonl
from .memory import merge_books, pins_to_lorebook
from .runtime import build_messages, list_models, resolve_base_url, stream_chat, BACKENDS
from .safety import RESOURCES, age_gate, looks_like_crisis
from .schema import Character


def cmd_import(a: argparse.Namespace) -> int:
    bundle = import_path(a.path)
    if a.swap_roles:
        for chat in bundle.chats:
            for m in chat.messages:
                m.is_user = not m.is_user
    if a.user_name:
        for chat in bundle.chats:
            chat.user_name = a.user_name
    out = Path(a.output)
    known = {c.name for c in bundle.characters}
    # A chat without a matching character still deserves a playable card.
    for chat in bundle.chats:
        if chat.character_name not in known:
            first_bot = next((m.text for m in chat.messages if not m.is_user), "")
            bundle.characters.append(Character(name=chat.character_name, greeting=first_bot,
                                               source="reconstructed-from-chat"))
            known.add(chat.character_name)
            bundle.warnings.append(f"'{chat.character_name}': no character definition found, "
                                   "made a minimal card from the chat — edit it to add personality")
    for c in bundle.characters:
        book = merge_books(c.extra.get("character_book"), pins_to_lorebook(bundle.chats, c.name))
        jp, _ = write_card(c, out / "characters", book)
        pins = len(book["entries"]) if book else 0
        print(f"  ✓ character  {c.name}  ({pins} memories)  → {jp}")
    for i, chat in enumerate(bundle.chats):
        p = write_chat(chat, out / "chats", i)
        print(f"  ✓ chat       {chat.character_name}  {len(chat.messages)} msgs, "
              f"{len(chat.pins)} pinned  → {p}")
    for w in bundle.warnings:
        print(f"  ! {w}", file=sys.stderr)
    if not bundle.characters and not bundle.chats:
        return 1
    print(f"\nDone. Import {out/'characters'} into SillyTavern, or run:\n"
          f"  localcai chat \"{out/'characters'}/<name>.card.png\" --model <your-model>")
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


def cmd_chat(a: argparse.Namespace) -> int:
    if not age_gate():
        print("抱歉，聊天功能僅供成人使用。/ Sorry, chat is for adults only.")
        return 1
    card = _load_card(Path(a.card))
    d = card.get("data", card)
    char, user = d.get("name", "Character"), a.user_name
    url = resolve_base_url(a.backend)

    history: list[dict] = []
    if a.resume:
        for m in import_chat_jsonl(Path(a.resume)).chats[0].messages:
            history.append({"role": "user" if m.is_user else "assistant", "content": m.text})
    elif d.get("first_mes"):
        history.append({"role": "assistant",
                        "content": d["first_mes"].replace("{{char}}", char).replace("{{user}}", user)})

    save = Path(a.resume) if a.resume else Path(a.save_dir) / f"{char}.{datetime.now():%Y%m%d-%H%M%S}.jsonl"
    save.parent.mkdir(parents=True, exist_ok=True)

    print(f"── {char} · {a.model} @ {url} · /quit to exit ──\n")
    for m in history[-6:]:
        print(f"{char if m['role'] == 'assistant' else user}: {m['content']}\n")
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
        history.append({"role": "user", "content": text})
        print(f"\n{char}: ", end="", flush=True)
        reply = []
        try:
            for tok in stream_chat(url, a.model, build_messages(card, history, user),
                                   temperature=a.temperature, max_tokens=a.max_tokens):
                print(tok, end="", flush=True)
                reply.append(tok)
        except OSError as e:
            print(f"\n[error talking to {url}: {e}]")
            history.pop()
            continue
        print("\n")
        history.append({"role": "assistant", "content": "".join(reply)})
        _save(save, history, char, user)
    print(f"Chat saved to {save}")
    return 0


def _save(path: Path, history: list[dict], char: str, user: str) -> None:
    lines = [{"user_name": user, "character_name": char}]
    lines += [{"name": user if m["role"] == "user" else char, "is_user": m["role"] == "user",
               "mes": m["content"]} for m in history]
    path.write_text("\n".join(json.dumps(l, ensure_ascii=False) for l in lines) + "\n", "utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="localcai", description="Bring your characters home.")
    p.add_argument("--version", action="version", version=f"localCAI {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("import", help="convert exported chats/characters")
    pi.add_argument("path")
    pi.add_argument("-o", "--output", default="localcai_out")
    pi.add_argument("--swap-roles", action="store_true", help="fix chats where user/character are swapped")
    pi.add_argument("--user-name", help="your display name in the converted chats")
    pi.set_defaults(fn=cmd_import)

    backend_help = "backend preset (" + ", ".join(BACKENDS) + ") or a full base URL"
    pm = sub.add_parser("models", help="list models on your local runner")
    pm.add_argument("--backend", default="ollama", help=backend_help)
    pm.set_defaults(fn=cmd_models)

    pc = sub.add_parser("chat", help="chat with a card on a local model")
    pc.add_argument("card")
    pc.add_argument("--model", required=True)
    pc.add_argument("--backend", default="ollama", help=backend_help)
    pc.add_argument("--user-name", default="User")
    pc.add_argument("--resume", help="continue an existing .jsonl chat")
    pc.add_argument("--save-dir", default="localcai_chats")
    pc.add_argument("--temperature", type=float, default=0.8)
    pc.add_argument("--max-tokens", type=int, default=512)
    pc.set_defaults(fn=cmd_chat)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
