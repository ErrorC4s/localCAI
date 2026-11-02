"""Render assets/logo.svg into assets/logo.ico (16–256 px, PNG-compressed entries).

Usage: python tools/make_icon.py   (needs playwright)
"""
import struct
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SIZES = [16, 24, 32, 48, 64, 128, 256]


def main():
    svg = (ROOT / "assets" / "logo.svg").read_text("utf-8")
    pngs = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for s in SIZES:
            ctx = b.new_context(viewport={"width": 128, "height": 128}, device_scale_factor=s / 128)
            page = ctx.new_page()
            page.set_content(f'<html><body style="margin:0;background:transparent">{svg}</body></html>')
            pngs.append(page.screenshot(omit_background=True))
            ctx.close()
        b.close()
    header = struct.pack("<HHH", 0, 1, len(pngs))
    offset = 6 + 16 * len(pngs)
    entries, data = b"", b""
    for s, png in zip(SIZES, pngs):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(png), offset + len(data))
        data += png
    out = ROOT / "assets" / "logo.ico"
    out.write_bytes(header + entries + data)
    print(out.relative_to(ROOT), f"{out.stat().st_size // 1024} KB", SIZES)


if __name__ == "__main__":
    main()
