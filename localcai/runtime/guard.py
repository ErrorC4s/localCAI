"""OOC guard: a quick second look at each reply, for any character.

After a reply is written, the model is asked to act as a strict editor and say whether the reply
breaks character. Length is checked in code (cheap and reliable); the rest is judged by the model
from a short summary of the character, the user's message and the reply. When something is wrong,
the caller rewrites the reply with the returned instruction (the same path as ✨ in the UI).
"""
from __future__ import annotations

import re
from typing import Callable

from .prompt import _words

CHECK_SYSTEM = ("You are a strict editor for a roleplay app. You check one reply written as a fictional "
                "character and decide whether it breaks character. You never write the reply yourself. "
                "Answer with exactly one line: either OK, or FIX: followed by a short instruction to the writer.")

CHECK_PROMPT = """Character: {char}
About {char}: {about}

{user}'s message:
<<<
{last_user}
>>>

{char}'s reply:
<<<
{reply}
>>>

Does the reply break character? Only these count as problems:
1. It says or hints that {char} is an AI, a model, a bot, a character or part of a story.
2. {char} acts like an assistant: offers to help with tasks, writes code, lists, or explanations {char} would not give.
3. {char} knows or uses things from outside {char}'s world (other games, books, shows, real-world tech or brands the setting wouldn't have) instead of reacting to them in character.
4. It writes {user}'s actions, words or feelings.
If none of these happen, answer OK. Otherwise answer FIX: and one short instruction, e.g. "FIX: {char} has never heard of that game; react with confusion instead."
"""


def length_issue(reply: str, target_words: int) -> str:
    """A reply far longer than the character usually writes."""
    if target_words and _words(reply) > max(target_words * 2.2, target_words + 25):
        return f"Much shorter: about {target_words} words, like {{char}}'s usual replies."
    return ""


def summarize_card(d: dict, limit: int = 700) -> str:
    parts = [d.get("creator_notes") or "", d.get("description") or "", d.get("personality") or ""]
    text = re.sub(r"\s+", " ", " ".join(p for p in parts if p)).strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def parse_verdict(text: str) -> str:
    """The fix instruction, or "" when the reply is fine (anything that isn't a clear FIX counts as OK)."""
    for line in (text or "").strip().splitlines():
        line = line.strip().strip("*").strip()
        if not line:
            continue
        m = re.match(r"FIX\s*[:：]\s*(.+)", line, re.I)
        return m.group(1).strip().strip("*").strip() if m else ""
    return ""


def check_reply(ask: Callable[[str, str], str], card: dict, user: str, last_user: str, reply: str,
                target_words: int = 0) -> str:
    """Return an instruction for rewriting the reply, or "" if it's in character."""
    d = card.get("data", card)
    char = d.get("name", "Character")
    fixes = []
    lengthy = length_issue(reply, target_words)
    if lengthy:
        fixes.append(lengthy.replace("{char}", char))
    try:
        verdict = ask(CHECK_SYSTEM, CHECK_PROMPT.format(
            char=char, user=user, about=summarize_card(d) or "(no description)",
            last_user=(last_user or "")[-1200:], reply=reply[-2500:]))
    except OSError:
        verdict = ""
    fix = parse_verdict(verdict)
    if fix:
        fixes.insert(0, fix)
    return " ".join(fixes)
