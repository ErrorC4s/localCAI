# localCAI Extractor (browser extension)

Saves **your own** Character.AI chats, pins, memories, personas, avatars, backgrounds and characters as a `.lcai.json` file that the localCAI app can import.

## Install (developer mode)

**Chrome / Edge / Brave**
1. Open `chrome://extensions` and switch on **Developer mode** (top right).
2. Click **Load unpacked** and pick this `extension/` folder (the one containing `manifest.json`).

**Firefox 128+ (including Firefox for Android)**
1. Open `about:debugging#/runtime/this-firefox`.
2. Click **Load Temporary Add-on** and pick `extension/manifest.json`. (You'll need to do this again after restarting Firefox until it's published on AMO.)

## Use

1. Open character.ai and go to the chat you want to keep.
2. **Refresh the page** (F5). The extension must be running before the page loads.
3. **Scroll up to the oldest message.** The extension can only see what the page actually loads.
4. Click the localCAI icon → **Export .lcai.json**. With *Include avatars & backgrounds* ticked (default), the pictures are downloaded from C.ai's image server and embedded in the file.
5. Drag the file into the localCAI app (or run `localcai import <file>`).

## How it works

- **Passive**: it reads the responses the C.ai web app already receives. It never sends requests of its own.
- **Allowlisted**: only chat, character, persona and memory endpoints are collected. Billing, subscription, birthday and account details are ignored.
- **No credentials**: request headers and cookies are never read; query strings are stripped from URLs.
- **Memory only**: captured data lives in that tab until you close it. Nothing is written to disk or sent anywhere.
- **Others' private definitions are never exported**: definitions are kept only for characters you created (C.ai doesn't send other creators' definitions anyway).

## Debug export

**Debug: raw data** downloads the captured JSON with secrets redacted (tokens, IDs, e-mail, birthday, subscription…). **It still contains your chat text**, so share it privately, or strip the messages before attaching it to an issue.

## Development

- `src/inject.js`: hooks fetch / XHR / WebSocket in the page and applies the endpoint allowlist
- `src/bridge.js`: collects captures and answers the popup
- `src/assets.js`: downloads avatars (converted to PNG) and backgrounds and embeds them as `data:` URLs
- `src/normalize.js`: **every C.ai-specific format rule lives here**; when C.ai changes something, this is the one file to edit
- Test: `NODE_PATH=$(npm root -g) node tests/e2e_extension/e2e.mjs` (Playwright + a mocked character.ai; never touches the real site)

> Formats confirmed against real data (Nov 2026): chats, swipes, pins, characters, personas, C.ai chat memory. Live messages over WebSocket are not yet verified.
