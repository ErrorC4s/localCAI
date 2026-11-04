"""Scene state: one line of what is true right now in the role-play (place, positions, ongoing actions,
clothing), rebuilt from the last few rounds after every reply.

The model sees the whole recent chat, but small models lose track of an action that started a few
replies ago and is still going on ("she's sitting in his lap") once the newest reply talks about
something else. This line hands it the result instead of making it dig through the history.

It is stored next to the chat (chats/<chat>.scene.json), keyed by the whole chat up to the reply it was
made after, so after an edit, rewind or swipe anywhere before it, an old note is never used.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Callable

ROUNDS = 5           # how far back to look: the last 5 exchanges (10 messages)
MSG_CHARS = 700      # each message is cut to its last part; the end is where the scene is now
KEEP = 8             # states kept per chat (enough for going back a few replies / swipes)

SCENE_SYSTEM = ("You keep notes on a role-play scene. You only report what the text shows; "
                "you never continue the story and never add anything.")

SCENE_PROMPT = """Role-play between {char} and {user}. Previous scene note: {prev}

The latest part of the role-play:
<<<
{log}
>>>

Write ONE line (at most 55 words) saying what is true right now, at the very end of the text:
where they are; {char}'s position and what {char} is doing (with hands and mouth); {user}'s position and what \
{user} is doing (with hands and mouth); \
anything still going on (holding, sitting on, lying with...); clothing only if the text changed it; \
{char}'s mood and how intense the moment is right now (e.g. calm, playful, nervous, angry, heated, near the edge; \
right after a climax, a scare or crying say so, e.g. "afterglow, still catching breath").
Keep actions that started earlier and haven't ended. Drop what has ended. Plain facts, present tense, no story.
Format: Where: ...; {char}: ...; {user}: ...; Mood: ...
"""


def scene_key(history: list[dict]) -> str:
    """Identifies "the chat exactly as it stands after this reply": every message up to it (the chosen
    version of each). Editing, rewinding or swiping any earlier message gives a new key, so a note made
    for the old version is never used (e.g. a place changed from library to beach several messages back)."""
    h = hashlib.sha1()
    for m in history:
        if m.get("content"):
            h.update(m["role"][0].encode() + re.sub(r"\s+", " ", m["content"]).strip().encode("utf-8") + b"\x1f")
    return h.hexdigest()[:16]


def state_path(chat_path: Path) -> Path:
    return chat_path.with_name(chat_path.stem + ".scene.json")


def load_states(chat_path: Path) -> dict:
    try:
        data = json.loads(state_path(chat_path).read_text("utf-8"))
        return data if isinstance(data, dict) and isinstance(data.get("states"), dict) else {"states": {}}
    except (OSError, ValueError):
        return {"states": {}}


def state_for(chat_path: Path, history: list[dict]) -> str:
    """The note made right after the last message of `history` (a reply), or ""."""
    if not history:
        return ""
    return str(load_states(chat_path)["states"].get(scene_key(history), {}).get("state", ""))


def save_state(chat_path: Path, history: list[dict], state: str) -> None:
    data = load_states(chat_path)
    states, key = data["states"], scene_key(history)
    states.pop(key, None)
    states[key] = {"state": state}
    while len(states) > KEEP:
        states.pop(next(iter(states)))
    state_path(chat_path).write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")


def recent_log(history: list[dict], char: str, user: str) -> str:
    msgs = [m for m in history if m.get("content")][-ROUNDS * 2:]
    out = []
    for m in msgs:
        text = re.sub(r"\n{3,}", "\n\n", m["content"].strip())
        if len(text) > MSG_CHARS:
            text = "…" + text[-MSG_CHARS:]
        out.append(f"{char if m['role'] == 'assistant' else user}: {text}")
    return "\n\n".join(out)


def clean_state(text: str, char: str, user: str) -> str:
    """First useful line of the model's answer; "" if it isn't a scene note."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    lines = [l.strip(" \t*-\"'`") for l in text.strip().splitlines() if l.strip(" \t*-\"'`")]
    if not lines:
        return ""
    # the format asks for "Where: …; char: …; user: …" on one line; models sometimes split it
    field = re.compile(r"(?:where|mood|%s|%s)\s*:" % (re.escape(char), re.escape(user)), re.I)
    if len(lines) > 1 and field.match(lines[0]):
        line = "; ".join(l.rstrip(" ;") for l in lines[:4] if field.match(l))
    else:
        line = lines[0]
    line = re.sub(r"\s*;(?:\s*;)+", ";", line)  # "a;; b" → "a; b"
    line = re.sub(r"^(?:scene(?: note| state)?|note|state)\s*:\s*", "", line, flags=re.I).strip()
    if len(line) < 12 or re.search(r"\b(?:I can(?:'|no)t|I'm sorry|as an AI)\b", line, re.I):
        return ""
    return line[:480]


def build_state(ask: Callable[[str, str], str], history: list[dict], char: str, user: str, prev: str = "") -> str:
    log = recent_log(history, char, user)
    if not log:
        return ""
    try:
        out = ask(SCENE_SYSTEM, SCENE_PROMPT.format(char=char, user=user, prev=prev or "(none)", log=log))
    except OSError:
        return ""
    return clean_state(out, char, user)
