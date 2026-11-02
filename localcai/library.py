"""The local library: where imported characters, chats and personas live.

Default location: ~/.localcai/library (override with the LOCALCAI_HOME env var).

    characters/<name>.card.json + <name>.card.png   Character Card V2
    chats/<name>.<id>.jsonl                          SillyTavern chat logs
    personas/personas.json                           your personas
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .exporters import write_card, write_chat
from .exporters.card_v2 import _safe
from .images import ext_for
from .importers import import_path
from .memory import merge_books, pins_to_lorebook
from .schema import Character


def home() -> Path:
    return Path(os.environ.get("LOCALCAI_HOME") or Path.home() / ".localcai")


def default_library() -> Path:
    return home() / "library"


@dataclass
class ImportReport:
    characters: list[dict] = field(default_factory=list)
    chats: list[dict] = field(default_factory=list)
    personas: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.characters and not self.chats and not self.personas


def import_into(src: str | Path, out: str | Path, swap_roles: bool = False,
                user_name: str | None = None) -> ImportReport:
    out = Path(out)
    bundle = import_path(src)
    rep = ImportReport(warnings=list(bundle.warnings))
    if swap_roles:
        for chat in bundle.chats:
            for m in chat.messages:
                m.is_user = not m.is_user
    if user_name:
        for chat in bundle.chats:
            chat.user_name = user_name

    known = {c.name for c in bundle.characters}
    for chat in bundle.chats:  # a chat without a matching character still deserves a playable card
        if chat.character_name not in known:
            first_bot = next((m.text for m in chat.messages if not m.is_user), "")
            bundle.characters.append(Character(name=chat.character_name, greeting=first_bot,
                                               source="reconstructed-from-chat"))
            known.add(chat.character_name)
            rep.warnings.append(f"'{chat.character_name}': no character definition found, so a minimal "
                                "card was made from the chat. Edit it to add personality.")

    for c in bundle.characters:
        book = merge_books(c.extra.get("character_book"), pins_to_lorebook(bundle.chats, c.name))
        jp, pp = write_card(c, out / "characters", book)
        if c.background:
            _write_image(out / "characters", f"{_safe(c.name)}.background", c.background)
        rep.characters.append({"name": c.name, "memories": len(book["entries"]) if book else 0,
                               "avatar": c.avatar_png is not None, "background": c.background is not None,
                               "card_json": str(jp), "card_png": str(pp)})
    for chat in bundle.chats:
        p = write_chat(chat, out / "chats")
        if chat.background:
            _write_image(out / "chats", f"{p.stem}.background", chat.background)
        rep.chats.append({"character": chat.character_name, "messages": len(chat.messages),
                          "pinned": len(chat.pins), "memories": len(chat.memories), "path": str(p)})

    if bundle.personas:
        pfile = out / "personas" / "personas.json"
        existing = json.loads(pfile.read_text("utf-8")) if pfile.exists() else []
        merged = {p["name"]: p for p in existing}
        for per in bundle.personas:  # newest wins; images become files next to personas.json
            entry = {"name": per["name"], "description": per.get("description", "")}
            old = merged.get(per["name"], {})
            if per.get("avatar_png"):
                entry["avatar"] = _write_image(out / "personas", f"{_safe(per['name'])}.avatar",
                                               ("image/png", per["avatar_png"]))
            elif old.get("avatar"):
                entry["avatar"] = old["avatar"]
            if per.get("background"):
                entry["background"] = _write_image(out / "personas", f"{_safe(per['name'])}.background",
                                                   per["background"])
            elif old.get("background"):
                entry["background"] = old["background"]
            merged[per["name"]] = entry
        pfile.parent.mkdir(parents=True, exist_ok=True)
        pfile.write_text(json.dumps(list(merged.values()), ensure_ascii=False, indent=2), "utf-8")
        rep.personas = [p["name"] for p in bundle.personas]
    return rep


def _write_image(folder: Path, stem: str, image: tuple[str, bytes]) -> str:
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob(f"{stem}.*"):  # replace an older image in another format
        old.unlink()
    path = folder / f"{stem}.{ext_for(image[0])}"
    path.write_bytes(image[1])
    return path.name


def _find(folder: Path, stem: str) -> str | None:
    hits = [p for p in folder.glob(f"{stem}.*") if p.suffix.lower() in (".png", ".jpg", ".webp", ".gif")]
    return hits[0].name if hits else None


def list_library(lib: Path) -> dict:
    from .runtime.prompt import guess_card_pronouns, guess_pronouns
    chars = []
    for jp in sorted((lib / "characters").glob("*.card.json")):
        try:
            d = json.loads(jp.read_text("utf-8")).get("data", {})
        except ValueError:
            continue
        name = d.get("name", jp.stem)
        chats = []
        for cp in sorted((lib / "chats").glob(f"{_safe(name)}.*.jsonl"),
                         key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                n = sum(1 for l in cp.read_text("utf-8").splitlines() if l.strip()) - 1
            except OSError:
                continue
            chats.append({"file": cp.name, "messages": max(n, 0), "modified": cp.stat().st_mtime,
                          "background": _find(lib / "chats", f"{cp.stem}.background")})
        book = d.get("character_book") or {}
        stem = jp.name.removesuffix(".card.json")
        local = (d.get("extensions", {}) or {}).get("localcai", {}) or {}
        chars.append({"name": name, "file": stem,
                      "has_avatar": bool(local.get("has_avatar")),
                      "background": _find(lib / "characters", f"{stem}.background"),
                      "tagline": d.get("creator_notes", ""), "creator": d.get("creator", ""),
                      "memories": len(book.get("entries", [])), "chats": chats,
                      "pronouns": local.get("pronouns", ""), "pronouns_guess": guess_card_pronouns(d)})
    pfile = lib / "personas" / "personas.json"
    personas = json.loads(pfile.read_text("utf-8")) if pfile.exists() else []
    for p in personas if isinstance(personas, list) else []:
        if isinstance(p, dict):
            p["pronouns_guess"] = guess_pronouns(str(p.get("description") or p.get("persona") or ""))
    return {"characters": chars, "personas": personas}


def delete_character(lib: Path, file_stem: str) -> int:
    """Move a character's card, background and chats to library/trash/<timestamp>/ (recoverable)."""
    from datetime import datetime
    if not file_stem or "/" in file_stem or "\\" in file_stem or file_stem.startswith("."):
        raise ValueError("bad name")
    card = lib / "characters" / f"{file_stem}.card.json"
    if not card.exists():
        raise FileNotFoundError(file_stem)
    trash = lib / "trash" / datetime.now().strftime("%Y%m%d-%H%M%S")
    moved = 0
    targets = list((lib / "characters").glob(f"{file_stem}.card.*")) + \
        list((lib / "characters").glob(f"{file_stem}.background.*")) + \
        list((lib / "chats").glob(f"{file_stem}.*"))
    for f in targets:
        dest = trash / f.parent.name / f.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        f.replace(dest)
        moved += 1
    return moved
