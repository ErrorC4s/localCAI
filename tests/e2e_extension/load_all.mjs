// "Load full history": the extension scrolls a C.ai-like chat until the first message.
// The mock page lazy-loads older pages on scroll (column-reverse list, like C.ai) and the
// last page has no next_token. Usage: NODE_PATH=$(npm root -g) node tests/e2e_extension/load_all.mjs
import { createRequire } from "node:module";
import { createHash } from "node:crypto";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const { chromium } = createRequire(import.meta.url)("playwright");
const here = path.dirname(fileURLToPath(import.meta.url));
const extDir = path.resolve(here, "../../localcai/extension");
const extId = [...createHash("sha256").update(extDir).digest("hex").slice(0, 32)]
  .map((c) => String.fromCharCode(97 + parseInt(c, 16))).join("");

const PAGES = 4, PER = 25; // 100 turns, newest page first
const turn = (i) => ({ turn_key: { chat_id: "chat-9", turn_id: "t" + i },
  create_time: new Date(Date.UTC(2026, 0, 1, 0, i)).toISOString(),
  author: i % 2 ? { name: "Me", is_human: true } : { name: "Bot" },
  candidates: [{ candidate_id: "c" + i, raw_content: "message " + i }], primary_candidate_id: "c" + i });
const page = (n) => { // n = 0 newest
  const hi = PAGES * PER - n * PER, lo = hi - PER;
  const turns = []; for (let i = hi - 1; i >= lo; i--) turns.push(turn(i));
  return { turns, meta: n < PAGES - 1 ? { next_token: "p" + (n + 1) } : {} };
};

const HTML = `<!doctype html><html><body style="margin:0">
<div id="list" style="height:400px;overflow-y:auto;display:flex;flex-direction:column-reverse"></div>
<style>#list > div { flex: none; }</style>
<script>
  let next = "p0", loading = false;
  const list = document.getElementById("list");
  async function loadMore() {
    if (loading || !next) return; loading = true;
    const r = await fetch("https://neo.character.ai/turns/chat-9/?next_token=" + next, { headers: { "x-from-page": "1" } }).then(r => r.json());
    for (const t of r.turns) { const d = document.createElement("div"); d.style.height = "60px";
      d.textContent = t.candidates[0].raw_content; list.appendChild(d); }
    next = r.meta.next_token || null; loading = false;
  }
  // like C.ai: older messages load when you scroll near the oldest end
  list.addEventListener("scroll", () => { if (list.scrollHeight + list.scrollTop - list.clientHeight < 200) loadMore(); });
  loadMore();
</script></body></html>`;

async function run(cors) {
  const ctx = await chromium.launchPersistentContext(mkdtempSync(path.join(tmpdir(), "lcai-")), {
    headless: true, channel: "chromium", args: [`--disable-extensions-except=${extDir}`, `--load-extension=${extDir}`] });
  await ctx.route("https://character.ai/**", (r) => r.fulfill({ status: 200, contentType: "text/html", body: HTML }));
  let direct = 0;
  await ctx.route("https://neo.character.ai/turns/**", (r) => {
    const req = r.request();
    const tok = new URL(req.url()).searchParams.get("next_token");
    const fromExtension = !req.headers()["x-from-page"];
    if (fromExtension && tok && tok !== "p0") direct++;
    const headers = cors ? { "Access-Control-Allow-Origin": "https://character.ai", "Access-Control-Allow-Credentials": "true",
      "Access-Control-Allow-Headers": "x-from-page" } : {};
    if (req.method() === "OPTIONS") return r.fulfill({ status: 204, headers });
    // without CORS the extension's direct request fails, the page's own requests still work (header marks them)
    if (!cors && !req.headers()["x-from-page"]) return r.fulfill({ status: 403, body: "" });
    r.fulfill({ status: 200, contentType: "application/json", headers, body: JSON.stringify(page(tok ? +tok.slice(1) : 0)) });
  });
  const tab = await ctx.newPage();
  await tab.goto("https://character.ai/chat/x");
  await tab.waitForTimeout(800);
  const popup = await ctx.newPage();
  await popup.goto(`chrome-extension://${extId}/popup/popup.html`);
  const ask = (type) => popup.evaluate(async (type) => {
    const [t] = await chrome.tabs.query({ url: "https://character.ai/*" });
    return chrome.tabs.sendMessage(t.id, { type });
  }, type);
  const first = await ask("stats");
  if (first.turns !== PER) fail("expected only the first page before loading, got " + first.turns);
  const t0 = Date.now();
  await ask("loadAll");
  let s;
  for (let i = 0; i < 60; i++) { await tab.waitForTimeout(500); s = await ask("stats"); if (s.job.done) break; }
  const secs = ((Date.now() - t0) / 1000).toFixed(1);
  // Clear, then Load full history again: it must start over, not say "already at the first message"
  await ask("clear");
  const c = await ask("stats");
  if (c.turns !== 0) fail("clear should empty what was collected, got " + c.turns);
  await ask("loadAll");
  let again;
  for (let i = 0; i < 60; i++) { await tab.waitForTimeout(500); again = await ask("stats"); if (again.job.done) break; }
  await ctx.close();
  if (cors && (again.turns !== PAGES * PER || !/Reached the first message/.test(again.job.message)))
    fail(`after Clear, loading again should fetch everything: ${again.turns} · ${again.job.message}`);
  if (!cors && !/Reload this C.ai page/.test(again.job.message))
    fail("after Clear without direct requests, it should say to reload the page: " + again.job.message);
  console.log(`  after Clear: ${again.job.message}`);
  console.log(`${cors ? "fast path" : "fallback "}: ${s.job.message} (${secs}s, direct requests: ${direct})`);
  if (s.turns !== PAGES * PER) fail(`loaded ${s.turns}/${PAGES * PER}`);
  if (!/Reached the first message/.test(s.job.message)) fail("should stop because C.ai said there is nothing older");
  if (cors && direct < PAGES - 1) fail("fast path should fetch the older pages directly");
}

// Clear while an older page is still on its way: its late answer must not be mixed into the new collection
// (it used to move the paging past the newest page, which was then lost: e.g. 75/100 and "at the start").
async function race() {
  const ctx = await chromium.launchPersistentContext(mkdtempSync(path.join(tmpdir(), "lcai-")), {
    headless: true, channel: "chromium", args: [`--disable-extensions-except=${extDir}`, `--load-extension=${extDir}`] });
  await ctx.route("https://character.ai/**", (r) => r.fulfill({ status: 200, contentType: "text/html", body: HTML }));
  let held = false;
  await ctx.route("https://neo.character.ai/turns/**", async (r) => {
    const req = r.request();
    const tok = new URL(req.url()).searchParams.get("next_token");
    const headers = { "Access-Control-Allow-Origin": "https://character.ai", "Access-Control-Allow-Credentials": "true",
      "Access-Control-Allow-Headers": "x-from-page" };
    if (req.method() === "OPTIONS") return r.fulfill({ status: 204, headers });
    if (tok === "p2" && !held && !req.headers()["x-from-page"]) { held = true; await new Promise((ok) => setTimeout(ok, 2500)); }
    r.fulfill({ status: 200, contentType: "application/json", headers, body: JSON.stringify(page(tok ? +tok.slice(1) : 0)) });
  });
  const tab = await ctx.newPage();
  await tab.goto("https://character.ai/chat/x");
  await tab.waitForTimeout(800);
  const popup = await ctx.newPage();
  await popup.goto(`chrome-extension://${extId}/popup/popup.html`);
  const ask = (type) => popup.evaluate(async (type) => {
    const [t] = await chrome.tabs.query({ url: "https://character.ai/*" });
    return chrome.tabs.sendMessage(t.id, { type });
  }, type);
  await ask("loadAll");
  await tab.waitForTimeout(1200);          // p1 is in, p2 is being held back
  await ask("clear");
  let s;
  for (let i = 0; i < 20; i++) { await tab.waitForTimeout(300); s = await ask("stats"); if (s.job.done) break; }
  await tab.waitForTimeout(2000);          // the held p2 answer arrives now, after Clear
  s = await ask("stats");
  if (s.turns !== 0) fail("an answer to a request sent before Clear was kept: " + s.turns);
  await ask("loadAll");
  for (let i = 0; i < 60; i++) { await tab.waitForTimeout(500); s = await ask("stats"); if (s.job.done && !s.job.running) break; }
  await ctx.close();
  if (s.turns !== PAGES * PER || !/Reached the first message/.test(s.job.message))
    fail(`after Clear during a load, loading again should get everything: ${s.turns} · ${s.job.message}`);
  console.log(`clear during load: ${s.job.message}`);
}

// Clear, then scroll the chat up yourself (the page loads older pages on its own), then Load full history:
// the newest page was cleared and the page never asks for it again, so the extension must fetch it.
async function clearThenScroll() {
  const ctx = await chromium.launchPersistentContext(mkdtempSync(path.join(tmpdir(), "lcai-")), {
    headless: true, channel: "chromium", args: [`--disable-extensions-except=${extDir}`, `--load-extension=${extDir}`] });
  await ctx.route("https://character.ai/**", (r) => r.fulfill({ status: 200, contentType: "text/html", body: HTML }));
  await ctx.route("https://neo.character.ai/turns/**", (r) => {
    const req = r.request();
    const tok = new URL(req.url()).searchParams.get("next_token");
    const headers = { "Access-Control-Allow-Origin": "https://character.ai", "Access-Control-Allow-Credentials": "true",
      "Access-Control-Allow-Headers": "x-from-page" };
    if (req.method() === "OPTIONS") return r.fulfill({ status: 204, headers });
    r.fulfill({ status: 200, contentType: "application/json", headers, body: JSON.stringify(page(tok ? +tok.slice(1) : 0)) });
  });
  const tab = await ctx.newPage();
  await tab.goto("https://character.ai/chat/x");
  await tab.waitForTimeout(800);                       // the page has loaded the newest page
  const popup = await ctx.newPage();
  await popup.goto(`chrome-extension://${extId}/popup/popup.html`);
  const ask = (type) => popup.evaluate(async (type) => {
    const [t] = await chrome.tabs.query({ url: "https://character.ai/*" });
    return chrome.tabs.sendMessage(t.id, { type });
  }, type);
  await ask("clear");
  for (let i = 0; i < 8; i++) {                        // scroll to the top: the page fetches older pages itself
    await tab.evaluate(() => { const l = document.getElementById("list"); l.scrollTop = -l.scrollHeight;
      l.dispatchEvent(new Event("scroll")); });
    await tab.waitForTimeout(250);
  }
  let s = await ask("stats");
  const scrolled = s.turns;
  await ask("loadAll");
  for (let i = 0; i < 60; i++) { await tab.waitForTimeout(500); s = await ask("stats"); if (s.job.done && !s.job.running) break; }
  const doc = (await ask("export")).doc;
  await ctx.close();
  const texts = new Set((doc.chats || []).flatMap((c) => (c.turns || []).flatMap((t) => t.candidates || [])));
  const newest = PAGES * PER - 1;
  if (s.turns !== PAGES * PER || !texts.has("message " + newest) || !/Reached the first message/.test(s.job.message))
    fail(`Clear → scroll → Load full history must collect everything incl. the newest page: ${s.turns} ` +
         `(had ${scrolled} after scrolling), newest present: ${texts.has("message " + newest)} · ${s.job.message}`);
  // every message id once, oldest first, no gaps
  const ids = (doc.chats[0].turns || []).map((t) => t.id);
  const want = Array.from({ length: PAGES * PER }, (_, i) => "t" + i);
  if (JSON.stringify(ids) !== JSON.stringify(want))
    fail(`export ids/order wrong: ${ids.length} ids, first ${ids.slice(0, 3)}, last ${ids.slice(-3)}`);
  console.log(`clear, scroll, load: ${s.job.message} (after scrolling only ${scrolled}); ids t0..t99 in order`);
}

const fail = (m) => { console.error("FAIL:", m); process.exit(1); };
await run(true);
await run(false);
await race();
await clearThenScroll();
console.log("LOAD-ALL PASS");
