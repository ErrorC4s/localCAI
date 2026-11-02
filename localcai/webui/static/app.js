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
// Real picture when we have one, coloured initial otherwise.
function avatar(el, name, src) {
  el.textContent = "";
  el.style.background = colorFor(name);
  if (src) {
    const img = new Image();
    img.alt = ""; img.src = src;
    img.onerror = () => { img.remove(); el.textContent = [...(name.trim() || "?")][0].toUpperCase(); };
    el.appendChild(img);
  } else {
    el.textContent = [...(name.trim() || "?")][0].toUpperCase();
  }
}
const enc = encodeURIComponent;
const charAvatar = (c) => (c.has_avatar ? `/api/avatar/${enc(c.file)}.png` : null);
function personaInfo() { return S.state.library.personas.find((p) => p.name === $("persona").value); }
// Safe mini-markdown: escape first, then *italic* / **bold**. Never injects raw HTML.
function render(text) {
  // Like C.ai: *actions* in soft italics, "spoken words" bright, (scene / narration) dimmed.
  const esc = String(text).trim().replace(/\r\n?/g, "\n")
    .replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  return esc.split(/\n{2,}/).map((para) => {
    let h = para.replace(/\*\*([\s\S]+?)\*\*/g, "<strong>$1</strong>").replace(/\*([^*\n]+?)\*/g, "<em>$1</em>")
      .replace(/(&quot;|“)([^\n]*?)(&quot;|”)/g, '<span class="say">$1$2$3</span>')
      // group scenes: "Tess: …" at the start of a line → speaker label
      .replace(/^([ \t]*)([A-Z\u4e00-\u9fff][\w'’ .-]{0,30}?)([:：])(?=[ \t])/gm,
        (m, sp, name, colon) => name.trim().split(/\s+/).length <= 3 ? `${sp}<b class="speaker">${name}${colon}</b>` : m);
    const scene = /^\(([\s\S]*)\)$/.test(para.trim());
    return `<p${scene ? ' class="scene"' : ""}>${h}</p>`;
  }).join("");
}
const fill = (t, char, user) => (t || "").replaceAll("{{char}}", char).replaceAll("{{user}}", user);

// ── State / top bar ───────────────────────────────────
async function loadState() {
  S.state = await api("/api/state");
  const st = S.state.settings;
  const b = $("backend");
  b.innerHTML = "";
  for (const [key, url] of Object.entries(S.state.backends))
    b.add(new Option(key === "builtin" ? "Built-in (llama.cpp)" : `${key}  (${url.replace(/^https?:\/\//, "")})`, key));
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
    sel.add(new Option(r.builtin ? "— set up in 🧠 —" : r.error ? "⚠ runner not reachable" : "no models found", ""));
    if (current) sel.add(new Option(current, current));
    if (r.error) toast(r.error, "warn");
  } else {
    sel.add(new Option("— pick a model —", ""));
    for (const m of r.models) sel.add(new Option(m, m));
    if (current && !r.models.includes(current)) sel.add(new Option(current + " (not found)", current));
  }
  sel.value = current || "";
}

$("backend").onchange = async () => { await saveSettings({ backend: $("backend").value }); loadModels(); refreshEngine(); };
$("model").onchange = async () => {
  await saveSettings({ model: $("model").value });
  if ($("backend").value === "builtin" && $("model").value) {
    await api("/api/engine/start", { json: { model: $("model").value } }).catch((e) => toast(e.message, "error"));
    refreshEngine();
  }
};

// ── Built-in engine ───────────────────────────────────
let engineTimer = null;
async function refreshEngine() {
  const builtin = $("backend").value === "builtin";
  $("open-engine").hidden = !builtin;
  const chip = $("engine-chip");
  if (!builtin) { chip.hidden = true; return; }
  const st = await api("/api/engine").catch(() => null);
  if (!st) return;
  S.engine = st;
  chip.hidden = false;
  const cpu = st.state === "ready" && !st.device;
  chip.className = "chip " + st.state + (cpu ? " slow" : "");
  chip.textContent = !st.installed ? "● engine not installed — click 🧠"
    : cpu ? "● ready · CPU (slow)"
    : { off: "● engine off", starting: "● loading model…", ready: "● ready", error: "● engine error" }[st.state];
  chip.title = st.error || (st.device ? "Running on " + st.device.name : "");
  renderEngineDialog(st);
  const busy = st.state === "starting" || (st.job && !st.job.done);
  clearTimeout(engineTimer);
  if (busy) engineTimer = setTimeout(refreshEngine, 1000);
  if (st.job && st.job.done && S.handledJob !== st.job.id) {  // a download finished (handle each job once)
    if (S.handledJob !== undefined) {
      if (st.job.error) toast(st.job.error, "error");
      else toast(st.job.message && st.job.message !== "Done" ? st.job.message : st.job.kind === "install" ? "Engine installed." : "Model downloaded.");
    }
    S.handledJob = st.job.id;
    loadModels();
  }
  if (S.handledJob === undefined) S.handledJob = st.job ? st.job.id : null;
}
function renderEngineDialog(st) {
  $("eng-status").textContent = (st.installed ? `Installed: ${st.build} (${st.version})` : "Not installed yet (about 30–80 MB download).")
    + (st.state === "ready" ? (st.device ? ` · running on ${st.device.name}` : " · running on the CPU") : "");
  $("eng-install").textContent = st.installed ? "Reinstall / update" : "Install engine";
  $("eng-upgrade").hidden = !st.cuda_upgrade;
  $("eng-folder").textContent = st.models_dir;
  const ul = $("eng-models"); ul.innerHTML = "";
  for (const m of st.models) { const li = document.createElement("li"); li.textContent = `${m.name} · ${m.size_gb} GB`; ul.appendChild(li); }
  if (!$("eng-starter").length) for (const [k, label] of Object.entries(st.starters)) $("eng-starter").add(new Option(label, k));
  const job = st.job, running = job && !job.done;
  $("eng-job").hidden = !job || (job.done && !job.error);
  if (job) { $("eng-bar").style.width = Math.round((job.progress || 0) * 100) + "%"; $("eng-msg").textContent = job.error ? `${job.message}: ${job.error}` : job.message; }
  $("eng-install").disabled = $("eng-download").disabled = !!running;
  $("eng-error").hidden = !st.error; $("eng-error").textContent = st.error || "";
}
$("open-engine").onclick = async () => { await refreshEngine(); $("engine-dialog").showModal(); };
$("eng-close").onclick = () => { $("engine-dialog").close(); loadModels(); };
const engineCall = (action, json = {}) => api("/api/engine/" + action, { json }).then(refreshEngine).catch((e) => toast(e.message, "error"));
$("eng-install").onclick = () => engineCall("install");
$("eng-download").onclick = () => engineCall("download", { model: $("eng-starter").value });
$("eng-open-folder").onclick = () => engineCall("open-folder");
$("eng-stop").onclick = () => engineCall("stop");
$("refresh-models").onclick = loadModels;
$("persona").onchange = () => saveSettings({ persona: $("persona").value });

// ── Characters ────────────────────────────────────────
function renderCharacters() {
  const nav = $("characters");
  nav.innerHTML = "";
  for (const c of S.state.library.characters) {
    const btn = document.createElement("button");
    btn.className = "char-item" + (S.character === c.file ? " active" : "");
    const av = document.createElement("div"); av.className = "avatar"; avatar(av, c.name, charAvatar(c));
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

const PRONOUN_NAMES = { "she/her": "she/her", "he/him": "he/him", "they/them": "they/them", group: "several characters" };
function pronounLabel(c) {
  if (c.pronouns) return PRONOUN_NAMES[c.pronouns] || c.pronouns;
  return c.pronouns_guess ? `${c.pronouns_guess} (guessed)` : "pronouns: not set (✎ Edit)";
}
function pronounSelect(current, guess, guessText, extra = true) {
  const sel = document.createElement("select");
  sel.add(new Option(guess ? `Auto (${guessText}: ${guess})` : `Auto (couldn't tell — please pick one)`, ""));
  for (const v of ["she/her", "he/him", "they/them"]) sel.add(new Option(v, v));
  if (extra) sel.add(new Option("Several characters (a group / narrator bot)", "group"));
  sel.value = current || "";
  return sel;
}
function charInfo(file) { return S.state.library.characters.find((c) => c.file === file); }

async function openCharacter(file, chatFile) {
  S.character = file;
  const c = charInfo(file);
  renderCharacters();
  $("welcome").hidden = true;
  $("chat-view").hidden = false;
  $("head-name").textContent = c.name;
  avatar($("head-avatar"), c.name, charAvatar(c));
  $("head-sub").textContent = [c.tagline, c.creator && `by ${c.creator}`, `${c.memories} memories`, pronounLabel(c)].filter(Boolean).join(" · ");
  $("download-card").href = `/api/card/${encodeURIComponent(file)}.png`;
  const pick = $("chat-picker");
  pick.innerHTML = "";
  for (const ch of c.chats) {
    const when = new Date(ch.modified * 1000).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
    pick.add(new Option(`${when} · ${ch.messages} msgs`, ch.file));
  }
  pick.hidden = !c.chats.length;
  if (chatFile || c.chats.length) await openChat(chatFile || c.chats[0].file);
  else { S.chat = null; S.rows = []; applyBackground(); renderMessages(); }
}
$("delete-char").onclick = async () => {
  const c = charInfo(S.character);
  if (!c || !confirm(`Delete "${c.name}" and its ${c.chats.length} chat(s)?\n\nThey're moved to the library's trash folder, so you can still recover them.`)) return;
  await api("/api/character/delete", { json: { character: S.character } });
  S.character = null; S.chat = null;
  $("chat-view").hidden = true;
  await loadState();
  toast(`Deleted ${c.name}.`);
};
$("chat-picker").onchange = () => openChat($("chat-picker").value);

const imgUrl = (sub, val) => { const [n, q] = val.split("?"); return `/api/image/${sub}/${enc(n)}${q ? "?" + q : ""}`; };
function currentChat() { const c = charInfo(S.character); return c && c.chats.find((x) => x.file === S.chat); }
function bgStyle() { return { dim: 45, blur: 0, off: false, ...((currentChat() || {}).bg_style || {}) }; }
function bgSource() {
  const c = charInfo(S.character), chat = currentChat();
  if (chat && chat.background) return { url: imgUrl("chats", chat.background), label: "This chat's picture", kind: "chat" };
  if (c && c.custom_background) return { url: imgUrl("characters", c.custom_background), label: `Your picture for every chat with ${c.name}`, kind: "character" };
  if (c && c.background) return { url: imgUrl("characters", c.background), label: "From Character.AI", kind: "imported" };
  return null;
}
function applyBackground() {
  const src = bgSource(), st = bgStyle(), on = !!src && !st.off;
  const layer = $("bg-layer");
  layer.style.backgroundImage = on ? `url("${src.url}")` : "";
  layer.style.setProperty("--bg-dim", st.dim / 100);
  layer.style.setProperty("--bg-blur", `${st.blur}px`);
  $("chat-view").classList.toggle("has-bg", on);
}
function refreshBgDialog() {
  const src = bgSource(), st = bgStyle();
  $("bg-preview").style.backgroundImage = src && !st.off ? `url("${src.url}")` : "";
  $("bg-source").textContent = !src ? "No background" : st.off ? `Hidden (${src.label})` : src.label;
  $("bg-remove").textContent = src && src.kind === "imported" && !st.off ? "Hide" : st.off ? "Show" : "Remove";
  $("bg-remove").disabled = !src;
  $("bg-dim").value = st.dim; $("bg-dim-val").textContent = `${st.dim}%`;
  $("bg-blur").value = st.blur; $("bg-blur-val").textContent = `${st.blur}px`;
  $("bg-preview").style.setProperty("--bg-dim", st.dim / 100);
  $("bg-preview").style.setProperty("--bg-blur", `${st.blur}px`);
}
async function saveBgStyle(patch) {
  const chat = currentChat(); if (!chat) return;
  chat.bg_style = { ...bgStyle(), ...patch };
  applyBackground(); refreshBgDialog();
  await api("/api/chat/background-style", { json: { chat: S.chat, ...chat.bg_style } }).catch((e) => toast(e.message, "error"));
}
$("open-bg").onclick = () => {
  if (!S.chat) return toast("Start or open a chat first.", "warn");
  const c = charInfo(S.character);
  $("bg-scope").options[1].text = `For every chat with ${c.name}`;
  refreshBgDialog(); $("bg-dialog").showModal();
};
$("bg-close").onclick = () => $("bg-dialog").close();
for (const k of ["dim", "blur"]) {
  $("bg-" + k).oninput = () => {  // live preview while dragging
    const v = +$("bg-" + k).value, unit = k === "dim" ? "%" : "px";
    $(`bg-${k}-val`).textContent = v + unit;
    for (const el of [$("bg-layer"), $("bg-preview")]) el.style.setProperty("--bg-" + k, k === "dim" ? v / 100 : `${v}px`);
  };
  $("bg-" + k).onchange = () => saveBgStyle({ [k]: +$("bg-" + k).value });
}

async function openChat(chatFile) {
  S.chat = chatFile;
  $("chat-picker").value = chatFile;
  applyBackground();
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
function msgEl(row, index) {
  const el = document.createElement("div");
  el.className = "msg" + (row.is_user ? " user" : "");
  const who = document.createElement("div"); who.className = "who";
  const face = document.createElement("span"); face.className = "avatar tiny";
  if (row.is_user) {
    const p = personaInfo();
    avatar(face, row.name || "?", p && p.avatar ? `/api/image/personas/${enc(p.avatar)}` : null);
  } else {
    const c = charInfo(S.character);
    avatar(face, row.name || "?", c ? charAvatar(c) : null);
  }
  const nm = document.createElement("span"); nm.textContent = row.name || "";
  who.append(face, nm);
  if (row.extra && row.extra.pinned) { const p = document.createElement("span"); p.className = "pin"; p.textContent = "📌 pinned"; who.appendChild(p); }
  if (row.extra && row.extra.edited) { const e = document.createElement("span"); e.className = "edited"; e.textContent = "edited"; who.appendChild(e); }
  const body = document.createElement("div"); body.className = "body"; body.innerHTML = render(row.mes || "");
  el.append(who, body);
  if (index !== undefined) el.appendChild(msgTools(row, index, el));
  return el;
}

// ── Message tools: swipe ◀ ▶, edit, pin, delete, rewind ─────
const editCall = (action, index, extra = {}) =>
  api("/api/chat/" + action, { json: { chat: S.chat, index, expect: S.rows[index].mes, ...extra } })
    .then((r) => { S.rows = r.rows; renderMessages(); })
    .catch((e) => toast(e.message, "error"));

function tool(label, title, fn) {
  const b = document.createElement("button");
  b.className = "tool"; b.type = "button"; b.textContent = label; b.title = title;
  b.onclick = (ev) => { ev.stopPropagation(); fn(); };
  return b;
}

function msgTools(row, i, el) {
  const bar = document.createElement("div"); bar.className = "tools";
  const isLast = i === S.rows.length - 1;
  const swipes = row.swipes || [row.mes];
  const sid = row.swipe_id || 0;
  if (!row.is_user && (swipes.length > 1 || isLast)) {
    const nav = document.createElement("span"); nav.className = "swipes";
    const prev = tool("◀", "Previous reply", () => editCall("swipe", i, { to: sid - 1 }));
    prev.disabled = sid === 0;
    const count = document.createElement("span"); count.textContent = `${sid + 1}/${swipes.length}`;
    const atEnd = sid === swipes.length - 1;
    const next = tool("▶", atEnd ? "Generate another reply" : "Next reply", () =>
      atEnd ? (isLast ? $("regen").click() : null) : editCall("swipe", i, { to: sid + 1 }));
    next.disabled = atEnd && !isLast;
    nav.append(prev, count, next);
    bar.appendChild(nav);
  }
  bar.append(
    tool("✏", "Edit", () => startEdit(row, i, el)),
    tool((row.extra || {}).pinned ? "📍" : "📌", (row.extra || {}).pinned ? "Unpin" : "Pin (the character always remembers pinned messages)",
      () => editCall("pin", i, { pinned: !(row.extra || {}).pinned })),
    tool("⤺", "Rewind: delete this and everything after it", () => {
      if (confirm(`Delete this message and the ${S.rows.length - i - 1} after it?`)) editCall("delete", i, { from_here: true });
    }),
    tool("🗑", "Delete this message", () => { if (confirm("Delete this message?")) editCall("delete", i); }),
  );
  return bar;
}

function startEdit(row, i, el) {
  const body = el.querySelector(".body");
  const ta = document.createElement("textarea");
  ta.className = "edit-box"; ta.value = row.mes || "";
  ta.rows = Math.min(16, Math.max(3, ta.value.split("\n").length + 1));
  const save = tool("Save", "Save changes", () => editCall("edit", i, { text: ta.value }));
  save.classList.add("primary");
  const cancel = tool("Cancel", "Discard changes", () => renderMessages());
  const btns = document.createElement("div"); btns.className = "edit-buttons"; btns.append(cancel, save);
  body.replaceWith(ta);
  el.querySelector(".tools").replaceWith(btns);
  ta.focus();
  ta.addEventListener("keydown", (e) => { if (e.key === "Escape") renderMessages(); if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) save.click(); });
}
function renderMessages() {
  const box = $("messages");
  box.innerHTML = "";
  if (!S.chat) {
    const p = document.createElement("p"); p.className = "muted";
    p.textContent = "No chats yet. Click “New chat” to start one.";
    box.appendChild(p);
  }
  S.rows.forEach((r, i) => box.appendChild(msgEl(r, i)));
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
  // the built-in engine may be loading the model for this reply: keep its status chip live
  const poll = $("backend").value === "builtin" ? setInterval(refreshEngine, 1000) : null;
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
    if (poll) { clearInterval(poll); refreshEngine(); }
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
  if (S.rows.length && !S.rows[S.rows.length - 1].is_user) { S.rows.pop(); renderMessages(); }  // the old reply stays as a swipe
  reply("/api/chat/regenerate", { character: S.character, chat: S.chat });
};

// ── Chat background & character editing ───────────────
$("bg-input").onchange = async (e) => {
  const f = e.target.files[0]; e.target.value = "";
  if (!f || !S.chat) return;
  const scope = $("bg-scope").value;
  const headers = { "Content-Type": f.type, ...(scope === "character" ? { "X-Character": enc(S.character) } : { "X-Chat": enc(S.chat) }) };
  try {
    await api("/api/chat/background", { body: f, headers });
    await loadState();
    if (bgStyle().off) await saveBgStyle({ off: false });
    applyBackground(); refreshBgDialog(); toast("Background set" + (scope === "character" ? " for every chat with this character." : " for this chat."));
  } catch (err) { toast(err.message, "error"); }
};
$("bg-remove").onclick = async () => {
  const src = bgSource(); if (!src) return;
  if (bgStyle().off) return saveBgStyle({ off: false });
  if (src.kind === "imported") return saveBgStyle({ off: true });
  try {
    if (src.kind === "chat") await api("/api/chat/background-remove", { json: { chat: S.chat, index: 0 } });
    else await api("/api/character/background-remove", { json: { character: S.character } });
    await loadState(); applyBackground(); refreshBgDialog();
  } catch (e) { toast(e.message, "error"); }
};
const CHAR_FIELDS = [["description", "Description"], ["personality", "Personality"], ["scenario", "Scenario"],
  ["first_mes", "Greeting (first message)"], ["mes_example", "Example dialogue / definition"],
  ["creator_notes", "Tagline"], ["system_prompt", "Custom instructions (optional)"]];
$("edit-char").onclick = async () => {
  if (!S.card) { const r = await api(`/api/chat?character=${enc(S.character)}&chat=${enc(S.chat || "")}`).catch(() => null); if (r) S.card = r.card; }
  const box = $("char-fields"); box.innerHTML = "";
  const ci = charInfo(S.character);
  const pl = document.createElement("label"); pl.className = "field";
  pl.textContent = "Pronouns (so the model keeps who's who straight)";
  const ps = pronounSelect(ci.pronouns, ci.pronouns_guess, "guessed from the description"); ps.id = "char-pronouns";
  pl.appendChild(ps); box.appendChild(pl);
  for (const [k, label] of CHAR_FIELDS) {
    const l = document.createElement("label"); l.className = "field"; l.textContent = label;
    const ta = document.createElement("textarea"); ta.dataset.key = k; ta.rows = k === "creator_notes" ? 1 : 4;
    ta.value = (S.card && S.card[k]) || ""; l.appendChild(ta); box.appendChild(l);
  }
  $("char-dialog-title").textContent = "Edit " + charInfo(S.character).name;
  $("char-dialog").showModal();
};
$("char-cancel").onclick = () => $("char-dialog").close();
$("char-save").onclick = async () => {
  const data = {};
  for (const ta of $("char-fields").querySelectorAll("textarea")) data[ta.dataset.key] = ta.value;
  try {
    const r = await api("/api/character/save", { json: { character: S.character, data, pronouns: $("char-pronouns").value } });
    S.card = r.card; $("char-dialog").close(); await loadState(); openCharacter(S.character, S.chat); toast("Character saved.");
  } catch (e) { toast(e.message, "error"); }
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
  $("set-reply-length").value = s.reply_length || "auto";
  $("set-recall").checked = s.recall !== false;
  $("set-pacing").checked = s.pacing !== false;
  {
    const who = $("persona").value, p = personaInfo();
    const map = s.persona_pronouns || {};
    const sel = pronounSelect(who in map ? map[who] : (who ? "" : s.user_pronouns), p && p.pronouns_guess,
      "guessed from your persona", false);
    sel.id = "set-pronouns"; $("set-pronouns").replaceWith(sel);
    $("pronouns-who").textContent = who ? `as "${who}"` : "(no persona)";
  }
  $("set-engine-variant").value = s.engine_variant; $("set-ctx").value = s.ctx_size; $("set-ngl").value = s.gpu_layers;
  api("/api/engine/devices").then((r) => {
    const sel = $("set-gpu"); sel.length = 2;
    for (const d of r.devices) sel.add(new Option(`${d.name} (${Math.round(d.mib / 1024)} GB)`, d.id));
    sel.value = s.gpu_device || "auto";
  }).catch(() => {});
  $("lib-path").textContent = S.state.library_path;
  $("settings-dialog").showModal();
};
$("set-temperature").oninput = () => ($("temp-val").textContent = $("set-temperature").value);
$("settings-cancel").onclick = () => $("settings-dialog").close();
$("settings-save").onclick = async () => {
  const patch = { user_name: $("set-user-name").value.trim(), temperature: parseFloat($("set-temperature").value),
    max_tokens: parseInt($("set-max-tokens").value, 10) || 512,
    reply_length: $("set-reply-length").value,
    engine_variant: $("set-engine-variant").value,
    recall: $("set-recall").checked,
    pacing: $("set-pacing").checked,
    persona_pronouns: { ...(S.state.settings.persona_pronouns || {}), [$("persona").value]: $("set-pronouns").value },
    ctx_size: parseInt($("set-ctx").value, 10) || 8192,
    gpu_layers: Math.max(0, parseInt($("set-ngl").value, 10) || 0),
    gpu_device: $("set-gpu").value };
  const custom = $("set-custom-url").value.trim();
  if (custom) patch.backend = custom;
  else if (!(S.state.settings.backend in S.state.backends)) patch.backend = "builtin";
  await saveSettings(patch);
  $("settings-dialog").close();
  await loadState(); loadModels();
};

// ── History analysis: 🔍 learn style, 📖 chat memory ───
let jobTimer = null;
async function watchJob(onDone) {
  clearTimeout(jobTimer);
  const j = await api("/api/job").catch(() => null);
  if (!j || !j.kind) { $("job-bar").hidden = true; return; }
  $("job-bar").hidden = j.done;
  $("job-fill").style.width = Math.round((j.progress || 0) * 100) + "%";
  $("job-msg").textContent = j.message || "";
  if (!j.done) { jobTimer = setTimeout(() => watchJob(onDone), 1000); return; }
  if (j.error) toast(j.error, "error"); else toast(j.message);
  if (onDone) onDone(j);
}
$("job-stop").onclick = () => api("/api/job/stop", { json: {} });

$("learn-style").onclick = async () => {
  if (!S.chat) return toast("Open a chat with some history first.", "warn");
  if (!(await ensureAdult())) return;
  if (!confirm("Learn how this character talks?\n\nThe model reads a sample of her replies (a minute or two), writes style notes into the character, and picks example dialogues. You can edit or undo it any time with ✎.")) return;
  try {
    await api("/api/analyze/style", { json: { character: S.character, chat: S.chat } });
    refreshEngine();
    watchJob(async () => { await loadState(); await openCharacter(S.character, S.chat); });
  } catch (e) { toast(e.message, "error"); }
};

async function openMemory() {
  const r = await api(`/api/chat?character=${enc(S.character)}&chat=${enc(S.chat)}`);
  const pinned = r.rows.filter((x) => (x.extra || {}).pinned).length;
  const book = (r.card.character_book || {}).entries || [];
  $("mem-counts").textContent = `📌 ${pinned} pinned in this chat · 🧠 ${book.length} memories from Character.AI (pins and chat memory)`;
  $("story-text").value = ((r.meta || {}).chat_metadata || {}).localcai_story || "";
  $("story-hint").textContent = `This chat has ${r.rows.length.toLocaleString()} messages. Generating reads them in parts with your model; you can stop any time and keep what was read.`;
  $("memory-dialog").showModal();
}
$("open-memory").onclick = () => (S.chat ? openMemory() : toast("Open a chat first.", "warn"));
$("memory-close").onclick = () => $("memory-dialog").close();
$("story-save").onclick = async () => {
  await api("/api/story/save", { json: { chat: S.chat, text: $("story-text").value } }).catch((e) => toast(e.message, "error"));
  toast("Saved. The character will keep this in mind.");
};
$("story-generate").onclick = async () => {
  if (!(await ensureAdult())) return;
  try {
    await api("/api/analyze/story", { json: { character: S.character, chat: S.chat, scope: +$("story-scope").value } });
    $("memory-dialog").close();
    refreshEngine();
    watchJob(() => { if (S.chat) openMemory(); });
  } catch (e) { toast(e.message, "error"); }
};

// ── Boot ──────────────────────────────────────────────
loadState().then(loadModels).then(refreshEngine).then(() => watchJob()).catch((e) => toast("Couldn't load: " + e.message, "error"));
