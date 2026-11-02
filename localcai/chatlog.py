"""Read/write chat logs (SillyTavern .jsonl) without losing data.

Rows are kept as raw dicts, so pins, swipes and anything else an importer wrote
survive when a chat is continued and saved again.
"""
from __future__ import annotations

import json
from pathlib import Path


def load(path: Path) -> tuple[dict, list[dict]]:
    lines = [json.loads(l) for l in Path(path).read_text("utf-8").splitlines() if l.strip()]
    if lines and "mes" not in lines[0]:
        return lines[0], lines[1:]
    return {}, lines


def save(path: Path, meta: dict, rows: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in [meta, *rows]) + "\n", "utf-8")
    tmp.replace(path)  # atomic: a crash never leaves a half-written chat


def row(name: str, is_user: bool, text: str, send_date: str = "") -> dict:
    return {"name": name, "is_user": is_user, "is_system": False, "send_date": send_date, "mes": text, "extra": {}}


def to_history(rows: list[dict]) -> list[dict]:
    return [{"role": "user" if r.get("is_user") else "assistant", "content": r.get("mes", "")}
            for r in rows if not r.get("is_system")]


def pinned_memories(rows: list[dict]) -> list[str]:
    return [f"{r.get('name', '')}: {r.get('mes', '')}" for r in rows if (r.get("extra") or {}).get("pinned")]


def set_swipe(row: dict, index: int) -> None:
    swipes = row.get("swipes") or [row.get("mes", "")]
    index = max(0, min(index, len(swipes) - 1))
    row["swipes"], row["swipe_id"], row["mes"] = swipes, index, swipes[index]


def add_swipe(row: dict, text: str) -> None:
    swipes = row.get("swipes") or [row.get("mes", "")]
    swipes.append(text)
    row["swipes"], row["swipe_id"], row["mes"] = swipes, len(swipes) - 1, text
