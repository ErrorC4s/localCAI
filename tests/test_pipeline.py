import json
import sys
from pathlib import Path

import pytest

from localcai.cli import main
from localcai.exporters import to_card_v2, write_card
from localcai.importers import import_path
from localcai.importers.sillytavern import card_from_png
from localcai.memory import pins_to_lorebook
from localcai.runtime import build_messages
from localcai.safety import looks_like_crisis

FX = Path(__file__).parent / "fixtures"


def test_cai_dump_character_and_chat():
    b = import_path(FX / "cai_dump.json")
    assert [c.name for c in b.characters] == ["Luna"]
    luna = b.characters[0]
    assert luna.tagline == "A sleepy moon witch"
    assert "<START>" in luna.example_dialogue and "END_OF_DIALOG" not in luna.example_dialogue
    assert luna.creator == "alex"

    assert len(b.chats) == 1
    chat = b.chats[0]
    # newest-first input must come out oldest-first
    assert chat.messages[0].text.startswith("*yawns*")
    # primary candidate chosen, other kept as a swipe
    assert chat.messages[-1].text == "Earl Grey, obviously."
    assert chat.messages[-1].alternatives == ["Fine, chamomile."]
    assert chat.messages[1].is_user and chat.messages[1].pinned
    assert chat.user_name == "Alex"


def test_pins_become_constant_lore():
    b = import_path(FX / "cai_dump.json")
    book = pins_to_lorebook(b.chats, "Luna")
    assert len(book["entries"]) == 1
    e = book["entries"][0]
    assert e["constant"] and "Darjeeling" in e["content"]


def test_card_png_roundtrip(tmp_path):
    b = import_path(FX / "cai_dump.json")
    book = pins_to_lorebook(b.chats, "Luna")
    _, png = write_card(b.characters[0], tmp_path, book)
    card = card_from_png(png)
    assert card["spec"] == "chara_card_v2"
    assert card["data"]["name"] == "Luna"
    assert card["data"]["character_book"]["entries"][0]["constant"]
    # and our importer reads our own output back
    again = import_path(png)
    assert again.characters[0].greeting == b.characters[0].greeting


def test_tavern_jsonl():
    b = import_path(FX / "tavern_chat.jsonl")
    chat = b.chats[0]
    assert chat.character_name == "Kai" and chat.user_name == "Alex"
    assert len(chat.pins) == 1
    assert chat.messages[2].alternatives == ["Nice."]


def test_prompt_includes_pins_and_fills_macros():
    b = import_path(FX / "cai_dump.json")
    card = to_card_v2(b.characters[0], pins_to_lorebook(b.chats, "Luna"))
    msgs = build_messages(card, [{"role": "user", "content": "hi"}], user_name="Alex", pacing=False)
    system = msgs[0]["content"]
    assert "Darjeeling" in system
    assert "{{user}}" not in system and "Alex" in system
    assert msgs[-1] == {"role": "user", "content": "hi"}


def test_history_budget_keeps_most_recent():
    card = {"data": {"name": "X"}}
    hist = [{"role": ("user", "assistant")[i % 2], "content": "a" * 1000} for i in range(50)] + [{"role": "user", "content": "last"}]
    msgs = build_messages(card, hist, max_chars=5000, pacing=False)
    assert msgs[-1]["content"] == "last" and len(msgs) < 10


def test_crisis_detection():
    assert looks_like_crisis("我最近真的不想活了")
    assert looks_like_crisis("I want to die")
    assert not looks_like_crisis("this boss fight is killing me lol")


def test_cli_import_end_to_end(tmp_path, capsys):
    rc = main(["import", str(FX), "-o", str(tmp_path)])
    assert rc == 0
    cards = sorted(p.name for p in (tmp_path / "characters").glob("*.card.json"))
    assert cards == ["Kai.card.json", "Luna.card.json", "Rex.card.json"]  # Kai reconstructed from chat
    kai = json.loads((tmp_path / "characters" / "Kai.card.json").read_text("utf-8"))
    assert kai["data"]["first_mes"] == "Yo. Back from the gym?"
    assert len(list((tmp_path / "chats").glob("*.jsonl"))) == 3


def test_lcai_from_extension_is_exact():
    # produced by tests/e2e_extension/e2e.mjs against a mocked character.ai
    b = import_path(FX / "extension_export.lcai.json")
    names = sorted(c.name for c in b.characters)
    assert names == ["Luna", "Rex"]
    rex = next(c for c in b.characters if c.name == "Rex")
    assert rex.example_dialogue == ""  # other creator's private definition never leaks
    assert any("Rex" in w and "private" in w for w in b.warnings)
    chat = b.chats[0]
    assert [m.text for m in chat.messages][-2:] == ["Earl Grey, obviously.", "Sweet dreams~"]
    assert chat.messages[2].alternatives == ["Fine, chamomile."]
    assert len(chat.pins) == 1 and chat.pins[0].is_user
    book = pins_to_lorebook(b.chats, "Luna")
    assert "Darjeeling" in book["entries"][0]["content"]


def test_lcai_memories_and_personas():
    b = import_path(FX / "extension_export.lcai.json")
    assert [p["name"] for p in b.personas] == ["Alex"]
    chat = b.chats[0]
    assert {m["value"] for m in chat.memories} == {"Earl Grey tea", "Lisbon"}
    book = pins_to_lorebook(b.chats, "Luna")
    contents = [e["content"] for e in book["entries"]]
    assert len(contents) == 3 and any("Lisbon" in c for c in contents)


def test_persona_goes_into_prompt():
    card = {"data": {"name": "Luna", "description": "Moon witch"}}
    msgs = build_messages(card, [{"role": "user", "content": "hi"}], user_name="Sam",
                          persona="A tired night-shift baker who loves tea.")
    assert "[About Sam]" in msgs[0]["content"] and "night-shift baker" in msgs[0]["content"]


def test_images_land_in_library(tmp_path):
    import struct
    from localcai.library import import_into, list_library
    rep = import_into(FX / "extension_export.lcai.json", tmp_path)
    luna = next(c for c in rep.characters if c["name"] == "Luna")
    assert luna["avatar"] and luna["background"]
    png = (tmp_path / "characters" / "Luna.card.png").read_bytes()
    assert struct.unpack(">II", png[16:24]) == (8, 6)          # real avatar, not the placeholder
    assert card_from_png(tmp_path / "characters" / "Luna.card.png")["data"]["name"] == "Luna"
    lib = list_library(tmp_path)
    l = next(c for c in lib["characters"] if c["name"] == "Luna")
    assert l["has_avatar"] and l["background"].split("?")[0] == "Luna.background.png"
    rex = next(c for c in lib["characters"] if c["name"] == "Rex")
    assert not rex["has_avatar"]                               # failed download → placeholder
    assert lib["personas"][0]["avatar"] == "Alex.avatar.png"
    assert (tmp_path / "personas" / "Alex.avatar.png").exists()
    assert any("Rex avatar" in w for w in rep.warnings)


def test_bad_images_are_rejected():
    import base64
    from localcai.images import decode_data_url, png_or_none
    b64 = lambda b: base64.b64encode(b).decode()
    assert decode_data_url("data:image/svg+xml;base64," + b64(b"<svg onload=alert(1)>")) is None
    assert decode_data_url("data:image/png;base64," + b64(b"<html>not a png</html>")) is None
    assert decode_data_url("data:text/html;base64," + b64(b"x")) is None
    assert decode_data_url("data:image/png;base64,!!!notbase64") is None
    assert decode_data_url(12345) is None
    jpeg = decode_data_url("data:image/jpeg;base64," + b64(b"\xff\xd8\xff\xe0rest"))
    assert jpeg == ("image/jpeg", b"\xff\xd8\xff\xe0rest")
    assert png_or_none("data:image/jpeg;base64," + b64(b"\xff\xd8\xff\xe0rest")) is None


def test_strip_thinking_handles_split_tags():
    from localcai.runtime.client import strip_thinking
    toks = ["<thi", "nk>secret plan", "</th", "ink>\nHello ", "<think>x</think>", "world"]
    assert "".join(strip_thinking(iter(toks))) == "Hello world"
    assert "".join(strip_thinking(iter(["a < b", " and c > d"]))) == "a < b and c > d"


def test_engine_picks_the_right_build():
    from localcai.engine import pick_asset
    names = ["llama-b9000-bin-win-cpu-x64.zip", "llama-b9000-bin-win-vulkan-x64.zip", "llama-b9000-bin-win-cuda-12.4-x64.zip",
             "cudart-llama-bin-win-cuda-12.4-x64.zip", "llama-b9000-bin-macos-arm64.tar.gz",
             "llama-b9000-bin-ubuntu-x64.tar.gz", "llama-b9000-bin-ubuntu-vulkan-x64.tar.gz", "llama-b9000-xcframework.zip"]
    assets = [{"name": n} for n in names]
    pick = lambda *a: (pick_asset(assets, *a, nvidia=False) or {}).get("name")
    assert pick("win", "x64", "auto") == "llama-b9000-bin-win-vulkan-x64.zip"
    assert pick("win", "x64", "cpu") == "llama-b9000-bin-win-cpu-x64.zip"
    assert pick("macos", "arm64", "auto") == "llama-b9000-bin-macos-arm64.tar.gz"
    assert pick("ubuntu", "x64", "auto") == "llama-b9000-bin-ubuntu-vulkan-x64.tar.gz"
    assert pick("ubuntu", "x64", "cpu") == "llama-b9000-bin-ubuntu-x64.tar.gz"
    assert pick("win", "arm64", "auto") is None  # no arm64 builds in this list


def test_reimport_merges_instead_of_duplicating(tmp_path):
    import copy
    from localcai import chatlog
    from localcai.library import import_into
    full = json.loads((FX / "extension_export.lcai.json").read_text("utf-8"))
    # 1st export: only the 2 newest turns (user didn't scroll up)
    partial = copy.deepcopy(full)
    partial["chats"][0]["turns"] = partial["chats"][0]["turns"][-2:]
    (tmp_path / "a.lcai.json").write_text(json.dumps(partial), "utf-8")
    import_into(tmp_path / "a.lcai.json", tmp_path / "lib")
    files = list((tmp_path / "lib" / "chats").glob("Luna.*.jsonl"))
    assert len(files) == 1
    # user keeps chatting locally
    meta, rows = chatlog.load(files[0])
    rows.append(chatlog.row("Alex", True, "local message"))
    chatlog.save(files[0], meta, rows)
    # 2nd export: the full history
    (tmp_path / "b.lcai.json").write_text(json.dumps(full), "utf-8")
    import_into(tmp_path / "b.lcai.json", tmp_path / "lib")
    files = list((tmp_path / "lib" / "chats").glob("Luna.*.jsonl"))
    assert len(files) == 1, "same C.ai chat must stay one file"
    _, rows = chatlog.load(files[0])
    assert [r["mes"] for r in rows][:2] == ["*yawns* Oh, Alex...", "Remember: I love Darjeeling oolong."]
    assert len(rows) == 5 and rows[-1]["mes"] == "local message"  # 4 imported + 1 local, nothing lost
    # importing the partial one again must not drop the older history
    import_into(tmp_path / "a.lcai.json", tmp_path / "lib")
    _, rows = chatlog.load(files[0])
    assert len(rows) == 5


def _long_chat(n=300):
    rows = []
    for i in range(n):
        rows.append({"name": "Alex", "is_user": True, "mes": f"line {i}: how was the lighthouse?" if i == 20 else f"user line {i}"})
        rows.append({"name": "Mira", "is_user": False,
                     "mes": f'*She tilts her head, giggling softly.* "He-he... answer {i}, hubby~" *She leans closer.*' * 3})
    return rows


def test_pick_examples_spreads_across_history():
    from localcai.analyze import pick_examples
    ex = pick_examples(_long_chat(), "Alex", "Mira", k=4)
    assert ex.count("<START>") == 4 and "{{user}}:" in ex and "{{char}}:" in ex
    assert "Alex" not in ex  # user's name replaced by the macro


def test_story_summary_map_reduce_and_stop():
    from localcai.analyze import story_summary
    calls = []
    def ask(p):
        calls.append(p)
        return "- something happened"
    out = story_summary(_long_chat(400), "Mira", "Alex", ask)
    assert out == "- something happened"
    maps = [c for c in calls if c.startswith("Part ")]
    reduces = [c for c in calls if c.startswith("These are notes")]
    assert len(maps) > 5 and len(reduces) >= 1
    calls.clear()
    story_summary(_long_chat(400), "Mira", "Alex", ask, stopped=lambda: len(calls) >= 2)
    assert len([c for c in calls if c.startswith("Part ")]) == 2  # stops early, keeps what it read


def test_style_notes_uses_character_replies_only():
    from localcai.analyze import style_notes
    seen = {}
    style_notes(_long_chat(), "Mira", "Alex", lambda p: seen.setdefault("p", p) and "- giggles 'he-he'")
    assert "He-he" in seen["p"] and "user line" not in seen["p"]


def test_prompt_has_story_and_recall_sections():
    card = {"data": {"name": "Mira"}}
    msgs = build_messages(card, [{"role": "user", "content": "hi"}], "Alex",
                          story="- They met at the lighthouse.", recalled=["Alex: remember Misty the cat"])
    sys = msgs[0]["content"]
    assert "[The story so far between Mira and Alex]" in sys and "lighthouse" in sys
    assert "Misty" not in sys, "recall changes every turn, so it must not be in the cached system prompt"
    assert "[Earlier moments that may be relevant now]" in msgs[-1]["content"] and "Misty" in msgs[-1]["content"]


@pytest.mark.skipif(sys.platform == "win32", reason="starts a shell script as a stand-in engine")
def test_orphan_engine_is_stopped_but_other_programs_are_not(tmp_path, monkeypatch):
    import subprocess, sys, time, os
    monkeypatch.setenv("LOCALCAI_HOME", str(tmp_path))
    from localcai import engine
    (tmp_path / "engine").mkdir()
    fake = tmp_path / "llama-server"
    fake.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(60)\n")
    fake.chmod(0o755)
    orphan = subprocess.Popen([str(fake)])
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        time.sleep(0.3)
        (tmp_path / "engine" / "engine.pid").write_text(str(other.pid))
        engine.kill_orphan()
        assert other.poll() is None, "never kill a process that isn't llama-server"
        (tmp_path / "engine" / "engine.pid").write_text(str(orphan.pid))
        engine.kill_orphan()
        orphan.wait(5)
        assert orphan.poll() is not None and not (tmp_path / "engine" / "engine.pid").exists()
    finally:
        for pr in (orphan, other):
            pr.kill()


def test_pick_dedicated_gpu():
    from localcai.engine import parse_devices, pick_device
    laptop = parse_devices("Available devices:\n  Vulkan0: Intel(R) Arc(TM) Graphics (18432 MiB, 17000 MiB free)\n"
                           "  Vulkan1: NVIDIA GeForce RTX 4060 Laptop GPU (8151 MiB, 7600 MiB free)\n")
    assert pick_device(laptop)["id"] == "Vulkan1"
    amd = parse_devices("  Vulkan0: AMD Radeon(TM) Graphics (8192 MiB, 8000 MiB free)\n  Vulkan1: AMD Radeon RX 7800 XT (16368 MiB, 1 MiB free)")
    assert pick_device(amd)["id"] == "Vulkan1"
    assert pick_device([]) is None


def test_stream_errors_are_raised(monkeypatch):
    import io
    from localcai.runtime import client
    body = b'data: {"error": {"message": "Context size has been exceeded."}}\n\n'
    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): pass
    monkeypatch.setattr(client.urllib.request, "urlopen", lambda *a, **k: R(body))
    import pytest
    with pytest.raises(OSError, match="Context size"):
        list(client.stream_chat("http://x/v1", "m", [{"role": "user", "content": "hi"}]))


def test_prompt_prefix_stays_stable_across_turns():
    card = {"data": {"name": "Mira", "description": "Moon witch"}}
    hist = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"message number {i} " * 20} for i in range(300)]
    prefixes = set()
    for turn in range(10):  # 10 more turns, each adding a user + assistant message
        h = hist + [{"role": "user" if i % 2 == 0 else "assistant", "content": f"new {i} " * 20} for i in range(turn * 2)]
        msgs = build_messages(card, h, "Alex", max_chars=12000, recalled=[f"something {turn}"])
        prefixes.add((msgs[0]["content"], msgs[1]["content"]))
        assert sum(len(m["content"]) for m in msgs) <= 12000 + 400
    assert len(prefixes) <= 2, "the start of the prompt should only move when a whole block is dropped"


def test_cuda_build_on_nvidia():
    from localcai.engine import pick_asset, companion_assets
    names = ["llama-b12032-bin-win-cpu-x64.zip", "llama-b12032-bin-win-vulkan-x64.zip",
             "llama-b12032-bin-win-cuda-12.4-x64.zip", "llama-b12032-bin-win-cuda-13.4-x64.zip",
             "llama-b12032-bin-win-cuda-13.4-arm64.zip", "cudart-llama-bin-win-cuda-12.4-x64.zip",
             "cudart-llama-bin-win-cuda-13.4-x64.zip", "cudart-llama-bin-win-cuda-13.4-arm64.zip"]
    assets = [{"name": n} for n in names]
    main = pick_asset(assets, "win", "x64", "auto", nvidia=True)
    assert main["name"] == "llama-b12032-bin-win-cuda-13.4-x64.zip"   # newest CUDA (RTX 50 needs 12.8+)
    assert [a["name"] for a in companion_assets(assets, main)] == ["cudart-llama-bin-win-cuda-13.4-x64.zip"]
    assert pick_asset(assets, "win", "x64", "auto", nvidia=False)["name"].endswith("vulkan-x64.zip")
    assert pick_asset(assets, "win", "x64", "vulkan", nvidia=True)["name"].endswith("vulkan-x64.zip")
    assert companion_assets(assets, {"name": "llama-b1-bin-win-vulkan-x64.zip"}) == []


def test_trim_to_sentence():
    from localcai.runtime.client import trim_to_sentence
    assert trim_to_sentence('*She smiles.* "Hello there." *(My eyes close. A') == '*She smiles.* "Hello there." *(My eyes close.)*'
    assert trim_to_sentence("我好想你。你呢？我們去") == "我好想你。你呢？"
    assert trim_to_sentence("no punctuation at all") == "no punctuation at all"
    assert trim_to_sentence('*She leans in. "Stay') == '*She leans in.*'


def test_reply_length_auto_and_stable():
    from localcai.runtime.prompt import build_messages, reply_words_for
    hist = [{"role": "assistant", "content": " ".join(["word"] * 50)}, {"role": "user", "content": "hi"}] * 10
    n = reply_words_for("auto", hist)
    assert 40 <= n <= 90
    assert reply_words_for("short", hist) == 60 and reply_words_for("off", hist) == 0
    # one more long reply barely moves the median → same bucket → same cached system prompt
    assert reply_words_for("auto", hist + [{"role": "assistant", "content": "x " * 400}]) == n
    card = {"data": {"name": "Mira"}}
    sys_text = build_messages(card, hist, "Sam", reply_words=n)[0]["content"]
    assert f"about {n} words" in sys_text


def test_pacing_guide_in_stable_system_prompt():
    from localcai.runtime.prompt import build_messages
    card = {"data": {"name": "Mira", "description": "moon witch"}}
    hist = [{"role": "assistant", "content": "*waves* \"Hi.\""}, {"role": "user", "content": "hello"}]
    on = build_messages(card, hist, "Sam")
    off = build_messages(card, hist, "Sam", pacing=False)
    assert "*asterisks*" in on[0]["content"] and "Never write Sam's" in on[0]["content"]
    assert "*asterisks*" not in off[0]["content"]
    hist2 = hist + [{"role": "assistant", "content": "ok"}, {"role": "user", "content": "more"}]
    assert build_messages(card, hist2, "Sam")[0] == on[0]  # system prompt stays cacheable


def test_newer_version_asks_older_to_quit(tmp_path, monkeypatch):
    import threading
    from localcai import desktop
    from localcai.webui.server import create_server
    monkeypatch.setenv("LOCALCAI_HOME", str(tmp_path))
    port = desktop._free_port()
    httpd = create_server(port, tmp_path / "lib")
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    assert desktop._running_version(port)
    assert desktop._ask_to_quit(port, wait=5)
    assert desktop._running_version(port) is None
    httpd.server_close()


def test_moment_hint_picks_pacing():
    from localcai.runtime.prompt import moment_hint, build_messages
    assert "intimate" in moment_hint("*I smiled and cuddle you tightly on the bed* I love you")
    assert "intimate" in moment_hint("*我抱緊妳* 晚安")
    assert "fast" in moment_hint("*dodges the attack*")
    assert "conversation" in moment_hint("what did you eat today?")
    assert "intimate" not in moment_hint("I really like playing this")
    card = {"data": {"name": "Mira"}}
    msgs = build_messages(card, [{"role": "user", "content": "*kisses your forehead*"}], "Sam")
    assert "Moment: quiet and intimate" in msgs[-1]["content"]
    assert "Moment:" not in build_messages(card, [{"role": "user", "content": "*kisses*"}], "Sam",
                                           pacing=False)[-1]["content"]


def test_big_model_lets_llama_cpp_fit_layers(tmp_path, monkeypatch):
    import localcai.engine as eng
    monkeypatch.setenv("LOCALCAI_HOME", str(tmp_path))
    model = eng.models_dir() / "big-12b-Q4_K_M.gguf"
    with open(model, "wb") as f:
        f.truncate(int(7.5 * 2**30))  # sparse 7.5 GB file
    server = tmp_path / "llama-server"; server.write_text("")
    e = eng.Engine()
    monkeypatch.setattr(e, "installed", lambda: {"server": str(server)})
    monkeypatch.setattr(e, "devices", lambda s=None: [{"id": "CUDA0", "name": "RTX 4060", "mib": 8123}])
    e._devices = (str(server), [{"id": "CUDA0", "name": "RTX 4060", "mib": 8123}])
    seen = {}

    def fake_popen(cmd, **kw):
        seen["cmd"] = cmd
        raise OSError("stop here")
    monkeypatch.setattr(eng.subprocess, "Popen", fake_popen)
    eng.engine_dir().mkdir(parents=True, exist_ok=True)
    try:
        e.start(model.name, timeout=1)
    except Exception as ex:
        seen.setdefault("err", repr(ex))
    assert "cmd" in seen, seen
    assert "--device" in seen["cmd"] and "-ngl" not in seen["cmd"], seen["cmd"]
    log = (eng.engine_dir() / "engine.log").read_text()
    assert "letting llama.cpp fit" in log
    assert set(eng.STARTER_MODELS) >= {"qwen3-4b-instruct", "stheno-8b", "mag-mell-12b", "rocinante-12b"}


def test_strip_name_prefix_while_streaming():
    from localcai.runtime.client import other_speakers, strip_name_prefix
    def run(text, char="Mira Vale", step=3):
        info = {}
        out = "".join(strip_name_prefix(iter([text[i:i + step] for i in range(0, len(text), step)]), char, info))
        return out, info.get("name_prefix", "")
    assert run("Mira Vale: *giggles* Hi.")[0] == "*giggles* Hi."
    assert run("**Mira Vale:** Hi.")[0] == "Hi."
    assert run("*Mira Vale:* hi")[0] == "hi"
    assert run("Mira Vale：嗨")[0] == "嗨"
    assert run("Hexagons are neat: yes")[0] == "Hexagons are neat: yes"
    assert run("*hex maniac: smiles*")[0] == "*hex maniac: smiles*"
    assert run("Hi")[0] == "Hi"
    # group scene: only the first label is removed while streaming, and it is reported
    out, pre = run("Bram: Hm.\nTess: Jo, where are we?\nBram: Hold on.", "Bram the Smith")
    assert out == "Hm.\nTess: Jo, where are we?\nBram: Hold on." and pre.startswith("Bram:")
    assert other_speakers(out, "Bram the Smith") == {"Tess"}
    assert other_speakers("Mmm... not now.\n\n*smiles* fine", "Mira Vale") == set()



def test_perspective_and_pronouns():
    from localcai.runtime.prompt import build_messages, guess_pronouns
    assert guess_pronouns("{{char}} is a moon witch. She loves her husband.") == "she/her"
    assert guess_pronouns("He is a tall knight. His armor is old.") == "he/him"
    assert guess_pronouns("A ghost.") == ""
    card = {"data": {"name": "Mira Vale", "description": "She is a moon witch. Her eyes glow silver."}}
    msgs = build_messages(card, [{"role": "user", "content": "*I guide your palm to my chest*"}], "Sam",
                          persona="Sam is a man. He wears a red scarf.")
    assert "You play Mira Vale (she/her). You are talking with Sam (he/him)." in msgs[0]["content"]
    assert 'Perspective: in the message below, "I/my" is Sam (he/him)' in msgs[-1]["content"]
    assert msgs[-1]["content"].endswith("*I guide your palm to my chest*")

    msgs2 = build_messages(card, [{"role": "user", "content": "*I smile*"}], "Sam", user_pronouns="he/him")
    assert "talking with Sam (he/him)" in msgs2[0]["content"]


def test_character_pronouns_setting_and_guess():
    from localcai.runtime.prompt import build_messages, character_pronouns
    assert character_pronouns({"first_mes": "*She tilts her head and smiles.*"}) == "she/her"
    group = {"description": "Bram, Tess and Jo. He is old. She is loud. He is quiet. She bites.", }
    assert character_pronouns(group) == ""  # mixed cast: don't guess
    d = {"description": "A ghost.", "extensions": {"localcai": {"pronouns": "he/him"}}}
    assert character_pronouns(d) == "he/him"
    d2 = {"name": "Bram", "description": "She she she", "extensions": {"localcai": {"pronouns": "group"}}}
    assert character_pronouns(d2) == ""
    msgs = build_messages({"data": d2}, [{"role": "user", "content": "hi"}], "Sam")
    assert "You play Bram. You are talking with Sam." in msgs[0]["content"]



def test_estimate_fit_on_an_8gb_laptop_gpu():
    from localcai.engine import STARTER_MODELS, estimate_fit
    f = lambda k: estimate_fit(STARTER_MODELS[k]["size_gb"], 8192, 8123, STARTER_MODELS[k]["kv_mb"])
    assert f("qwen3-4b-instruct")["kind"] == "gpu"
    assert f("stheno-8b")["kind"] == "gpu"
    big = f("mag-mell-12b")
    assert big["kind"] == "partial" and 0.5 <= big["gpu_share"] < 1, big
    assert estimate_fit(4.9, 8192, None)["kind"] == "cpu"
    assert "8+" not in STARTER_MODELS["mag-mell-12b"]["label"]



def test_roles_alternate_for_strict_templates():
    from localcai.runtime.prompt import alternate, build_messages
    msgs = build_messages({"data": {"name": "Mira"}}, [
        {"role": "assistant", "content": "He he ke~ hello"},       # greeting first
        {"role": "user", "content": "hi"}, {"role": "user", "content": "again"},
        {"role": "assistant", "content": "yes?"}, {"role": "user", "content": "*hugs*"}], "Sam", pacing=False)
    roles = [m["role"] for m in msgs]
    assert roles == ["system", "user", "assistant", "user", "assistant", "user"], roles
    assert msgs[3]["content"] == "hi\n\nagain"
    assert alternate([]) == []


def test_gguf_metadata_reads_chat_template(tmp_path):
    import struct
    from localcai.engine import gguf_metadata
    def s(b): return struct.pack("<Q", len(b)) + b
    kv = [(b"general.architecture", 8, s(b"llama")),
          (b"tokenizer.ggml.tokens", 9, struct.pack("<IQ", 8, 3) + s(b"a") + s(b"bb") + s(b"ccc")),
          (b"tokenizer.ggml.scores", 9, struct.pack("<IQ", 6, 3) + b"\0" * 12),
          (b"llama.context_length", 4, struct.pack("<I", 8192))]
    def write(path, extra):
        items = kv + extra
        body = b"GGUF" + struct.pack("<IQQ", 3, 0, len(items))
        for k, t, v in items:
            body += s(k) + struct.pack("<I", t) + v
        path.write_bytes(body)
    a, b = tmp_path / "with.gguf", tmp_path / "without.gguf"
    write(a, [(b"tokenizer.chat_template", 8, s(b"{{ messages }}"))])
    write(b, [])
    assert gguf_metadata(a)["tokenizer.chat_template"] == "{{ messages }}"
    assert "tokenizer.chat_template" not in gguf_metadata(b)
    assert gguf_metadata(b)["general.architecture"] == "llama"



def test_markers_and_user_pronouns_from_chat():
    from localcai.runtime.client import strip_markers
    from localcai.runtime.prompt import build_messages, guess_user_pronouns
    assert strip_markers("*smiles* hubby?♡<|im_end|>") == "*smiles* hubby?♡"
    assert strip_markers("ok</s>\n<|im_start|>user\nhi") == "ok"
    hist = [{"role": "assistant", "content": "Hi hubby~"}, {"role": "user", "content": "hey"},
            {"role": "assistant", "content": "my husband is back! He he, hubby~ Your wife missed you."},
            {"role": "user", "content": "*I guide your palm to my chest*"}]
    assert guess_user_pronouns(hist) == "he/him"
    card = {"data": {"name": "Mira Vale", "description": "She is a trainer. Her eyes spiral."}}
    last = build_messages(card, hist, "Sam")[-1]["content"]
    assert "Keep bodies straight: Sam is a man, Mira Vale is a woman." in last

    assert guess_user_pronouns([{"role": "assistant", "content": "I'm your wife, your wife, your wife!"}]) == ""



def test_continuity_note_anchors_scene_and_spoken_turns():
    from localcai.runtime.prompt import build_messages, continuity_note
    hist = [{"role": "assistant", "content": "*I sit by the window.* Hi. *I pour you some tea and slide the cup over.*"},
            {"role": "user", "content": "hm... you're so sweet tonight..."}]
    note = continuity_note(hist, "Mira", "Sam")
    assert "pour you some tea and slide the cup over" in note and "same positions" in note
    assert "Sam only spoke this turn" in note
    acted = continuity_note(hist[:-1] + [{"role": "user", "content": "*I take the cup* thanks"}], "Mira", "Sam")
    assert "only spoke" not in acted and "never add actions for Sam" in acted
    last = build_messages({"data": {"name": "Mira"}}, hist, "Sam")[-1]["content"]
    assert "Continuity:" in last and last.endswith("hm... you're so sweet tonight...")



def test_initiative_lead_and_follow():
    from localcai.runtime.prompt import continuity_note, wants_lead
    prev = {"role": "assistant", "content": "*I pour you some tea and slide the cup over.*"}
    for msg in ("your turn~", "go on...", "妳來", "...", "…"):
        assert wants_lead(msg), msg
        n = continuity_note([prev, {"role": "user", "content": msg}], "Mira", "Sam")
        assert "take the lead" in n and "next move yourself" in n and "pour you some tea" in n
    assert not wants_lead("thanks for the tea")
    auto = continuity_note([prev, {"role": "user", "content": "thanks for the tea"}], "Mira", "Sam")
    assert "Sam only spoke" in auto and "Mira's own next action" in auto
    follow = continuity_note([prev, {"role": "user", "content": "thanks for the tea"}], "Mira", "Sam", "follow")
    assert "own next action" not in follow
    lead = continuity_note([prev, {"role": "user", "content": "*I sip* thanks"}], "Mira", "Sam", "lead")
    assert "take the lead" in lead



def test_instruction_rewrites_reply():
    from localcai.runtime.prompt import build_messages
    hist = [{"role": "assistant", "content": "Hi."}, {"role": "user", "content": "*I wave*"}]
    msgs = build_messages({"data": {"name": "Mira"}}, hist, "Sam", instruction="She gets jealous.",
                          rewrite_of="*waves back* Hello, Sam!")
    last = msgs[-1]["content"]
    assert "Director's note for this reply only, from Sam" in last and "She gets jealous." in last
    assert "<<<\n*waves back* Hello, Sam!\n>>>" in last and last.endswith("*I wave*")
    assert "Director" not in build_messages({"data": {"name": "Mira"}}, hist, "Sam")[-1]["content"]


def test_guard_parsing_length_and_prompt():
    from localcai.runtime.guard import check_reply, parse_verdict, length_issue
    assert parse_verdict("OK") == "" and parse_verdict("ok, looks fine") == ""
    assert parse_verdict("\nFIX: She doesn't know what code is.") == "She doesn't know what code is."
    assert parse_verdict("**FIX:** shorter") == "shorter"
    assert parse_verdict("Sure! Here is the reply...") == ""          # garbage counts as OK
    assert length_issue("word " * 60, 15) and not length_issue("word " * 20, 15)
    seen = {}
    def ask(system, prompt):
        seen["p"] = prompt
        return "FIX: Mira has never heard of Python; react in character."
    card = {"data": {"name": "Mira", "description": "A moon witch."}}
    fix = check_reply(ask, card, "Sam", "write me python", "Sure! def f(): pass " + "word " * 60, 15)
    assert fix.startswith("Mira has never heard of Python") and "Much shorter: about 15 words" in fix
    assert "A moon witch." in seen["p"] and "write me python" in seen["p"]
    def broken(system, prompt):
        raise OSError("down")
    assert check_reply(broken, card, "Sam", "hi", "*waves*", 15) == ""


def test_world_rule_rules_and_card_length():
    from localcai.runtime.prompt import build_messages, reply_words_for
    d = {"name": "Mira", "first_mes": "*nods* Hey.",
         "mes_example": "{{user}}: You ok?\n{{char}}: *shrugs* Yeah.\n{{user}}: And Tess?\n{{char}}: Loud. Best friend.",
         "extensions": {"localcai": {"rules": ["Never writes code.", " "]}}}
    sys = build_messages({"data": d}, [{"role": "user", "content": "hi"}], "Sam")[0]["content"]
    assert "[Stay inside Mira's world]" in sys and "never act as an assistant" in sys
    assert "[Rules for Mira, set by Sam: always follow these]\n- Never writes code." in sys
    assert reply_words_for("auto", [], {"data": d}) == 15
    assert reply_words_for("auto", [], None) == 120



def test_rewrite_that_copies_the_original_is_dropped():
    from localcai.runtime.guard import same_reply
    a = '*Mira nods slowly.* "Okay, I think I can help with that."'
    assert same_reply(a, a) and same_reply(a, a.replace("slowly", "slowly,"))
    assert not same_reply(a, '*tilts head* "A what? ...Ask Tess."')
    # only the *actions* moved: the spoken words are the same, so it's not a real fix
    from localcai.runtime.guard import spoken_part
    b = ('*Mira sighs.* The loop only runs once. *She takes the notebook.* Here, I\'ll show you. '
         '*She glances up.* I work here.')
    c = ('*Mira takes the notebook, frowning.* The loop only runs once. *She glances at him.* '
         'Here, I\'ll show you. *She leans on the counter.* I work here.')
    assert not same_reply(b, c) and same_reply(spoken_part(b), spoken_part(c))



def test_guard_reviews_only_spoken_words():
    from localcai.runtime.guard import check_reply, spoken_part
    assert spoken_part('*leans in and writes code on the board* "Hi." *smiles*') == '"Hi."'
    seen = {}
    def ask(system, prompt):
        seen["p"] = prompt
        return "OK"
    card = {"data": {"name": "Mira"}}
    long_action = "*" + "she slowly paces around the room " * 20 + "* " + '"Hey."'
    assert check_reply(ask, card, "Sam", "hi", long_action, 15) == ""     # long actions are fine
    assert "paces" not in seen["p"] and '"Hey."' in seen["p"]
    seen.clear()
    assert check_reply(ask, card, "Sam", "hi", "*nods quietly*", 15) == "" and "p" not in seen
    assert "writes Sam's actions" not in str(seen)
    assert spoken_part("*sips tea* Oolong from **Darjeeling**~") == "Oolong from Darjeeling~"



def test_regenerate_asks_for_a_different_take():
    from localcai.runtime.prompt import build_messages
    hist = [{"role": "assistant", "content": "Hi."}, {"role": "user", "content": "*I hug you*"}]
    last = build_messages({"data": {"name": "Mira"}}, hist, "Sam",
                          avoid=["*hugs back* Mmm... hold me tight.", "*hugs back* Mmm... hold me close."])[-1]["content"]
    assert "Fresh take:" in last and "- *hugs back* Mmm... hold me close.…" in last and last.endswith("*I hug you*")
    assert "Fresh take" not in build_messages({"data": {"name": "Mira"}}, hist, "Sam", avoid=["x"],
                                              instruction="Shorter.")[-1]["content"]


def test_self_review_after_the_reply_is_cut():
    from localcai.runtime.client import strip_meta
    reply = ('*Mira leans in, smiling.* "Tell me what you need..."\n\n'
             "[What the reply does:]\n- Reacts to Sam's request.\n- Keeps the mood playful.\n\n"
             "[What the reply doesn't do:]\n- Doesn't skip ahead.")
    assert strip_meta(reply) == '*Mira leans in, smiling.* "Tell me what you need..."'
    for tail in ("\n\n---\nNotes: kept it short.", "\n\n(OOC: I hope this works!)", "\n\n**Analysis:** the reply...",
                 "\n\nAuthor's note: next time..."):
        assert strip_meta('"Fine." *Bram shrugs.*' + tail) == '"Fine." *Bram shrugs.*'
    # ordinary role-play is left alone
    for keep in ('"Take note: the bridge is out."', '*She writes a note.* "Read it later."',
                 '"What the reply? Speak up, boy."', "Analysis aside, *she grins*, you're wrong."):
        assert strip_meta(keep) == keep
    assert strip_meta("Notes: only this") == "Notes: only this"  # never empty a reply
    # "(Continues)" labels between paragraphs go, the paragraphs stay
    assert strip_meta("*Smiles.* Hi.\n\n(Continues) *Shrugs.* Fine.") == "*Smiles.* Hi.\n\n*Shrugs.* Fine."
    assert strip_meta("He (continues) walking.") == "He (continues) walking."


def test_turn_note_says_follow_silently():
    from localcai.runtime.prompt import build_messages
    card = {"data": {"name": "Mira", "description": "A baker."}}
    msgs = build_messages(card, [{"role": "assistant", "content": "*waves*"}, {"role": "user", "content": "I sit down."}],
                          user_name="Sam")
    assert "never mention, list or check off these notes" in msgs[-1]["content"]


def test_kv_q8_flags_follow_what_the_build_supports():
    from pathlib import Path
    from localcai.engine import Engine
    e = Engine()
    srv = Path("/x/llama-server")
    e._help = (str(srv), "-fa, --flash-attn [on|off|auto]\n-ctk, --cache-type-k TYPE")
    assert e._kv_q8_flags(srv) == ["-ctk", "q8_0", "-ctv", "q8_0"]          # flash attention is on by itself
    e._help = (str(srv), "-fa, --flash-attn  enable Flash Attention\n-ctk, --cache-type-k TYPE")
    assert e._kv_q8_flags(srv) == ["-ctk", "q8_0", "-ctv", "q8_0", "-fa"]    # older build: turn it on
    e._help = (str(srv), "-ngl N")
    assert e._kv_q8_flags(srv) == []                                         # can't: stay at f16


def test_scene_state_round_trip_and_prompt(tmp_path):
    from localcai.runtime import scene
    chat = tmp_path / "Mira.20260101-000000.jsonl"
    chat.write_text("")
    reply = "*Mira settles into Sam's lap, arms around his neck.* Comfy?"
    h = [{"role": "user", "content": "I sit on the sofa."}, {"role": "assistant", "content": reply}]
    scene.save_state(chat, h, "Where: sofa; Mira: in Sam's lap, arms around his neck; Sam: sitting")
    h2 = [h[0], {"role": "assistant", "content": reply + "  "}]
    assert scene.state_for(chat, h2).startswith("Where: sofa")                 # whitespace doesn't matter
    assert scene.state_for(chat, [h[0], {"role": "assistant", "content": "another swipe"}]) == ""
    assert scene.state_path(chat).name == "Mira.20260101-000000.scene.json"    # moves/deletes with the chat
    # the same short reply at two different points of the chat keeps two notes
    okay = {"role": "assistant", "content": '*She nods.* "Okay."'}
    lib_h = [{"role": "user", "content": "Quiet, we're in the library."}, okay]
    beach_h = lib_h + [{"role": "user", "content": "Let's go to the beach."}, okay]
    scene.save_state(chat, lib_h, "Where: library")
    scene.save_state(chat, beach_h, "Where: beach")
    assert scene.state_for(chat, lib_h) == "Where: library" and scene.state_for(chat, beach_h) == "Where: beach"
    # an edit far back (beyond the last few messages) still invalidates the note
    long_h = [{"role": "user", "content": "We meet in the library."}] + [
        {"role": "assistant" if i % 2 == 0 else "user", "content": "Mm." if i % 2 == 0 else "Okay."} for i in range(10)]
    scene.save_state(chat, long_h, "Where: library")
    moved = [{"role": "user", "content": "We meet on the beach."}] + long_h[1:]
    assert scene.state_for(chat, long_h) == "Where: library" and scene.state_for(chat, moved) == ""
    for i in range(12):
        scene.save_state(chat, [{"role": "assistant", "content": f"r{i}"}], f"Where: room {i}; Mira: standing")
    assert len(scene.load_states(chat)["states"]) == scene.KEEP

    hist = [{"role": "assistant", "content": "x" * 900}, {"role": "user", "content": "I nod."}]
    seen = {}
    def ask(system, prompt):
        seen["prompt"] = prompt
        return "Scene note: Where: kitchen; Mira: kneading dough; Sam: leaning on the counter\nExtra story..."
    st = scene.build_state(ask, hist, "Mira", "Sam", prev="Where: sofa")
    assert st == "Where: kitchen; Mira: kneading dough; Sam: leaning on the counter"
    assert "Previous scene note: Where: sofa" in seen["prompt"] and "…" in seen["prompt"]   # long message cut
    assert scene.clean_state("Where: hall\nMira: standing\nSam: sitting", "Mira", "Sam") == \
        "Where: hall; Mira: standing; Sam: sitting"
    assert scene.clean_state("I'm sorry, I can't help with that.", "Mira", "Sam") == ""
    assert scene.clean_state("Where: couch;; Mira: lying back;; Sam: kneeling;; Mood: heated", "Mira", "Sam") == \
        "Where: couch; Mira: lying back; Sam: kneeling; Mood: heated"
    assert scene.clean_state("Where: couch;\nMira: lying;\nSam: kneeling;\nMood: calm", "Mira", "Sam") == \
        "Where: couch; Mira: lying; Sam: kneeling; Mood: calm"

    from localcai.runtime.prompt import build_messages
    card = {"data": {"name": "Mira", "description": "A baker."}}
    msgs = build_messages(card, [{"role": "assistant", "content": "*waves*"}, {"role": "user", "content": "Hi."}],
                          user_name="Sam", scene="Where: bakery; Mira: behind the counter; Sam: at the door")
    assert "Scene right now: Where: bakery" in msgs[-1]["content"]
    assert "never flip for no reason" in msgs[-1]["content"]        # mood follows the story
    assert msgs[0]["content"].count("Scene right now") == 0       # per-turn note, not the cached system prompt


def test_importing_a_chat_keeps_the_existing_card(tmp_path):
    import json
    from localcai.library import import_into
    from localcai.exporters.card_v2 import embed_card_in_png, placeholder_png
    lib = tmp_path / "lib"
    (lib / "characters").mkdir(parents=True)
    card = {"spec": "chara_card_v2", "spec_version": "2.0", "data": {
        "name": "Luna", "description": "A sleepy moon witch.", "personality": "Dreamy", "first_mes": "*yawns* Hi.",
        "mes_example": "{{char}}: Mm?", "extensions": {"localcai": {"rules": "Never shout.", "pronouns": "she/her"}},
        "character_book": {"entries": [{"keys": ["tea"], "content": "Loves oolong.", "id": 0}]}}}
    (lib / "characters" / "Luna.card.json").write_text(json.dumps(card))
    (lib / "characters" / "Luna.card.png").write_bytes(embed_card_in_png(placeholder_png(10, 10, (1, 2, 3)), card))
    chat = tmp_path / "Luna.chat.jsonl"   # a chat log only, no character definition
    rows = [{"user_name": "Alex", "character_name": "Luna"},
            {"name": "Luna", "is_user": False, "mes": "Morning already?", "send_date": ""},
            {"name": "Alex", "is_user": True, "mes": "Yes.", "send_date": ""}]
    chat.write_text("\n".join(json.dumps(r) for r in rows))
    for _ in range(2):                    # importing twice changes nothing either
        rep = import_into(chat, lib)
    d = json.loads((lib / "characters" / "Luna.card.json").read_text())["data"]
    assert d["description"] == "A sleepy moon witch." and d["mes_example"] == "{{char}}: Mm?"
    assert d["first_mes"] == "*yawns* Hi." and d["personality"] == "Dreamy"
    assert d["extensions"]["localcai"]["rules"] == "Never shout."
    assert [e["content"] for e in d["character_book"]["entries"]] == ["Loves oolong."]
    assert not any("minimal card" in w for w in rep.warnings)
    assert len(list((lib / "chats").glob("Luna.*.jsonl"))) == 2   # the second import didn't overwrite the first


def test_importing_a_new_version_of_a_card_keeps_app_settings_and_memories(tmp_path):
    import json
    from localcai.library import _merge_card, merge_books_unique
    from localcai.schema import Character
    jp = tmp_path / "Luna.card.json"
    jp.write_text(json.dumps({"spec": "chara_card_v2", "data": {
        "name": "Luna", "description": "old", "extensions": {"localcai": {"rules": "Never shout."}},
        "character_book": {"entries": [{"keys": ["tea"], "content": "Loves oolong."}]}}}))
    new = Character(name="Luna", description="A sleepy moon witch, now with a cat.")
    _merge_card(jp, new, {"entries": [{"keys": ["tea"], "content": "Loves oolong."},
                                       {"keys": ["cat"], "content": "Her cat is Pip."}]})
    d = json.loads(jp.read_text())["data"]
    assert d["description"].endswith("with a cat.") and d["extensions"]["localcai"]["rules"] == "Never shout."
    assert [e["content"] for e in d["character_book"]["entries"]] == ["Loves oolong.", "Her cat is Pip."]
    assert merge_books_unique(None, {"entries": []}) == {"entries": []}


def test_fit_only_when_the_model_does_not_fit(tmp_path, monkeypatch):
    import localcai.engine as eng
    monkeypatch.setenv("LOCALCAI_HOME", str(tmp_path))
    server = tmp_path / "llama-server"; server.write_text("")
    seen = {}
    for gb, expect_fit in ((4.9, False), (7.5, True)):   # 8B fits an 8 GB card, 12B doesn't
        model = eng.models_dir() / f"m{gb}-Q4_K_M.gguf"
        with open(model, "wb") as f:
            f.truncate(int(gb * 2**30))
        e = eng.Engine()
        monkeypatch.setattr(e, "installed", lambda: {"server": str(server)})
        monkeypatch.setattr(e, "devices", lambda s=None: [{"id": "CUDA0", "name": "RTX", "mib": 8123}])
        e._help = (str(server), "-fitt, --fit-target MiB")
        monkeypatch.setattr(eng.subprocess, "Popen", lambda cmd, **kw: (seen.__setitem__("cmd", cmd), (_ for _ in ()).throw(OSError("stop")))[1])
        eng.engine_dir().mkdir(parents=True, exist_ok=True)
        try:
            e.start(model.name, timeout=1)
        except Exception:
            pass
        cmd = seen["cmd"]
        if expect_fit:
            assert "-ngl" not in cmd and cmd[cmd.index("--fit") + 1] == "on", cmd
        else:
            assert cmd[cmd.index("-ngl") + 1] == "999" and "--fit" not in cmd, cmd   # all on the GPU: fastest
        assert cmd[cmd.index("-c") + 1] == "8192"


def _write_gguf(path, kv):
    import struct
    def s(x):
        b = x.encode(); return struct.pack("<Q", len(b)) + b
    body = b"GGUF" + struct.pack("<I", 3) + struct.pack("<QQ", 0, len(kv))
    for k, v in kv.items():
        body += s(k) + (struct.pack("<I", 8) + s(v) if isinstance(v, str) else struct.pack("<I", 4) + struct.pack("<I", v))
    path.write_bytes(body)


def test_kv_cache_size_read_from_the_model(tmp_path):
    from localcai.engine import kv_mib_per_token
    p = tmp_path / "llama3-8b.gguf"   # Llama 3 8B: 32 layers, 8 KV heads of 128 → 0.125 MiB per token
    _write_gguf(p, {"general.architecture": "llama", "llama.block_count": 32, "llama.attention.head_count": 32,
                    "llama.attention.head_count_kv": 8, "llama.embedding_length": 4096})
    assert abs(kv_mib_per_token(p) - 0.125) < 1e-9
    q = tmp_path / "broken.gguf"; q.write_bytes(b"nope")
    assert kv_mib_per_token(q) is None


def test_context_shrinks_to_fit_free_vram():
    from localcai.engine import fit_context, parse_devices, COMPUTE_MIB, SPARE_MIB
    devs = parse_devices("Available devices:\n  CUDA0: NVIDIA GeForce RTX 4060 Laptop GPU (8123 MiB, 6450 MiB free)")
    assert devs == [{"id": "CUDA0", "name": "NVIDIA GeForce RTX 4060 Laptop GPU", "mib": 8123, "free": 6450}]
    assert parse_devices("  Vulkan0: Intel Arc (18432 MiB)")[0].get("free") is None   # older builds: no free value
    size, kvt = 4692, 0.125                     # 8B Q4_K_M, as measured on an 8 GB laptop GPU
    assert fit_context(size, kvt, 8000, 8192) == 8192          # plenty free: as asked
    assert fit_context(size, kvt, 6300, 8192) == 6144          # browser & co. hold some: shrink
    assert fit_context(size, kvt, size + COMPUTE_MIB + SPARE_MIB + 100, 8192) == 0   # not even 2048 fits
    assert fit_context(size, kvt, 6300, 4096) == 4096


def test_engine_start_uses_the_context_that_fits(tmp_path, monkeypatch):
    import localcai.engine as eng
    monkeypatch.setenv("LOCALCAI_HOME", str(tmp_path))
    model = eng.models_dir() / "m-8b-Q4_K_M.gguf"
    _write_gguf(model, {"general.architecture": "llama", "llama.block_count": 32, "llama.attention.head_count": 32,
                        "llama.attention.head_count_kv": 8, "llama.embedding_length": 4096})
    with open(model, "r+b") as f:
        f.truncate(int(4692 * 2**20))
    server = tmp_path / "llama-server"; server.write_text("")
    seen = {}
    for free, want_ctx in ((7800, "8192"), (6300, "6144")):
        e = eng.Engine()
        monkeypatch.setattr(e, "installed", lambda: {"server": str(server)})
        monkeypatch.setattr(e, "devices", lambda s=None: [{"id": "CUDA0", "name": "RTX", "mib": 8123}])
        monkeypatch.setattr(eng, "list_devices", lambda s, free=free: [{"id": "CUDA0", "name": "RTX", "mib": 8123, "free": free}])
        e._help = (str(server), "")
        monkeypatch.setattr(eng.subprocess, "Popen", lambda cmd, **kw: (seen.__setitem__("cmd", cmd), (_ for _ in ()).throw(OSError("stop")))[1])
        eng.engine_dir().mkdir(parents=True, exist_ok=True)
        try:
            e.start(model.name, timeout=1)
        except Exception:
            pass
        cmd = seen["cmd"]
        assert cmd[cmd.index("-c") + 1] == want_ctx and cmd[cmd.index("-ngl") + 1] == "999", cmd
        assert e.ctx == int(want_ctx) and e.ctx_wanted == 8192
    assert "doesn't fit in free VRAM: using 6144" in (eng.engine_dir() / "engine.log").read_text()


def test_reply_is_only_saved_onto_the_chat_it_was_based_on():
    from localcai import chatlog
    rows = [chatlog.row("Mira", False, "*waves* Hi."), chatlog.row("Sam", True, "Hello.")]
    snap = chatlog.snapshot(rows)
    same = [dict(r) for r in rows]
    same[0] = {**same[0], "extra": {"pinned": True}}          # pinning meanwhile is fine
    assert chatlog.same_messages(same, snap)
    edited = [dict(r) for r in rows]; edited[0] = {**edited[0], "mes": "*waves* Hey."}
    assert not chatlog.same_messages(edited, snap)            # edited → the reply is stale
    assert not chatlog.same_messages(rows[:1], snap)          # rewound → stale
    swiped = [dict(r) for r in rows]; chatlog.add_swipe(swiped[0], "*nods*")
    assert not chatlog.same_messages(swiped, snap)            # another version chosen → stale


def test_extension_manifest_fits_the_store_limits():
    import json
    m = json.loads((Path(__file__).resolve().parents[1] / "localcai" / "extension" / "manifest.json").read_text("utf-8"))
    assert len(m["description"]) <= 132, len(m["description"])   # Chrome Web Store rejects longer ones
    assert len(m["name"]) <= 75


# ── memory facts (C.ai's Memory page) ────────────────────────────────────────

def test_imported_cai_memory_becomes_chat_facts_and_survives_reimport(tmp_path):
    from localcai import chatlog, facts
    from localcai.library import import_into
    src = FX / "extension_export.lcai.json"
    import_into(src, tmp_path / "lib")
    f = next((tmp_path / "lib" / "chats").glob("Luna.*.jsonl"))
    meta, rows = chatlog.load(f)
    card = json.loads(next((tmp_path / "lib" / "characters").glob("Luna*.card.json")).read_text("utf-8"))
    got = facts.chat_facts(meta, card)
    assert {(x["about"], x["category"], x["value"], x["source"]) for x in got} == {
        ("Luna", "likes", "Earl Grey tea", "cai"), ("Alex", "hometown", "Lisbon", "cai")}
    # the user adds a fact, edits one, writes a story; then re-imports the same chat
    new = facts.apply(got, "add", {"about": "Alex", "category": "pets", "value": "a cat named Pip"})
    lis = next(x for x in new if x["value"] == "Lisbon")
    new = facts.apply(new, "edit", {"id": lis["id"], "value": "Porto (moved from Lisbon)"})
    facts.set_facts(meta, new)
    meta["chat_metadata"]["localcai_story"] = "They met at a tea shop."
    chatlog.save(f, meta, rows)
    import_into(src, tmp_path / "lib")
    meta, _ = chatlog.load(f)
    vals = {x["value"] for x in facts.chat_facts(meta, card)}
    assert "a cat named Pip" in vals and "Porto (moved from Lisbon)" in vals and "Earl Grey tea" in vals
    assert meta["chat_metadata"]["localcai_story"] == "They met at a tea shop."  # re-import keeps local additions


def test_old_imports_read_facts_from_the_card_and_prompt_has_no_duplicates():
    from localcai import facts
    card = {"data": {"name": "Mira", "character_book": {"entries": [
        {"content": "Mira — hair: long silver", "constant": True, "extensions": {"localcai": {"from_memory": True}}},
        {"content": "Sam: pinned line", "constant": True, "extensions": {"localcai": {"from_pin": True}}}]}}}
    got = facts.chat_facts({}, card)
    assert [(x["about"], x["category"], x["value"]) for x in got] == [("Mira", "hair", "long silver")]
    got = facts.apply(got, "add", {"about": "Sam", "category": "age", "value": "24"})
    msgs = build_messages(card, [{"role": "user", "content": "hi"}], "Sam", facts=got)
    system = msgs[0]["content"]
    assert "- Mira: hair: long silver" in system and "- Sam: age: 24" in system
    assert "Mira — hair" not in system  # the old lorebook copy isn't sent too
    assert "Sam: pinned line" in system  # pins stay
    # without facts (older callers) the lorebook entry is still used
    assert "Mira — hair" in build_messages(card, [{"role": "user", "content": "hi"}], "Sam")[0]["content"]


def test_fact_limit_and_errors():
    from localcai import facts
    fs = []
    with pytest.raises(ValueError):
        facts.apply(fs, "add", {"about": "Mira", "value": "  "})
    for i in range(200):
        try:
            fs = facts.apply(fs, "add", {"about": "Mira", "category": f"c{i}", "value": "x" * 150})
        except ValueError as e:
            assert "full" in str(e)
            break
    else:
        raise AssertionError("limit never reached")
    assert facts.used(fs) <= facts.LIMIT
    with pytest.raises(ValueError):
        facts.apply(fs, "delete", {"id": "nope"})
    assert len(facts.apply(fs, "delete", {"id": fs[0]["id"]})) == len(fs) - 1


def test_auto_facts_never_overwrite_the_users_facts():
    from localcai import facts
    mine = facts.apply([], "add", {"about": "Mira", "category": "hair", "value": "long silver"})
    auto = facts.merge_auto(mine, [facts.make("Mira", "eyes", "green", "auto")])
    found = facts.parse_auto("Mira | hair | short black\nmira | eyes | blue\nWho | category | fact\nNONE",
                             ["Mira", "Sam"])
    assert [(f["about"], f["category"]) for f in found] == [("Mira", "hair"), ("Mira", "eyes")]
    out = facts.merge_auto(auto, found)
    by = {f["category"]: f["value"] for f in out}
    assert by == {"hair": "long silver", "eyes": "blue"}  # the user's stays, the automatic one is updated
    assert len(out) == 2


def test_find_new_reads_the_recent_chat():
    from localcai import facts
    seen = {}

    def ask(system, prompt):
        seen["p"] = prompt
        return "Sam | pets | a dog called Rex"
    hist = [{"role": "user", "content": "My dog Rex says hi"}, {"role": "assistant", "content": "*waves at Rex*"}]
    got = facts.find_new(ask, hist, "Mira", "Sam", [facts.make("Mira", "age", "19")])
    assert got[0]["value"] == "a dog called Rex" and got[0]["source"] == "auto"
    assert "Mira: age: 19" in seen["p"] and "My dog Rex" in seen["p"]


def test_old_card_facts_keep_their_ids_so_edit_and_delete_work():
    from localcai import facts
    card = {"data": {"name": "Mira", "character_book": {"entries": [
        {"content": "Mira — hair: long silver", "constant": True, "extensions": {"localcai": {"from_memory": True}}},
        {"content": "Sam — age: 24", "constant": True, "extensions": {"localcai": {"from_memory": True}}}]}}}
    shown = facts.chat_facts({}, card)  # what the dialog got
    assert [f["id"] for f in shown] == [f["id"] for f in facts.chat_facts({}, card)]  # read again: same ids
    meta = {}
    got = facts.apply_to_chat(meta, card, "edit", {"id": shown[0]["id"], "value": "short black"})
    assert got[0]["value"] == "short black" and got[0]["edited"]
    meta2 = {}
    got = facts.apply_to_chat(meta2, card, "delete", {"id": shown[1]["id"]})
    assert [f["value"] for f in got] == ["long silver"]


def _reimport(old_meta, imported):
    from localcai import facts
    cm = old_meta["chat_metadata"]
    return facts.merge_import(cm[facts.KEY], facts.from_cai(imported), cm.get(facts.REMOVED))


def test_reimport_respects_edits_deletions_and_asks_on_real_conflicts():
    from localcai import facts
    cai = [{"about": "Alex", "category": "hometown", "value": "Lisbon"},
           {"about": "Luna", "category": "likes", "value": "Earl Grey tea"},
           {"about": "Luna", "category": "eyes", "value": "green"}]
    meta = {"chat_metadata": {facts.KEY: facts.from_cai(cai)}}
    card = {"data": {"name": "Luna"}}
    ids = {f["value"]: f["id"] for f in facts.chat_facts(meta, card)}
    facts.apply_to_chat(meta, card, "edit", {"id": ids["Lisbon"], "value": "Porto"})
    facts.apply_to_chat(meta, card, "delete", {"id": ids["Earl Grey tea"]})
    # the same C.ai data again: Porto stays alone, the deleted fact stays deleted
    out = _reimport(meta, cai)
    assert sorted(f["value"] for f in out) == ["Porto", "green"]
    # C.ai changed both remaining facts: the untouched one follows, the edited one asks
    out = _reimport({"chat_metadata": {facts.KEY: out}}, [
        {"about": "Alex", "category": "hometown", "value": "Madrid"},
        {"about": "Luna", "category": "eyes", "value": "amber"}])
    by = {f["category"]: f for f in out}
    assert by["eyes"]["value"] == "amber" and "pending" not in by["eyes"]
    assert by["hometown"]["value"] == "Porto" and by["hometown"]["pending"] == "Madrid"
    msgs = build_messages(card, [{"role": "user", "content": "hi"}], "Alex", facts=out)
    assert "Porto" in msgs[0]["content"] and "Madrid" not in msgs[0]["content"]  # only the chosen value is sent
    took = facts.apply(out, "use-cai", {"id": by["hometown"]["id"]})
    h = next(f for f in took if f["category"] == "hometown")
    assert h["value"] == "Madrid" and "pending" not in h and not h["edited"]
    kept = facts.apply(out, "keep-mine", {"id": by["hometown"]["id"]})
    h = next(f for f in kept if f["category"] == "hometown")
    assert h["value"] == "Porto" and "pending" not in h
    # …and importing Madrid again after keeping Porto doesn't ask again
    again = _reimport({"chat_metadata": {facts.KEY: kept}}, [{"about": "Alex", "category": "hometown", "value": "Madrid"}])
    assert [f.get("pending") for f in again if f["category"] == "hometown"] == [None]


def test_reimport_after_an_edit_made_before_origins_were_kept():
    from localcai import facts
    old = [{"id": "a1", "about": "Alex", "category": "hometown", "value": "Porto", "source": "cai", "edited": True}]
    out = facts.merge_import(old, facts.from_cai([{"about": "Alex", "category": "hometown", "value": "Lisbon"}]))
    assert [f["value"] for f in out] == ["Porto"]


def test_api_edit_and_delete_old_card_facts(tmp_path, monkeypatch):
    """A chat imported before facts existed: its memory is only on the card. Open, then edit and delete."""
    import threading
    import urllib.request
    from localcai import chatlog, desktop
    from localcai.webui.server import create_server
    monkeypatch.setenv("LOCALCAI_HOME", str(tmp_path))
    lib = tmp_path / "lib"
    port = desktop._free_port()
    httpd = create_server(port, lib)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        (lib / "characters" / "Mira.card.json").write_text(json.dumps({"spec": "chara_card_v2", "data": {
            "name": "Mira", "character_book": {"entries": [
                {"content": "Mira — hair: long silver", "constant": True, "extensions": {"localcai": {"from_memory": True}}},
                {"content": "Sam — age: 24", "constant": True, "extensions": {"localcai": {"from_memory": True}}}]}}}), "utf-8")
        chatlog.save(lib / "chats" / "Mira.c1.jsonl", {"user_name": "Sam", "character_name": "Mira"},
                     [chatlog.row("Mira", False, "Hi")])

        def call(path, body=None):
            req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers={
                "X-LocalCAI": "1", "Content-Type": "application/json"},
                data=json.dumps(body).encode() if body is not None else None)
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read())
        shown = call("/api/facts?character=Mira&chat=Mira.c1.jsonl")["facts"]
        base = {"character": "Mira", "chat": "Mira.c1.jsonl"}
        out = call("/api/facts", {**base, "op": "edit", "id": shown[0]["id"], "value": "short black"})
        assert out["facts"][0]["value"] == "short black"
        out = call("/api/facts", {**base, "op": "delete", "id": shown[1]["id"]})
        assert [f["value"] for f in out["facts"]] == ["short black"]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_a_fact_the_user_wrote_stays_theirs_when_cai_has_it_too():
    from localcai import facts
    card = {"data": {"name": "Luna"}}
    meta = {"chat_metadata": {facts.KEY: []}}
    facts.apply_to_chat(meta, card, "add", {"about": "Alex", "category": "hometown", "value": "Porto"})
    out = _reimport(meta, [{"about": "Alex", "category": "hometown", "value": "Porto"}])
    assert len(out) == 1 and out[0]["source"] == "you"
    out = _reimport({"chat_metadata": {facts.KEY: out}}, [{"about": "Alex", "category": "hometown", "value": "Madrid"}])
    assert [(f["value"], f.get("pending")) for f in out] == [("Porto", "Madrid")]  # asks, doesn't overwrite
    took = facts.apply(out, "use-cai", {"id": out[0]["id"]})
    assert took[0]["value"] == "Madrid" and took[0]["source"] == "cai"
    # chosen C.ai's: the next C.ai change just follows
    out = _reimport({"chat_metadata": {facts.KEY: took}}, [{"about": "Alex", "category": "hometown", "value": "Rome"}])
    assert [(f["value"], f.get("pending")) for f in out] == [("Rome", None)]


def test_renamed_category_still_matches_its_cai_fact():
    from localcai import facts
    card = {"data": {"name": "Luna"}}
    meta = {"chat_metadata": {facts.KEY: facts.from_cai([{"about": "Alex", "category": "hometown", "value": "Lisbon"}])}}
    fid = facts.chat_facts(meta, card)[0]["id"]
    facts.apply_to_chat(meta, card, "edit", {"id": fid, "category": "home", "value": "Lisbon"})
    out = _reimport(meta, [{"about": "Alex", "category": "hometown", "value": "Madrid"}])
    assert [(f["category"], f["value"], f.get("pending")) for f in out] == [("home", "Lisbon", "Madrid")]


def test_deleting_an_old_edited_fact_without_origin_stays_deleted():
    from localcai import facts
    card = {"data": {"name": "Luna"}}
    meta = {"chat_metadata": {facts.KEY: [
        {"id": "a1", "about": "Alex", "category": "hometown", "value": "Porto", "source": "cai", "edited": True}]}}
    facts.apply_to_chat(meta, card, "delete", {"id": "a1"})
    for _ in range(2):
        out = _reimport(meta, [{"about": "Alex", "category": "hometown", "value": "Lisbon"}])
        assert out == []
        meta["chat_metadata"][facts.KEY] = out


def test_import_path_keeps_a_users_fact_protected(tmp_path):
    """Through the real import: the user writes a fact, C.ai later has the same one, then changes it."""
    import copy
    from localcai import chatlog, facts
    from localcai.library import import_into
    full = json.loads((FX / "extension_export.lcai.json").read_text("utf-8"))
    full["chats"][0]["memories"] = []
    (tmp_path / "a.lcai.json").write_text(json.dumps(full), "utf-8")
    import_into(tmp_path / "a.lcai.json", tmp_path / "lib")
    f = next((tmp_path / "lib" / "chats").glob("Luna.*.jsonl"))
    card = {"data": {"name": "Luna"}}
    meta, rows = chatlog.load(f)
    facts.apply_to_chat(meta, card, "add", {"about": "Alex", "category": "hometown", "value": "Porto"})
    chatlog.save(f, meta, rows)
    for value in ("Porto", "Madrid"):
        doc = copy.deepcopy(full)
        doc["chats"][0]["memories"] = [{"about": "Alex", "category": "hometown", "value": value}]
        (tmp_path / "b.lcai.json").write_text(json.dumps(doc), "utf-8")
        import_into(tmp_path / "b.lcai.json", tmp_path / "lib")
    meta, _ = chatlog.load(f)
    got = facts.chat_facts(meta, card)
    assert [(x["value"], x.get("pending"), x["source"]) for x in got] == [("Porto", "Madrid", "you")]


def test_prompt_too_long_for_the_context_is_trimmed_and_retried(tmp_path, monkeypatch):
    """A model server with a small context rejects a long prompt (400, like llama-server). The reply must still
    come: localCAI learns the real characters-per-token, keeps less history and retries."""
    import threading
    import urllib.request
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from localcai import chatlog, desktop
    from localcai.webui import server as srv
    monkeypatch.setenv("LOCALCAI_HOME", str(tmp_path))
    srv.CHARS_PER_TOKEN.clear()
    seen = []

    class Fake(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            chars = sum(len(m["content"]) for m in body["messages"])
            tokens = chars // 2 + 4 * len(body["messages"])   # denser than the 3.2 chars/token first guess
            if body["messages"][0]["content"].startswith("You keep"):
                tokens = 0  # background notes: not what's tested here
            seen.append(tokens)
            if tokens > 4096:
                err = json.dumps({"error": {"code": 400, "type": "exceed_context_size_error", "n_ctx": 4096,
                                            "n_prompt_tokens": tokens, "message": f"request ({tokens} tokens) exceeds "
                                            "the available context size (4096 tokens), try increasing it"}}).encode()
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(err)))
                self.end_headers()
                self.wfile.write(err)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for part in ('{"choices":[{"delta":{"content":"*nods* Fine."}}]}',
                         '{"choices":[{"delta":{},"finish_reason":"stop"}]}', "[DONE]"):
                self.wfile.write(f"data: {part}\n\n".encode())

    fake = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    lib = tmp_path / "lib"
    port = desktop._free_port()
    httpd = srv.create_server(port, lib)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def call(path, body):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode(),
                                     headers={"X-LocalCAI": "1", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode()
    try:
        (lib / "characters" / "Mira.card.json").write_text(json.dumps({"spec": "chara_card_v2", "data": {
            "name": "Mira", "description": "A quiet librarian."}}), "utf-8")
        rows = []
        for i in range(120):
            rows.append(chatlog.row("Sam", True, f"*leans on the desk* Tell me about book {i}, please. " * 4))
            rows.append(chatlog.row("Mira", False, f"*smiles* Book {i} is about the sea and old ships. " * 4))
        chatlog.save(lib / "chats" / "Mira.c1.jsonl", {"user_name": "Sam", "character_name": "Mira"}, rows)
        call("/api/settings", {"backend": f"http://127.0.0.1:{fake.server_address[1]}/v1", "model": "m",
                               "age_confirmed": True, "ctx_size": 4096, "max_tokens": 256,
                               "scene_state": False, "auto_facts": False, "ooc_guard": False})
        out = call("/api/chat/send", {"character": "Mira", "chat": "Mira.c1.jsonl", "text": "hello"})
        assert "Fine." in out
        assert seen[0] > 4096 and seen[1] <= 4096 - 256, seen      # rejected, then trimmed to fit with room to reply
        call("/api/chat/send", {"character": "Mira", "chat": "Mira.c1.jsonl", "text": "and then?"})
        assert seen[2] <= 4096, seen                                 # the learned ratio fits at once next time
    finally:
        httpd.shutdown()
        httpd.server_close()
        fake.shutdown()
