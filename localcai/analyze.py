"""Learn from chat history.

- pick_examples:   choose a few exchanges that show the character's style (no model needed)
- style_notes:     the model reads a sample of the character's replies and writes how they talk
- story_summary:   the model reads the chat in chunks and writes "the story so far" (map → reduce)

Everything here is saved into the card / chat, so it keeps helping on every later reply.
"""
from __future__ import annotations

import re
from typing import Callable

from .runtime import stream_chat

AUTO_MARK = "localcai_auto"  # extensions key recording which card fields were auto-written


def complete(url: str, model: str, prompt: str, system: str = "", max_tokens: int = 700,
             temperature: float = 0.4, on_text: Callable[[str], None] | None = None) -> str:
    """The model's whole answer. on_text gets the text so far as it's written (for progress)."""
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    out = []
    for tok in stream_chat(url, model, msgs, temperature=temperature, max_tokens=max_tokens):
        out.append(tok)
        if on_text:
            on_text("".join(out))
    return "".join(out).strip()


def _clean(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text or "").strip()


def _spread(items: list, n: int) -> list:
    """n items spread evenly across the list (keeps early, middle and late history)."""
    if len(items) <= n:
        return list(items)
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


def _styled(text: str) -> float:
    """How well a reply shows a roleplay style: has narration (*…*) and dialogue ("…"), mid length."""
    score = 0.0
    if re.search(r"\*[^*]{6,}\*", text):
        score += 1
    if re.search(r'["“][^"”]{4,}["”]', text):
        score += 1
    n = len(text)
    score += 1.0 if 250 <= n <= 1100 else 0.4 if 120 <= n <= 1600 else 0
    return score


# ── 3. example dialogue ────────────────────────────────────────────────────
def pick_examples(rows: list[dict], user: str, char: str, k: int = 4) -> str:
    pairs = []
    for i in range(1, len(rows)):
        u, b = rows[i - 1], rows[i]
        if u.get("is_user") and not b.get("is_user") and u.get("mes") and b.get("mes"):
            if 8 <= len(u["mes"]) <= 600:
                pairs.append((u["mes"].strip(), b["mes"].strip()))
    if not pairs:
        return ""
    best = sorted(pairs, key=lambda p: _styled(p[1]), reverse=True)[: max(k * 6, 12)]
    order = {id(p): n for n, p in enumerate(pairs)}
    chosen = _spread(sorted(best, key=lambda p: order[id(p)]), k)  # variety across the timeline
    blocks = []
    for u, b in chosen:
        u = u.replace(user, "{{user}}") if user else u
        b = b.replace(user, "{{user}}") if user else b
        blocks.append(f"<START>\n{{{{user}}}}: {u}\n{{{{char}}}}: {b}")
    return "\n".join(blocks)


# ── 1. style notes ─────────────────────────────────────────────────────────
STYLE_SYSTEM = "You are an expert at analysing fictional characters' voices for roleplay writers."


def style_notes(rows: list[dict], char: str, user: str, ask: Callable[[str], str],
                sample: int = 24, budget: int = 14000) -> str:
    replies = [r["mes"].strip() for r in rows if not r.get("is_user") and len(r.get("mes", "")) > 30]
    if len(replies) < 2:
        raise ValueError("Not enough of the character's messages to learn from yet.")
    picked = _spread(sorted(replies, key=_styled, reverse=True)[: sample * 3], sample)
    text, used = [], 0
    for r in picked:
        r = r[:900]
        if used + len(r) > budget:
            break
        text.append(r)
        used += len(r)
    joined = "\n---\n".join(text)
    prompt = (f"Below are {len(text)} messages written by the character \"{char}\" in a long roleplay with {user}.\n\n"
              f"{joined}\n\n"
              f"Write concise notes another writer can follow to sound exactly like {char}. Cover, as short bullet points:\n"
              f"- personality and attitude toward {user}\n- how they speak (tone, sentence length, verbal tics, catchphrases, "
              f"pet names, how they address {user})\n- how they write actions/narration (point of view, *asterisks*, "
              f"(parentheses), formatting)\n- recurring themes or habits\n"
              f"Write only the notes, in English, at most 15 bullets. Describe the style; don't copy long passages.")
    return _clean(ask(prompt))


# ── story summary (map → reduce) ───────────────────────────────────────────
STORY_SYSTEM = "You summarise long roleplay chats into memory notes. Be factual and concise."


def chunk_rows(rows: list[dict], max_chars: int = 9000) -> list[str]:
    chunks, cur, n = [], [], 0
    for r in rows:
        line = f"{r.get('name', '')}: {re.sub(chr(10) + '+', ' ', r.get('mes', ''))}"
        if n + len(line) > max_chars and cur:
            chunks.append("\n".join(cur))
            cur, n = [], 0
        cur.append(line[:2500])
        n += len(line)
    if cur:
        chunks.append("\n".join(cur))
    return chunks


def story_summary(rows: list[dict], char: str, user: str, ask: Callable[[str], str],
                  progress: Callable[[int, int], None] = lambda d, t: None,
                  stopped: Callable[[], bool] = lambda: False) -> str:
    chunks = chunk_rows(rows)
    notes: list[str] = []
    for i, ch in enumerate(chunks):
        if stopped():
            break
        progress(i, len(chunks))
        notes.append(_clean(ask(
            f"Part {i + 1} of a roleplay between {user} and {char}:\n\n{ch}\n\n"
            f"List the important things that happen or are revealed in this part: events, decisions, "
            f"facts about {user} or {char}, how their relationship changes, promises, names, places. "
            f"At most 8 short bullet points. Only the bullets.")))
    progress(len(notes), len(chunks))
    if not notes:
        return ""
    # reduce in rounds until it fits
    while len(notes) > 1:
        merged, group, size = [], [], 0
        for n in notes:
            if size + len(n) > 9000 and group:
                merged.append(group)
                group, size = [], 0
            group.append(n)
            size += len(n)
        merged.append(group)
        if len(merged) == len(notes) and len(notes) > 1:  # can't shrink further by grouping
            merged = [notes[i:i + 2] for i in range(0, len(notes), 2)]
        notes = [_clean(ask(
            f"These are notes from consecutive parts of a roleplay between {user} and {char}, in order:\n\n"
            + "\n\n".join(g) + "\n\nMerge them into one chronological summary of the story so far and the "
            f"relationship between {user} and {char}. Keep names, promises and important facts. "
            f"At most 20 bullet points. Only the bullets.")) for g in merged]
        if stopped():
            break
    return notes[0]


# ── the learned style as its own thing (the Style window), stored in the card's personality ──────
STYLE_HEADER = "[Style notes from your chats]"


def _auto(d: dict) -> dict:
    return d.setdefault("extensions", {}).setdefault(AUTO_MARK, {})


def style_notes_of(d: dict) -> str:
    """The style notes in a card: the whole personality when Learn style wrote it, else the part after the header."""
    p = d.get("personality") or ""
    if (d.get("extensions") or {}).get(AUTO_MARK, {}).get("personality"):
        return p.strip()
    return p.split(STYLE_HEADER, 1)[1].strip() if STYLE_HEADER in p else ""


def set_style_notes(d: dict, notes: str) -> None:
    """Put style notes in the card, keeping a personality the user wrote themselves (notes go after it)."""
    notes = (notes or "").strip()
    auto = _auto(d)
    own = "" if auto.get("personality") else (d.get("personality") or "").split(STYLE_HEADER, 1)[0].rstrip()
    if own:
        d["personality"] = own + (f"\n\n{STYLE_HEADER}\n{notes}" if notes else "")
        auto.pop("personality", None)
    else:
        d["personality"] = notes
        if notes:
            auto["personality"] = True
        else:
            auto.pop("personality", None)


def set_examples(d: dict, examples: str, learned: bool) -> None:
    """learned: written by Learn style (replaced next time); otherwise the user's own (kept)."""
    d["mes_example"] = (examples or "").strip()
    auto = _auto(d)
    if learned and d["mes_example"]:
        auto["mes_example"] = True
    else:
        auto.pop("mes_example", None)
