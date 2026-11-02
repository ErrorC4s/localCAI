// Isolated-world content script: collects what inject.js saw (in memory only, this tab only)
// and answers the popup. Nothing is stored on disk or sent anywhere.
(() => {
  const MAX_CAPTURES = 50000;
  const captures = [];
  // History paging: C.ai's turns endpoint returns meta.next_token while older messages exist.
  const paging = { lastPageAt: 0, reachedStart: false };

  window.addEventListener("message", (ev) => {
    if (ev.source !== window || !ev.data || ev.data.__localcai !== true) return;
    const { kind, url, t, data } = ev.data;
    captures.push({ kind, url, t, data });
    if (captures.length > MAX_CAPTURES) captures.shift();
    if (/\/turns\/[^/]+\/?$/.test(url || "") && Array.isArray(data?.turns)) {
      paging.lastPageAt = Date.now();
      if (!data.turns.length || !data.meta || !data.meta.next_token) paging.reachedStart = true;
    }
  });

  // ── Load full history: scroll the chat up like a person would ──────────────
  // The page itself fetches older messages (we never call C.ai ourselves and never touch the
  // login token); we only scroll, wait, and stop when C.ai says there's nothing older.
  const job = { running: false, done: false, stopped: false, turns: 0, message: "" };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const pause = () => 300 + Math.random() * 400; // a short, human-ish breather between pages
  async function waitForPage(since, timeout = 6000) {
    const end = Date.now() + timeout;
    while (Date.now() < end && paging.lastPageAt <= since) await sleep(100);
    return paging.lastPageAt > since;
  }
  const turnCount = () => globalThis.LocalCAINormalize.stats(globalThis.LocalCAINormalize.normalize(captures)).turns;

  function findScroller() {
    let best = null, bestScore = 0;
    for (const el of document.querySelectorAll("div, main, section, ol, ul")) {
      const cs = getComputedStyle(el);
      if (!/(auto|scroll)/.test(cs.overflowY) || el.scrollHeight <= el.clientHeight + 20) continue;
      const score = el.scrollHeight * Math.min(el.clientWidth, 2000);
      if (score > bestScore) { best = el; bestScore = score; }
    }
    // some layouts scroll the whole page instead of a chat panel
    const page = document.scrollingElement;
    if (!best && page && page.scrollHeight > page.clientHeight + 20) best = page;
    return best;
  }

  function scrollToOldest(el) {
    const reversed = getComputedStyle(el).flexDirection === "column-reverse";
    // column-reverse lists put the oldest messages at the most negative scrollTop
    el.scrollTop = reversed ? -el.scrollHeight : 0;
    el.dispatchEvent(new WheelEvent("wheel", { deltaY: -600, bubbles: true }));
    el.dispatchEvent(new Event("scroll", { bubbles: true }));
  }

  async function loadAll() {
    if (job.running) return;
    Object.assign(job, { running: true, done: false, stopped: false, message: "Looking for the chat…" });
    try {
      job.turns = turnCount();
      if (paging.reachedStart) { job.message = `Already at the first message. ${job.turns} messages loaded.`; return; }
      const el = findScroller();
      if (!el) throw new Error("Couldn't find the chat on this page. Open a chat first.");
      let idleRounds = 0;
      while (!job.stopped) {
        const before = job.turns;
        const since = paging.lastPageAt;
        scrollToOldest(el);
        await waitForPage(since);      // move on as soon as C.ai answers…
        await sleep(pause());          // …after a short pause
        job.turns = turnCount();
        job.message = `Loading older messages… ${job.turns}`;
        if (paging.reachedStart) { job.message = `Reached the first message. ${job.turns} messages loaded.`; break; }
        idleRounds = job.turns > before ? 0 : idleRounds + 1;
        if (idleRounds >= 5) { job.message = `No more messages are loading. ${job.turns} messages loaded.`; break; }
      }
      if (job.stopped) job.message = `Stopped. ${job.turns} messages loaded.`;
    } catch (e) {
      job.message = e.message;
    } finally {
      job.running = false; job.done = true;
    }
  }

  chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
    const N = globalThis.LocalCAINormalize;
    if (msg?.type === "stats") {
      reply({ captures: captures.length, ...N.stats(N.normalize(captures)), job: { ...job },
              version: chrome.runtime.getManifest().version });
    } else if (msg?.type === "export") {
      reply({ doc: N.normalize(captures, { version: chrome.runtime.getManifest().version }) });
    } else if (msg?.type === "raw") {
      reply({ doc: N.redactedDump(captures) });
    } else if (msg?.type === "loadAll") {
      loadAll();
      reply({ ok: true });
    } else if (msg?.type === "stopLoad") {
      job.stopped = true;
      reply({ ok: true });
    } else if (msg?.type === "clear") {
      captures.length = 0;
      reply({ ok: true });
    }
    return false;
  });
})();
