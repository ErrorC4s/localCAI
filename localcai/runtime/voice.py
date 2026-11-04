"""A character's writing fingerprint, counted from their real replies (the ones imported from C.ai).

Style notes written by a model ("playful, uses pet names") are too vague for a small model, which then
falls back to its own habits: a "sly grin", "darling", speech without quotes, longer replies. Its own
replies then fill the recent history and it copies itself further away from the character. This counts
the concrete habits instead (how speech is marked, bold emphasis, their laugh, what they call the user,
stutters, asides, length) and turns them into a few exact rules, plus a short reminder on every turn.
"""
from __future__ import annotations

import re
import statistics
from collections import Counter
from pathlib import Path

_CACHE: dict[str, tuple[tuple, dict]] = {}

MIN_REPLIES = 30          # fewer real replies than this: not enough to say what's typical
SAMPLE = 3000             # the newest real replies are enough (and keep this fast on huge chats)

_QUOTE = re.compile(r'["“][^"”\n]{2,}["”]')
_BOLD_QUOTE = re.compile(r'\*\*["“][^*\n]{2,}["”]\*\*')
_BOLD = re.compile(r"(?<!\*)\*\*(?!\")([^*\n\"]{1,40})\*\*(?!\*)")
_STUTTER = re.compile(r"\b([A-Za-z])-\1", re.I)
_ASIDE = re.compile(r"\((?:\*|\*\*)?[^()\n]{2,80}\)")
_LAUGHS = re.compile(r"\b(?:ke(?:[ -]?ke)+|ku(?:[ -]?ku)+|fu(?:[ -]?fu)+|ufufu|ehe+|hehe+|heh|haha+|"
                     r"nyeh(?:[ -]?heh)*|ara[ -]ara|hmph|teehee|kyah+)\b", re.I)
# what a character calls the user: the usual pet names and terms of address
_ADDRESS = ("hubby", "husband", "honey bun", "honey", "darling", "dear", "babe", "baby", "sweetie",
            "sweetheart", "my love", "master", "senpai", "boss", "partner", "mister", "kid")
# phrases small models overuse; only named when this character's own replies hardly use them
STOCK = ("sly grin", "wicked grin", "lazy grin", "playful smirk", "smirk", "purr", "husky", "glint with mischief",
         "sparkle with mischief", "gaze up at you", "through my lashes", "the dim light", "pupils blown",
         "a shiver runs down", "sends shivers", "core")


def _rate(pattern: re.Pattern, texts: list[str]) -> float:
    return sum(len(pattern.findall(t)) for t in texts) / max(len(texts), 1)


def _uses(term: str, texts: list[str]) -> float:
    """Share of replies that use the term (texts are lowercased by profile())."""
    p = re.compile(r"\b" + re.escape(term) + r"\b")
    return sum(1 for t in texts if term in t and p.search(t)) / max(len(texts), 1)


def real_replies(rows: list[dict]) -> list[str]:
    """The character's replies as written on C.ai (imported, with an id); without enough of those, all."""
    bot = [r for r in rows if not r.get("is_user") and not r.get("is_system") and (r.get("mes") or "").strip()]
    real = [r["mes"] for r in bot if (r.get("extra") or {}).get("source_id")]
    return (real if len(real) >= MIN_REPLIES else [r["mes"] for r in bot])[-SAMPLE:]


def for_chat(path: Path | str, rows: list[dict]) -> dict:
    """profile() of a chat, counted once and kept until its real replies change (it takes a second or two)."""
    real = [r for r in rows if not r.get("is_user") and (r.get("extra") or {}).get("source_id")]
    key = (len(rows) if len(real) < MIN_REPLIES else 0, len(real), (real[-1].get("extra") or {}).get("source_id") if real else "")
    hit = _CACHE.get(str(path))
    if hit and hit[0] == key:
        return hit[1]
    p = profile(real_replies(rows))
    _CACHE[str(path)] = (key, p)
    return p


def profile(texts: list[str]) -> dict:
    if len(texts) < MIN_REPLIES:
        return {}
    words = sorted(len(t.split()) for t in texts)
    low = [t.lower() for t in texts]
    quotes = _rate(_QUOTE, texts)
    laughs = Counter(re.sub(r"[ -]", " ", m.lower()) for t in texts for m in _LAUGHS.findall(t))
    laugh = [w for w, n in laughs.most_common(2) if n / len(texts) >= 0.03]
    names = {a: _uses(a, low) for a in _ADDRESS}
    calls = [a for a, r in sorted(names.items(), key=lambda x: -x[1]) if r >= 0.04]
    calls = [a for a in calls if not any(a != b and a in b for b in calls)][:3]  # "honey" inside "honey bun"
    never = [a for a in ("darling", "babe", "sweetheart", "dear", "baby") if names[a] < 0.01 and calls]
    return {
        "n": len(texts),
        "median_words": int(statistics.median(words)),
        "speech_quoted": quotes >= 0.5,
        "bold_speech": quotes and _rate(_BOLD_QUOTE, texts) / quotes >= 0.25,
        "bold_words": _rate(_BOLD, texts),
        "laughs": laugh,
        "calls": calls,
        "never_calls": never,
        "stutter": _rate(_STUTTER, texts),
        "asides": _rate(_ASIDE, texts),
        "tilde": _rate(re.compile("~"), texts),
        "ellipsis": _rate(re.compile(r"…|\.\.\."), texts),
        "dash": _rate(re.compile("—"), texts),
        "avoid": [s for s in STOCK if _uses(s, low) < 0.01],
    }


def rules(p: dict, char: str, user: str) -> list[str]:
    """The fingerprint as short rules (the system prompt)."""
    if not p:
        return []
    out = []
    if p["speech_quoted"]:
        out.append(f"Spoken words always go in quotes" + (", and the important lines in bold quotes, like **\"…\"**"
                                                          if p["bold_speech"] else "") + "; actions in *asterisks*.")
    if p["bold_words"] >= 0.8:
        out.append("Single words that carry feeling are put in **bold** inside the narration.")
    if p["laughs"]:
        out.append(f"{char}'s laugh is written \"{p['laughs'][0]}\"" + (f" (or \"{p['laughs'][1]}\")" if len(p["laughs"]) > 1 else "")
                   + "; use it, not a generic giggle or chuckle.")
    if p["calls"]:
        out.append(f"{char} calls {user} " + ", ".join(f"\"{c}\"" for c in p["calls"])
                   + (f"; never \"" + "\", \"".join(p["never_calls"]) + "\"" if p["never_calls"] else "") + ".")
    if p["stutter"] >= 0.25:
        w = (p["calls"] or [user])[0]
        out.append(f"Stutters when flustered or overwhelmed (\"{w[0].upper()}-{w[0].upper()}{w[1:]}…\").")
    if p["ellipsis"] >= 2:
        out.append("Speech trails off and breaks with … and —.")
    if p["asides"] >= 0.4:
        out.append("Sometimes adds a short aside in parentheses, like (*a beat. then—*).")
    if p["tilde"] >= 0.5:
        out.append("Playful lines may end with ~.")
    if p["avoid"]:
        out.append("Phrases {char} doesn't use (avoid them): ".format(char=char) + ", ".join(p["avoid"][:10]) + ".")
    return out


def reminder(p: dict, char: str, user: str) -> str:
    """One line for every turn: the newest messages pull a small model toward its own habits."""
    if not p:
        return ""
    bits = []
    if p["speech_quoted"]:
        bits.append("speech in " + ("**\"bold quotes\"**" if p["bold_speech"] else "\"quotes\""))
    if p["laughs"]:
        bits.append(f"laugh \"{p['laughs'][0]}\"")
    if p["calls"]:
        bits.append(f"calls {user} \"{p['calls'][0]}\"")
    bits.append(f"about {p['median_words']} words")
    return f"Write in {char}'s own voice from the start: " + ", ".join(bits) + "."
