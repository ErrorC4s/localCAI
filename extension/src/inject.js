// Runs in the page's own JS world (MAIN) so it can see the data the C.ai web app loads.
// PASSIVE: it never makes requests of its own. It only reads *response bodies* of
// requests the page already makes. Request headers (where login tokens live) are never touched.
(() => {
  if (window.__localcaiInjected) return;
  window.__localcaiInjected = true;

  const isCai = (url) => {
    try {
      const h = new URL(url, location.href).hostname;
      return h === "character.ai" || h.endsWith(".character.ai");
    } catch { return false; }
  };

  const post = (kind, url, body) => {
    let data;
    try { data = typeof body === "string" ? JSON.parse(body) : body; } catch { return; }
    if (!data || typeof data !== "object") return;
    // strip query strings: they can carry ids/tokens and we don't need them
    const cleanUrl = String(url).split("?")[0];
    window.postMessage({ __localcai: true, kind, url: cleanUrl, t: Date.now(), data }, location.origin);
  };

  // fetch
  const origFetch = window.fetch;
  window.fetch = async function (...args) {
    const res = await origFetch.apply(this, args);
    try {
      const url = typeof args[0] === "string" ? args[0] : args[0]?.url;
      const ct = res.headers.get("content-type") || "";
      if (isCai(url) && (ct.includes("json") || ct.includes("text/plain"))) {
        res.clone().text().then((txt) => {
          try { post("http", url, JSON.parse(txt)); }
          catch { // some endpoints stream newline-delimited JSON
            for (const line of txt.split("\n")) if (line.trim()) post("http", url, line);
          }
        }).catch(() => {});
      }
    } catch {}
    return res;
  };

  // XMLHttpRequest
  const origOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this.__localcaiUrl = url;
    return origOpen.call(this, method, url, ...rest);
  };
  const origSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function (...args) {
    if (isCai(this.__localcaiUrl)) {
      this.addEventListener("load", () => {
        try {
          if (this.responseType === "" || this.responseType === "text") post("http", this.__localcaiUrl, this.responseText);
          else if (this.responseType === "json") post("http", this.__localcaiUrl, this.response);
        } catch {}
      });
    }
    return origSend.apply(this, args);
  };

  // WebSocket (new chat messages arrive here)
  const OrigWS = window.WebSocket;
  function WrappedWS(url, protocols) {
    const ws = protocols === undefined ? new OrigWS(url) : new OrigWS(url, protocols);
    if (isCai(url)) {
      ws.addEventListener("message", (ev) => {
        if (typeof ev.data === "string") post("ws", url, ev.data);
      });
    }
    return ws;
  }
  WrappedWS.prototype = OrigWS.prototype;
  for (const k of ["CONNECTING", "OPEN", "CLOSING", "CLOSED"]) WrappedWS[k] = OrigWS[k];
  window.WebSocket = WrappedWS;
})();
