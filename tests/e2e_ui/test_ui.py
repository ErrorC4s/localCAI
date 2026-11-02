"""Drives the web UI in headless Chromium like a user would.

Run: python tests/e2e_ui/test_ui.py [screenshot.png]
Needs: pip install playwright (browsers installed).
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "extension_export.lcai.json"
UI_PORT, LLM_PORT = 8799, 8798
BASE = f"http://127.0.0.1:{UI_PORT}"


def wait_up(url):
    for _ in range(50):
        try:
            urllib.request.urlopen(url, timeout=1)
            return
        except urllib.error.HTTPError:
            return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"{url} never came up")


def http(method, path, headers=None, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=body, headers=headers or {})
    try:
        return urllib.request.urlopen(req, timeout=5).status
    except urllib.error.HTTPError as e:
        return e.code


def main(shot=None):
    home = tempfile.mkdtemp(prefix="lcai-home-")
    last = last_path = os.path.join(home, "last_request.json")
    env = {**os.environ, "LOCALCAI_HOME": home, "PYTHONPATH": str(ROOT)}
    procs = [
        subprocess.Popen([sys.executable, str(Path(__file__).parent / "fake_llm.py"), str(LLM_PORT), last]),
        subprocess.Popen([sys.executable, "-m", "localcai", "ui", "--no-browser", "--port", str(UI_PORT)], env=env, cwd=home),
    ]
    try:
        wait_up(f"http://127.0.0.1:{LLM_PORT}/v1/models")
        wait_up(BASE + "/")

        # security checks
        assert http("GET", "/api/state", {"Host": f"evil.example:{UI_PORT}"}) == 403, "DNS-rebinding guard"
        assert http("POST", "/api/settings", {"Content-Type": "application/json"}, b"{}") == 403, "CSRF guard"
        assert http("GET", "/api/card/..%2F..%2Fconfig.png") == 404, "path traversal"
        assert http("GET", "/api/image/personas/..%2F..%2Fconfig.json") == 404, "path traversal (images)"
        assert http("GET", "/api/image/characters/x.svg") == 404, "only raster images are served"

        with sync_playwright() as p:
            page = p.chromium.launch().new_page(viewport={"width": 1280, "height": 820})
            page.goto(BASE)
            expect(page.locator("#welcome")).to_be_visible()

            # import
            page.set_input_files("#file-input", str(FIXTURE))
            expect(page.locator(".toast", has_text="Imported")).to_have_count(1)
            expect(page.locator(".char-item")).to_have_count(2)
            expect(page.locator("#persona option")).to_have_count(2)  # (no persona) + Alex

            # point at the fake model server via Settings
            page.click("#open-settings")
            page.fill("#set-custom-url", f"http://127.0.0.1:{LLM_PORT}/v1")
            page.fill("#set-user-name", "Tester")
            page.click("#settings-save")
            expect(page.locator("#model option", has_text="fake-model")).to_have_count(1)
            page.select_option("#model", "fake-model")

            # open Luna: imported chat with pinned message
            page.click(".char-item:has-text('Luna')")
            expect(page.locator("#head-name")).to_have_text("Luna")
            expect(page.locator(".msg .pin")).to_have_count(1)
            # real avatar (8x6 test image) in the sidebar, header and messages; background applied
            assert page.eval_on_selector("#head-avatar img", "i => i.complete && i.naturalWidth") == 8
            assert page.locator(".char-item:has-text('Rex') .avatar img").count() == 0  # no picture → initial
            assert "Luna.background.png" in page.eval_on_selector("#messages", "e => e.style.backgroundImage")
            n_before = page.locator(".msg").count()

            # first message triggers the age gate
            page.fill("#input", "What tea do I like?")
            page.keyboard.press("Enter")
            expect(page.locator("#age-dialog")).to_be_visible()
            page.click("#age-yes")
            expect(page.locator(".msg").last.locator("strong")).to_have_text("Alishan")  # streamed + markdown
            expect(page.locator(".msg")).to_have_count(n_before + 2)
            sent = json.load(open(last, encoding="utf-8"))
            assert sent["model"] == "fake-model"
            assert "Alishan" in sent["messages"][0]["content"], "pinned memory in prompt"
            assert sent["messages"][-1]["content"] == "What tea do I like?"

            # persona
            page.select_option("#persona", "Alex")
            page.fill("#input", "hello again")
            page.click("#send")
            expect(page.locator(".msg")).to_have_count(n_before + 4)
            sent = json.load(open(last, encoding="utf-8"))
            assert "[About Alex]" in sent["messages"][0]["content"], "persona in prompt"
            user_face = page.locator(".msg.user .who img").last
            expect(user_face).to_have_attribute("src", "/api/image/personas/Alex.avatar.png")

            # regenerate keeps the count
            page.click("#regen")
            page.wait_for_timeout(600)
            expect(page.locator(".msg")).to_have_count(n_before + 4)

            # ── C.ai-style message tools ──
            last = page.locator(".msg").last
            expect(last.locator(".swipes")).to_contain_text("2/2")       # ↻ above kept the old reply as a swipe
            last.locator(".swipes .tool").first.click()                 # ◀
            expect(page.locator(".msg").last.locator(".swipes")).to_contain_text("1/2")
            page.locator(".msg").last.locator(".swipes .tool").last.click()  # ▶ back to 2/2
            expect(page.locator(".msg").last.locator(".swipes")).to_contain_text("2/2")
            page.locator(".msg").last.locator(".swipes .tool").last.click()  # ▶ at the end → generate a 3rd
            expect(page.locator(".msg").last.locator(".swipes")).to_contain_text("3/3", timeout=10000)
            count = page.locator(".msg").count()

            # edit a line
            page.locator(".msg").last.locator(".tool[title='Edit']").click()
            page.fill(".edit-box", "*smiles* Edited line.")
            page.click(".edit-buttons .tool.primary")
            expect(page.locator(".msg").last.locator(".body")).to_have_text("smiles Edited line.")
            expect(page.locator(".msg").last.locator(".edited")).to_have_count(1)

            # pin it → it becomes a memory in the next prompt
            page.locator(".msg").last.locator(".tool[title^='Pin']").click()
            expect(page.locator(".msg").last.locator(".pin")).to_have_count(1)
            page.fill("#input", "still there?")
            page.click("#send")
            expect(page.locator(".msg")).to_have_count(count + 2)
            sent = json.load(open(last_path, encoding="utf-8"))
            assert "Edited line." in sent["messages"][0]["content"], "pinned message in memories"

            # delete one message, then rewind
            page.on("dialog", lambda d: d.accept())
            page.locator(".msg").last.locator(".tool[title='Delete this message']").click()
            expect(page.locator(".msg")).to_have_count(count + 1)
            page.locator(".msg").nth(count - 1).locator(".tool[title^='Rewind']").click()
            expect(page.locator(".msg")).to_have_count(count - 1)

            # custom chat background
            bg = Path(home) / "bg.png"
            bg.write_bytes(Path(ROOT / "extension" / "icons" / "icon48.png").read_bytes())
            page.set_input_files("#bg-input", str(bg))
            expect(page.locator(".toast", has_text="Background set")).to_have_count(1)
            assert "/api/image/chats/" in page.eval_on_selector("#messages", "e => e.style.backgroundImage")
            page.click("#bg-remove")
            page.wait_for_timeout(400)
            assert "/api/image/chats/" not in page.eval_on_selector("#messages", "e => e.style.backgroundImage")
            bad = Path(home) / "evil.png"; bad.write_text("<svg onload=alert(1)>")
            assert http("POST", "/api/chat/background", {"X-LocalCAI": "1", "Content-Type": "image/png",
                        "X-Chat": "x.jsonl"}, b"<svg/>") in (400, 404), "fake images rejected"

            # edit the character
            page.click("#edit-char")
            page.fill("#char-fields textarea[data-key='description']", "Lives on the moon. Loves riddles.")
            page.click("#char-save")
            expect(page.locator(".toast", has_text="Character saved")).to_have_count(1)
            page.fill("#input", "riddle me")
            page.click("#send")
            page.wait_for_timeout(800)
            sent = json.load(open(last_path, encoding="utf-8"))
            assert "Loves riddles." in sent["messages"][0]["content"], "edited description used"
            card = json.loads((Path(home) / "library" / "characters" / "Luna.card.json").read_text("utf-8"))
            assert card["data"]["description"].endswith("Loves riddles.")
            # 🔍 learn style from history → personality + example dialogue written into the card
            page.click("#learn-style")   # confirm() accepted by the dialog handler
            expect(page.locator(".toast", has_text="Learned her style")).to_have_count(1, timeout=20000)
            card = json.loads((Path(home) / "library" / "characters" / "Luna.card.json").read_text("utf-8"))
            assert "Alishan" in card["data"]["personality"], "style notes saved"
            assert "Hello~" in card["data"]["mes_example"], "a creator's own example dialogue is never overwritten"

            # 📖 chat memory: generate the story so far, then it's used in the prompt
            page.click("#open-memory")
            expect(page.locator("#mem-counts")).to_contain_text("pinned in this chat")
            page.select_option("#story-scope", "0")
            page.click("#story-generate")
            expect(page.locator(".toast", has_text="story so far is ready")).to_have_count(1, timeout=20000)
            expect(page.locator("#memory-dialog")).to_be_visible()
            expect(page.locator("#story-text")).not_to_have_value("")
            page.fill("#story-text", "- Luna and Alex share tea every night.")
            page.click("#story-save")
            page.click("#memory-close")
            page.fill("#input", "tea time?")
            page.click("#send")
            page.wait_for_timeout(800)
            sent = json.load(open(last_path, encoding="utf-8"))
            assert "share tea every night" in sent["messages"][0]["content"], "story in prompt"
            n_before = page.locator(".msg").count() - 4  # keep later count checks relative

            # crisis banner (shown, never blocking)
            page.fill("#input", "honestly I want to die")
            page.click("#send")
            expect(page.locator("#crisis")).to_be_visible()
            expect(page.locator("#helplines li")).to_have_count(4)
            expect(page.locator(".msg")).to_have_count(n_before + 6)
            page.click("#crisis-close")

            # reload: the chat persisted on disk
            page.reload()
            page.click(".char-item:has-text('Luna')")
            expect(page.locator(".msg")).to_have_count(n_before + 6)

            # new chat starts with the greeting
            page.click("#new-chat")
            expect(page.locator(".msg")).to_have_count(1)
            expect(page.locator(".msg").first).to_contain_text("Oh, Alex")
            expect(page.locator("#chat-picker option")).to_have_count(2)

            # card download
            with page.expect_download() as dl:
                page.click("#download-card")
            assert dl.value.suggested_filename == "Luna.card.png"

            # XSS: character text is never rendered as HTML
            page.evaluate("document.querySelector('#messages').innerHTML = ''")
            assert page.evaluate("typeof render") == "function"
            assert "<img" not in page.evaluate("render('<img src=x onerror=alert(1)>')")

            # delete Rex (moved to trash, not destroyed)
            page.click(".char-item:has-text('Rex')")
            page.click("#delete-char")  # confirm() accepted by the handler registered above
            expect(page.locator(".char-item")).to_have_count(1)
            assert list(Path(home, "library", "trash").rglob("Rex.card.json")), "Rex should be in trash"
            assert http("POST", "/api/character/delete", {"X-LocalCAI": "1", "Content-Type": "application/json"},
                        b'{"character": "../personas/personas"}') == 400, "delete path traversal"

            if shot:
                page.click(".char-item:has-text('Luna')")
                page.select_option("#chat-picker", index=1)
                page.wait_for_timeout(400)
                page.screenshot(path=shot)
        print("UI E2E PASS")
    finally:
        for pr in procs:
            pr.terminate()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
