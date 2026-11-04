"""Chat memory facts, like C.ai's Memory page: short facts grouped by who they are about
("Mira — hair: long silver"), kept per chat, editable one by one, sent with every reply.

Stored in the chat file's metadata (chat_metadata.localcai_facts) as a list of
{"id", "about", "category", "value", "source": "cai"|"you"|"auto", "edited": bool}.

Chats imported before facts existed have their C.ai memory only as lorebook entries on the
character card ("about — category: value"); those are read as the chat's facts until the chat
gets its own list (the first look at them in the Memory dialog saves them, with fixed ids).
Imported C.ai facts keep what C.ai had ("orig") so re-imports respect the user's edits and deletions.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from typing import Callable

KEY = "localcai_facts"
REMOVED = "localcai_facts_removed"  # C.ai facts the user deleted: a re-import doesn't bring them back
LIMIT = 3000          # characters of facts sent with every reply (~750 tokens); like C.ai's memory bar
AUTO_STOP = 0.9       # automatic facts stop being added past this share of the limit
AUTO_EVERY = 6        # look for new facts every 6 replies
AUTO_MESSAGES = 12    # in the last 12 messages
MAX_VALUE = 200


def _id() -> str:
    return uuid.uuid4().hex[:10]


def _clean(s: object, n: int) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()[:n]


def make(about: str, category: str, value: str, source: str = "you", edited: bool = False) -> dict:
    return {"id": _id(), "about": _clean(about, 60), "category": _clean(category, 40),
            "value": _clean(value, MAX_VALUE), "source": source, "edited": bool(edited)}


def orig_key(f: dict) -> str:
    """Identifies an imported C.ai fact as C.ai had it (who, category, value), whatever it was changed to here."""
    o = f.get("orig") if isinstance(f.get("orig"), dict) else f
    return "\x1f".join(_clean(o.get(k), 200).casefold() for k in ("about", "category", "value"))


def _stable_id(f: dict, n: int) -> str:
    # the same fact read twice gets the same id (facts read from the card are not stored with ids)
    return hashlib.sha1(f"{n}\x1f{orig_key(f)}".encode("utf-8")).hexdigest()[:10]


def normalize(facts: object) -> list[dict]:
    out, seen = [], set()
    for n, f in enumerate(facts if isinstance(facts, list) else []):
        if not isinstance(f, dict) or not _clean(f.get("value"), MAX_VALUE):
            continue
        g = make(f.get("about", ""), f.get("category", ""), f.get("value", ""),
                 f.get("source") if f.get("source") in ("cai", "you", "auto") else "you", f.get("edited", False))
        g["id"] = _clean(f["id"], 20) if f.get("id") else _stable_id(f, n)
        o = f.get("orig") if isinstance(f.get("orig"), dict) else None
        if not o and g["source"] == "cai" and not g["edited"]:
            o = g  # an untouched C.ai fact is what C.ai had
        if o:  # any fact can be known to C.ai too (e.g. one the user wrote that a later import also had)
            g["orig"] = {k: _clean(o.get(k), MAX_VALUE) for k in ("about", "category", "value")}
        if _clean(f.get("pending"), MAX_VALUE):
            g["pending"] = _clean(f["pending"], MAX_VALUE)
        k = _same(g)
        if k in seen:
            continue
        seen.add(k)
        out.append(g)
    return out


def is_theirs(f: dict) -> bool:
    """The user decided this fact (wrote or edited it): imports and automatic facts never change it,
    whatever its source says."""
    return f["source"] == "you" or bool(f["edited"])


def slot_key(about: str, category: str) -> str:
    return "slot\x1f" + _clean(about, 60).casefold() + "\x1f" + _clean(category, 40).casefold()


def _slot_of(f: dict) -> str:
    """Which C.ai fact this is, by who and category as C.ai had them (the user may have renamed the category)."""
    o = f.get("orig") or f
    return slot_key(o.get("about", ""), o.get("category", ""))


def _same(f: dict) -> tuple:
    return (f["about"].casefold(), f["category"].casefold(), f["value"].casefold())


def from_cai(memories: list[dict]) -> list[dict]:
    """C.ai conversation facts ({about, category, value}) as chat facts."""
    return normalize([{**m, "source": "cai"} for m in memories or []])


def parse_legacy(content: str) -> dict | None:
    """A lorebook entry written by older versions: "about — category: value" (either part may be missing)."""
    m = re.match(r"^(?:(.*?) — )?(?:([^:]{1,40}): )?(.+)$", content.strip(), re.S)
    if not m or not m.group(3).strip():
        return None
    return make(m.group(1) or "", m.group(2) or "", m.group(3), "cai")


def card_facts(card: dict) -> list[dict]:
    d = card.get("data", card)
    out = []
    for e in (d.get("character_book") or {}).get("entries", []):
        if ((e.get("extensions") or {}).get("localcai") or {}).get("from_memory"):
            f = parse_legacy(e.get("content", ""))
            if f:
                f.pop("id")  # normalize gives it an id that's the same every time it's read
                out.append(f)
    return normalize(out)


def is_memory_entry(e: dict) -> bool:
    return bool(((e.get("extensions") or {}).get("localcai") or {}).get("from_memory"))


def chat_facts(meta: dict, card: dict) -> list[dict]:
    cm = meta.get("chat_metadata") or {}
    if KEY in cm:
        return normalize(cm[KEY])
    return card_facts(card)


def set_facts(meta: dict, facts: list[dict]) -> None:
    meta.setdefault("chat_metadata", {})[KEY] = normalize(facts)


def merge_import(old: list[dict], new: list[dict], removed: list[str] | None = None) -> list[dict]:
    """Re-importing a chat. Every imported C.ai fact remembers what C.ai had (orig), so:
    - a C.ai fact the user edited or deleted here stays edited / deleted;
    - C.ai changing a fact the user never touched updates it;
    - C.ai changing a fact the user edited doesn't overwrite theirs: the new C.ai value waits as
      "pending" (not sent to the model) until they pick one in the Memory dialog;
    - new C.ai facts are added; the user's own and automatic facts are kept."""
    out = [dict(f) for f in normalize(old)]
    gone = set(removed or [])
    for f in normalize(new):
        k = orig_key(f)
        if k in gone or _slot_of(f) in gone or any(g.get("orig") and orig_key(g) == k for g in out):
            continue  # already here (maybe edited) or deleted by the user
        if any(_same(g) == _same(f) for g in out):
            for g in out:  # the same fact is already here: from now on it's known as C.ai's too
                if _same(g) == _same(f):
                    g["orig"] = dict(f["orig"])
                    if g["source"] == "auto":
                        g["source"] = "cai"  # the user's own stays theirs (and protected)
                    break
            continue
        if not f["category"]:
            out.append(f)
            continue
        # the same C.ai fact (who + category as C.ai had them), now with another value
        slot = [g for g in out if g.get("orig") and _slot_of(g) == _slot_of(f)]
        slot = slot or [g for g in out if g["source"] == "cai" and not g.get("orig") and _slot_of(g) == _slot_of(f)]
        if slot:
            g = slot[0]
            if not is_theirs(g):
                g.update(value=f["value"], orig=dict(f["orig"]))
                g.pop("pending", None)
            elif not g.get("orig"):
                g["orig"] = dict(f["orig"])  # edited before origins were kept: this is what it was edited from
            else:
                g["pending"], g["orig"] = f["value"], dict(f["orig"])
            continue
        out.append(f)
    return out


def facts_block(facts: list[dict]) -> str:
    """Grouped by who the fact is about, one line each: "Mira: hair: long silver; age: 19"."""
    groups: dict[str, list[str]] = {}
    for f in normalize(facts):
        groups.setdefault(f["about"] or "Story", []).append(
            f"{f['category']}: {f['value']}" if f["category"] else f["value"])
    return "\n".join(f"- {who}: " + "; ".join(items) for who, items in groups.items())


def used(facts: list[dict]) -> int:
    return len(facts_block(facts))


def apply_to_chat(meta: dict, card: dict, op: str, body: dict) -> list[dict]:
    """One change from the Memory dialog, saved into the chat's metadata (the caller saves the file)."""
    facts = chat_facts(meta, card)
    f = next((f for f in facts if f["id"] == body.get("id")), None)
    new = apply(facts, op, body)
    if op == "delete" and f and (f.get("orig") or f["source"] == "cai"):
        # remember the deletion so a re-import doesn't bring it back; a C.ai fact edited before origins
        # were kept doesn't know what C.ai had, so remember its place (who + category) instead
        cm = meta.setdefault("chat_metadata", {})
        cm[REMOVED] = sorted(set(cm.get(REMOVED) or []) | {orig_key(f) if f.get("orig") else _slot_of(f)})
    set_facts(meta, new)
    return normalize(new)


def apply(facts: list[dict], op: str, body: dict) -> list[dict]:
    """add / edit / delete one fact; keep (keep-mine) or take (use-cai) a pending C.ai value."""
    facts = normalize(facts)
    if op == "add":
        f = make(body.get("about", ""), body.get("category", ""), body.get("value", ""), "you")
        if not f["value"]:
            raise ValueError("Write the fact first.")
        if used(facts + [f]) > LIMIT:
            raise ValueError("Memory is full. Delete or shorten some facts first.")
        return facts + [f]
    i = next((i for i, f in enumerate(facts) if f["id"] == body.get("id")), -1)
    if i < 0:
        raise ValueError("That fact isn't there any more. Reopen Memory.")
    if op == "delete":
        return facts[:i] + facts[i + 1:]
    if op in ("keep-mine", "use-cai"):
        g = dict(facts[i])
        if op == "use-cai" and g.get("pending"):
            g.update(value=g["pending"], edited=False, source="cai")  # now C.ai's: later C.ai updates follow
        g.pop("pending", None)
        return facts[:i] + [g] + facts[i + 1:]
    if op == "edit":
        g = make(body.get("about", facts[i]["about"]), body.get("category", facts[i]["category"]),
                 body.get("value", ""), facts[i]["source"], True)
        if not g["value"]:
            raise ValueError("A fact can't be empty. Delete it instead.")
        g["id"] = facts[i]["id"]
        for k in ("orig", "pending"):
            if k in facts[i]:
                g[k] = facts[i][k]
        new = facts[:i] + [g] + facts[i + 1:]
        if used(new) > LIMIT and used(new) > used(facts):
            raise ValueError("Memory is full. Shorten this or delete other facts first.")
        return new
    raise ValueError(f"unknown action: {op}")


# ── automatic facts ──────────────────────────────────────────────────────────

FACTS_SYSTEM = ("You keep a short list of lasting facts about the people in a role-play. "
                "You only write what the text clearly states; you never guess and never continue the story.")

FACTS_PROMPT = """Role-play between {char} and {user}.

Facts already known:
{known}

The latest part of the role-play:
<<<
{log}
>>>

List facts from this text that are NEW or CHANGED and will still be true later: names, age, appearance \
(hair, eyes, height, clothing style), species, job, family, pets, where they live, relationships between \
them, likes and dislikes, important promises or events. Not what someone is doing right now, not moods, \
not anything already in the known facts.
One per line, exactly: Who | category | fact
At most 4 lines. If there is nothing new, write: NONE
"""


def _log(history: list[dict], char: str, user: str) -> str:
    out = []
    for m in [m for m in history if m.get("content")][-AUTO_MESSAGES:]:
        text = m["content"].strip()
        if len(text) > 900:
            text = text[:900] + "…"
        out.append(f"{char if m['role'] == 'assistant' else user}: {text}")
    return "\n\n".join(out)


def parse_auto(text: str, names: list[str]) -> list[dict]:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    out = []
    for line in text.splitlines():
        parts = [p.strip(" \t*-\"'`") for p in line.split("|")]
        if len(parts) != 3 or not all(parts):
            continue
        who, cat, val = parts
        if who.casefold() in ("who", "name") or re.search(r"\b(?:I can(?:'|no)t|I'm sorry|as an AI)\b", val, re.I):
            continue
        # keep the names as the chat spells them
        who = next((n for n in names if n.casefold() == who.casefold()), who)
        if len(who) > 40 or len(cat) > 30:
            continue
        out.append(make(who, cat.lower(), val, "auto"))
    return out[:4]


def merge_auto(facts: list[dict], new: list[dict]) -> list[dict]:
    """Add what the model found. A changed fact replaces an automatic one in the same slot;
    the user's own facts, C.ai facts and edited facts are never overwritten. Stops when memory is nearly full."""
    out = normalize(facts)
    for f in new:
        if any(_same(f) == _same(g) for g in out):
            continue
        slot = [i for i, g in enumerate(out) if g["about"].casefold() == f["about"].casefold()
                and g["category"].casefold() == f["category"].casefold()]
        if slot:
            g = out[slot[0]]
            if g["source"] != "auto" or is_theirs(g):
                continue  # theirs or C.ai's: leave it
            trial = out[:slot[0]] + [{**f, "id": g["id"]}] + out[slot[0] + 1:]
        else:
            trial = out + [f]
        if used(trial) > LIMIT * AUTO_STOP:
            break
        out = trial
    return out


def find_new(ask: Callable[[str, str], str], history: list[dict], char: str, user: str,
             facts: list[dict]) -> list[dict]:
    log = _log(history, char, user)
    if not log:
        return []
    try:
        out = ask(FACTS_SYSTEM, FACTS_PROMPT.format(char=char, user=user, known=facts_block(facts) or "(none)",
                                                    log=log))
    except OSError:
        return []
    return parse_auto(out, [char, user] + sorted({f["about"] for f in facts if f["about"]}))
