"""Recall: find moments from the whole chat that relate to what's being said now.

The model only sees the last few dozen messages. Recall searches everything older
(BM25 keyword ranking, no model needed, fast even for tens of thousands of messages)
and the best matches are added to the prompt as "earlier moments".
Works for English and CJK text (CJK is indexed as character bigrams).
"""
from __future__ import annotations

import math
import re
from collections import Counter

_WORD = re.compile(r"[a-z0-9']{2,}")
_CJK = re.compile(r"[぀-ヿ㐀-鿿豈-﫿가-힯]+")
STOP = set("""the and you your for are was were but not that this with have has had his her him she they them
their what when where who how all can will just out its it's i'm im don't dont about from into then than there
here like get got one would could should been being very really more some any our ours yeah yes okay well""".split())


def tokens(text: str) -> list[str]:
    t = text.lower()
    out = [w for w in _WORD.findall(t) if w not in STOP]
    for run in _CJK.findall(t):
        out += [run[i:i + 2] for i in range(len(run) - 1)] or [run]
    return out


class Index:
    def __init__(self, docs: list[str], k1: float = 1.4, b: float = 0.75):
        self.docs = docs
        self.tf = [Counter(tokens(d)) for d in docs]
        self.len = [sum(c.values()) for c in self.tf]
        self.avg = (sum(self.len) / len(self.len)) if self.len else 1.0
        df: Counter = Counter()
        for c in self.tf:
            df.update(c.keys())
        n = len(docs)
        self.idf = {w: math.log(1 + (n - f + 0.5) / (f + 0.5)) for w, f in df.items()}
        self.k1, self.b = k1, b

    def search(self, query: str, k: int = 3) -> list[int]:
        q = set(tokens(query))
        if not q:
            return []
        scores = []
        for i, c in enumerate(self.tf):
            s = 0.0
            for w in q:
                f = c.get(w)
                if f:
                    s += self.idf[w] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.len[i] / self.avg))
            if s > 0:
                scores.append((s, i))
        scores.sort(reverse=True)
        return [i for _, i in scores[:k]]


def recall(rows: list[dict], query: str, exclude_last: int = 40, k: int = 3,
           max_chars: int = 1800, cache_key: str | None = None) -> list[str]:
    """Return up to k short 'Name: text' snippets from rows older than the last `exclude_last`."""
    older = rows[:-exclude_last] if exclude_last else rows
    if len(older) < 5:
        return []
    names, idx = _index_for(older, cache_key)
    picks, used = [], 0
    for i in sorted(idx.search(query, k)):
        text = re.sub(r"\s+", " ", idx.docs[i]).strip()
        snippet = f"{names[i]}: {text[:600]}"
        if used + len(snippet) > max_chars:
            break
        picks.append(snippet)
        used += len(snippet)
    return picks


# One cached index (the chat being talked in). Rebuilt when ~100 messages were added or the chat changed.
_cache: dict = {}


def _index_for(rows: list[dict], key: str | None) -> tuple[list[str], Index]:
    hit = _cache.get("v")
    if key and hit and hit[0] == key and 0 <= len(rows) - hit[1] < 100:
        return hit[2], hit[3]
    names = [r.get("name", "") for r in rows]
    idx = Index([r.get("mes", "") for r in rows])
    if key:
        _cache["v"] = (key, len(rows), names, idx)
    return names, idx
