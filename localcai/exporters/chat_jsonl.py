"""SillyTavern chat .jsonl writer."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .. import facts
from ..schema import Chat
from .card_v2 import _safe


def chat_key(chat: Chat) -> str:
    """Stable id: re-importing the same chat updates it instead of duplicating it."""
    if chat.source_id:
        return hashlib.sha1(f"id|{chat.source_id}".encode("utf-8")).hexdigest()[:8]
    first = chat.messages[0].text if chat.messages else ""
    return hashlib.sha1(f"{chat.character_name}|{chat.created}|{first}".encode("utf-8")).hexdigest()[:8]


def _merge(old_rows: list[dict], new_rows: list[dict]) -> list[dict]:
    """Union of imported messages by id (newest copy wins, sorted by time), then any local rows
    (written in localCAI, no id) in their original order. A partial export never loses history."""
    by_id: dict[str, dict] = {}
    local: list[dict] = []
    for r in old_rows:
        rid = (r.get("extra") or {}).get("source_id")
        (by_id.__setitem__(rid, r) if rid else local.append(r))
    for r in new_rows:
        by_id[r["extra"]["source_id"]] = r
    imported = sorted(by_id.values(), key=lambda r: r.get("send_date") or "")
    return imported + local


def write_chat(chat: Chat, out_dir: Path, index: int = 0) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"{_safe(chat.character_name)}.{chat_key(chat)}.jsonl"
    lines = [{"user_name": chat.user_name, "character_name": chat.character_name,
              "create_date": chat.created or "", "chat_metadata": {"localcai_title": chat.title,
                                                                   "source_id": chat.source_id}}]
    if chat.memories:  # C.ai chat memory: this chat's facts (see facts.py)
        lines[0]["chat_metadata"][facts.KEY] = facts.from_cai(chat.memories)
    rows = []
    for m in chat.messages:
        extra = {"pinned": True} if m.pinned else {}
        if m.id:
            extra["source_id"] = m.id
        row = {"name": m.author, "is_user": m.is_user, "is_system": False,
               "send_date": m.timestamp or "", "mes": m.text, "extra": extra}
        if m.alternatives:
            row["swipes"] = [m.text] + m.alternatives
            row["swipe_id"] = 0
        rows.append(row)
    if p.exists() and all(r["extra"].get("source_id") for r in rows):
        from ..chatlog import load
        old_meta, old_rows = load(p)
        rows = _merge(old_rows, rows)
        # keep what was added in localCAI (story, background, the user's facts and edits)
        old_cm = old_meta.get("chat_metadata") or {}
        new_cm = lines[0]["chat_metadata"]
        if facts.KEY in old_cm:
            new_cm[facts.KEY] = facts.merge_import(old_cm[facts.KEY], new_cm.get(facts.KEY, []),
                                                    old_cm.get(facts.REMOVED))
        lines[0]["chat_metadata"] = {**old_cm, **new_cm}
    elif p.exists():
        # can't line the messages up without ids: keep the existing chat (it may have been continued
        # in localCAI) and save this import next to it instead of over it
        n = 2
        while (alt := p.with_name(f"{p.stem}-{n}.jsonl")).exists():
            n += 1
        p = alt
    lines += rows
    p.write_text("\n".join(json.dumps(l, ensure_ascii=False) for l in lines) + "\n", "utf-8")
    return p
