# localCAI

**Bring your characters home.**

localCAI moves your Character.AI chats, pinned messages, memories, personas, avatars, backgrounds and the characters you created into open, portable files, then lets you keep chatting with them on **a local model you choose**. No cloud, no filters you didn't pick, and no platform that can take them away.

> ⚠️ localCAI is an independent community project. It is **not affiliated with, endorsed by, or sponsored by Character Technologies, Inc.** ("Character.AI").

## How it works

1. **Extract**: the localCAI Extractor browser extension saves your chats from character.ai as a `.lcai.json` file.
2. **Import**: drag that file into the localCAI app.
3. **Chat**: pick a local model from a dropdown and continue where you left off.

## Install

You need **Python 3.10+** and a local model runner such as [Ollama](https://ollama.com), LM Studio, llama.cpp or KoboldCpp.

**Easiest (no terminal):** download the repo (Code → Download ZIP), unzip it and double-click **`start-localcai.bat`** (Windows) or **`start-localcai.sh`** (macOS/Linux). The app opens in your browser.

**With pip:**

```bash
pip install git+https://github.com/ErrorC4s/localCAI
ollama pull qwen3:4b        # or any model you like
localcai                    # opens the app in your browser
```

### The browser extension

See [`extension/README.md`](extension/README.md). Short version: open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked** and pick the `extension` folder. Then open a chat on character.ai, **refresh the page**, scroll up to load older messages, click the localCAI icon and choose **Export .lcai.json**.

## The app

Run `localcai` and it opens at `http://127.0.0.1:8765`:

- **Import files**: drop in `.lcai.json`, CAI Tools / SillyTavern chats, Tavern character cards (JSON/PNG) or a `.zip`
- **Backend / Model**: choose your runner and model from dropdowns (custom URLs in ⚙ Settings)
- **You are**: pick one of your C.ai personas so the character knows who you are
- **Chats**: continue an imported chat or start a new one, stream replies, stop or regenerate
- **⬇ Card**: download a Character Card V2 PNG for SillyTavern, RisuAI, etc.
- ⚙ **Settings**: your name, creativity (temperature) and reply length

Your library lives in `~/.localcai/library` (override with the `LOCALCAI_HOME` environment variable).

## What gets carried over

| From Character.AI | Becomes |
|---|---|
| Character name, tagline, description, greeting | Character Card V2 fields |
| Definition (only for **characters you created**) | Example dialogue (`END_OF_DIALOG` → `<START>`) |
| Full chat history, oldest first | SillyTavern `.jsonl` chat |
| Rerolled replies | Swipes |
| 📌 Pinned messages | Always-on lorebook memories |
| Chat memory ("conversation facts") | Always-on lorebook memories |
| Your personas | Selectable "You are" profiles |
| Character & persona avatars | Real pictures (the character's avatar becomes the card PNG) |
| Character, persona & chat backgrounds | Chat backgrounds in the app |

## Principles

- **Your data only.** Your chats, your pins, characters you created. Other creators' private definitions are never exported (C.ai doesn't send them anyway).
- **Passive extraction.** The extension reads what the C.ai web app already loads. It sends no requests of its own and never touches your login token.
- **Minimal collection.** The extension only listens to an allowlist of chat/character endpoints. Billing, subscription, birthday and account details are never collected.
- **Local-only.** No telemetry, nothing uploaded. The app only listens on `127.0.0.1`.
- **Adults only for chat (18+)**, asked once. If a message looks like a crisis, help-line information is shown on screen. It never blocks the conversation or reports anything.

## Command line

Everything the app does is also available in a terminal:

```bash
localcai import my_export.lcai.json            # into your library (or -o DIR)
localcai models --backend ollama               # list models
localcai chat ~/.localcai/library/characters/Luna.card.png --model qwen3:4b \
    --persona ~/.localcai/library/personas/personas.json
```

Backends: `ollama`, `lmstudio`, `llamacpp`, `koboldcpp`, or a full URL (`--backend http://host:port/v1`). Continue a chat with `--resume path/to/chat.jsonl`.

## Other ways to get your data

- **Official export** (useful for phone-only users): Profile → Settings → Account → *Manage Account & Data* → *Export Data*. It arrives by email and can take weeks; the link expires after a few days.
- **Other extensions**: CAI Tools (SillyTavern format) and Wilds AI Exporter (JSON) also import.

## Known limitations

- The official C.ai data export hasn't been tested against a real file yet. The importer recognises it by shape. If yours parses badly, please open an issue with a **redacted** sample of its structure.
- Character and persona backgrounds are supported. Per-chat backgrounds are recognised if C.ai sends them with the chat, but this hasn't been confirmed on a real chat yet.
- C.ai lets you choose a different persona per chat, but that link isn't in the captured data yet, so you pick the persona in the app.
- Live messages over WebSocket haven't been verified against the real site yet. History export is confirmed.
- CAI Tools Tavern-format chats can have user/character swapped. localCAI warns when it notices; fix with `--swap-roles`.

## Roadmap

- [x] Confirm the extractor against real C.ai data (chats, swipes, pins, characters, personas, memory)
- [x] Desktop-friendly app with buttons and dropdowns
- [ ] Verify live-message capture over WebSocket
- [ ] Extractor: "export all my chats" (opt-in, slow, one at a time)
- [ ] Publish the extension on the Chrome Web Store & Firefox Add-ons
- [ ] Map personas to the chats they were used in
- [ ] Persona → SillyTavern persona export
- [ ] Group chats / rooms
- [ ] Summarised long-term memory for very long chats
- [ ] One-click installer that also sets up Ollama and a recommended small model

## Development

```bash
pip install -e .[dev]
pytest                                            # unit tests
python tests/e2e_ui/test_ui.py                    # web app, driven in headless Chromium
NODE_PATH=$(npm root -g) node tests/e2e_extension/e2e.mjs   # extension against a mocked character.ai
```

Pure Python standard library at runtime, no dependencies, so it stays easy to install for non-developers. The `.lcai.json` format is documented in [`docs/lcai-format.md`](docs/lcai-format.md).

## License

MIT
