# Store submission kit: localCAI Extractor

Everything to copy-paste into the Chrome Web Store and Firefox Add-ons (AMO) forms.
Build the upload files with `python tools/package_extension.py` → `dist/`.

| Store | Upload | Notes |
|---|---|---|
| Chrome Web Store | `dist/localcai-extractor-<ver>-chrome.zip` | Developer account needs a one-time registration fee |
| Firefox Add-ons | `dist/localcai-extractor-<ver>-firefox.zip` | Free. Also works on Firefox for Android (142+) |

Privacy policy URL (both stores): `https://github.com/ErrorC4s/localCAI/blob/main/PRIVACY.md`
Homepage / support URL: `https://github.com/ErrorC4s/localCAI` · `https://github.com/ErrorC4s/localCAI/issues`

---

## Name
localCAI Extractor

## Short description (Chrome: max 132 characters · Firefox "Summary": max 250)
**EN:** Save your own Character.AI chats, pins, memories and characters to an open file, and keep chatting with them on a local AI.
**zh-TW:** 把你在 Character.AI 的聊天、釘選、記憶和角色存成開放格式，在本地 AI 上繼續聊。

## Category
Chrome: **Tools** (or Productivity) · Firefox: **Download Management** / **Privacy & Security**

## Detailed description (EN)
Your Character.AI chats are yours. localCAI Extractor saves them to a file you control, so you can keep them, back them up, or keep chatting with your characters on a local AI model with the free, open-source localCAI app.

WHAT IT SAVES
• Your full chat history, including alternative replies (swipes)
• Pinned messages and Character.AI's chat memory
• Characters you created, including their definitions
• Public info of other characters you chat with (name, greeting, description). Private definitions are never exported
• Your personas
• Avatars and backgrounds (optional)

HOW TO USE
1. Open a chat on character.ai and refresh the page
2. Click the localCAI icon → "Load full history" (loads tens of thousands of messages in about a minute)
3. Click "Export .lcai.json"
4. Drag the file into the localCAI app, or import it into SillyTavern and other tools that read character cards

PRIVATE BY DESIGN
• Everything stays on your computer. No servers, no analytics, no tracking
• Only reads chat and character data on character.ai. Ignores billing, subscription and account details
• Never reads or stores your login. Your browser handles your session as usual
• Open source (MIT): https://github.com/ErrorC4s/localCAI

Please follow Character.AI's Terms of Service. Only export your own chats, and don't redistribute other creators' characters.

localCAI is an independent project and is not affiliated with, endorsed by, or sponsored by Character Technologies, Inc.

## Detailed description (zh-TW)
你的 Character.AI 聊天紀錄屬於你。localCAI Extractor 把它們存成你自己保管的檔案：可以備份、留作紀念，或用免費開源的 localCAI App，在本地 AI 模型上繼續跟角色聊天。

可以保存的內容
• 完整聊天紀錄，包含重骰的其他回覆
• 釘選訊息與 Character.AI 的聊天記憶
• 你自己建立的角色（包含定義）
• 你聊過的其他角色的公開資訊（名字、開場白、描述）。私密定義一律不匯出
• 你的 persona
• 頭像與背景（可選）

使用方式
1. 打開 character.ai 的聊天，重新整理頁面
2. 點 localCAI 圖示 →「Load full history」（幾萬則訊息約一分鐘）
3. 按「Export .lcai.json」
4. 把檔案拖進 localCAI App，或匯入 SillyTavern 等支援角色卡的工具

隱私設計
• 所有資料都留在你的電腦，沒有伺服器、沒有分析、沒有追蹤
• 只讀取 character.ai 的聊天與角色資料，帳務、訂閱、帳號資訊一律忽略
• 不讀取也不儲存你的登入資訊，登入狀態由瀏覽器自己處理
• 開源（MIT）：https://github.com/ErrorC4s/localCAI

請遵守 Character.AI 的服務條款：只匯出你自己的聊天，不要散布其他創作者的角色。

localCAI 是獨立專案，與 Character Technologies, Inc. 沒有任何關係，也未受其認可或贊助。

---

## Chrome Web Store: "Privacy practices" tab

**Single purpose:**
Export the user's own Character.AI chats, characters and personas to a local file so they can keep them and use them in local AI chat apps.

**Permission justification: host permissions**
- `https://character.ai/*`, `https://*.character.ai/*`: read the chat and character data that the character.ai page loads, and when the user clicks "Load full history", request older pages of the open chat from character.ai's own history endpoint.
- `https://characterai.io/*`, `https://*.characterai.io/*`: when the user exports with "Include avatars & backgrounds", download the avatar and background images of the characters and personas being exported.

**Remote code:** No, I am not using remote code. (All JavaScript is packaged in the extension.)

**Data usage:** tick these, because the extension *handles* them locally when exporting:
- ☑ Personal communications (the user's chat messages)
- ☑ Website content (character descriptions, images)

Then certify all three:
- ☑ I do not sell or transfer user data to third parties, outside of the approved use cases
- ☑ I do not use or transfer user data for purposes that are unrelated to my item's single purpose
- ☑ I do not use or transfer user data to determine creditworthiness or for lending purposes

(Explain in the listing that the data never leaves the user's computer; see PRIVACY.md.)

## Firefox Add-ons: notes for reviewers
```
localCAI Extractor saves the user's own Character.AI chats to a local JSON file.

- Content scripts run only on character.ai. inject.js (MAIN world) wraps fetch/XHR/WebSocket to
  read response bodies of an allowlist of chat/character endpoints (see ALLOW in src/inject.js).
  It never reads request headers or cookies.
- bridge.js keeps captures in memory for the popup. "Load full history" requests older pages from
  https://neo.character.ai/turns/<chat>/?next_token=… with credentials: "include" (same request the
  site makes on scroll), 200–400 ms apart.
- Images are fetched by the popup from characterai.io only when the user exports with images.
- No remote code, no analytics, no external servers. data_collection_permissions: none.
- Source is not minified or bundled; the uploaded files are the source:
  https://github.com/ErrorC4s/localCAI/tree/main/localcai/extension
- Test: open any character.ai chat, refresh, click the toolbar icon → Load full history → Export.
```

## Images
- Icon: `localcai/extension/icons/icon128.png`
- Screenshots (1280×800): `store/screenshots/*.png`
- Chrome small promo tile (440×280): `store/promo-440x280.png`

## Checklist
- [ ] Chrome: register a developer account, verify e-mail, pay the registration fee
- [ ] Chrome: upload zip → fill Store listing (description, category, screenshots, promo tile, language)
- [ ] Chrome: Privacy practices tab (single purpose, justifications, data usage, privacy policy URL)
- [ ] Chrome: Distribution: Public, all regions → Submit for review
- [ ] Firefox: sign in at addons.mozilla.org/developers → Submit a New Add-on → "On this site"
- [ ] Firefox: upload zip → summary, description, category, privacy policy, reviewer notes → Submit
- [ ] After approval: put the store links at the top of README.md
