"""Build the message list sent to the local model from a Character Card V2."""
from __future__ import annotations


def _fill(text: str, char: str, user: str) -> str:
    return (text.replace("{{char}}", char).replace("{{user}}", user)
                .replace("<BOT>", char).replace("<USER>", user))


def active_lore(book: dict | None, recent_text: str) -> list[str]:
    if not book:
        return []
    out, low = [], recent_text.lower()
    for e in sorted(book.get("entries", []), key=lambda e: e.get("insertion_order", 0)):
        if not e.get("enabled", True):
            continue
        keys = e.get("keys", [])
        if e.get("constant") or any((k if e.get("case_sensitive") else k.lower()) in
                                    (recent_text if e.get("case_sensitive") else low) for k in keys if k):
            out.append(e["content"])
    return out


def build_messages(card: dict, history: list[dict], user_name: str = "User",
                   max_chars: int = 24000, persona: str = "") -> list[dict]:
    """history: [{"role": "user"|"assistant", "content": str}, ...]"""
    d = card.get("data", card)
    char = d.get("name", "Character")
    parts = [d.get("system_prompt") or
             f"You are {char}. Stay in character and reply as {char} would, "
             f"in the same language {user_name} uses. Never speak for {user_name}."]
    for label, key in (("Description", "description"), ("Personality", "personality"),
                       ("Scenario", "scenario")):
        if d.get(key):
            parts.append(f"[{label}]\n{d[key]}")
    if persona:
        # C.ai "persona": who the user says they are in this story
        parts.append(f"[About {user_name}]\n{persona}")
    book = d.get("character_book")
    scan_depth = (book or {}).get("scan_depth", 4)
    recent = "\n".join(m["content"] for m in history[-scan_depth:])
    lore = active_lore(book, recent)
    if lore:
        parts.append("[Memories — always keep these in mind]\n" + "\n".join(f"- {x}" for x in lore))
    if d.get("mes_example"):
        parts.append("[Example dialogue — style reference only]\n" + d["mes_example"])
    system = _fill("\n\n".join(parts), char, user_name)

    # Keep as much recent history as fits in the budget (rough char-based budget).
    budget = max_chars - len(system)
    kept: list[dict] = []
    for m in reversed(history):
        budget -= len(m["content"])
        if budget < 0:
            break
        kept.append(m)
    kept.reverse()
    # (The greeting is part of `history` — the chat loop seeds it as the first assistant turn.)
    return [{"role": "system", "content": system}] + kept
