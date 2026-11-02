"""Small helpers for embedded images (data: URLs from the extension)."""
from __future__ import annotations

import base64
import binascii
import re

MAX_BYTES = 15 * 1024 * 1024
EXT = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg", "image/webp": "webp", "image/gif": "gif"}
_DATA_URL = re.compile(r"^data:(image/[a-z0-9.+-]+);base64,(.*)$", re.S | re.I)
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def decode_data_url(value: object) -> tuple[str, bytes] | None:
    """Return (mime, bytes) for a valid image data: URL, else None. Never raises."""
    if not isinstance(value, str):
        return None
    m = _DATA_URL.match(value.strip())
    if not m or m.group(1).lower() not in EXT:
        return None
    try:
        data = base64.b64decode(m.group(2), validate=True)
    except (binascii.Error, ValueError):
        return None
    if not data or len(data) > MAX_BYTES or not looks_like(m.group(1).lower(), data):
        return None
    return m.group(1).lower(), data


def looks_like(mime: str, data: bytes) -> bool:
    sig = {"image/png": data[:8] == PNG_MAGIC,
           "image/jpeg": data[:3] == b"\xff\xd8\xff", "image/jpg": data[:3] == b"\xff\xd8\xff",
           "image/webp": data[:4] == b"RIFF" and data[8:12] == b"WEBP",
           "image/gif": data[:4] == b"GIF8"}
    return sig.get(mime, False)


def png_or_none(value: object) -> bytes | None:
    d = decode_data_url(value)
    return d[1] if d and d[0] == "image/png" else None


def ext_for(mime: str) -> str:
    return EXT.get(mime, "bin")
