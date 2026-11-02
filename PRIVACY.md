# Privacy Policy: localCAI

_Last updated: 2 November 2026_

localCAI (the **localCAI Extractor** browser extension and the **localCAI** app) is built so that your chats never leave your computer. This policy covers both.

## What the extension handles

When you open a chat on character.ai, the extension reads the responses the character.ai web page already receives (your chat messages, pinned messages, chat memory, characters, personas, and their avatar and background image links). It does this only on `character.ai` pages.

- This data is kept **in the memory of that browser tab only**. It is not written to disk and disappears when you close the tab.
- It is saved to your computer **only when you click "Export .lcai.json"**. The file goes to your Downloads folder like any other download.
- **Load full history** asks character.ai for older pages of the chat you have open, the same request the site makes when you scroll up. Your browser attaches your normal character.ai session; the extension never reads, stores or sends passwords, tokens or cookies.
- **Include avatars & backgrounds** downloads those images from character.ai's image server (`characterai.io`) into the exported file.

The extension does **not** collect: login data, billing or subscription information, your birthday, e-mail address or other account details. Requests to those character.ai endpoints are ignored.

## What the app handles

The localCAI app runs on your own computer and only listens on `127.0.0.1` (it can't be reached from other devices). Imported characters, chats, personas and settings are stored in the `.localcai` folder in your user folder. Chats are sent only to the model runner you choose (the built-in engine, Ollama, LM Studio, etc.), which runs on your computer unless you point it somewhere else.

The app only connects to the internet when you click to download something: the llama.cpp engine (from GitHub) or a model (from Hugging Face).

## What we receive

**Nothing.** localCAI has no servers, analytics, telemetry, ads or tracking. We (the developers) never receive, see, sell or share your data.

## Your control

- Close the tab or click **Clear** in the extension to discard captured data.
- Delete exported `.lcai.json` files or the `.localcai` folder to remove everything the app stored.
- Uninstalling the extension removes it and anything it held in memory.

## Children

Chat in the localCAI app is for adults (18+). Neither the extension nor the app is directed at children.

## Contact

Questions or concerns: open an issue at https://github.com/ErrorC4s/localCAI/issues

localCAI is an independent project and is not affiliated with, endorsed by, or sponsored by Character Technologies, Inc. ("Character.AI").
