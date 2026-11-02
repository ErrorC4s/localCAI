// Isolated-world content script: collects what inject.js saw (in memory only, this tab only)
// and answers the popup. Nothing is stored on disk or sent anywhere.
(() => {
  const MAX_CAPTURES = 20000;
  const captures = [];

  window.addEventListener("message", (ev) => {
    if (ev.source !== window || !ev.data || ev.data.__localcai !== true) return;
    const { kind, url, t, data } = ev.data;
    captures.push({ kind, url, t, data });
    if (captures.length > MAX_CAPTURES) captures.shift();
  });

  chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
    const N = globalThis.LocalCAINormalize;
    if (msg?.type === "stats") {
      reply({ captures: captures.length, ...N.stats(N.normalize(captures)) });
    } else if (msg?.type === "export") {
      reply({ doc: N.normalize(captures, { version: chrome.runtime.getManifest().version }) });
    } else if (msg?.type === "raw") {
      reply({ doc: N.redactedDump(captures) });
    } else if (msg?.type === "clear") {
      captures.length = 0;
      reply({ ok: true });
    }
    return false;
  });
})();
