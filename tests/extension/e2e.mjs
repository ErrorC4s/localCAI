// End-to-end test for the extension with a mocked character.ai (no real network).
// Usage: node tests/extension/e2e.mjs <output.lcai.json>
import { createRequire } from "node:module";
import { createHash } from "node:crypto";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

// works with a local or a global (NODE_PATH) playwright install
const { chromium } = createRequire(import.meta.url)("playwright");
const here = path.dirname(fileURLToPath(import.meta.url));
const extDir = path.resolve(here, "../../extension");
const out = process.argv[2] || path.join(tmpdir(), "e2e.lcai.json");

// Chromium derives an unpacked extension's id from its absolute path.
const extId = [...createHash("sha256").update(extDir).digest("hex").slice(0, 32)]
  .map((c) => String.fromCharCode(97 + parseInt(c, 16))).join("");

const ME = { user: { username: "alex", id: 1, account: { name: "Alex" } } };
const CHAR = { character: { external_id: "abc123", name: "Luna", title: "A sleepy moon witch",
  description: "Lives on the moon.", greeting: "*yawns* Oh, {{user}}...",
  definition: "{{user}}: Hi\n{{char}}: Hello~", user__username: "alex", avatar_file_name: "u/luna.webp" } };
const OTHER = { character: { external_id: "zzz", name: "Rex", title: "Someone else's bot",
  greeting: "Rawr.", definition: "SECRET DEFINITION", user__username: "someone_else" } };
const turn = (id, t, name, human, cands, primary, pinned = false) => ({
  turn_key: { chat_id: "chat-1", turn_id: id }, create_time: t, author: { name, is_human: human },
  candidates: cands.map((c, i) => ({ candidate_id: `${id}-${i}`, raw_content: c })),
  primary_candidate_id: `${id}-${primary}`, is_pinned: pinned });
const HISTORY = { turns: [ // newest first, like a paginated history endpoint
  turn("t3", "2026-10-01T10:03:00Z", "Luna", false, ["Fine, chamomile.", "Earl Grey, obviously."], 1),
  turn("t2", "2026-10-01T10:02:00Z", "Alex", true, ["Remember: I love Alishan oolong."], 0, true),
  turn("t1", "2026-10-01T10:01:00Z", "Luna", false, ["*yawns* Oh, Alex..."], 0),
], meta: { access_token: "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnop" } };
const WS_NEW = { command: "add_turn", turn: turn("t4", "2026-10-01T10:04:00Z", "Luna", false, ["Sweet dreams~"], 0) };

const PAGE = `<!doctype html><html><body>mock c.ai<script>
  (async () => {
    await fetch("https://neo.character.ai/user/me").then(r => r.json());
    await fetch("https://neo.character.ai/character/abc123").then(r => r.json());
    await fetch("https://neo.character.ai/character/zzz").then(r => r.json());
    const x = new XMLHttpRequest(); x.open("GET", "https://neo.character.ai/turns/chat-1?token=abc"); x.send();
    await new Promise(r => x.onload = r);
    const ws = new WebSocket("wss://neo.character.ai/ws/");
    ws.onmessage = () => { document.title = "ws-ok"; };
  })();
</script></body></html>`;

const userDataDir = mkdtempSync(path.join(tmpdir(), "lcai-"));
const ctx = await chromium.launchPersistentContext(userDataDir, {
  headless: true, channel: "chromium",
  args: [`--disable-extensions-except=${extDir}`, `--load-extension=${extDir}`],
});
const json = (o) => ({ status: 200, contentType: "application/json", body: JSON.stringify(o) });
await ctx.route("https://character.ai/**", (r) => r.fulfill({ status: 200, contentType: "text/html", body: PAGE }));
await ctx.route("https://neo.character.ai/user/me", (r) => r.fulfill(json(ME)));
await ctx.route("https://neo.character.ai/character/abc123", (r) => r.fulfill(json(CHAR)));
await ctx.route("https://neo.character.ai/character/zzz", (r) => r.fulfill(json(OTHER)));
await ctx.route("https://neo.character.ai/turns/**", (r) => r.fulfill(json(HISTORY)));
await ctx.routeWebSocket("wss://neo.character.ai/ws/", (ws) => { ws.send(JSON.stringify(WS_NEW)); });

const page = await ctx.newPage();
await page.goto("https://character.ai/chat/abc123");
await page.waitForFunction(() => document.title === "ws-ok", null, { timeout: 10000 });
await page.waitForTimeout(300);

const popup = await ctx.newPage();
await popup.goto(`chrome-extension://${extId}/popup/popup.html`);
const result = await popup.evaluate(async () => {
  const [tab] = await chrome.tabs.query({ url: "https://character.ai/*" });
  const stats = await chrome.tabs.sendMessage(tab.id, { type: "stats" });
  const doc = (await chrome.tabs.sendMessage(tab.id, { type: "export" })).doc;
  const raw = (await chrome.tabs.sendMessage(tab.id, { type: "raw" })).doc;
  return { stats, doc, raw };
});
await ctx.close();

const fail = (m) => { console.error("FAIL:", m); process.exit(1); };
const { stats, doc, raw } = result;
console.log("stats", stats);
if (stats.characters !== 2 || stats.chats !== 1 || stats.turns !== 4 || stats.pinned !== 1) fail("stats");
const luna = doc.characters.find((c) => c.name === "Luna");
const rex = doc.characters.find((c) => c.name === "Rex");
if (!luna.is_own || !luna.definition.includes("Hello~")) fail("own definition should be kept");
if (rex.definition !== "" || !rex.definition_withheld) fail("other creator's definition must be withheld");
const t = doc.chats[0].turns;
if (t.map((x) => x.id).join() !== "t1,t2,t3,t4") fail("turn order " + t.map((x) => x.id));
if (t[2].candidates[t[2].primary] !== "Earl Grey, obviously.") fail("primary candidate");
if (!t[1].pinned || !t[1].author.is_user) fail("pin");
if (doc.chats[0].character_name !== "Luna") fail("chat character name");
const rawStr = JSON.stringify(raw);
if (rawStr.includes("eyJhbGci") || !rawStr.includes("[redacted]")) fail("redaction");
if (rawStr.includes("token=abc")) fail("query string leaked");
writeFileSync(out, JSON.stringify(doc, null, 2));
console.log("PASS — wrote", out);
