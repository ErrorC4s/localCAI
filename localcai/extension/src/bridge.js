// Isolated-world content script: collects what inject.js saw (in memory only, this tab only)
// and answers the popup. Nothing is stored on disk or sent anywhere.
(() => {
  const MAX_CAPTURES = 50000;
  const captures = [];
  // History paging: C.ai's turns endpoint returns meta.next_token while older messages exist.
  // chatId/nextToken: where the oldest page we've seen says older messages continue.
  const paging = { lastPageAt: 0, reachedStart: false, chatId: null, nextToken: null, cleared: false,
                   clearedAt: 0, round: 0, needNewest: false };
  // needNewest: after Clear the chat's newest page is gone from the collection, and the page never asks for it
  // again (scrolling up only loads older pages). Only our own fetch of the newest page clears this, so
  // Load full history always starts from the newest page after a Clear.

  const seenTurns = new Set();
  function record(kind, url, t, data, t0) {
    // an answer to a request sent before Clear belongs to the old collection: never mix it in
    // (it would move the paging past the newest page and lose it)
    if (t0 && t0 < paging.clearedAt) return;
    captures.push({ kind, url, t, data });
    if (captures.length > MAX_CAPTURES) captures.shift();
    const m = /\/turns\/([^/]+)\/?$/.exec(url || "");
    if (m && Array.isArray(data?.turns)) {
      for (const tn of data.turns) seenTurns.add(tn?.turn_key?.turn_id || JSON.stringify(tn).slice(0, 120));
      paging.lastPageAt = Date.now();
      if (data.turns.length) paging.cleared = false;
      if (paging.chatId !== m[1]) {
        Object.assign(paging, { chatId: m[1], reachedStart: false, nextToken: null });
      }
      if (!data.turns.length || !data.meta || !data.meta.next_token) paging.reachedStart = true;
      else paging.nextToken = data.meta.next_token; // pages arrive newest → oldest
    }
  }

  window.addEventListener("message", (ev) => {
    if (ev.source !== window || !ev.data || ev.data.__localcai !== true) return;
    const { kind, url, t, data, t0 } = ev.data;
    record(kind, url, t, data, t0);
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
  const turnCount = () => seenTurns.size; // cheap: updated as pages arrive

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
      if (paging.needNewest) {
        // cleared (and maybe scrolled up since): start over from the newest page, so the export is complete
        // and collected in one continuous run (pages already seen just merge)
        Object.assign(paging, { reachedStart: false, nextToken: null, cleared: true });
      }
      if (paging.reachedStart) { job.message = `Already at the first message. ${job.turns} messages loaded.`; return; }
      if (await fastLoad()) return;         // direct page-by-page history requests
      if (job.stopped) return;
      if (paging.cleared) {                 // nothing left to scroll to: the page has to fetch it again
        job.message = "Cleared. Reload this C.ai page, then press Load full history again.";
        return;
      }
      job.message = "Switching to scrolling…";  // fallback: scroll like a person
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

  // Fast path: ask C.ai's history endpoint for the next older page directly, exactly the request
  // its own web app makes when you scroll up. The browser attaches your session cookie by itself;
  // the extension never reads or handles any login data. Returns false to fall back to scrolling.
  async function fastLoad() {
    // after Clear there is no next_token: start again from the newest page of the same chat
    if (!paging.chatId || (!paging.nextToken && !paging.cleared)) return false;
    let retries = 0;
    const round = paging.round;   // Clear starts a new round; this loop's late answers are then dropped
    while (!job.stopped && !paging.reachedStart && round === paging.round) {
      const url = `https://neo.character.ai/turns/${encodeURIComponent(paging.chatId)}/`;
      const t0 = Date.now();
      let res;
      try {
        res = await fetch(paging.nextToken ? `${url}?next_token=${encodeURIComponent(paging.nextToken)}` : url,
                          { credentials: "include" });
      } catch { return false; }
      if (res.status === 429 || res.status >= 500) {          // busy: back off, then fall back
        if (++retries > 3) return false;
        job.message = `C.ai is busy, waiting… ${job.turns}`;
        await sleep(3000 * retries);
        continue;
      }
      if (!res.ok) return false;
      let data;
      try { data = await res.json(); } catch { return false; }
      if (!Array.isArray(data?.turns)) return false;
      if (round !== paging.round) break;   // cleared while this page was on its way
      retries = 0;
      const wasNewest = !paging.nextToken;
      record("http", url, Date.now(), data, t0);
      if (wasNewest) paging.needNewest = false;
      job.turns = turnCount();
      job.message = `Loading older messages… ${job.turns}`;
      await sleep(200 + Math.random() * 200);
    }
    job.message = job.stopped ? `Stopped. ${job.turns} messages loaded.`
      : `Reached the first message. ${job.turns} messages loaded.`;
    return true;
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
      seenTurns.clear();
      // forget how far back we got too, or "Load full history" would think it's already done
      Object.assign(paging, { reachedStart: false, nextToken: null, cleared: true, lastPageAt: 0,
                              clearedAt: Date.now(), round: paging.round + 1, needNewest: true });
      if (job.running) job.stopped = true;   // a load in progress ends; its late answers are ignored
      else Object.assign(job, { done: false, stopped: false, turns: 0, message: "" });
      reply({ ok: true });
    }
    return false;
  });
})();
