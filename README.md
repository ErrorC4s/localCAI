<p align="center"><img src="assets/logo-wordmark.svg" alt="localCAI" width="360"></p>

<p align="center"><b>Bring your characters home.</b></p>

localCAI moves your Character.AI chats, pinned messages, memories, personas, avatars, backgrounds and the characters you created into open, portable files, then lets you keep chatting with them on **a local model you choose**. No cloud, no filters you didn't pick, and no platform that can take them away.

> ⚠️ localCAI is an independent community project. It is **not affiliated with, endorsed by, or sponsored by Character Technologies, Inc.** ("Character.AI").

## How it works

1. **Extract**: the localCAI Extractor browser extension saves your chats from character.ai as a `.lcai.json` file.
2. **Import**: drag that file into the localCAI app.
3. **Chat**: pick a local model from a dropdown and continue where you left off.

## Install

You need **Python 3.10+**. That's it: localCAI has a **built-in model engine** (llama.cpp), so Ollama or LM Studio are optional.

**Windows, easiest:** download **`localCAI.exe`** from the [latest release](https://github.com/ErrorC4s/localCAI/releases) and double-click it. It opens in its own window with no console and doesn't need Python. To build it yourself: download the repo, then double-click **`build-exe.bat`** (needs Python once, for building).

**Any OS, from source:** download the repo (Code → Download ZIP), unzip it and double-click **`start-localcai.bat`** (Windows) or **`start-localcai.sh`** (macOS/Linux). With `pip install pywebview` it opens in its own window, otherwise in your browser.

**With pip:**

```bash
pip install git+https://github.com/ErrorC4s/localCAI
localcai                    # opens the app in your browser
```

### First run: set up the built-in engine

1. Click **🧠** next to the Model list.
2. **Install engine**: downloads the official llama.cpp build for your computer (GPU via Vulkan on Windows/Linux, Metal on Apple Silicon; a CPU-only build is in Settings).
3. **Model slot**: click **Download** for the starter model (Qwen3 4B Instruct, ~2.5 GB), or drop any `.gguf` file into the models folder (**📂 Open folder**).
4. Pick the model in the **Model** list. It loads automatically (the status shows *● ready*).

Already use Ollama, LM Studio, llama.cpp or KoboldCpp? Just pick it in **Backend** instead.

### The browser extension

**Easiest:** open the localCAI app and click **Set up the extension** on the start screen. It gets the extension folder ready, opens it, copies its path, and shows the four clicks for your browser (Chrome, Edge, Brave, Opera or Firefox).

**Without the app** (Chrome, Edge, Brave, Opera):

1. Download [`localcai-extractor-0.5.6-chrome.zip`](downloads/localcai-extractor-0.5.6-chrome.zip) and unzip it (right-click → *Extract All*).
2. Open a new tab and go to `chrome://extensions` (Edge: `edge://extensions`).
3. Turn on **Developer mode**.
4. Click **Load unpacked** and choose the unzipped folder, the one that has `manifest.json` directly inside it.

**Firefox 140+:** download [`localcai-extractor-0.5.6-firefox.zip`](downloads/localcai-extractor-0.5.6-firefox.zip) → go to `about:debugging#/runtime/this-firefox` → **Load Temporary Add-on** → pick the zip. Firefox keeps it until you close the browser.

**Then, for each chat:** open it on character.ai, **refresh the page**, click the localCAI icon → **Load full history** (about a minute for tens of thousands of messages) → **Export .lcai.json**, and drag the file into the app.

More in [`localcai/extension/README.md`](localcai/extension/README.md).

## The app

Run `localcai` and it opens at `http://127.0.0.1:8765`:

- **Import files**: drop in `.lcai.json`, CAI Tools / SillyTavern chats, Tavern character cards (JSON/PNG) or a `.zip`
- **Backend / Model**: the built-in engine (default) or your own runner, and the model, from dropdowns (custom URLs in ⚙ Settings)
- **🧠 Engine**: install llama.cpp, download a starter model, open the model slot folder, stop the engine
- **You are**: pick one of your C.ai personas so the character knows who you are
- **Chats**: continue an imported chat or start a new one, stream replies, stop
- **C.ai-style message tools** (hover a message):
  - **◀ 2/3 ▶** browse alternative replies; ▶ on the last one generates a new one (old replies are kept)
  - **✏ Edit** any line, yours or the character's
  - **📌 Pin**: pinned messages become memories the character always keeps in mind
  - **🗑 Delete** a message, or **⤺ Rewind** to delete it and everything after
- **🖼 Background**: set your own picture as a chat's background (✕ to remove)
- **✎ Edit character**: description, personality, scenario, greeting, example dialogue, custom instructions, pronouns, rules, and reply length (like their past replies, short, medium, long)
- **🔍 Style**: view and edit how the character talks: style notes, example dialogue, and the habits counted from their real C.ai replies (laugh, pet names, how speech is marked…). **Learn from this chat** has the model read a sample of their replies and write the notes, plus pick example dialogues. Great for characters whose definition is private
- **🗑 Trash**: deleted characters and chats wait there; restore them or delete them for good
- **📖 Chat memory**: **memory facts** like C.ai's Memory page (grouped by who they're about, with categories; add, edit, delete, usage bar; your C.ai memory imported; new facts picked up from the chat every few replies), see what's always remembered (pins), and edit *the story so far*, or **✨ generate it from history** (last 500 / 2,000 / 5,000 messages or the whole chat; stoppable)
- **Recall**: on every reply, moments from the whole chat that match what you're talking about are found (fast keyword search, works for English and Chinese) and added to the prompt, so old events aren't forgotten
- **⬇ Card**: download a Character Card V2 PNG for SillyTavern, RisuAI, etc.
- ⚙ **Settings**: your name, creativity (temperature), the hard limit per reply, and for the built-in engine: build (GPU/CPU), context size and GPU layers

Your library lives in `~/.localcai/library`, models in `~/.localcai/models` and the engine in `~/.localcai/engine` (override the base folder with the `LOCALCAI_HOME` environment variable). Re-importing a newer export of the same chat **merges** it: nothing is duplicated and no history is lost.

## What gets carried over

| From Character.AI | Becomes |
|---|---|
| Character name, tagline, description, greeting | Character Card V2 fields |
| Definition (only for **characters you created**) | Example dialogue (`END_OF_DIALOG` → `<START>`) |
| Full chat history, oldest first | SillyTavern `.jsonl` chat |
| Rerolled replies | Swipes |
| 📌 Pinned messages | Always-on lorebook memories |
| Chat memory ("conversation facts") | Memory facts per chat (editable, sent with every reply) |
| Your personas | Selectable "You are" profiles |
| Character & persona avatars | Real pictures (the character's avatar becomes the card PNG) |
| Character, persona & chat backgrounds | Chat backgrounds in the app |

## Principles

- **Your data only.** Your chats, your pins, characters you created. Other creators' private definitions are never exported (C.ai doesn't send them anyway).
- **Passive extraction.** The extension reads what the C.ai web app already loads. The only requests it makes are the web app's own "older messages" requests when you press *Load full history*; the browser adds your session cookie itself, and the extension never reads or stores login data.
- **Minimal collection.** The extension only listens to an allowlist of chat/character endpoints. Billing, subscription, birthday and account details are never collected.
- **Local-only.** No telemetry, nothing uploaded. The app only listens on `127.0.0.1`. The only downloads are the ones you click (the engine from llama.cpp's GitHub releases, models from Hugging Face).
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
- [x] Extractor: load a chat's full history automatically
- [ ] Extractor: export all chats in one go
- [ ] Publish the extension on the Chrome Web Store & Firefox Add-ons (submission kit ready in [`store/`](store/listing.md))
- [ ] Map personas to the chats they were used in
- [ ] Persona → SillyTavern persona export
- [ ] Group chats / rooms
- [ ] Summarised long-term memory for very long chats
- [x] Built-in engine (llama.cpp) with a model slot and a one-click starter model
- [x] Windows app (`localCAI.exe`): own window, taskbar logo, no Python needed
- [ ] macOS app bundle

## Development

```bash
pip install -e .[dev]
pytest                                            # unit tests
python tests/e2e_ui/test_ui.py                    # web app, driven in headless Chromium
python tests/e2e_ui/test_engine.py                # built-in engine with fake GitHub / Hugging Face / llama-server
NODE_PATH=$(npm root -g) node tests/e2e_extension/e2e.mjs        # extension against a mocked character.ai
NODE_PATH=$(npm root -g) node tests/e2e_extension/load_all.mjs   # "Load full history" auto-scroll
```

Every push to `main` that changes the app or the extension builds `localCAI.exe` and the extension zips on GitHub Actions and publishes them as the release for the current version (`localcai/__init__.py`).

Pure Python standard library at runtime, no dependencies, so it stays easy to install for non-developers. The `.lcai.json` format is documented in [`docs/lcai-format.md`](docs/lcai-format.md).

## Privacy

See [PRIVACY.md](PRIVACY.md). Short version: no servers, no analytics, nothing leaves your computer.

## License

MIT
