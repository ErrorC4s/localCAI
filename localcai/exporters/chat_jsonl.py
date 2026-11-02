"""SillyTavern chat .jsonl writer."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..schema import Chat
from .card_v2 import _safe


def chat_key(chat: Chat) -> str:
    """Stable id: re-importing the same chat overwrites it instead of duplicating it."""
    first = chat.messages[0].text if chat.messages else ""
    return hashlib.sha1(f"{chat.character_name}|{chat.created}|{first}".encode("utf-8")).hexdigest()[:8]


def write_chat(chat: Chat, out_dir: Path, index: int = 0) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"{_safe(chat.character_name)}.{chat_key(chat)}.jsonl"
    lines = [{"user_name": chat.user_name, "character_name": chat.character_name,
              "create_date": chat.created or "", "chat_metadata": {"localcai_title": chat.title}}]
    for m in chat.messages:
        row = {"name": m.author, "is_user": m.is_user, "is_system": False,
               "send_date": m.timestamp or "", "mes": m.text,
               "extra": {"pinned": True} if m.pinned else {}}
        if m.alternatives:
            row["swipes"] = [m.text] + m.alternatives
            row["swipe_id"] = 0
        lines.append(row)
    p.write_text("\n".join(json.dumps(l, ensure_ascii=False) for l in lines) + "\n", "utf-8")
    return p
