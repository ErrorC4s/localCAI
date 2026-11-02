// End-to-end test for the extension with a mocked character.ai (no real network).
// Usage: node tests/e2e_extension/e2e.mjs <output.lcai.json>
import { createRequire } from "node:module";
import { createHash } from "node:crypto";
import { mkdtempSync, writeFileSync } from "node:fs";
import { deflateSync, crc32 } from "node:zlib";
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

// Shapes mirror real neo.character.ai responses (captured 2026-11); content is synthetic.
// tiny solid-colour PNG for the mocked image CDN
function png(w, h, rgb) {
  const chunk = (type, body) => {
    const len = Buffer.alloc(4); len.writeUInt32BE(body.length);
    const tb = Buffer.concat([Buffer.from(type), body]);
    const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(tb) >>> 0);
    return Buffer.concat([len, tb, crc]);
  };
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 2;
  const row = Buffer.concat([Buffer.from([0]), Buffer.from(Array(w).fill(rgb).flat())]);
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(Buffer.concat(Array(h).fill(row)))), chunk("IEND", Buffer.alloc(0))]);
}

const ME = { user: { user: { username: "alex", id: 42, account: { name: "Alex", avatar_file_name: "a.webp" },
  subscription: { type: "PLUS" } }, email: "x@example.com", date_of_birth: "2000-01-01T00:00:00Z", name: "Alex" } };
const CHAR = { character: { external_id: "abc123", name: "Luna", title: "A sleepy moon witch", visibility: "PRIVATE",
  description: "Lives on the moon.", greeting: "*yawns* Oh, {{user}}...", additional_greetings: null,
  definition: "{{user}}: Hi\n{{char}}: Hello~", has_definition: true, user__username: "alex",
  avatar_file_name: "u/luna.webp", background_image_url: "https://characterai.io/bg/moon.png" }, status: "OK" };
const OTHER = { character: { external_id: "zzz", name: "Rex", title: "Someone else's bot", visibility: "PUBLIC",
  greeting: "Rawr.", has_definition: true, user__username: "someone_else", avatar_file_name: "u/rex.webp" }, status: "OK" };
const PERSONAS = { personas: [{ id: 7, external_id: "p1", title: "Alex", greeting: "Hello!", description: "My persona",
  definition: "A tired night-shift baker.", avatar_file_name: "p.webp", visibility: "PRIVATE",
  participant__name: "Alex", user__username: "alex", is_persona: true }] };
const FACTS = { conversation_facts: { Luna: { facts: [{ category: "likes", value: "Earl Grey tea" }] },
  Alex: { facts: [{ category: "hometown", value: "Lisbon" }] } } };
const RECENT = { chats: [{ chat_id: "chat-1", create_time: "2026-10-01T10:00:00Z", creator_id: "42",
  character_id: "abc123", character_name: "Luna", type: "TYPE_ONE_ON_ONE" }], meta: { next_token: "secret-next" } };
const turn = (id, t, name, human, cands, primary, pinned = false) => {
  const o = { turn_key: { chat_id: "chat-1", turn_id: id }, create_time: t, last_update_time: t, state: "STATE_OK",
    author: human ? { author_id: "42", is_human: true, name } : { author_id: "abc123", name },
    candidates: cands.map((c, i) => ({ candidate_id: `${id}-${i}`, create_time: t, raw_content: c, is_final: true })),
    primary_candidate_id: `${id}-${primary}` };
  if (pinned) o.is_pinned = true; // real API only includes the key on pinned turns
  return o;
};
const HISTORY = { turns: [ // newest first, like the real paginated endpoint
  turn("t3", "2026-10-01T10:03:00Z", "Luna", false, ["Fine, chamomile.", "Earl Grey, obviously."], 1),
  turn("t2", "2026-10-01T10:02:00Z", "Alex", true, ["Remember: I love Alishan oolong."], 0, true),
  turn("t1", "2026-10-01T10:01:00Z", "Luna", false, ["*yawns* Oh, Alex..."], 0),
], meta: { next_token: "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnop" } };
const WS_NEW = { command: "add_turn", turn: turn("t4", "2026-10-01T10:04:00Z", "Luna", false, ["Sweet dreams~"], 0) };

const PAGE = `<!doctype html><html><body>mock c.ai<script>
  (async () => {
    const j = (u, o) => fetch(u, o).then(r => r.json());
    await j("https://neo.character.ai/user/");
    await j("https://neo.character.ai/character/v1/get_character_info", { method: "POST", body: "{}" });
    await j("https://neo.character.ai/character/v1/get_character_info", { method: "POST", body: '{"x":1}' });
    await j("https://neo.character.ai/character/v1/get_user_personas");
    await j("https://neo.character.ai/chats/recent/abc123");
    await j("https://neo.character.ai/chat/chat-1/conversation-facts/");
    await j("https://subscription.api.character.ai/v1/vc/users/42/balances");   // must NOT be captured
    await j("https://neo.character.ai/turns/count");                           // must NOT be captured
    const x = new XMLHttpRequest(); x.open("GET", "https://neo.character.ai/turns/chat-1/?next_token=abc"); x.send();
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
let infoCalls = 0;
await ctx.route("https://neo.character.ai/user/", (r) => r.fulfill(json(ME)));
await ctx.route("https://neo.character.ai/character/v1/get_character_info", (r) => r.fulfill(json(infoCalls++ ? OTHER : CHAR)));
await ctx.route("https://neo.character.ai/character/v1/get_user_personas", (r) => r.fulfill(json(PERSONAS)));
await ctx.route("https://neo.character.ai/chats/recent/abc123", (r) => r.fulfill(json(RECENT)));
await ctx.route("https://neo.character.ai/chat/chat-1/conversation-facts/", (r) => r.fulfill(json(FACTS)));
await ctx.route("https://subscription.api.character.ai/**", (r) => r.fulfill(json({ balance: 999, secret_marker: "BILLING" })));
await ctx.route("https://neo.character.ai/turns/count", (r) => r.fulfill(json({ turn_counts: [{ chat_id: "OTHERCHAT" }] })));
await ctx.route("https://neo.character.ai/turns/**", (r) => r.fulfill(json(HISTORY)));
// image CDN: 800px Luna avatar exists, the persona only at 400px, Rex's avatar is broken
const img = (buf, type = "image/png") => ({ status: 200, contentType: type, body: buf });
await ctx.route("https://characterai.io/i/800/static/avatars/u/luna.webp", (r) => r.fulfill(img(png(8, 6, [200, 80, 80]), "image/webp")));
await ctx.route("https://characterai.io/i/800/static/avatars/p.webp", (r) => r.fulfill({ status: 404, body: "" }));
await ctx.route("https://characterai.io/i/400/static/avatars/p.webp", (r) => r.fulfill(img(png(4, 4, [80, 80, 200]))));
await ctx.route("https://characterai.io/i/*/static/avatars/u/rex.webp", (r) => r.fulfill({ status: 404, body: "" }));
await ctx.route("https://characterai.io/bg/moon.png", (r) => r.fulfill(img(png(16, 9, [20, 20, 60]))));
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
  await LocalCAIAssets.embed(doc);
  return { stats, doc, raw };
});
await ctx.close();

const fail = (m) => { console.error("FAIL:", m); process.exit(1); };
const { stats, doc, raw } = result;
console.log("stats", stats);
if (stats.characters !== 2 || stats.chats !== 1 || stats.turns !== 4 || stats.pinned !== 1 || stats.captures !== 8) fail("stats");
const luna = doc.characters.find((c) => c.name === "Luna");
const rex = doc.characters.find((c) => c.name === "Rex");
if (!luna.is_own || !luna.definition.includes("Hello~")) fail("own definition should be kept");
if (rex.definition !== "" || !rex.definition_withheld) fail("other creator's definition must be withheld");
if (doc.characters.some((c) => c.name === "Alex")) fail("account/persona misread as a character");
if (doc.personas.length !== 1 || !doc.personas[0].description.includes("baker")) fail("persona");
if (doc.chats[0].memories.length !== 2) fail("memories " + JSON.stringify(doc.chats[0].memories));
if (!luna.avatar_png?.startsWith("data:image/png;base64,")) fail("Luna avatar not embedded as PNG");
const dims = (d) => { const b = Buffer.from(d.split(",")[1], "base64"); return [b.readUInt32BE(16), b.readUInt32BE(20)]; };
if (dims(luna.avatar_png).join("x") !== "8x6") fail("avatar should come from the 800px URL: " + dims(luna.avatar_png));
if (!luna.background?.startsWith("data:image/png")) fail("Luna background: " + JSON.stringify({ url: luna.background_url, errs: doc.asset_errors }));
if (!doc.personas[0].avatar_png || dims(doc.personas[0].avatar_png).join("x") !== "4x4") fail("persona avatar fallback to 400px");
if (rex.avatar_png || !doc.asset_errors.some((e) => e.startsWith("Rex avatar"))) fail("broken image should be reported, not fatal");
const t = doc.chats[0].turns;
if (t.map((x) => x.id).join() !== "t1,t2,t3,t4") fail("turn order " + t.map((x) => x.id));
if (t[2].candidates[t[2].primary] !== "Earl Grey, obviously.") fail("primary candidate");
if (!t[1].pinned || !t[1].author.is_user) fail("pin");
if (doc.chats[0].character_name !== "Luna") fail("chat character name");
const rawStr = JSON.stringify(raw);
if (rawStr.includes("eyJhbGci") || !rawStr.includes("[redacted]")) fail("redaction");
if (rawStr.includes("token=abc")) fail("query string leaked");
for (const leak of ["BILLING", "OTHERCHAT", "2000-01-01", "x@example.com", "PLUS", "secret-next"])
  if (rawStr.includes(leak)) fail("raw dump leaked: " + leak);
// the redacted debug dump must still contain everything needed to rebuild the export
const N = createRequire(import.meta.url)(path.join(extDir, "src/normalize.js"));
const again = N.stats(N.normalize(raw.captures));
if (JSON.stringify(again) !== JSON.stringify({ characters: 2, chats: 1, turns: 4, pinned: 1 }))
  fail("redaction destroyed chat data: " + JSON.stringify(again));
writeFileSync(out, JSON.stringify(doc, null, 2));
console.log("PASS — wrote", out);
