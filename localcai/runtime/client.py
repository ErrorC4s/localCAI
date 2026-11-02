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
