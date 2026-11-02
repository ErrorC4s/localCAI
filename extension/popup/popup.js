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
    $("load-msg").hidden = !job.message;
    $("load-msg").textContent = job.message || "";
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
$("load-all").onclick = async () => {
  const s = await ask("stats");
  await ask(s.job && s.job.running ? "stopLoad" : "loadAll");
  refresh();
};
$("clear").onclick = async () => { await ask("clear"); refresh(); };

refresh();
setInterval(refresh, 1500);
