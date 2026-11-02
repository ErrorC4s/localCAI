"""Basic safety layer.

Companion apps sit in a sensitive spot: people talk to characters when they
are lonely or struggling. localCAI runs entirely locally and does not phone
home. This module only *shows* help resources on screen when a message looks
like a crisis. It never blocks the conversation and never reports anything.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path


def config_path() -> Path:
    return Path(os.environ.get("LOCALCAI_HOME") or Path.home() / ".localcai") / "config.json"


_CRISIS_PATTERNS = [
    # English
    r"\bkill (my ?self|myself)\b", r"\bsuicid", r"\bend (my|it all) life\b", r"\bwant to die\b",
    r"\bself[- ]?harm", r"\bcut(ting)? myself\b", r"\bno reason to live\b",
    # Chinese (traditional + simplified)
    r"自殺", r"想死", r"不想活", r"輕生", r"自殘", r"割腕", r"活不下去", r"結束生命", r"自杀", r"自残",
]
_CRISIS_RE = re.compile("|".join(_CRISIS_PATTERNS), re.IGNORECASE)

HELPLINES = [
    ("Taiwan", "1925 Mental Health Line (24h) · Lifeline 1995"),
    ("UK & Ireland", "Samaritans 116 123"),
    ("US", "988 Suicide & Crisis Lifeline (call or text 988)"),
    ("Anywhere else", "https://findahelpline.com"),
]

RESOURCES = "\n".join(
    ["──────────────────────────────────────────────",
     " If you're going through something hard, you don't have to face it alone.", ""]
    + [f"   {region:<14}{line}" for region, line in HELPLINES]
    + ["──────────────────────────────────────────────"])


def looks_like_crisis(text: str) -> bool:
    return bool(_CRISIS_RE.search(text))


def load_config() -> dict:
    try:
        return json.loads(config_path().read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(cfg: dict) -> None:
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2), "utf-8")


def age_gate(input_fn=input) -> bool:
    """Ask once; remembered in ~/.localcai/config.json."""
    cfg = load_config()
    if cfg.get("age_confirmed"):
        return True
    ans = input_fn("Chat in localCAI is for adults. Are you 18 or older? [y/N] ").strip().lower()
    if ans in ("y", "yes"):
        cfg["age_confirmed"] = True
        save_config(cfg)
        return True
    return False
