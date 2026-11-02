# localCAI

**把你的角色和回憶帶回家。** / **Bring your characters home.**

localCAI turns your Character.AI exports (your chats, pinned messages and the characters you created) into open, portable files, then lets you keep chatting with them on **a local model you choose**. No cloud, no filters you didn't pick, and no platform that can take them away.

> ⚠️ localCAI is an independent, community project. It is **not affiliated with, endorsed by, or sponsored by Character Technologies, Inc.** ("Character.AI").

---

## 中文說明

### 它能做什麼
- **匯入**：官方「Export Data」檔、CAI Tools 匯出的 Tavern / SillyTavern 格式、Wilds AI Exporter 的 JSON、Tavern 角色卡（JSON / PNG）
- **萃取角色設定**：名字、標語、描述、開場白、定義（`END_OF_DIALOG` 會自動轉成 `<START>`）
- **萃取對話紀錄**：保留重骰（swipes）的其他候選回覆
- **釘選 → 長期記憶**：C.ai 的釘選訊息會轉成「常駐」lorebook 條目，每次對話都會帶進 prompt
- **輸出**：Character Card V2（`.card.json` + `.card.png`），SillyTavern、RisuAI、KoboldCpp 等都能直接讀
- **自選本地模型**：Ollama、LM Studio、llama.cpp、KoboldCpp，或任何 OpenAI 相容 API

### 快速開始
1. 安裝瀏覽器擴充功能（見 [`extension/README.md`](extension/README.md)），打開你的 C.ai 聊天 → 匯出 `.lcai.json`
2. 轉換並開聊：
```bash
pip install git+https://github.com/<you>/localCAI
localcai import localcai-xxxx.lcai.json -o 我的角色
ollama pull qwen3:4b
localcai chat "我的角色/characters/Luna.card.png" --model qwen3:4b --user-name 你的名字
```

### 原則
- **只處理你自己的資料**：你的聊天、你的釘選、你建立的角色。localCAI 不會、也不打算去抓別人設成私密的角色定義。
- **不呼叫 Character.AI 的非官方 API**：只讀你已經匯出的檔案，降低帳號被封的風險。
- **完全本地**：沒有遙測、不會上傳任何東西。
- **聊天功能限 18 歲以上**。若訊息看起來像是危機狀況，畫面上會顯示求助專線，不會中斷對話，也不會回報任何資料。

---

## English

### What it does
| Step | Details |
|---|---|
| Import | Official C.ai *Export Data* file, CAI Tools Tavern/SillyTavern exports, Wilds AI Exporter JSON, Tavern cards (JSON/PNG), `.zip` or whole folders |
| Characters | name, tagline, description, greeting, definition (`END_OF_DIALOG` → `<START>`) |
| Chats | full history, oldest-first, alternate candidates kept as swipes |
| Pins → memory | pinned messages become **constant lorebook entries**, injected into every prompt |
| Output | Character Card V2 (`.card.json` + `.card.png` with embedded `chara` chunk) and SillyTavern `.jsonl` chats |
| Run | built-in chat against any OpenAI-compatible local server |

### Quick start
```bash
pip install git+https://github.com/<you>/localCAI
localcai import my_export.zip -o my_characters
localcai models --backend ollama          # see what you have
localcai chat my_characters/characters/Luna.card.png --model qwen3:4b
```
Backends: `ollama`, `lmstudio`, `llamacpp`, `koboldcpp`, or a full URL (`--backend http://host:port/v1`).
Continue an old conversation with `--resume path/to/chat.jsonl`.

### How to get your data out of Character.AI
1. **localCAI Extractor (recommended)**: our own browser extension in [`extension/`](extension/). Open your chat, click *Export .lcai.json*. It's instant, and the format is our own ([spec](docs/lcai-format.md)), so nothing is guessed on import. Passive and read-only: it never sends requests of its own.
2. **Official export** (fallback, works for phone-only users): Profile → Settings → Account → *Manage Account & Data* → *Export Data*. It arrives by email (can take weeks; the link expires).
3. **Other extensions**: CAI Tools (SillyTavern format) or Wilds AI Exporter (JSON) also work.
Feed any of those files, or a folder of them, to `localcai import`.

### Scope & ethics
- **Your data only.** Your chats, your pins, characters you created. localCAI will not extract other creators' private definitions.
- **No unofficial API scraping.** localCAI reads files you already exported.
- **Local-only.** No telemetry, nothing uploaded.
- **Adults only for chat (18+)**, asked once. If a message looks like a crisis, help-line info is shown on screen. It never blocks or reports anything.

### Known limitations (v0.1)
- C.ai export formats aren't documented. The `cai_json` importer recognises characters and chat turns by shape. **If your file parses badly, please open an issue with a redacted sample of its structure.** That's the most useful contribution right now.
- CAI Tools Tavern-format chats can have user/character swapped. localCAI warns when it notices; fix with `--swap-roles`.
- Token budgeting is character-count based for now.

### Roadmap
- [x] Confirm the extractor's rules against a real (redacted) C.ai debug dump
- [ ] Extractor: "export all my chats" (opt-in, slow, one at a time)
- [ ] Publish extractor on Chrome Web Store & Firefox Add-ons
- [ ] Real-world fixtures for the official export & Wilds JSON
- [ ] Desktop GUI (PySide6): drag in an export, pick a model, chat
- [ ] Persona import (your C.ai persona → SillyTavern persona)
- [ ] Group chats / rooms
- [ ] Summarised long-term memory for very long chats
- [ ] One-click installer that also sets up Ollama + a recommended small model

### Development
```bash
pip install -e .[dev]
pytest
```
Pure standard library, no runtime dependencies, so it stays easy to install for non-developers.

## License
MIT
