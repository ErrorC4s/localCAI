"use strict";
const $ = (id) => document.getElementById(id);
const S = { state: null, character: null, chat: null, rows: [], card: null, abort: null };

// ── API ───────────────────────────────────────────────
async function api(path, opts = {}) {
  const headers = { "X-LocalCAI": "1", ...(opts.headers || {}) };
  if (opts.json !== undefined) { headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(opts.json); }
  const res = await fetch(path, { method: opts.method || (opts.body ? "POST" : "GET"), headers, body: opts.body, signal: opts.signal });
  if (opts.stream) return res;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}
const saveSettings = (patch) => api("/api/settings", { json: patch }).then((s) => (S.state.settings = s));

// ── UI helpers ────────────────────────────────────────
function toast(text, kind = "") {
  const t = document.createElement("div");
  t.className = "toast " + kind;
  t.textContent = text;
  $("toasts").appendChild(t);
  setTimeout(() => t.remove(), kind === "error" ? 9000 : 6000);
}
function colorFor(name) {
  let h = 0; for (const ch of name) h = (h * 31 + ch.codePointAt(0)) % 360;
  return `hsl(${h} 45% 42%)`;
}
function avatar(el, name) {
  el.textContent = [...(name.trim() || "?")][0].toUpperCase();
  el.style.background = colorFor(name);
}
// Safe mini-markdown: escape first, then *italic* / **bold**. Never injects raw HTML.
function render(text) {
  const esc = text.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  return esc.replace(/\*\*([\s\S]+?)\*\*/g, "<strong>$1</strong>").replace(/\*([^*\n]+?)\*/g, "<em>$1</em>");
}
const fill = (t, char, user) => (t || "").replaceAll("{{char}}", char).replaceAll("{{user}}", user);

// ── State / top bar ───────────────────────────────────
async function loadState() {
  S.state = await api("/api/state");
  const st = S.state.settings;
  const b = $("backend");
  b.innerHTML = "";
  for (const [key, url] of Object.entries(S.state.backends)) b.add(new Option(`${key}  (${url.replace(/^https?:\/\//, "")})`, key));
  if (st.backend && !(st.backend in S.state.backends)) b.add(new Option("custom: " + st.backend, st.backend));
  b.value = st.backend;
  const p = $("persona");
  p.length = 1;
  for (const per of S.state.library.personas) p.add(new Option(per.name, per.name));
  p.value = st.persona || "";
  $("helplines").innerHTML = "";
  for (const [region, line] of S.state.helplines) {
    const li = document.createElement("li"); li.textContent = `${region}: ${line}`; $("helplines").appendChild(li);
  }
  renderCharacters();
}

async function loadModels() {
  const sel = $("model");
  const current = S.state.settings.model;
  const r = await api("/api/models?backend=" + encodeURIComponent($("backend").value));
  sel.innerHTML = "";
  if (!r.models.length) {
    sel.add(new Option(r.error ? "⚠ runner not reachable" : "no models found", ""));
    if (current) sel.add(new Option(current, current));
    if (r.error) toast(r.error, "warn");
  } else {
    sel.add(new Option("— pick a model —", ""));
    for (const m of r.models) sel.add(new Option(m, m));
    if (current && !r.models.includes(current)) sel.add(new Option(current + " (not found)", current));
  }
  sel.value = current || "";
}

$("backend").onchange = async () => { await saveSettings({ backend: $("backend").value }); loadModels(); };
$("model").onchange = () => saveSettings({ model: $("model").value });
$("refresh-models").onclick = loadModels;
$("persona").onchange = () => saveSettings({ persona: $("persona").value });

// ── Characters ────────────────────────────────────────
function renderCharacters() {
  const nav = $("characters");
  nav.innerHTML = "";
  for (const c of S.state.library.characters) {
    const btn = document.createElement("button");
    btn.className = "char-item" + (S.character === c.file ? " active" : "");
    const av = document.createElement("div"); av.className = "avatar"; avatar(av, c.name);
    const info = document.createElement("div"); info.className = "grow";
    const nm = document.createElement("div"); nm.textContent = c.name;
    const meta = document.createElement("div"); meta.className = "meta";
    meta.textContent = `${c.chats.length} chat${c.chats.length === 1 ? "" : "s"} · ${c.memories} memories`;
    info.append(nm, meta);
    btn.append(av, info);
    btn.onclick = () => openCharacter(c.file);
    nav.appendChild(btn);
  }
  $("welcome").hidden = !!S.character;
}

function charInfo(file) { return S.state.library.characters.find((c) => c.file === file); }

async function openCharacter(file, chatFile) {
  S.character = file;
  const c = charInfo(file);
  renderCharacters();
  $("welcome").hidden = true;
  $("chat-view").hidden = false;
  $("head-name").textContent = c.name;
  avatar($("head-avatar"), c.name);
  $("head-sub").textContent = [c.tagline, c.creator && `by ${c.creator}`, `${c.memories} memories`].filter(Boolean).join(" · ");
  $("download-card").href = `/api/card/${encodeURIComponent(file)}.png`;
  const pick = $("chat-picker");
  pick.innerHTML = "";
  for (const ch of c.chats) {
    const when = new Date(ch.modified * 1000).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
    pick.add(new Option(`${when} · ${ch.messages} msgs`, ch.file));
  }
  pick.hidden = !c.chats.length;
  if (chatFile || c.chats.length) await openChat(chatFile || c.chats[0].file);
  else { S.chat = null; S.rows = []; renderMessages(); }
}
$("chat-picker").onchange = () => openChat($("chat-picker").value);

async function openChat(chatFile) {
  S.chat = chatFile;
  $("chat-picker").value = chatFile;
  const r = await api(`/api/chat?character=${encodeURIComponent(S.character)}&chat=${encodeURIComponent(chatFile)}`);
  S.rows = r.rows; S.card = r.card;
  renderMessages();
}

$("new-chat").onclick = async () => {
  if (!(await ensureAdult())) return;
  const r = await api("/api/chat/new", { json: { character: S.character } });
  await loadState();
  await openCharacter(S.character, r.chat);
};

// ── Messages ──────────────────────────────────────────
function msgEl(row) {
  const el = document.createElement("div");
  el.className = "msg" + (row.is_user ? " user" : "");
  const who = document.createElement("div"); who.className = "who";
  who.textContent = row.name || "";
  if (row.extra && row.extra.pinned) { const p = document.createElement("span"); p.className = "pin"; p.textContent = "📌 pinned"; who.appendChild(p); }
  const body = document.createElement("div"); body.className = "body"; body.innerHTML = render(row.mes || "");
  el.append(who, body);
  return el;
}
function renderMessages() {
  const box = $("messages");
  box.innerHTML = "";
  if (!S.chat) {
    const p = document.createElement("p"); p.className = "muted";
    p.textContent = "No chats yet. Click “New chat” to start one.";
    box.appendChild(p);
  }
  for (const r of S.rows) box.appendChild(msgEl(r));
  box.scrollTop = box.scrollHeight;
  const canTalk = !!S.chat;
  $("input").disabled = !canTalk; $("send").disabled = !canTalk;
  $("regen").disabled = !canTalk || !S.rows.length || S.rows[S.rows.length - 1].is_user;
}

async function ensureAdult() {
  if (S.state.settings.age_confirmed) return true;
  const d = $("age-dialog");
  d.showModal();
  return new Promise((resolve) => {
    $("age-yes").onclick = async () => { d.close(); await saveSettings({ age_confirmed: true }); resolve(true); };
    $("age-no").onclick = () => { d.close(); toast("Sorry, chat is for adults only.", "warn"); resolve(false); };
  });
}

async function reply(path, payload) {
  if (!(await ensureAdult())) return false;
  if (!S.state.settings.model) { toast("Pick a model in the top bar first.", "warn"); return false; }
  const box = $("messages");
  const bot = msgEl({ name: (S.card && S.card.name) || "", mes: "" });
  bot.classList.add("streaming");
  box.appendChild(bot); box.scrollTop = box.scrollHeight;
  const body = bot.querySelector(".body");
  S.abort = new AbortController();
  $("stop").hidden = false; $("send").disabled = true; $("regen").disabled = true;
  let text = "";
  try {
    const res = await api(path, { json: payload, stream: true, signal: S.abort.signal });
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.error || res.statusText); }
    if (res.headers.get("X-LocalCAI-Crisis") === "1") $("crisis").hidden = false;
    const reader = res.body.getReader(); const dec = new TextDecoder();
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      text += dec.decode(value, { stream: true });
      body.innerHTML = render(text);
      box.scrollTop = box.scrollHeight;
    }
  } catch (e) {
    if (e.name !== "AbortError") { toast(e.message, "error"); bot.remove(); }
  } finally {
    S.abort = null; $("stop").hidden = true; bot.classList.remove("streaming");
  }
  await openChat(S.chat); // reload from disk: the server is the source of truth
  return true;
}

$("composer").onsubmit = async (e) => {
  e.preventDefault();
  const text = $("input").value.trim();
  if (!text || !S.chat) return;
  const userName = $("persona").value || S.state.settings.user_name || "User";
  $("messages").appendChild(msgEl({ name: userName, is_user: true, mes: text }));
  $("input").value = "";
  const ok = await reply("/api/chat/send", { character: S.character, chat: S.chat, text });
  if (!ok) $("input").value = text;
};
$("input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("composer").requestSubmit(); }
});
$("regen").onclick = () => {
  if (S.rows.length && !S.rows[S.rows.length - 1].is_user) { S.rows.pop(); renderMessages(); }
  reply("/api/chat/regenerate", { character: S.character, chat: S.chat });
};
$("stop").onclick = () => S.abort && S.abort.abort();
$("crisis-close").onclick = () => ($("crisis").hidden = true);

// ── Import ────────────────────────────────────────────
async function importFiles(files) {
  let last = null;
  for (const f of files) {
    try {
      const r = await api("/api/import", { body: f, headers: { "X-Filename": encodeURIComponent(f.name).replace(/%20/g, " ") } });
      const parts = [];
      if (r.characters.length) parts.push(`${r.characters.length} character(s): ${r.characters.map((c) => c.name).join(", ")}`);
      if (r.chats.length) parts.push(`${r.chats.length} chat(s), ${r.chats.reduce((n, c) => n + c.messages, 0)} messages`);
      if (r.personas.length) parts.push(`persona: ${r.personas.join(", ")}`);
      toast(`Imported ${f.name}\n` + (parts.join("\n") || "nothing recognised"), parts.length ? "" : "warn");
      for (const w of r.warnings) toast(w, "warn");
      if (r.characters.length) last = r.characters[0].name;
    } catch (e) { toast(`${f.name}: ${e.message}`, "error"); }
  }
  await loadState();
  if (last) {
    const c = S.state.library.characters.find((x) => x.name === last);
    if (c) openCharacter(c.file);
  }
}
$("file-input").onchange = (e) => { importFiles([...e.target.files]); e.target.value = ""; };
let dragDepth = 0;
window.addEventListener("dragenter", (e) => { if (e.dataTransfer?.types?.includes("Files")) { dragDepth++; $("drop-overlay").hidden = false; } });
window.addEventListener("dragleave", () => { if (--dragDepth <= 0) { dragDepth = 0; $("drop-overlay").hidden = true; } });
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => {
  e.preventDefault(); dragDepth = 0; $("drop-overlay").hidden = true;
  if (e.dataTransfer?.files?.length) importFiles([...e.dataTransfer.files]);
});

// ── Settings ──────────────────────────────────────────
$("open-settings").onclick = () => {
  const s = S.state.settings;
  $("set-user-name").value = s.user_name || "";
  $("set-custom-url").value = s.backend in S.state.backends ? "" : s.backend;
  $("set-temperature").value = s.temperature; $("temp-val").textContent = s.temperature;
  $("set-max-tokens").value = s.max_tokens;
  $("lib-path").textContent = S.state.library_path;
  $("settings-dialog").showModal();
};
$("set-temperature").oninput = () => ($("temp-val").textContent = $("set-temperature").value);
$("settings-cancel").onclick = () => $("settings-dialog").close();
$("settings-save").onclick = async () => {
  const patch = { user_name: $("set-user-name").value.trim(), temperature: parseFloat($("set-temperature").value),
    max_tokens: parseInt($("set-max-tokens").value, 10) || 512 };
  const custom = $("set-custom-url").value.trim();
  if (custom) patch.backend = custom;
  else if (!(S.state.settings.backend in S.state.backends)) patch.backend = "ollama";
  await saveSettings(patch);
  $("settings-dialog").close();
  await loadState(); loadModels();
};

// ── Boot ──────────────────────────────────────────────
loadState().then(loadModels).catch((e) => toast("Couldn't load: " + e.message, "error"));
