"""Pick the right importer for a file."""
from __future__ import annotations

import json
import zipfile
import tempfile
from pathlib import Path

from ..schema import Bundle
from .sillytavern import import_card, import_chat_jsonl
from .cai_json import import_cai_json


def import_path(path: str | Path) -> Bundle:
    p = Path(path)
    if p.is_dir():
        b = Bundle()
        for f in sorted(p.rglob("*")):
            if f.is_file() and f.suffix.lower() in (".json", ".jsonl", ".png", ".zip"):
                b.merge(import_path(f))
        return b
    suffix = p.suffix.lower()
    if suffix == ".zip":
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(p) as z:
                for member in z.namelist():
                    # refuse path traversal in untrusted archives
                    target = (Path(tmp) / member).resolve()
                    if not str(target).startswith(str(Path(tmp).resolve())):
                        raise ValueError(f"unsafe path in zip: {member}")
                z.extractall(tmp)
            return import_path(tmp)
    if suffix == ".jsonl":
        return import_chat_jsonl(p)
    if suffix == ".png":
        try:
            return import_card(p)
        except ValueError as e:
            return Bundle(warnings=[str(e)])
    if suffix == ".json":
        data = json.loads(p.read_text("utf-8"))
        if isinstance(data, dict) and (data.get("spec", "").startswith("chara_card")
                                       or {"first_mes", "mes_example"} & data.keys()):
            return import_card(p)
        return import_cai_json(p)
    return Bundle(warnings=[f"{p.name}: unsupported file type"])
