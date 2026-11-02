"""Build the message list sent to the local model from a Character Card V2."""
from __future__ import annotations

import re


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
                   reply_words: int = 0, pacing: bool = True, user_pronouns: str = "") -> list[dict]:
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
    char_pr = character_pronouns(d)
    user_pr = user_pronouns or guess_pronouns(persona)
    parts.append(perspective_block(char, user_name, char_pr, user_pr))
    if pacing:
        parts.append(PACING.format(char=char, user=user_name))
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
    if history and history[-1]["role"] == "user" and _FIRST_PERSON.search(history[-1]["content"]):
        u = f"{user_name} ({user_pr})" if user_pr else user_name
        extra.append(f'Perspective: in the message below, "I/my" is {u} and "you/your" is {char}. '
                     f'Reply as {char}: in your reply "I/my" is {char} and "you/your" is {user_name}.')
    if pacing and history and history[-1]["role"] == "user":
        hint = moment_hint(history[-1]["content"])
        if hint:
            extra.append(hint.format(char=char))
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


_FIRST_PERSON = re.compile(r"\b(?:I|I'm|I've|I'll|me|my|myself)\b|我", re.I)
_SHE = re.compile(r"\b(?:she|her|hers|herself|girl|woman|female|wife|mother|lady)\b|她", re.I)
_HE = re.compile(r"\b(?:he|him|his|himself|boy|man|male|husband|father|guy)\b|他", re.I)


def guess_pronouns(text: str) -> str:
    """'she/her' or 'he/him' when a description clearly talks about one, else ''."""
    she, he = len(_SHE.findall(text or "")), len(_HE.findall(text or ""))
    if she >= 2 and she >= 2 * he:
        return "she/her"
    if he >= 2 and he >= 2 * she:
        return "he/him"
    return ""


PRONOUN_CHOICES = ("she/her", "he/him", "they/them", "group")


def character_pronouns(d: dict) -> str:
    """The character's pronouns: set by the user in Edit, else guessed from the card.
    "group" (a bot that plays several characters) means: don't state any."""
    set_ = ((d.get("extensions") or {}).get("localcai") or {}).get("pronouns", "")
    if set_ in PRONOUN_CHOICES:
        return "" if set_ == "group" else set_
    return guess_card_pronouns(d)


def guess_card_pronouns(d: dict) -> str:
    # greetings and descriptions usually talk about the character in third person ("*She smiles*")
    return guess_pronouns(" ".join(str(d.get(k) or "") for k in
                                   ("description", "personality", "scenario", "first_mes", "creator_notes")))


def perspective_block(char: str, user: str, char_pr: str = "", user_pr: str = "") -> str:
    c = f"{char} ({char_pr})" if char_pr else char
    u = f"{user} ({user_pr})" if user_pr else user
    return (f"[Who is who]\nYou play {c}. You are talking with {u}.\n"
            f'In {user}\'s messages, "I/me/my" means {user} and "you/your" means {char}. '
            f'In your replies it is the other way round: "I/me/my" is {char} and "you/your" is {user}. '
            f"Never swap them: {char}'s own body, feelings and actions are \"my\", {user}'s are \"your\". "
            f"Keep to first and second person; don't switch to talking about {char} or {user} as he/she.")


PACING = """[How to write {char}'s replies]
Keep three things apart: actions and body language go in *asterisks*, spoken words go in "quotes", and the scene (place, light, sounds, weather) is described briefly and only when it changes or matters. If {char}'s earlier replies use a different format, follow theirs.
Let the moment decide the balance between action and speech:
- intimate, tender or sleepy moments (cuddling, kissing, holding each other, lying in bed): mostly slow, gentle actions and touch, with at most one or two short whispered lines — closeness is shown, not talked about;
- talking, teasing, arguing or explaining: mostly dialogue, with small gestures;
- fast or physical moments (fighting, running, a battle, cooking): short action beats and short lines.
Don't attach a line of speech to every gesture, and don't alternate action, line, action, line. Several actions can flow together in one paragraph; {char} can act without speaking, or speak without a gesture. Write in normal paragraphs, not one-line poem stacks. Never write {user}'s actions or words."""


_MOMENTS = (
    ("intimate", re.compile(
        r"cuddl|snuggl|kiss|hug|embrac|nuzzl|caress|hold(?:s|ing)? (?:you|her|him|hands?)|"
        r"in (?:my|your) arms|lean(?:s|ing)? (?:on|against)|stroke|pat(?:s|ting)? (?:your|her|his) head|"
        r"\bbed\b|sleep|\b(?:lie|lies|lying|lay|lays|laying)\b|"
        r"抱|擁|親|吻|摸摸|蹭|依偎|靠在|牽手|睡|床", re.I),
     "Moment: quiet and intimate. Reply mostly with slow, gentle actions and touch. "
     "{char} says very little here: one or two short, soft lines at most, or none."),
    ("action", re.compile(
        r"\b(?:fight|attack|punch|kick|run(?:s|ning)?|chase|dodge|battle|shoot|grab|throw|escape)|"
        r"打架|打鬥|攻擊|揍|踢|奔跑|追|閃開|戰鬥|逃", re.I),
     "Moment: fast and physical. Use short action beats and short lines."),
)


def moment_hint(text: str) -> str:
    """A per-turn nudge about pacing, picked from what the user just did."""
    for _name, rx, hint in _MOMENTS:
        if rx.search(text):
            return hint
    acts = "".join(re.findall(r"\*[^*]+\*", text))
    if "?" in text or "？" in text or (text.strip() and len(acts) < len(text) * 0.2):
        return "Moment: conversation. Reply mostly with dialogue and small gestures."
    return ""


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
