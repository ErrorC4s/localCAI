"""SillyTavern / TavernAI formats.

CAI Tools can save chats "in Oobabooga, Tavern & SillyTavern formats" and
characters as Tavern cards, so supporting these covers CAI Tools output too.

- Chat: .jsonl — line 1 is metadata {user_name, character_name, ...},
  every following line is {name, is_user, send_date, mes, swipes?}.
- Character: Tavern card V1 (flat JSON), V2 ({spec: chara_card_v2, data: {...}}),
  or a PNG with the JSON base64-encoded in a tEXt chunk named "chara" / "ccv3".
"""
from __future__ import annotations

import base64
import json
import struct
import zlib
from pathlib import Path

from ..schema import Bundle, Character, Chat, Message
from ._util import pick, as_text


def read_png_text_chunks(data: bytes) -> dict[str, str]:
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file")
    out: dict[str, str] = {}
    pos = 8
    while pos + 8 <= len(data):
        length, ctype = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if ctype == b"tEXt":
            key, _, val = body.partition(b"\x00")
            out[key.decode("latin-1")] = val.decode("latin-1")
        elif ctype == b"zTXt":
            key, _, rest = body.partition(b"\x00")
            out[key.decode("latin-1")] = zlib.decompress(rest[1:]).decode("latin-1")
        elif ctype == b"IEND":
            break
    return out


def card_from_png(path: Path) -> dict:
    chunks = read_png_text_chunks(path.read_bytes())
    raw = chunks.get("ccv3") or chunks.get("chara")
    if not raw:
        raise ValueError(f"{path.name}: PNG has no character card chunk")
    return json.loads(base64.b64decode(raw).decode("utf-8"))


def character_from_card(card: dict, source: str = "tavern-card") -> Character:
    data = card.get("data", card) if isinstance(card.get("data"), dict) else card
    return Character(
        name=as_text(pick(data, "name", "char_name", default="Unnamed")),
        description=as_text(pick(data, "description", "char_persona")),
        personality=as_text(pick(data, "personality")),
        scenario=as_text(pick(data, "scenario", "world_scenario")),
        greeting=as_text(pick(data, "first_mes", "char_greeting")),
        alternate_greetings=list(pick(data, "alternate_greetings", default=[])),
        example_dialogue=as_text(pick(data, "mes_example", "example_dialogue")),
        creator=as_text(pick(data, "creator")),
        tagline=as_text(pick(data, "creator_notes")),
        tags=list(pick(data, "tags", default=[])),
        source=source,
        extra={"character_book": data["character_book"]} if data.get("character_book") else {},
    )


def import_card(path: Path) -> Bundle:
    card = card_from_png(path) if path.suffix.lower() == ".png" else json.loads(path.read_text("utf-8"))
    return Bundle(characters=[character_from_card(card)])


def import_chat_jsonl(path: Path) -> Bundle:
    lines = [json.loads(l) for l in path.read_text("utf-8").splitlines() if l.strip()]
    if not lines:
        return Bundle(warnings=[f"{path.name}: empty chat file"])
    meta = lines[0] if "mes" not in lines[0] else {}
    rows = lines[1:] if meta else lines
    user = as_text(pick(meta, "user_name", default="User"))
    char = as_text(pick(meta, "character_name", default=""))
    msgs = []
    for r in rows:
        is_user = bool(r.get("is_user"))
        name = as_text(pick(r, "name", default=user if is_user else char))
        swipes = [s for s in r.get("swipes", []) if s != r.get("mes")]
        msgs.append(Message(author=name, is_user=is_user, text=as_text(r.get("mes")),
                            timestamp=as_text(r.get("send_date")) or None,
                            pinned=bool(r.get("extra", {}).get("pinned") or r.get("is_pinned")),
                            alternatives=swipes))
        if not char and not is_user:
            char = name
    warnings = []
    # Known CAI Tools issue: Tavern-format chats can come out with user/character swapped.
    if msgs and msgs[0].is_user and char and msgs[0].author == char:
        warnings.append(f"{path.name}: first message is marked as user but authored by "
                        f"'{char}' — roles may be swapped; re-run with --swap-roles if so")
    return Bundle(chats=[Chat(character_name=char or "Unknown", user_name=user,
                              messages=msgs, created=as_text(meta.get("create_date")) or None,
                              source="sillytavern-jsonl")], warnings=warnings)
