import json
from pathlib import Path

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
    msgs = build_messages(card, [{"role": "user", "content": "hi"}], user_name="Alex")
    system = msgs[0]["content"]
    assert "Darjeeling" in system
    assert "{{user}}" not in system and "Alex" in system
    assert msgs[-1] == {"role": "user", "content": "hi"}


def test_history_budget_keeps_most_recent():
    card = {"data": {"name": "X"}}
    hist = [{"role": "user", "content": "a" * 1000} for _ in range(50)] + [{"role": "user", "content": "last"}]
    msgs = build_messages(card, hist, max_chars=5000)
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
    assert l["has_avatar"] and l["background"] == "Luna.background.png"
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
