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


HISTORY_BLOCK = 16  # history is dropped in blocks, so the prompt's beginning stays the same for many turns


def build_messages(card: dict, history: list[dict], user_name: str = "User",
                   max_chars: int = 24000, persona: str = "", memories: list[str] | None = None,
                   story: str = "", recalled: list[str] | None = None,
                   reply_words: int = 0) -> list[dict]:
    """history: [{"role": "user"|"assistant", "content": str}, ...]

    Built to be prompt-cache friendly: everything that stays the same from turn to turn
    (character, persona, constant memories, story, older history) comes first and only
    changes rarely; things that change every turn (keyword-triggered memories, recalled
    moments) are attached to the newest user message. The model server can then reuse
    its cache and only read the new part, which makes replies much faster.
    """
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
    book = d.get("character_book") or {}
    constant = [e["content"] for e in sorted(book.get("entries", []), key=lambda e: e.get("insertion_order", 0))
                if e.get("enabled", True) and e.get("constant")]
    for m in memories or []:  # pinned in this chat (in localCAI or on C.ai)
        if m not in constant:
            constant.append(m)
    if constant:
        parts.append("[Memories — always keep these in mind]\n" + "\n".join(f"- {x}" for x in constant))
    if story:
        parts.append(f"[The story so far between {char} and {user_name}]\n{story}")
    if d.get("mes_example"):
        parts.append("[Example dialogue — style reference only]\n" + d["mes_example"])
    if reply_words:
        parts.append(f"[Reply length]\nKeep each reply to about {reply_words} words or fewer, "
                     f"like {char}'s earlier replies. Say one or two things, then stop at a natural point "
                     f"and leave room for {user_name} to answer. Don't repeat yourself.")
    system = _fill("\n\n".join(parts), char, user_name)

    # per-turn context: keyword-triggered memories + recalled earlier moments
    scan_depth = book.get("scan_depth", 4)
    recent = "\n".join(m["content"] for m in history[-scan_depth:])
    triggered = [x for x in active_lore({**book, "entries": [e for e in book.get("entries", [])
                                                             if not e.get("constant")]}, recent) if x not in constant]
    extra = []
    if triggered:
        extra.append("[Relevant memories]\n" + "\n".join(f"- {x}" for x in triggered))
    if recalled:
        extra.append("[Earlier moments that may be relevant now]\n" + "\n".join(f"- {x}" for x in recalled))
    note = _fill("\n\n".join(extra), char, user_name) if extra else ""

    # Keep as much history as fits; drop the oldest in blocks so the kept part's start rarely moves.
    budget = max_chars - len(system) - len(note)
    total, start = 0, len(history)
    for i in range(len(history) - 1, -1, -1):
        total += len(history[i]["content"])
        if total > budget:
            break
        start = i
    if start > 0:
        start = min(len(history) - 1, -(-start // HISTORY_BLOCK) * HISTORY_BLOCK)
    kept = [dict(m) for m in history[start:]]
    if note:
        for m in reversed(kept):
            if m["role"] == "user":
                m["content"] = f"({note})\n\n{m['content']}"
                break
    # (The greeting is part of `history` — the chat loop seeds it as the first assistant turn.)
    return [{"role": "system", "content": system}] + kept


LENGTH_PRESETS = {"short": 60, "medium": 120, "long": 220}
_BUCKETS = (40, 60, 90, 120, 160, 220, 300)


def _words(text: str) -> int:
    cjk = sum(1 for ch in text if "\u3040" <= ch <= "\u9fff" or "\uac00" <= ch <= "\ud7af")
    return len(text.split()) + cjk // 2


def reply_words_for(setting: str, history: list[dict]) -> int:
    """Target reply length in words. "auto" copies how long the character's replies usually are
    (median, rounded to a few fixed steps so the prompt stays the same turn after turn)."""
    if setting in LENGTH_PRESETS:
        return LENGTH_PRESETS[setting]
    if setting == "off":
        return 0
    lens = sorted(_words(m["content"]) for m in history if m["role"] == "assistant" and m["content"].strip())
    if len(lens) < 3:
        return LENGTH_PRESETS["medium"]
    med = lens[len(lens) // 2]
    return min(_BUCKETS, key=lambda b: abs(b - med * 1.15))
