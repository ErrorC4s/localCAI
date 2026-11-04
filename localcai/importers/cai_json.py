"""Heuristic importer for Character.AI-shaped JSON.

Covers (best effort):
- The official "Export Data" file from Character.AI settings
- Wilds AI Exporter JSON
- Raw C.ai API-style dumps (turns with candidates / primary_candidate_id)

None of these formats is formally documented, so instead of hard-coding one
layout this walks the whole JSON tree and recognises things that *look like*
characters and chat turns. When you get a real export file that parses badly,
add a fixture under tests/fixtures/ and tighten the rules here.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..schema import Bundle, Character, Chat, Message
from ._util import pick, walk, as_text

CHAR_SIGNAL_KEYS = {"greeting", "definition", "first_mes", "title", "avatar_file_name"}
TEXT_KEYS = ("raw_content", "text", "content", "mes", "message")
PIN_KEYS = ("is_pinned", "pinned", "isPinned")


def _looks_like_character(d: dict) -> bool:
    return isinstance(d.get("name"), str) and len(CHAR_SIGNAL_KEYS & d.keys()) >= 1 \
        and not any(k in d for k in ("candidates", "is_human"))


def _clean_definition(defn: str) -> str:
    # C.ai separates example chats with END_OF_DIALOG; Tavern uses <START>.
    from .lcai import cai_definition
    return cai_definition(defn)


def _character(d: dict) -> Character:
    avatar = pick(d, "avatar_url", "avatar")
    if not avatar and d.get("avatar_file_name"):
        avatar = "https://characterai.io/i/400/static/avatars/" + d["avatar_file_name"]
    return Character(
        name=d["name"],
        tagline=as_text(pick(d, "title", "tagline")),
        description=as_text(pick(d, "description", "long_description")),
        greeting=as_text(pick(d, "greeting", "first_mes")),
        example_dialogue=_clean_definition(as_text(pick(d, "definition"))),
        creator=as_text(pick(d, "user__username", "creator", "creator_name", "author.name")),
        avatar_url=avatar or None,
        source="cai-json",
    )


def _turn_to_message(t: dict, char_name: str) -> Message | None:
    # C.ai API turn: candidates[] + primary_candidate_id
    if isinstance(t.get("candidates"), list) and t["candidates"]:
        cands = t["candidates"]
        primary = t.get("primary_candidate_id")
        chosen = next((c for c in cands if c.get("candidate_id") == primary), cands[-1])
        text = as_text(pick(chosen, *TEXT_KEYS))
        alts = [as_text(pick(c, *TEXT_KEYS)) for c in cands if c is not chosen]
    else:
        text = as_text(pick(t, *TEXT_KEYS))
        alts = []
    if not text:
        return None
    author = pick(t, "author.name", "author", "name", "src.name", "sender", default="")
    if isinstance(author, dict):
        author = as_text(author.get("name"))
    is_user = pick(t, "author.is_human", "is_human", "is_user", "isUser", default=None)
    if is_user is None:
        role = as_text(pick(t, "role", "type")).lower()
        is_user = role in ("user", "human") or (bool(author) and author != char_name and role != "assistant")
    return Message(
        author=as_text(author) or ("User" if is_user else char_name),
        is_user=bool(is_user),
        text=text,
        timestamp=as_text(pick(t, "create_time", "timestamp", "created", "send_date")) or None,
        pinned=any(bool(t.get(k)) for k in PIN_KEYS),
        alternatives=[a for a in alts if a],
    )


def _looks_like_turn_list(lst: list) -> bool:
    if len(lst) < 1 or not all(isinstance(x, dict) for x in lst):
        return False
    hits = sum(1 for x in lst if "candidates" in x or any(k in x for k in TEXT_KEYS))
    return hits >= max(1, int(len(lst) * 0.8))


def import_cai_json(path: Path) -> Bundle:
    data: Any = json.loads(path.read_text("utf-8"))
    bundle = Bundle()
    seen_chars: dict[str, Character] = {}
    for node in walk(data):
        if isinstance(node, dict) and _looks_like_character(node):
            c = _character(node)
            # keep the richest version if the same character appears twice
            prev = seen_chars.get(c.name)
            if not prev or len(c.example_dialogue + c.description) > len(prev.example_dialogue + prev.description):
                seen_chars[c.name] = c
    bundle.characters = list(seen_chars.values())
    default_char = bundle.characters[0].name if len(bundle.characters) == 1 else ""

    claimed: set[int] = set()
    for node in walk(data):
        if not isinstance(node, dict):
            continue
        for key in ("turns", "messages", "history", "chat", "msgs"):
            lst = node.get(key)
            if isinstance(lst, list) and id(lst) not in claimed and _looks_like_turn_list(lst):
                claimed.add(id(lst))
                char_name = as_text(pick(node, "character_name", "character.name", "name", default=default_char))
                msgs = [m for m in (_turn_to_message(t, char_name) for t in lst) if m]
                if _looks_newest_first(lst):
                    msgs.reverse()
                if not char_name:
                    char_name = next((m.author for m in msgs if not m.is_user), "Unknown")
                bundle.chats.append(Chat(character_name=char_name,
                                         user_name=next((m.author for m in msgs if m.is_user), "User"),
                                         messages=msgs, title=as_text(pick(node, "title", "name")),
                                         created=as_text(pick(node, "create_time", "created")) or None,
                                         source="cai-json"))
    if not bundle.characters and not bundle.chats:
        bundle.warnings.append(f"{path.name}: no characters or chats recognised — please open an issue "
                               "with a redacted sample of this file's structure")
    return bundle


def _looks_newest_first(lst: list) -> bool:
    times = [as_text(pick(t, "create_time", "timestamp")) for t in lst]
    times = [t for t in times if t]
    return len(times) >= 2 and times[0] > times[-1]
