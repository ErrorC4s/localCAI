"""Reader for localCAI's own `.lcai.json` format (see docs/lcai-format.md). Exact, no heuristics."""
from __future__ import annotations

import json
from pathlib import Path

from ..images import decode_data_url, png_or_none
from ..schema import Bundle, Character, Chat, Message

SUPPORTED_VERSIONS = {1}


def is_lcai(data: object) -> bool:
    return isinstance(data, dict) and data.get("format") == "localcai"


def import_lcai(path: Path, data: dict | None = None) -> Bundle:
    data = data if data is not None else json.loads(path.read_text("utf-8"))
    b = Bundle()
    if data.get("version") not in SUPPORTED_VERSIONS:
        b.warnings.append(f"{path.name}: .lcai version {data.get('version')} is newer than this "
                          "localCAI understands; upgrade with `pip install -U localcai`")
        return b
    for c in data.get("characters", []):
        b.characters.append(Character(
            name=c.get("name") or "Unnamed",
            tagline=c.get("tagline", ""),
            description=c.get("description", ""),
            greeting=c.get("greeting", ""),
            alternate_greetings=list(c.get("alternate_greetings") or []),
            example_dialogue=(c.get("definition") or "").replace("END_OF_DIALOG", "<START>").strip(),
            creator=c.get("creator", ""),
            avatar_url=c.get("avatar_url"),
            avatar_png=png_or_none(c.get("avatar_png")),
            background=decode_data_url(c.get("background")),
            source="lcai",
            extra={"id": c.get("id"), "is_own": c.get("is_own", False)},
        ))
        if c.get("definition_withheld"):
            b.warnings.append(f"'{c.get('name')}': the creator keeps this definition private, so only "
                              "the public parts were exported. The card will feel thinner; "
                              "you can add personality by hand")
    for ch in data.get("chats", []):
        msgs = []
        for t in ch.get("turns", []):
            cands = [x for x in t.get("candidates", []) if x]
            if not cands:
                continue
            p = t.get("primary", 0)
            p = p if 0 <= p < len(cands) else 0
            a = t.get("author", {})
            msgs.append(Message(author=a.get("name", ""), is_user=bool(a.get("is_user")),
                                text=cands[p], timestamp=t.get("created"),
                                pinned=bool(t.get("pinned")),
                                alternatives=[x for i, x in enumerate(cands) if i != p]))
        b.chats.append(Chat(character_name=ch.get("character_name", "Unknown"),
                            user_name=ch.get("user_name") or "User", messages=msgs,
                            title=ch.get("title", ""), created=ch.get("created"), source="lcai",
                            memories=[m for m in ch.get("memories", []) if m.get("value")],
                            background=decode_data_url(ch.get("background"))))
    for p in data.get("personas", []):
        if p.get("name"):
            b.personas.append({"name": p["name"], "description": p.get("description", ""),
                               "avatar_png": png_or_none(p.get("avatar_png")),
                               "background": decode_data_url(p.get("background"))})
    for err in data.get("asset_errors", []) or []:
        b.warnings.append(f"image not downloaded by the extension: {err}")
    return b
