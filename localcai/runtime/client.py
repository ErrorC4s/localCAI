"""Minimal OpenAI-compatible chat client (stdlib only, streaming).

Every popular local runner exposes this API, so "pick your own model" is just
a base URL + model name:
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Iterator


class ContextTooLong(OSError):
    """The model server refused the prompt: more tokens than its context holds (llama-server answers 400
    with how many tokens the prompt had and how many fit)."""

    def __init__(self, message: str, n_prompt: int, n_ctx: int):
        super().__init__(message)
        self.n_prompt, self.n_ctx = n_prompt, n_ctx


def _http_error(e: urllib.error.HTTPError) -> OSError:
    """The server's own reason instead of a bare "HTTP Error 400: Bad Request"."""
    try:
        body = e.read().decode("utf-8", "replace")
    except OSError:
        body = ""
    msg, err = body.strip()[:300], {}
    try:
        obj = json.loads(body)
        err = obj.get("error") if isinstance(obj, dict) else None
        err = err if isinstance(err, dict) else {"message": str(err or "")}
        msg = str(err.get("message") or msg)
    except ValueError:
        pass
    m = re.search(r"\((\d+) tokens\).*?context size \((\d+) tokens\)", msg)
    n_prompt = int(err.get("n_prompt_tokens") or (m and m.group(1)) or 0)
    n_ctx = int(err.get("n_ctx") or (m and m.group(2)) or 0)
    if (err.get("type") == "exceed_context_size_error" or "exceeds the available context" in msg) and n_prompt and n_ctx:
        return ContextTooLong(msg, n_prompt, n_ctx)
    return OSError(f"HTTP {e.code}: {msg or e.reason}")

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


# Chat-format markers some models write out as plain text when their tokenizer has no such special token
TEMPLATE_MARKERS = ("<|im_end|>", "<|im_start|>", "<|eot_id|>", "<|end_of_text|>", "<|endoftext|>", "</s>",
                    "[/INST]", "[INST]", "<end_of_turn>", "<start_of_turn>")


def strip_markers(text: str) -> str:
    """Cut a reply at the first leaked chat-format marker (everything after it is the model running on)."""
    cut = min((i for i in (text.find(m) for m in TEMPLATE_MARKERS) if i >= 0), default=-1)
    return (text[:cut] if cut >= 0 else text).rstrip()


# The model stepping outside the story to review its own reply ("[What the reply does:]", "Notes:",
# "(OOC: ...)", "Analysis:") — usually it is echoing the hidden per-turn direction back as a checklist.
_META = re.compile(
    r"^[ \t>*_#-]*[\[(]?[ \t*_]*(?:"
    r"what (?:the|this|my) (?:reply|response|message)\b"
    r"|(?:reply|response|writing|scene) (?:notes?|analysis|summary|checklist|breakdown)\b"
    r"|(?:author'?s |writer'?s |director'?s )?notes?[ \t*_]*[:\])]"
    r"|ooc\b|\(\(|out of character\b"
    r"|(?:self[- ]?check|checklist|analysis|explanation|breakdown|commentary)[ \t*_]*[:\])]"
    r")", re.I | re.M)


# "(Continues)" / "[continued]" labels some models put between paragraphs of one reply
_CONT = re.compile(r"(?im)^([ \t>*_]*)[\[(](?:cont(?:inues|inued|\.)?|continuing)[\])][ \t]*")


def strip_meta(text: str) -> str:
    """Cut a reply where the model stops role-playing and starts commenting on the reply itself."""
    text = _CONT.sub(r"\1", text or "")
    m = _META.search(text or "")
    if not m:
        return text
    head = text[:m.start()].rstrip()
    head = re.sub(r"(?:\n[ \t]*(?:-{3,}|\*{3,}|_{3,})[ \t]*)+$", "", head).rstrip()  # a trailing --- divider
    return head if re.search(r"\w", head) else text  # never throw away the whole reply


def name_patterns(char: str) -> list[str]:
    """Ways a model may label the character's own lines: the full name and its first word."""
    names = {char.strip()}
    first = char.strip().split()[0] if char.strip() else ""
    if len(first) >= 3:
        names.add(first)
    return sorted((n for n in names if n), key=len, reverse=True)


def strip_name_prefix(tokens: Iterator[str], char: str, info: dict | None = None) -> Iterator[str]:
    """Remove a chat-log label like "Mira Vale:" (or "**Mira:**") at the very start of a reply.

    Roleplay-tuned models often open with "Name:"; the bubble already shows the name. Only the
    first line is touched, so group scenes ("Bram: … / Tess: …") keep their labels; the removed
    label is reported in info["name_prefix"] so it can be put back if other speakers turn up.
    """
    names = name_patterns(char)
    if not names:
        yield from tokens
        return
    alt = "|".join(re.escape(n) for n in names)
    rx = re.compile(rf"^[ \t]*(?:(\*\*?)(?:{alt})\1[ \t]*[:：]|(\*\*?)(?:{alt})[ \t]*[:：]\2|(?:{alt})[ \t]*[:：])[ \t]*", re.I)
    hold = max(len(n) for n in names) + 8
    buf, decided = "", False
    for tok in tokens:
        if decided:
            yield tok
            continue
        buf += tok
        nl = buf.find("\n")
        head = buf if nl < 0 else buf[:nl]
        if nl < 0 and len(head) < hold:
            continue  # not enough of the first line yet to decide
        m = rx.match(head)
        if m:
            if info is not None:
                info["name_prefix"] = buf[:m.end()]
            buf = buf[m.end():]
        decided = True
        if buf:
            yield buf
    if not decided and buf:
        m = rx.match(buf)
        if m and info is not None:
            info["name_prefix"] = buf[:m.end()]
        yield buf[m.end():] if m else buf


_SPEAKER = re.compile(r"^[ \t]*\**([A-Z\u4e00-\u9fff][\w'’ .-]{0,30}?)\**[ \t]*[:：]\**[ \t]", re.M)


def other_speakers(text: str, char: str) -> set[str]:
    """Names other than the character that label lines in a reply (a group scene)."""
    own = {n.lower() for n in name_patterns(char)}
    return {m.group(1).strip() for m in _SPEAKER.finditer(text)
            if m.group(1).strip().lower() not in own and len(m.group(1).split()) <= 3}


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
    try:
        r = urllib.request.urlopen(req, timeout=300)
    except urllib.error.HTTPError as e:
        raise _http_error(e) from None
    with r:
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
