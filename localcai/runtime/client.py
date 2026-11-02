"""Minimal OpenAI-compatible chat client (stdlib only, streaming).

Every popular local runner exposes this API, so "pick your own model" is just
a base URL + model name:
"""
from __future__ import annotations

import json
import re
import urllib.request
from typing import Iterator

BACKENDS = {
    "ollama":    "http://localhost:11434/v1",
    "lmstudio":  "http://localhost:1234/v1",
    "llamacpp":  "http://localhost:8080/v1",
    "koboldcpp": "http://localhost:5001/v1",
}


def resolve_base_url(backend_or_url: str) -> str:
    return BACKENDS.get(backend_or_url, backend_or_url).rstrip("/")


def list_models(base_url: str, timeout: float = 5) -> list[str]:
    with urllib.request.urlopen(f"{base_url}/models", timeout=timeout) as r:
        return [m["id"] for m in json.load(r).get("data", [])]


def name_patterns(char: str) -> list[str]:
    """Ways a model may label the character's own lines: the full name and its first word."""
    names = {char.strip()}
    first = char.strip().split()[0] if char.strip() else ""
    if len(first) >= 3:
        names.add(first)
    return sorted((n for n in names if n), key=len, reverse=True)


def strip_name_prefix(tokens: Iterator[str], char: str) -> Iterator[str]:
    """Remove a leading "Mira Vale:" (or "**Mira:**", "Mira Vale：") at the start of any line.

    Roleplay-tuned models often write chat-log style "Name: text"; the bubble already shows the name.
    Works while streaming: only the first few characters of each line are held back.
    """
    names = name_patterns(char)
    if not names:
        yield from tokens
        return
    alt = "|".join(re.escape(n) for n in names)
    rx = re.compile(rf"^[ \t]*(?:(\*\*?)(?:{alt})\1[ \t]*[:：]|(\*\*?)(?:{alt})[ \t]*[:：]\2|(?:{alt})[ \t]*[:：])[ \t]*", re.I)
    hold = max(len(n) for n in names) + 8
    buf, at_start = "", True
    for tok in tokens:
        buf += tok
        out = ""
        while buf:
            if at_start:
                nl = buf.find("\n")
                head = buf if nl < 0 else buf[:nl]
                if nl < 0 and len(head) < hold:
                    break  # not enough of this line yet to decide
                m = rx.match(head)
                if m:
                    buf = buf[m.end():]
                at_start = False
                continue
            nl = buf.find("\n")
            if nl < 0:
                out += buf; buf = ""
            else:
                out += buf[:nl + 1]; buf = buf[nl + 1:]; at_start = True
        if out:
            yield out
    if buf:
        m = rx.match(buf) if at_start else None
        yield buf[m.end():] if m else buf


def strip_thinking(tokens: Iterator[str]) -> Iterator[str]:
    """Drop <think>…</think> sections that reasoning models emit, even when tags are split across tokens."""
    buf, inside = "", False
    for tok in tokens:
        buf += tok
        while True:
            if inside:
                end = buf.find("</think>")
                if end < 0:
                    buf = buf[-8:]  # keep a tail in case the closing tag is split
                    break
                buf, inside = buf[end + 8:].lstrip("\n"), False
            else:
                start = buf.find("<think>")
                if start < 0:
                    safe = len(buf) - 7  # hold back a possible partial "<think>"
                    if safe > 0:
                        yield buf[:safe]
                        buf = buf[safe:]
                    break
                if start:
                    yield buf[:start]
                buf, inside = buf[start + 7:], True
    if buf and not inside:
        yield buf


def stream_chat(base_url: str, model: str, messages: list[dict], temperature: float = 0.8,
                max_tokens: int = 512, api_key: str = "localcai", info: dict | None = None,
                extra: dict | None = None) -> Iterator[str]:
    """Stream reply text. `info["finish_reason"]` is set at the end ("length" = hit max_tokens).
    `extra` adds sampler settings (only send these to servers that accept them)."""
    return strip_thinking(_stream_chat(base_url, model, messages, temperature, max_tokens, api_key, info, extra))


def _stream_chat(base_url: str, model: str, messages: list[dict], temperature: float = 0.8,
                 max_tokens: int = 512, api_key: str = "localcai", info: dict | None = None,
                 extra: dict | None = None) -> Iterator[str]:
    payload_obj = {"model": model, "messages": messages, "temperature": temperature,
                   "max_tokens": max_tokens, "stream": True}
    payload_obj.update(extra or {})
    body = json.dumps(payload_obj).encode("utf-8")
    req = urllib.request.Request(f"{base_url}/chat/completions", data=body, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req, timeout=300) as r:
        for raw in r:
            line = raw.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                obj = json.loads(payload)
            except ValueError:
                continue
            if isinstance(obj, dict) and obj.get("error"):  # e.g. llama-server "Context size has been exceeded"
                err = obj["error"]
                raise OSError(err.get("message") if isinstance(err, dict) else str(err))
            try:
                choice = obj["choices"][0]
                delta = choice.get("delta", {})
            except (KeyError, IndexError, TypeError):
                continue
            if info is not None and choice.get("finish_reason"):
                info["finish_reason"] = choice["finish_reason"]
            if delta.get("content"):
                yield delta["content"]


_END = re.compile(r'[。！？…～」』）]|[.!?~)\]"”*](?=\s|$)')


def trim_to_sentence(text: str) -> str:
    """A reply cut off by max_tokens: drop the unfinished last sentence (keep it if nothing would be left)."""
    text = text.rstrip()
    ends = list(_END.finditer(text))
    if not ends:
        return text
    cut = ends[-1].end()
    if cut < len(text) * 0.4:
        return text
    out = text[:cut].rstrip()
    # don't leave an unclosed *action* or "quote" behind
    if out.count("(") > out.count(")"):
        out += ")"
    if out.count("*") % 2:
        out += "*"
    if out.count('"') % 2:
        out += '"'
    return out
