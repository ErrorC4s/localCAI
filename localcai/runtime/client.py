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


def stream_chat(base_url: str, model: str, messages: list[dict], temperature: float = 0.8,
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
