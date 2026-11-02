"""Build store-ready zips of the browser extension.

    python tools/package_extension.py        → dist/localcai-extractor-<ver>-chrome.zip
                                               dist/localcai-extractor-<ver>-firefox.zip

Chrome gets a manifest without Firefox-only keys (avoids "unrecognized key" warnings);
Firefox keeps browser_specific_settings (add-on id + data_collection_permissions).
"""
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "extension"
DIST = ROOT / "dist"
SKIP = {"README.md", ".DS_Store"}


def build(target: str) -> Path:
    manifest = json.loads((EXT / "manifest.json").read_text("utf-8"))
    if target == "chrome":
        manifest.pop("browser_specific_settings", None)
    out = DIST / f"localcai-extractor-{manifest['version']}-{target}.zip"
    DIST.mkdir(exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
        for f in sorted(EXT.rglob("*")):
            rel = f.relative_to(EXT).as_posix()
            if f.is_file() and rel != "manifest.json" and f.name not in SKIP:
                z.write(f, rel)
    return out


if __name__ == "__main__":
    for t in ("chrome", "firefox"):
        p = build(t)
        print(f"{p.relative_to(ROOT)}  ({p.stat().st_size / 1024:.0f} KB)")
