"""The local library: where imported characters, chats and personas live.

Default location: ~/.localcai/library (override with the LOCALCAI_HOME env var).

    characters/<name>.card.json + <name>.card.png   Character Card V2
    chats/<name>.<id>.jsonl                          SillyTavern chat logs
    personas/personas.json                           your personas
"""
from __future__ import annotations

import json
import shutil
import os
from dataclasses import dataclass, field
from pathlib import Path

from .exporters import write_card, write_chat
from .exporters.card_v2 import _safe, embed_card_in_png, to_card_v2
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


def _entry_key(e: dict) -> tuple:
    return (str(e.get("content", "")).strip(), tuple(sorted(str(k) for k in e.get("keys") or [])))


def merge_books_unique(a: dict | None, b: dict | None) -> dict | None:
    """Like merge_books, but an entry that's already there (same text and keys) isn't added twice,
    so importing the same chat again doesn't duplicate its memories."""
    if not a or not b:
        return a or b
    have = {_entry_key(e) for e in a.get("entries", [])}
    new = [e for e in b.get("entries", []) if _entry_key(e) not in have]
    return merge_books(a, {**b, "entries": new}) if new else a


def _merge_card(jp: Path, c: Character, book: dict | None) -> tuple[Path, Path]:
    """Update a card that's already in the library from an import without losing anything.

    - a card rebuilt from a chat (no real definition) leaves the existing definition untouched;
    - a real card in the import replaces the definition, but the localCAI settings made in the
      app (rules, pronouns...) and the existing memories are kept;
    - the avatar is kept unless the import brings one."""
    old = json.loads(jp.read_text("utf-8"))
    od = old.get("data", old)
    if c.source == "reconstructed-from-chat":
        card = old if "data" in old else {"spec": "chara_card_v2", "spec_version": "2.0", "data": od}
        d = card["data"]
    else:
        card = to_card_v2(c, None)
        d = card["data"]
        mine = (od.get("extensions") or {}).get("localcai") or {}
        d["extensions"]["localcai"] = {**mine, **d["extensions"]["localcai"]}  # keep rules, pronouns…
        for k, v in (od.get("extensions") or {}).items():
            d["extensions"].setdefault(k, v)
    merged = merge_books_unique(od.get("character_book"), book)
    if merged:
        d["character_book"] = merged
    jp.write_text(json.dumps(card, ensure_ascii=False, indent=2), "utf-8")
    pp = jp.with_name(jp.name.removesuffix(".card.json") + ".card.png")
    try:
        image = c.avatar_png or (pp.read_bytes() if pp.exists() else None)
        if image:
            pp.write_bytes(embed_card_in_png(image, card))
        else:
            from .exporters.card_v2 import placeholder_png
            pp.write_bytes(embed_card_in_png(placeholder_png(), card))
    except (OSError, ValueError):
        pass
    return jp, pp


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
            if not (out / "characters" / f"{_safe(chat.character_name)}.card.json").exists():
                rep.warnings.append(f"'{chat.character_name}': no character definition found, so a minimal "
                                    "card was made from the chat. Edit it to add personality.")

    for c in bundle.characters:
        book = merge_books(c.extra.get("character_book"), pins_to_lorebook(bundle.chats, c.name))
        existing = out / "characters" / f"{_safe(c.name)}.card.json"
        if existing.exists():
            # Already in the library: never lose what's there (the user's edits, memories, rules,
            # pronouns, avatar). A chat-only import just adds its pinned memories to the card.
            jp, pp = _merge_card(existing, c, book)
        else:
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
    # "?v=<mtime>" so a replaced picture with the same name isn't served from the cache
    return f"{hits[0].name}?v={int(hits[0].stat().st_mtime)}" if hits else None


def _chat_style(cp: Path) -> dict:
    try:
        with cp.open(encoding="utf-8") as f:
            meta = json.loads(f.readline() or "{}")
        return (meta.get("chat_metadata") or {}).get("localcai_bg") or {}
    except (OSError, ValueError):
        return {}


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
                          "background": _find(lib / "chats", f"{cp.stem}.background"),
                          "bg_style": _chat_style(cp)})
        book = d.get("character_book") or {}
        stem = jp.name.removesuffix(".card.json")
        local = (d.get("extensions", {}) or {}).get("localcai", {}) or {}
        chars.append({"name": name, "file": stem,
                      "has_avatar": bool(local.get("has_avatar")),
                      "background": _find(lib / "characters", f"{stem}.background"),
                      "custom_background": _find(lib / "characters", f"{stem}.custom-bg"),
                      "tagline": d.get("creator_notes", ""), "creator": d.get("creator", ""),
                      "memories": len(book.get("entries", [])), "chats": chats,
                      "pronouns": local.get("pronouns", ""), "pronouns_guess": guess_card_pronouns(d),
                      "reply_length": local.get("reply_length", "")})
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


# ── trash: what Delete moved away, to look at, restore or delete for good ─────────────────────

def _trash_batch(lib: Path, batch: str) -> Path:
    if not batch or "/" in batch or "\\" in batch or batch.startswith("."):
        raise ValueError("bad name")
    p = lib / "trash" / batch
    if not p.is_dir():
        raise FileNotFoundError(batch)
    return p


def list_trash(lib: Path) -> list[dict]:
    """Newest first: each deletion with the characters and chats in it."""
    out = []
    root = lib / "trash"
    for b in sorted((d for d in root.iterdir() if d.is_dir()), reverse=True) if root.is_dir() else []:
        chars, chats, size = [], [], 0
        for f in b.rglob("*"):
            if f.is_file():
                size += f.stat().st_size
        for jp in sorted((b / "characters").glob("*.card.json")):
            try:
                chars.append(json.loads(jp.read_text("utf-8")).get("data", {}).get("name") or jp.name[:-10])
            except (OSError, ValueError):
                chars.append(jp.name[:-10])
        for cp in sorted((b / "chats").glob("*.jsonl")):
            with cp.open("rb") as fh:
                n = max(0, sum(1 for _ in fh) - 1)
            chats.append({"file": cp.name, "character": cp.name.split(".")[0], "messages": n})
        out.append({"batch": b.name, "characters": chars, "chats": chats, "bytes": size})
    return out


def restore_trash(lib: Path, batch: str) -> dict:
    """Move a deletion back. A character that's in the library again (e.g. imported anew) keeps its current
    card; its old chats come back next to the new ones (renamed "-restored" if the same name is taken)."""
    b = _trash_batch(lib, batch)
    kept_cards, renamed, restored = [], [], 0
    for f in sorted((b / "characters").glob("*")) if (b / "characters").is_dir() else []:
        dest = lib / "characters" / f.name
        if dest.exists():
            if f.name.endswith(".card.json"):
                kept_cards.append(f.name[:-10])
            continue
        f.replace(dest)
        restored += 1
    chat_dir = b / "chats"
    for cp in sorted(chat_dir.glob("*.jsonl")) if chat_dir.is_dir() else []:
        stem = cp.name[:-6]
        new_stem, n = stem, 1
        while (lib / "chats" / f"{new_stem}.jsonl").exists():
            new_stem = f"{stem}-restored" + (f"{n}" if n > 1 else "")
            n += 1
        if new_stem != stem:
            renamed.append(f"{new_stem}.jsonl")
        for f in sorted(chat_dir.glob(f"{stem}.*")):  # the chat and its files (scene notes, background)
            f.replace(lib / "chats" / f"{new_stem}{f.name[len(stem):]}")
            restored += 1
    if not any(f.is_file() for f in b.rglob("*")):  # leftovers (the old card of a character that's back) stay
        shutil.rmtree(b, ignore_errors=True)
    return {"restored": restored, "kept_cards": kept_cards, "renamed": renamed}


def empty_trash(lib: Path, batch: str) -> None:
    shutil.rmtree(_trash_batch(lib, batch))
