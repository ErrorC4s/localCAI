from __future__ import annotations

from typing import Any, Iterable


def pick(d: dict, *keys: str, default: Any = "") -> Any:
    """Return the first present, non-empty value among several possible key names.

    Export formats disagree on naming (greeting / first_mes / greetingText ...),
    so importers list every alias they know about.
    """
    for k in keys:
        if "." in k:  # dotted path, e.g. "author.name"
            cur: Any = d
            for part in k.split("."):
                cur = cur.get(part) if isinstance(cur, dict) else None
                if cur is None:
                    break
            if cur not in (None, "", [], {}):
                return cur
        elif k in d and d[k] not in (None, "", [], {}):
            return d[k]
    return default


def walk(obj: Any) -> Iterable[Any]:
    """Yield every dict and list nested anywhere inside obj (depth-first)."""
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            yield cur
            stack.extend(cur.values())
        elif isinstance(cur, list):
            yield cur
            stack.extend(cur)


def as_text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    return str(v)
