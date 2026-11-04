"""Drives the web UI in headless Chromium like a user would.

Run: python tests/e2e_ui/test_ui.py [screenshot.png]
Needs: pip install playwright (browsers installed).
"""
import json
import re
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
            # guided extension setup: the bundled extension is copied to a folder ready for "Load unpacked"
            page.click("#open-extractor")
            expect(page.locator("#extractor-dialog")).to_be_visible()
            page.click("#ex-browser .tab[data-b=edge]")
            expect(page.locator("#ex-url")).to_have_text("edge://extensions")
            page.click("#ex-prepare")
            expect(page.locator("#ex-path-row")).to_be_visible()
            ext = Path(home, "extractor", "chromium", "manifest.json")
            assert ext.exists() and "browser_specific_settings" not in json.loads(ext.read_text()), "chromium copy"
            assert Path(home, "extractor", "chromium", "src", "bridge.js").exists()
            page.click("#ex-browser .tab[data-b=firefox]")
            page.click("#ex-prepare")
            expect(page.locator("#ex-path")).to_contain_text("manifest.json")
            ffm = Path(home, "extractor", "firefox", "manifest.json")
            assert "browser_specific_settings" in json.loads(ffm.read_text()), "firefox keeps its add-on id"
            page.click("#ex-close")

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
            assert "Luna.background.png" in page.eval_on_selector("#bg-layer", "e => e.style.backgroundImage")
            n_before = page.locator(".msg").count()

            # first message triggers the age gate
            page.fill("#input", "What tea do I like?")
            page.keyboard.press("Enter")
            expect(page.locator("#age-dialog")).to_be_visible()
            page.click("#age-yes")
            expect(page.locator(".msg").last.locator("strong")).to_have_text("Darjeeling")  # streamed + markdown
            expect(page.locator(".msg")).to_have_count(n_before + 2)
            sent = json.load(open(last, encoding="utf-8"))
            assert sent["model"] == "fake-model"
            assert "Darjeeling" in sent["messages"][0]["content"], "pinned memory in prompt"
            assert "Scene right now" not in sent["messages"][-1]["content"], "no scene note before the first reply"
            assert sent["messages"][-1]["content"].endswith("What tea do I like?")
            assert "Moment: conversation" in sent["messages"][-1]["content"]

            # persona
            page.select_option("#persona", "Alex")
            page.wait_for_timeout(1000)  # the scene note is written in the background after a reply
            page.fill("#input", "hello again")
            page.click("#send")
            expect(page.locator(".msg")).to_have_count(n_before + 4)
            sent = json.load(open(last, encoding="utf-8"))
            assert "[About Alex]" in sent["messages"][0]["content"], "persona in prompt"
            # scene memory: the note made after the last reply rides along with the next turn
            assert "Scene right now: Where: the tea room" in sent["messages"][-1]["content"], "scene note in prompt"
            scene_req = json.load(open(last + ".scene", encoding="utf-8"))
            assert "Darjeeling" in scene_req["messages"][-1]["content"], "scene note built from the recent chat"
            assert "[Reply length]" in sent["messages"][0]["content"], "reply length guidance"
            assert "top_k" not in sent, "sampler extras only go to the built-in engine"

            # a reply cut off by the token limit is saved without the half sentence
            page.fill("#input", "please ramble")
            page.click("#send")
            expect(page.locator(".msg")).to_have_count(n_before + 6)
            expect(page.locator(".msg").last).not_to_contain_text("Then she lea", timeout=8000)
            expect(page.locator(".msg").last).to_contain_text("She nods.")
            n_before += 2  # keep the later count checks relative
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

            # ✨ change the last reply with an instruction → a new swipe written with a director's note
            n0 = page.locator(".msg").count()
            page.fill("#input", "hello again"); page.click("#send")
            expect(page.locator(".msg")).to_have_count(n0 + 2)
            page.wait_for_timeout(800)
            before = page.locator(".msg").last.locator(".swipes span").inner_text()
            page.locator(".msg").last.locator(".tool[title^='Tell the character']").click()
            page.fill("#direct-text", "She gets jealous.")
            page.click("#direct-form button[type=submit]")
            page.wait_for_timeout(1500)
            sent = json.load(open(last_path, encoding="utf-8"))
            assert "Director's note for this reply only" in sent["messages"][-1]["content"]
            assert "She gets jealous." in sent["messages"][-1]["content"] and "<<<" in sent["messages"][-1]["content"]
            after = page.locator(".msg").last.locator(".swipes span").inner_text()
            assert int(after.split("/")[1]) == int(before.split("/")[1]) + 1, (before, after)
            page.locator(".msg").last.locator(".tool[title^='Tell the character']").click()
            expect(page.locator("#direct-recent .chip-btn")).to_have_text(["She gets jealous."])
            page.click("#direct-cancel")

            # OOC guard: the reviewer flags the reply → it is rewritten, first try kept one swipe back
            n0 = page.locator(".msg").count()
            page.fill("#input", "ooc test: do you like video games?"); page.click("#send")
            expect(page.locator(".msg")).to_have_count(n0 + 2)
            expect(page.locator(".msg").last.locator(".body")).to_have_text("tilts head A video... what?", timeout=15000)
            expect(page.locator(".msg").last.locator(".fixed")).to_be_visible()
            expect(page.locator(".msg").last.locator(".swipes")).to_contain_text("2/2")
            chk = json.load(open(last_path + ".check", encoding="utf-8"))
            assert "ooc test" in chk["messages"][-1]["content"] and "Darjeeling" in chk["messages"][-1]["content"]
            sent = json.load(open(last_path, encoding="utf-8"))
            assert "never heard of video games" in sent["messages"][-1]["content"]

            # editing the chat while a reply is being written: the edit stays, the stale reply isn't saved,
            # and the message that was sent goes back into the input box
            n0 = page.locator(".msg").count()
            page.fill("#input", "slow reply please"); page.click("#send")
            page.wait_for_timeout(700)
            chat_file = next(Path(home, "library", "chats").glob("Luna.*.jsonl"))
            first_bot = next(i for i, l in enumerate(chat_file.read_text("utf-8").splitlines()[1:])
                             if not json.loads(l)["is_user"])
            r = page.evaluate("""async ([chat, i]) => (await fetch('/api/chat/edit', {method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-LocalCAI': '1'},
                body: JSON.stringify({chat, index: i, text: 'Edited while she was thinking.'})})).status""",
                [chat_file.name, first_bot])
            assert r == 200, r
            expect(page.locator(".toast", has_text="reply wasn't saved")).to_have_count(1, timeout=15000)
            expect(page.locator("#input")).to_have_value("slow reply please")
            expect(page.locator(".msg")).to_have_count(n0)
            rows = [json.loads(l) for l in chat_file.read_text("utf-8").splitlines()[1:]]
            assert rows[first_bot]["mes"] == "Edited while she was thinking.", "the edit survived"
            assert not any("slow reply please" in r["mes"] for r in rows), "the stale turn wasn't written"
            page.fill("#input", "")

            # ✨ "always do this" → saved as a rule on the character, sent with every reply after
            page.locator(".msg").last.locator(".tool[title^='Tell the character']").click()
            page.fill("#direct-text", "Never writes code.")
            page.check("#direct-keep")
            page.click("#direct-form button[type=submit]")
            expect(page.locator(".toast", has_text="Saved as a rule")).to_have_count(1)
            page.wait_for_timeout(1500)
            page.fill("#input", "hello"); page.click("#send"); page.wait_for_timeout(1500)
            sent = json.load(open(last_path, encoding="utf-8"))
            assert "- Never writes code." in sent["messages"][0]["content"], "rule in system prompt"
            assert "[Stay inside" in sent["messages"][0]["content"], "world boundary rule"
            page.click("#edit-char")
            expect(page.locator("#char-rules")).to_have_value("Never writes code.")
            page.click("#char-cancel")

            # custom backgrounds: this chat, then every chat with the character, hide the C.ai one
            bg = Path(home) / "bg.png"
            bg.write_bytes(Path(ROOT / "localcai" / "extension" / "icons" / "icon48.png").read_bytes())
            layer = lambda: page.eval_on_selector("#bg-layer", "e => e.style.backgroundImage")
            page.click("#open-bg")
            expect(page.locator("#bg-source")).to_have_text("From Character.AI")
            page.set_input_files("#bg-input", str(bg))
            expect(page.locator(".toast", has_text="Background set for this chat")).to_have_count(1)
            assert "/api/image/chats/" in layer()
            expect(page.locator("#bg-source")).to_have_text("This chat's picture")
            page.fill("#bg-dim", "70"); page.dispatch_event("#bg-dim", "change")
            page.wait_for_timeout(300)
            assert page.eval_on_selector("#bg-layer", "e => e.style.getPropertyValue('--bg-dim')") == "0.7"
            page.click("#bg-remove")
            expect(page.locator("#bg-source")).to_have_text("From Character.AI")
            page.select_option("#bg-scope", "character")
            page.set_input_files("#bg-input", str(bg))
            expect(page.locator(".toast", has_text="every chat with this character")).to_have_count(1)
            assert "custom-bg" in layer()
            page.click("#bg-remove")                       # remove the character picture
            expect(page.locator("#bg-source")).to_have_text("From Character.AI")
            page.click("#bg-remove")                       # "Hide" the C.ai one for this chat
            expect(page.locator("#bg-source")).to_contain_text("Hidden")
            assert layer() == ""
            page.click("#bg-remove")                       # "Show" again
            assert "Luna.background.png" in layer()
            page.click("#bg-close")
            page.reload(); page.click(".char-item:has-text('Luna')")
            page.wait_for_timeout(500)
            assert page.eval_on_selector("#bg-layer", "e => e.style.getPropertyValue('--bg-dim')") == "0.7", "style saved"
            bad = Path(home) / "evil.png"; bad.write_text("<svg onload=alert(1)>")
            assert http("POST", "/api/chat/background", {"X-LocalCAI": "1", "Content-Type": "image/png",
                        "X-Chat": "x.jsonl"}, b"<svg/>") in (400, 404), "fake images rejected"

            # edit the character
            page.click("#edit-char")
            page.fill("#char-fields textarea[data-key='description']", "Lives on the moon. Loves riddles.")
            page.select_option("#char-pronouns", "she/her")
            expect(page.locator("#char-reply-length")).to_have_value("auto")
            page.select_option("#char-reply-length", "short")   # reply length belongs to the character
            # meanwhile something else (e.g. Learn style finishing) changes the card: saving must not undo it
            cp = Path(home) / "library" / "characters" / "Luna.card.json"
            cj = json.loads(cp.read_text("utf-8")); cj["data"]["scenario"] = "Written meanwhile."
            cp.write_text(json.dumps(cj), "utf-8")
            page.click("#char-save")
            expect(page.locator(".toast", has_text="Character saved")).to_have_count(1)
            expect(page.locator("#head-sub")).to_contain_text("she/her")
            page.fill("#input", "riddle me")
            page.click("#send")
            page.wait_for_timeout(800)
            sent = json.load(open(last_path, encoding="utf-8"))
            assert "Loves riddles." in sent["messages"][0]["content"], "edited description used"
            assert "about 60 words or fewer" in sent["messages"][0]["content"], "the character's own reply length"
            assert page.locator("#set-reply-length").count() == 0, "no longer a global setting"
            card = json.loads((Path(home) / "library" / "characters" / "Luna.card.json").read_text("utf-8"))
            assert card["data"]["description"].endswith("Loves riddles.")
            assert card["data"]["scenario"] == "Written meanwhile.", "Edit only saves the fields changed in it"
            # 🔍 learn style from history → personality + example dialogue written into the card
            page.click("#learn-style")                                    # the Style window, any time
            expect(page.locator("#style-dialog")).to_be_visible()
            page.click("#style-learn")   # confirm() accepted by the dialog handler
            expect(page.locator(".toast", has_text="Learned Luna's style")).to_have_count(1, timeout=20000)
            expect(page.locator("#style-dialog")).to_be_visible()          # opens again with what was learned
            expect(page.locator("#style-just")).to_be_visible()
            expect(page.locator("#style-notes")).to_have_value(re.compile("Darjeeling"))
            if os.environ.get("LCAI_SHOT_STYLE"):
                page.locator("#style-dialog").screenshot(path=os.environ["LCAI_SHOT_STYLE"])
            page.click("#style-close")
            card = json.loads((Path(home) / "library" / "characters" / "Luna.card.json").read_text("utf-8"))
            assert "Darjeeling" in card["data"]["personality"], "style notes saved"
            assert "Hello~" in card["data"]["mes_example"], "a creator's own example dialogue is never overwritten"
            # …and stays editable later from the same button
            page.click("#learn-style")
            expect(page.locator("#style-just")).to_be_hidden()
            page.fill("#style-notes", "- Speaks softly, ends lines with ~")
            page.click("#style-save")
            expect(page.locator(".toast", has_text="Style saved")).to_have_count(1)
            card = json.loads((Path(home) / "library" / "characters" / "Luna.card.json").read_text("utf-8"))
            assert "Speaks softly" in card["data"]["personality"] and "Hello~" in card["data"]["mes_example"]
            page.fill("#input", "style?"); page.click("#send"); page.wait_for_timeout(800)
            sent = json.load(open(last_path, encoding="utf-8"))
            assert "Speaks softly, ends lines with ~" in sent["messages"][0]["content"], "edited style used"

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
            # memory facts, like C.ai's Memory page: imported ones, then add / edit / delete
            # one tab per person: the character first, you second; facts about you aren't under the character
            expect(page.locator("#fact-tabs .tab").first).to_have_text("Luna · 1")
            expect(page.locator("#fact-tabs .tab.active")).to_contain_text("Luna")
            expect(page.locator("#facts-list .fact", has_text="Earl Grey tea")).to_contain_text("C.ai")
            expect(page.locator("#facts-list .fact", has_text="Lisbon")).to_have_count(0)
            expect(page.locator("#mem-used")).to_contain_text("% left")
            expect(page.locator("#fact-about")).to_be_hidden()
            page.locator("#fact-tabs .tab", has_text="Alex (you)").click()
            expect(page.locator("#facts-list .fact", has_text="Earl Grey tea")).to_have_count(0)
            page.fill("#fact-category", "pets")
            page.fill("#fact-value", "a cat named Pip")
            page.click("#fact-add")
            pip = page.locator("#facts-list .fact", has_text="a cat named Pip")
            expect(pip).to_have_count(1)
            fid = page.locator("#facts-list .fact", has_text="Lisbon").get_attribute("data-id")
            lisbon = page.locator(f'#facts-list .fact[data-id="{fid}"]')
            lisbon.locator(".f-edit").click()
            lisbon.locator(".f-val").fill("Porto")
            lisbon.locator(".f-val").press("Enter")
            expect(page.locator("#facts-list .fact", has_text="Porto")).to_contain_text("edited")
            # someone else: a new tab of their own
            page.locator("#fact-tabs .tab", has_text="Someone else").click()
            expect(page.locator("#fact-about")).to_be_visible()
            page.fill("#fact-about", "Biscuit")
            page.fill("#fact-category", "species")
            page.fill("#fact-value", "a grey cat")
            page.click("#fact-add")
            expect(page.locator("#fact-tabs .tab.active")).to_have_text("Biscuit · 1")
            expect(page.locator("#facts-list .fact", has_text="a grey cat")).to_have_count(1)
            if os.environ.get("LCAI_SHOT"):
                page.locator("#fact-tabs .tab", has_text="Alex (you)").click()
                page.locator("#memory-dialog").screenshot(path=os.environ["LCAI_SHOT"])
            page.locator("#fact-tabs .tab", has_text="Luna").click()
            page.locator("#facts-list .fact", has_text="Earl Grey tea").locator(".f-del").click()
            expect(page.locator("#facts-list .fact", has_text="Earl Grey tea")).to_have_count(0)
            page.click("#memory-close")
            page.fill("#input", "tea time?")
            page.click("#send")
            page.wait_for_timeout(800)
            sent = json.load(open(last_path, encoding="utf-8"))
            assert "share tea every night" in sent["messages"][0]["content"], "story in prompt"
            alex = next((l for l in sent["messages"][0]["content"].splitlines() if l.startswith("- Alex: ") and "hometown" in l), "")
            assert "hometown: Porto" in alex and "pets: a cat named Pip" in alex, ("facts in prompt", alex)
            assert "Earl Grey" not in sent["messages"][0]["content"], "a deleted fact isn't sent"
            assert "- Biscuit: species: a grey cat" in sent["messages"][0]["content"]
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
            # 🗑 Trash: see what was deleted, restore it
            page.click("#open-trash")
            item = page.locator(".trash-item", has_text="Character: Rex")
            expect(item).to_have_count(1)
            if os.environ.get("LCAI_SHOT_TRASH"):
                page.screenshot(path=os.environ["LCAI_SHOT_TRASH"])
            item.locator(".t-restore").click()
            expect(page.locator(".char-item", has_text="Rex")).to_have_count(1)
            expect(page.locator(".trash-item", has_text="Character: Rex")).to_have_count(0)
            page.click("#trash-close")
            page.click(".char-item:has-text('Rex')")
            page.click("#delete-char")
            expect(page.locator(".char-item")).to_have_count(1)
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
