# localCAI Extractor (browser extension)

把你在 Character.AI 上**自己的**聊天、釘選和角色存成 `.lcai.json`，再用 `localcai import` 轉成可以在本地模型上跑的角色卡。

## 安裝（開發版）
**Chrome / Edge / Brave**
1. 打開 `chrome://extensions`，開啟右上角「開發人員模式」
2. 按「載入未封裝項目」，選這個 `extension/` 資料夾

**Firefox（128 以上，含 Android 版）**
1. 打開 `about:debugging#/runtime/this-firefox`
2. 按「載入暫時附加元件」，選 `extension/manifest.json`（重開瀏覽器後要再載一次，等上架 AMO 就不用）

## 使用
1. 打開 character.ai，進到你想保存的聊天
2. **往上滑到最舊的訊息**，擴充功能只看得到網頁實際載入過的內容
3. 點工具列的 localCAI 圖示 → **匯出 .lcai.json**
4. `localcai import localcai-xxxx.lcai.json -o 我的角色`

## 運作方式
- **被動**：只讀 C.ai 網頁自己載入的回應內容，不會額外發任何請求，所以看起來跟你正常使用一模一樣。
- **不碰登入資訊**：不讀 request header 跟 cookie，網址的 query string 也會先去掉。
- **只存在記憶體**：資料只留在那個分頁裡，關掉就沒了，不會寫入硬碟，也不會傳到任何地方。
- **別人的私密定義不匯出**：只有你自己建立的角色（或平台標示為公開的定義）才會包含 definition。

## 除錯匯出（幫助我們修格式）
「除錯：原始資料」會下載收集到的原始 JSON，token、email、cookie、session 這類欄位會自動遮蔽，看起來像 JWT 的字串也會遮掉。**裡面還是有你的聊天內容**，請私下分享，或先把文字刪掉再貼到 issue。

## 開發
- `src/inject.js`：在頁面環境攔截 fetch / XHR / WebSocket 的回應
- `src/bridge.js`：收集資料、回應 popup
- `src/normalize.js`：**所有 C.ai 格式相關的規則都在這裡**，C.ai 改版時只需要改這一個檔
- 測試：`NODE_PATH=$(npm root -g) node tests/extension/e2e.mjs`（Playwright + 模擬的 character.ai，不會連到真網站）

> 目前的格式規則還是暫定的，要用真實的除錯匯出確認過才算定案。
