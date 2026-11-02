// Runs in the page's own JS world (MAIN) so it can see the data the C.ai web app loads.
// PASSIVE: it never makes requests of its own. It only reads *response bodies* of
// requests the page already makes. Request headers (where login tokens live) are never touched.
(() => {
  if (window.__localcaiInjected) return;
  window.__localcaiInjected = true;

  // ALLOWLIST: only the endpoints that hold chats, characters, pins, memory and personas.
  // Everything else (billing, subscriptions, analytics, account details...) is never collected.
  const ALLOW = [
    /^\/turns\/[^/]+\/?$/,                         // chat history pages (incl. pins & swipes)
    /^\/chat\/[^/]+\/?$/,                          // chat metadata
    /^\/chat\/[^/]+\/conversation-facts\/?$/,      // C.ai chat memory
    /^\/chats\/recent\/[^/]+\/?$/,                 // chat list for one character
    /^\/character\/v1\/get_character_info\/?$/,    // character profile
    /^\/character\/v1\/get_user_personas\/?$/,     // your personas
    /^\/user\/?$/,                                 // only to learn your username (trimmed below)
    /^\/ws\/?$/,                                   // live messages
  ];
  const isCai = (url) => {
    try {
      const u = new URL(url, location.href);
      const h = u.hostname;
      if (!(h === "neo.character.ai" || h === "plus.character.ai")) return false;
      if (u.pathname === "/turns/count/" || u.pathname === "/turns/count") return false;
      return ALLOW.some((re) => re.test(u.pathname));
    } catch { return false; }
  };
  // From the account endpoint keep only what we need to tell "your" characters apart.
  const trim = (url, data) => {
    try {
      if (/^\/user\/?$/.test(new URL(url, location.href).pathname)) {
        const u = data?.user?.user || {};
        return { user: { user: { username: u.username, account: { name: u.account?.name } } } };
      }
    } catch {}
    return data;
  };

  const post = (kind, url, body) => {
    let data;
    try { data = typeof body === "string" ? JSON.parse(body) : body; } catch { return; }
    if (!data || typeof data !== "object") return;
    // strip query strings: they can carry ids/tokens and we don't need them
    const cleanUrl = String(url).split("?")[0];
    window.postMessage({ __localcai: true, kind, url: cleanUrl, t: Date.now(), data: trim(url, data) }, location.origin);
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
