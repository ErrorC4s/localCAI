"""Character Card V2 (chara_card_v2) — the de-facto standard read by
SillyTavern, RisuAI, Agnai, KoboldCpp, etc."""
from __future__ import annotations

import base64
import json
import struct
import zlib
from pathlib import Path

from ..schema import Character


def to_card_v2(c: Character, character_book: dict | None = None) -> dict:
    book = character_book or c.extra.get("character_book")
    data = {
        "name": c.name,
        "description": c.description,
        "personality": c.personality,
        "scenario": c.scenario,
        "first_mes": c.greeting,
        "mes_example": c.example_dialogue,
        "creator_notes": c.tagline,
        "system_prompt": "",
        "post_history_instructions": "",
        "alternate_greetings": c.alternate_greetings,
        "tags": c.tags,
        "creator": c.creator,
        "character_version": "",
        "extensions": {"localcai": {"source": c.source, "avatar_url": c.avatar_url,
                                    "has_avatar": c.avatar_png is not None}},
    }
    if book:
        data["character_book"] = book
    return {"spec": "chara_card_v2", "spec_version": "2.0", "data": data}


def _chunk(ctype: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + ctype + body + struct.pack(">I", zlib.crc32(ctype + body) & 0xFFFFFFFF)


def placeholder_png(w: int = 400, h: int = 600, rgb=(60, 64, 82)) -> bytes:
    row = b"\x00" + bytes(rgb) * w
    raw = zlib.compress(row * h, 9)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + _chunk(b"IDAT", raw) + _chunk(b"IEND", b""))


def embed_card_in_png(png: bytes, card: dict) -> bytes:
    """Insert a tEXt 'chara' chunk right before IEND (replacing any existing one)."""
    if png[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("avatar is not a PNG")
    payload = base64.b64encode(json.dumps(card, ensure_ascii=False).encode("utf-8"))
    out, pos = [png[:8]], 8
    while pos < len(png):
        length = struct.unpack(">I", png[pos:pos + 4])[0]
        ctype = png[pos + 4:pos + 8]
        chunk = png[pos:pos + 12 + length]
        pos += 12 + length
        if ctype == b"tEXt" and chunk[8:].split(b"\x00", 1)[0] in (b"chara", b"ccv3"):
            continue
        if ctype == b"IEND":
            out.append(_chunk(b"tEXt", b"chara\x00" + payload))
        out.append(chunk)
    return b"".join(out)


def write_card(c: Character, out_dir: Path, character_book: dict | None = None,
               avatar_png: bytes | None = None) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    card = to_card_v2(c, character_book)
    stem = _safe(c.name)
    jp = out_dir / f"{stem}.card.json"
    jp.write_text(json.dumps(card, ensure_ascii=False, indent=2), "utf-8")
    pp = out_dir / f"{stem}.card.png"
    pp.write_bytes(embed_card_in_png(avatar_png or c.avatar_png or placeholder_png(), card))
    return jp, pp


def _safe(name: str) -> str:
    keep = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in name).strip()
    return keep or "character"
