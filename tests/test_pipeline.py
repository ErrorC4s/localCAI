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
    assert e["constant"] and "Alishan" in e["content"]


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
    assert "Alishan" in system
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
    # produced by tests/extension/e2e.mjs against a mocked character.ai
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
    assert "Alishan" in book["entries"][0]["content"]
