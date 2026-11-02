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
    $("main").hidden = false;
  } catch {
    $("not-cai").hidden = false;
  }
}

$("export").onclick = async () => download((await ask("export")).doc, `localcai-${stamp()}.lcai.json`);
$("raw").onclick = async () => download((await ask("raw")).doc, `localcai-raw-${stamp()}.json`);
$("clear").onclick = async () => { await ask("clear"); refresh(); };

refresh();
setInterval(refresh, 1500);
