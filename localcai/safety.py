"""Basic safety layer.

Companion apps sit in a sensitive spot: people talk to characters when they
are lonely or struggling. localCAI runs entirely locally and does not phone
home — this module only *shows* help resources on screen when a message
looks like a crisis. It never blocks the conversation and never reports anything.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

CONFIG = Path.home() / ".localcai" / "config.json"

_CRISIS_PATTERNS = [
    # English
    r"\bkill (my ?self|myself)\b", r"\bsuicid", r"\bend (my|it all) life\b", r"\bwant to die\b",
    r"\bself[- ]?harm", r"\bcut(ting)? myself\b", r"\bno reason to live\b",
    # 中文
    r"自殺", r"想死", r"不想活", r"輕生", r"自殘", r"割腕", r"活不下去", r"結束生命", r"自杀", r"自残",
]
_CRISIS_RE = re.compile("|".join(_CRISIS_PATTERNS), re.IGNORECASE)

RESOURCES = """\
──────────────────────────────────────────────
 如果你正在經歷很難熬的時刻，你不用一個人撐著。
 If you're going through something hard, you don't have to face it alone.

   台灣  安心專線 1925（24 小時）｜生命線 1995
   UK    Samaritans 116 123
   US    988 Suicide & Crisis Lifeline (call or text 988)
   其他地區 / elsewhere: https://findahelpline.com
──────────────────────────────────────────────"""


def looks_like_crisis(text: str) -> bool:
    return bool(_CRISIS_RE.search(text))


def load_config() -> dict:
    try:
        return json.loads(CONFIG.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(cfg: dict) -> None:
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=2), "utf-8")


def age_gate(input_fn=input) -> bool:
    """Ask once; remembered in ~/.localcai/config.json."""
    cfg = load_config()
    if cfg.get("age_confirmed"):
        return True
    ans = input_fn("localCAI 的聊天功能僅供 18 歲以上使用。你已滿 18 歲嗎？/ "
                   "Chat is for adults (18+). Are you 18 or older? [y/N] ").strip().lower()
    if ans in ("y", "yes", "是", "對"):
        cfg["age_confirmed"] = True
        save_config(cfg)
        return True
    return False
