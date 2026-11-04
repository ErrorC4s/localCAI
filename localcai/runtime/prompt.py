"""Build the message list sent to the local model from a Character Card V2."""
from __future__ import annotations

import re

from ..facts import facts_block, is_memory_entry


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


FIXED_SHARE = 0.6  # at most this much of the prompt for what's sent every time; the rest is the chat


def _shorten(text: str, n: int, keep_end: bool = False) -> str:
    """Cut to about n characters at a sentence or word end, marked with "…"."""
    text = text.strip()
    if len(text) <= n:
        return text
    if keep_end:
        cut = text[-n:]
        m = re.search(r"(?<=[.!?…~\n])\s", cut)
        return "…" + (cut[m.end():] if m and m.end() < n // 2 else cut).lstrip()
    cut = text[:n]
    ends = [m.end() for m in re.finditer(r"[.!?…~\"*)](?=\s)", cut)]
    end = ends[-1] if ends and ends[-1] > n // 2 else (cut.rfind(" ") if cut.rfind(" ") > n // 2 else n)
    return cut[:end].rstrip() + " …"


def build_messages(card: dict, history: list[dict], user_name: str = "User",
                   max_chars: int = 24000, persona: str = "", memories: list[str] | None = None,
                   story: str = "", recalled: list[str] | None = None,
                   reply_words: int = 0, pacing: bool = True, user_pronouns: str = "",
                   initiative: str = "auto", instruction: str = "", rewrite_of: str = "",
                   avoid: list[str] | None = None, scene: str = "",
                   facts: list[dict] | None = None) -> list[dict]:
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
    lore = [e["content"] for e in sorted(book.get("entries", []), key=lambda e: e.get("insertion_order", 0))
            if e.get("enabled", True) and e.get("constant")
            and not (facts is not None and is_memory_entry(e))]  # the chat's own facts replace these
    pins = [m for m in memories or [] if m not in lore]  # pinned in this chat (in localCAI or on C.ai)
    example = d.get("mes_example") or ""
    head = list(parts)
    constant = lore + pins  # (read by the per-turn part below)

    def memory_parts(lore: list[str], pins: list[str], story: str, example: str) -> list[str]:
        out = []
        if lore or pins:
            out.append("[Memories — always keep these in mind]\n" + "\n".join(f"- {x}" for x in lore + pins))
        if facts:
            out.append("[Facts to remember — grouped by who they are about; keep them true]\n" + facts_block(facts))
        if story:
            out.append(f"[The story so far between {char} and {user_name}]\n{story}")
        if example:
            out.append("[Example dialogue — style reference only]\n" + example)
        return out

    char_pr = character_pronouns(d)
    user_pr = user_pronouns or guess_pronouns(persona) or guess_user_pronouns(history)
    parts.append(perspective_block(char, user_name, char_pr, user_pr))
    parts.append(WORLD.format(char=char))
    rules = [r for r in (((d.get("extensions") or {}).get("localcai") or {}).get("rules") or []) if str(r).strip()]
    if rules:
        parts.append(f"[Rules for {char}, set by {user_name}: always follow these]\n"
                     + "\n".join(f"- {str(r).strip()}" for r in rules))
    if pacing:
        parts.append(PACING.format(char=char, user=user_name))
    if reply_words:
        parts.append(f"[Reply length]\nKeep each reply to about {reply_words} words or fewer, "
                     f"like {char}'s earlier replies. Say one or two things, then stop at a natural point "
                     f"and leave room for {user_name} to answer. Don't repeat yourself.")
    tail = parts[len(head):]

    def assemble(lore, pins, story, example) -> str:
        return _fill("\n\n".join(head + memory_parts(lore, pins, story, example) + tail), char, user_name)

    # What's sent every time (card, memories, guidance) must leave room for the chat itself. When it's too
    # long for the context (many long pinned messages, a long example dialogue...), shorten the parts that
    # matter least first: the example dialogue, then each long pinned message, then the oldest pins.
    # The card, the facts and the guidance are never cut.
    limit = int(max_chars * FIXED_SHARE)
    system = assemble(lore, pins, story, example)
    steps = [lambda l, p, st, ex: (l, p, st, _shorten(ex, 1200)),
             lambda l, p, st, ex: (l, [_shorten(x, 400) for x in p], st, ex),
             lambda l, p, st, ex: (l, p, _shorten(st, 1500, keep_end=True), ex),
             lambda l, p, st, ex: (l, p, st, ""),
             lambda l, p, st, ex: (l, [_shorten(x, 200) for x in p], st, ex),
             lambda l, p, st, ex: ([_shorten(x, 200) for x in l], p, st, ex)]
    state = (lore, pins, story, example)
    for step in steps:
        if len(system) <= limit:
            break
        state = step(*state)
        system = assemble(*state)
    while len(system) > limit and state[1]:  # still too long: keep the newest pins
        state = (state[0], state[1][1:], state[2], state[3])
        system = assemble(*state)

    # per-turn context: keyword-triggered memories + recalled earlier moments
    scan_depth = book.get("scan_depth", 4)
    recent = "\n".join(m["content"] for m in history[-scan_depth:])
    triggered = [x for x in active_lore({**book, "entries": [e for e in book.get("entries", [])
                                                             if not e.get("constant")]}, recent) if x not in constant]
    extra = []
    if triggered:
        extra.append("[Relevant memories]\n" + "\n".join(f"- {x}" for x in triggered))
    if scene and history and history[-1]["role"] == "user":
        # what is true right now (built from the last few rounds): ongoing actions an older reply started
        extra.append(f"Scene right now: {scene.strip()}\nKeep all of this true (positions, what each is doing, "
                     f"clothing) unless this turn changes it; carry ongoing actions on, don't drop or restart them. "
                     f"Mood moves with the story: keep {char}'s current mood and intensity unless what just happened "
                     f"gives a reason to change it; a real reason (a surprise, a hurtful word, a climax, a sudden "
                     f"danger) can change it at once, otherwise let it shift gradually, never flip for no reason.")
    if pacing and history and history[-1]["role"] == "user":
        c = continuity_note(history, char, user_name, initiative)
        if c:
            extra.append(c)
    if history and history[-1]["role"] == "user" and _FIRST_PERSON.search(history[-1]["content"]):
        u = f"{user_name} ({user_pr})" if user_pr else user_name
        bodies = {"he/him": "a man", "she/her": "a woman"}
        who = ""
        if user_pr in bodies or char_pr in bodies:
            who = " Keep bodies straight: " + ", ".join(
                f"{n} is {bodies[p]}" for n, p in ((user_name, user_pr), (char, char_pr)) if p in bodies) + "."
        extra.append(f'Perspective: in the message below, "I/my" is {u} and "you/your" is {char}. '
                     f'Reply as {char}: in your reply "I/my" is {char} and "you/your" is {user_name}.{who}')
    if pacing and history and history[-1]["role"] == "user":
        hint = moment_hint(history[-1]["content"])
        if hint:
            extra.append(hint.format(char=char))
    if avoid and not instruction:
        # regenerating: earlier versions of this reply exist, so make this one clearly different
        shown = [re.sub(r"\s+", " ", a).strip()[:180] for a in avoid[-3:] if a and a.strip()]
        if shown:
            extra.append(f"Fresh take: {user_name} asked for another version of {char}'s reply. Write one that is clearly "
                         f"different from the earlier versions below (different actions, wording and direction), "
                         f"still in character and at the same moment:\n" + "\n".join(f"- {x}…" for x in shown))
    if instruction:
        # the user's own direction for this one reply (✨ on a message): it wins over the defaults above
        d_note = (f"Director's note for this reply only, from {user_name} — follow it closely, it overrides "
                  f"the guidance above where they conflict: {instruction.strip()}")
        if rewrite_of:
            d_note += (f"\nRewrite {char}'s reply below to follow the note. Keep the parts the note doesn't "
                       f"ask to change, same perspective and format:\n<<<\n{rewrite_of.strip()}\n>>>")
        extra.append(d_note)
    if recalled:
        extra.append("[Earlier moments that may be relevant now]\n" + "\n".join(f"- {x}" for x in recalled))
    if extra:
        extra.append(f"(Direction for you only: follow it silently. Write just {char}'s reply, never mention, "
                     f"list or check off these notes, and add no notes or commentary after the reply.)")
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
    return [{"role": "system", "content": system}] + alternate(kept)


def alternate(msgs: list[dict]) -> list[dict]:
    """user/assistant strictly taking turns, starting with the user — some models' chat templates
    (Mistral-style) reject anything else. Same-role neighbours are merged; a chat that opens with the
    character's greeting gets a short opening line from the user."""
    out: list[dict] = []
    for m in msgs:
        if out and out[-1]["role"] == m["role"]:
            out[-1] = {**out[-1], "content": out[-1]["content"] + "\n\n" + m["content"]}
        else:
            out.append(dict(m))
    if out and out[0]["role"] == "assistant":
        out.insert(0, {"role": "user", "content": "(The roleplay begins.)"})
    return out


_FIRST_PERSON = re.compile(r"\b(?:I|I'm|I've|I'll|me|my|myself)\b|我", re.I)
_SHE = re.compile(r"\b(?:she|her|hers|herself|girl|woman|female|wife|mother|lady)\b|她", re.I)
_HE = re.compile(r"\b(?:he|him|his|himself|boy|man|male|husband|father|guy)\b|他", re.I)


# only words aimed at the user ("hubby", "my husband"), not the character talking about itself ("your wife")
_CALLS_HIM = re.compile(r"\bhubby\b|\bdaddy\b|\bmy (?:husband|man|boy|prince|lord|king|boyfriend)\b|老公", re.I)
_CALLS_HER = re.compile(r"\bwifey\b|\bmommy\b|\bmy (?:wife|girl|lady|princess|queen|girlfriend)\b|老婆", re.I)


def guess_user_pronouns(history: list[dict]) -> str:
    """How the character addresses the user in its own replies ("hubby", "my lady", 老公…)."""
    text = "\n".join(m["content"] for m in history if m["role"] == "assistant")
    him, her = len(_CALLS_HIM.findall(text)), len(_CALLS_HER.findall(text))
    if him >= 3 and him >= 3 * her:
        return "he/him"
    if her >= 3 and her >= 3 * him:
        return "she/her"
    return ""


_ACTION = re.compile(r"\*([^*\n]{3,})\*")


_LEAD = re.compile(r"\b(?:your turn|your move|take (?:the )?lead|you lead|lead the way|do (?:whatever|what) you want|"
                   r"surprise me|show me|go on|continue|keep going|don'?t stop)\b|妳來|你來|主導|繼續|隨妳|隨你|交給妳|交給你",
                   re.I)


def wants_lead(text: str) -> bool:
    """The user hands the scene to the character ("your turn", "go on", "妳來", or just "...")."""
    t = text.strip()
    return bool(_LEAD.search(t)) or bool(t) and not re.sub(r"[.…。\s~～*]", "", t)


def continuity_note(history: list[dict], char: str, user: str, initiative: str = "auto") -> str:
    """Keep the scene flowing without jumps.

    - Anchor: where the last reply left off (its last actions) — continue from there, nothing skipped.
    - Never invent the user's moves; when the user only spoke they did nothing new physically.
    - Initiative: the character may (auto), or should (lead / when asked), build on its last action
      and make the next move itself; with "follow" it mostly reacts.
    """
    last_user = history[-1]["content"]
    prev = next((m["content"] for m in reversed(history[:-1]) if m["role"] == "assistant"), "")
    parts = []
    acts = _ACTION.findall(prev)
    if acts:
        anchor = " … ".join(a.strip() for a in acts[-2:])
        if len(anchor) > 260:
            anchor = "…" + anchor[-259:]
        parts.append(f"Continuity: the scene is exactly where {char}'s last reply left it ({anchor}). "
                     f"Continue from there: same place, same positions, nothing skipped.")
    spoke_only = not _ACTION.search(last_user) and not re.match(r"\s*(?:I|I'm|我)\b", last_user)
    lead = initiative == "lead" or (initiative == "auto" and wants_lead(last_user))
    if lead:
        parts.append(f"{user} wants {char} to take the lead: build directly on that last action and make the "
                     f"next move yourself, one clear step forward in {char}'s own actions and words. "
                     f"Don't decide what {user} does, says or feels.")
    elif spoke_only:
        parts.append(f"{user} only spoke this turn and did nothing new with their body: don't describe {user} "
                     f"doing or touching anything new. React to their words"
                     + ("." if initiative == "follow" else
                        f", then {char} may carry the scene on with her own next action, following on from the last one.")
                     .replace("her own", f"{char}'s own"))
    else:
        parts.append(f"React to what {user} actually did; never add actions for {user} beyond what they wrote."
                     + ("" if initiative == "follow" else
                        f" Then {char} can continue with a next action of {char}'s own that follows from it."))
    return " ".join(parts)


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


WORLD = """[Stay inside {char}'s world]
{char} only knows what someone living in {char}'s world would plausibly know. Anything from outside it (other games, books or shows, AI chatbots, real-world brands or tech the setting wouldn't have, skills {char} wouldn't have) gets {char}'s own in-character reaction: confused, dismissive, curious or joking. Never step out of the role and never act as an assistant: no code, essays, lists or helpful explanations unless {char} would really give them. Never say or hint that {char} is an AI, a model, a bot, a character or part of a story."""


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
_BUCKETS = (15, 25, 40, 60, 90, 120, 160, 220, 300)


def _words(text: str) -> int:
    cjk = sum(1 for ch in text if "\u3040" <= ch <= "\u9fff" or "\uac00" <= ch <= "\ud7af")
    return len(text.split()) + cjk // 2


def card_reply_samples(d: dict) -> list[str]:
    """The character's own lines in the card: greeting and example-dialogue turns."""
    name = d.get("name", "")
    out = [d["first_mes"]] if d.get("first_mes") else []
    for line in re.split(r"\n(?=\s*(?:\{\{(?:char|user)\}\}|<START>|[^\n:]{1,40}:))", d.get("mes_example") or ""):
        m = re.match(r"\s*(?:\{\{char\}\}|" + re.escape(name) + r")\s*:\s*(.+)", line, re.S) if name else \
            re.match(r"\s*\{\{char\}\}\s*:\s*(.+)", line, re.S)
        if m and m.group(1).strip():
            out.append(m.group(1).strip())
    return out


def reply_words_for(setting: str, history: list[dict], card: dict | None = None) -> int:
    """Target reply length in words. "auto" copies how long the character's replies usually are
    (median, rounded to a few fixed steps so the prompt stays the same turn after turn). A new chat
    with fewer than 3 replies learns it from the card's greeting and example dialogue instead."""
    if setting in LENGTH_PRESETS:
        return LENGTH_PRESETS[setting]
    if setting == "off":
        return 0
    lens = sorted(_words(m["content"]) for m in history if m["role"] == "assistant" and m["content"].strip())
    if len(lens) < 3 and card:
        d = card.get("data", card)
        samples = card_reply_samples(d)
        if samples:
            lens = sorted(_words(t) for t in samples)
    if not lens:
        return LENGTH_PRESETS["medium"]
    med = lens[len(lens) // 2]
    return min(_BUCKETS, key=lambda b: abs(b - med * 1.15))