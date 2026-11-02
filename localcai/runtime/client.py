"""Minimal OpenAI-compatible chat client (stdlib only, streaming).

Every popular local runner exposes this API, so "pick your own model" is just
a base URL + model name:
"""
from __future__ import annotations

import json
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
                max_tokens: int = 512, api_key: str = "localcai") -> Iterator[str]:
    return strip_thinking(_stream_chat(base_url, model, messages, temperature, max_tokens, api_key))


def _stream_chat(base_url: str, model: str, messages: list[dict], temperature: float = 0.8,
                 max_tokens: int = 512, api_key: str = "localcai") -> Iterator[str]:
    body = json.dumps({"model": model, "messages": messages, "temperature": temperature,
                       "max_tokens": max_tokens, "stream": True}).encode("utf-8")
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
                delta = json.loads(payload)["choices"][0].get("delta", {})
            except (ValueError, KeyError, IndexError):
                continue
            if delta.get("content"):
                yield delta["content"]
