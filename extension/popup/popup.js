const $ = (id) => document.getElementById(id);

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function ask(type) {
  const tab = await activeTab();
  return chrome.tabs.sendMessage(tab.id, { type });
}

function download(obj, name) {
  const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
  const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: name });
  document.body.appendChild(a);
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
}

const stamp = () => new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");

async function refresh() {
  try {
    const s = await ask("stats");
    for (const k of ["characters", "chats", "turns", "pinned"]) $("s-" + k).textContent = s[k];
    $("export").disabled = !s.turns && !s.characters;
    const job = s.job || {};
    $("load-all").textContent = job.running ? "■ Stop loading" : "⏫ Load full history";
    const stale = s.version !== chrome.runtime.getManifest().version;
    const msg = stale ? STALE : job.message || "";
    $("load-msg").hidden = !msg;
    $("load-msg").textContent = msg;
    $("main").hidden = false;
  } catch {
    $("not-cai").hidden = false;
  }
}

$("export").onclick = async () => {
  const btn = $("export"), prog = $("progress");
  btn.disabled = true;
  try {
    const doc = (await ask("export")).doc;
    if ($("with-images").checked) {
      prog.hidden = false;
      await LocalCAIAssets.embed(doc, (d, n) => (prog.textContent = n ? `Downloading images… ${d}/${n}` : ""));
      prog.textContent = doc.asset_errors.length
        ? `Saved. ${doc.asset_errors.length} image(s) couldn't be downloaded.` : "";
      prog.hidden = !prog.textContent;
    }
    download(doc, `localcai-${stamp()}.lcai.json`);
  } finally { btn.disabled = false; }
};
$("raw").onclick = async () => download((await ask("raw")).doc, `localcai-raw-${stamp()}.json`);
const STALE = "The extension was updated. Refresh the character.ai page (F5), then try again.";
$("load-all").onclick = async () => {
  try {
    const s = await ask("stats");
    if (!s || s.version !== chrome.runtime.getManifest().version) throw new Error(STALE);
    const ok = await ask(s.job && s.job.running ? "stopLoad" : "loadAll");
    if (!ok) throw new Error(STALE);
  } catch (e) {
    $("load-msg").hidden = false;
    $("load-msg").textContent = e.message.includes("Receiving end") ? STALE : e.message;
    return;
  }
  refresh();
};
$("clear").onclick = async () => { await ask("clear"); refresh(); };

refresh();
setInterval(refresh, 1500);
