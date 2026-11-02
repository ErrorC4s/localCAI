"""Turn C.ai pinned messages and chat memory ("conversation facts") into long-term memory.

On C.ai, pinning a message means "always remember this". The closest local
equivalent is a *constant* lorebook entry: it is injected into every prompt,
regardless of keywords. That is what we generate.
"""
from __future__ import annotations

from .schema import Chat


def pins_to_lorebook(chats: list[Chat], character_name: str) -> dict | None:
    entries = []
    for chat in chats:
        if chat.character_name != character_name:
            continue
        for m in chat.pins:
            entries.append({
                "id": len(entries),
                "name": f"pin-{len(entries) + 1}",
                "keys": [],
                "content": f"{m.author}: {m.text}",
                "enabled": True,
                "constant": True,
                "insertion_order": len(entries),
                "case_sensitive": False,
                "comment": f"Pinned on Character.AI{(' at ' + m.timestamp) if m.timestamp else ''}",
                "extensions": {"localcai": {"from_pin": True}},
            })
        for f in chat.memories:
            entries.append({
                "id": len(entries),
                "name": f"memory-{len(entries) + 1}",
                "keys": [],
                "content": f"{f.get('about', '')} — {f.get('category', '')}: {f['value']}".strip(" —:"),
                "enabled": True,
                "constant": True,
                "insertion_order": len(entries),
                "case_sensitive": False,
                "comment": "Character.AI chat memory (conversation fact)",
                "extensions": {"localcai": {"from_memory": True}},
            })
    if not entries:
        return None
    return {
        "name": f"{character_name} — memories",
        "description": "Imported from Character.AI pinned messages and chat memory by localCAI",
        "scan_depth": 4,
        "token_budget": 1024,
        "recursive_scanning": False,
        "extensions": {},
        "entries": entries,
    }


def merge_books(a: dict | None, b: dict | None) -> dict | None:
    if not a:
        return b
    if not b:
        return a
    merged = dict(a)
    start = len(a.get("entries", []))
    merged["entries"] = list(a.get("entries", [])) + [
        {**e, "id": start + i, "insertion_order": start + i} for i, e in enumerate(b["entries"])
    ]
    return merged
