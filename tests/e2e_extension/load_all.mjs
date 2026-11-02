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
const extDir = path.resolve(here, "../../extension");
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
    if (fromExtension && tok !== "p0") direct++;
    const headers = cors ? { "Access-Control-Allow-Origin": "https://character.ai", "Access-Control-Allow-Credentials": "true",
      "Access-Control-Allow-Headers": "x-from-page" } : {};
    if (req.method() === "OPTIONS") return r.fulfill({ status: 204, headers });
    // without CORS the extension's direct request fails, the page's own requests still work (header marks them)
    if (!cors && !req.headers()["x-from-page"]) return r.fulfill({ status: 403, body: "" });
    r.fulfill({ status: 200, contentType: "application/json", headers, body: JSON.stringify(page(+tok.slice(1))) });
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
  await ctx.close();
  console.log(`${cors ? "fast path" : "fallback "}: ${s.job.message} (${secs}s, direct requests: ${direct})`);
  if (s.turns !== PAGES * PER) fail(`loaded ${s.turns}/${PAGES * PER}`);
  if (!/Reached the first message/.test(s.job.message)) fail("should stop because C.ai said there is nothing older");
  if (cors && direct < PAGES - 1) fail("fast path should fetch the older pages directly");
}

const fail = (m) => { console.error("FAIL:", m); process.exit(1); };
await run(true);
await run(false);
console.log("LOAD-ALL PASS");
