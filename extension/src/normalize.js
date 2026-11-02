// Turns raw captured JSON into a .lcai.json document (docs/lcai-format.md).
//
// PROVISIONAL: the shapes recognised below are based on what's publicly known about
// C.ai's web app (turns with candidates / primary_candidate_id / is_pinned, characters with
// greeting / definition / title). They must be confirmed against a real redacted dump.
// Every rule lives in this one file, so fixing it after C.ai changes something is one edit.
(function (root) {
  const walk = function* (obj) {
    const stack = [obj];
    while (stack.length) {
      const cur = stack.pop();
      if (Array.isArray(cur)) { stack.push(...cur); }
      else if (cur && typeof cur === "object") { yield cur; stack.push(...Object.values(cur)); }
    }
  };
  const str = (v) => (v == null ? "" : String(v));
  const first = (o, ...keys) => {
    for (const k of keys) {
      let cur = o;
      for (const part of k.split(".")) cur = cur && typeof cur === "object" ? cur[part] : undefined;
      if (cur !== undefined && cur !== null && cur !== "") return cur;
    }
    return undefined;
  };

  const isTurn = (o) => Array.isArray(o.candidates) && o.author && typeof o.author === "object";
  const isCharacter = (o) =>
    typeof o.name === "string" && !isTurn(o) && !("is_human" in o) &&
    ("greeting" in o || "definition" in o || "avatar_file_name" in o ||
      (("external_id" in o || "character_id" in o) && "title" in o));
  const isChatMeta = (o) => typeof o.chat_id === "string" && (o.character_id || o.character_name) && !isTurn(o);

  function currentUsername(captures) {
    for (const c of captures) for (const o of walk(c.data)) {
      const u = o.user && typeof o.user === "object" ? o.user : null;
      if (u && typeof u.username === "string" && ("account" in u || "id" in u || "is_staff" in u)) return u.username;
    }
    return "";
  }

  function normalize(captures, opts = {}) {
    const me = currentUsername(captures);
    const characters = new Map(); // id|name -> char
    const chatMeta = new Map();   // chat_id -> meta
    const turns = new Map();      // turn_id -> {chatId, turn, t}

    for (const cap of captures) {
      for (const o of walk(cap.data)) {
        if (isTurn(o)) {
          const id = str(first(o, "turn_key.turn_id", "turn_id", "id")) || JSON.stringify(o).slice(0, 200);
          const chatId = str(first(o, "turn_key.chat_id", "chat_id")) || "unknown-chat";
          const prev = turns.get(id);
          const upd = str(first(o, "last_update_time", "create_time"));
          if (!prev || upd >= prev.upd) turns.set(id, { chatId, turn: o, upd });
        } else if (isCharacter(o)) {
          const id = str(first(o, "external_id", "character_id", "id")) || o.name;
          const prev = characters.get(id);
          const richness = (x) => str(x.definition).length + str(x.description).length + str(x.greeting).length;
          if (!prev || richness(o) >= richness(prev)) characters.set(id, o);
        }
        if (isChatMeta(o)) {
          chatMeta.set(o.chat_id, { ...(chatMeta.get(o.chat_id) || {}), ...o });
        }
      }
    }

    const outChars = [...characters.entries()].map(([id, c]) => {
      const creator = str(first(c, "user__username", "creator_name", "author.username", "author.name"));
      const isOwn = !!me && creator === me;
      const defn = str(c.definition);
      // Other creators' definitions are only kept when the platform marks them public.
      const defPublic = /public/i.test(str(first(c, "definition_visibility", "definitionVisibility")));
      const keepDef = isOwn || defPublic;
      const avatarFile = str(c.avatar_file_name);
      return {
        id, name: c.name,
        tagline: str(c.title),
        description: str(first(c, "description", "long_description")),
        greeting: str(c.greeting),
        definition: keepDef ? defn : "",
        definition_withheld: !keepDef && defn.length > 0,
        avatar_url: str(first(c, "avatar_url")) ||
          (avatarFile ? "https://characterai.io/i/400/static/avatars/" + avatarFile : null),
        creator, is_own: isOwn,
      };
    });
    const charName = (cid) => outChars.find((c) => c.id === cid)?.name;

    const byChat = new Map();
    for (const { chatId, turn } of turns.values()) {
      if (!byChat.has(chatId)) byChat.set(chatId, []);
      byChat.get(chatId).push(turn);
    }
    const outChats = [...byChat.entries()].map(([chatId, ts]) => {
      ts.sort((a, b) => str(a.create_time).localeCompare(str(b.create_time)));
      const meta = chatMeta.get(chatId) || {};
      const outTurns = ts.map((t) => {
        const cands = t.candidates.filter((c) => c && first(c, "raw_content", "text") !== undefined);
        const texts = cands.map((c) => str(first(c, "raw_content", "text")));
        let primary = cands.findIndex((c) => c.candidate_id && c.candidate_id === t.primary_candidate_id);
        if (primary < 0) primary = texts.length - 1;
        return {
          id: str(first(t, "turn_key.turn_id", "turn_id")),
          created: str(t.create_time) || null,
          author: { name: str(first(t, "author.name")), is_user: !!first(t, "author.is_human") },
          pinned: !!(t.is_pinned || t.pinned),
          candidates: texts,
          primary: Math.max(0, primary),
        };
      }).filter((t) => t.candidates.length);
      const bot = outTurns.find((t) => !t.author.is_user);
      const user = outTurns.find((t) => t.author.is_user);
      const cid = str(meta.character_id);
      return {
        id: chatId, character_id: cid || null,
        character_name: str(meta.character_name) || charName(cid) || bot?.author.name || "Unknown",
        title: str(first(meta, "name", "title")),
        created: str(meta.create_time) || outTurns[0]?.created || null,
        user_name: user?.author.name || me || "User",
        turns: outTurns,
      };
    });

    return {
      format: "localcai", version: 1,
      exported_at: (opts.now || new Date()).toISOString(),
      exporter: { name: "localCAI extension", version: opts.version || "dev", source: "character.ai" },
      characters: outChars, chats: outChats, personas: [],
    };
  }

  function stats(doc) {
    const turns = doc.chats.reduce((n, c) => n + c.turns.length, 0);
    const pinned = doc.chats.reduce((n, c) => n + c.turns.filter((t) => t.pinned).length, 0);
    return { characters: doc.characters.length, chats: doc.chats.length, turns, pinned };
  }

  // Raw dump for debugging the format. Strips anything that looks like a secret.
  const SECRET_KEY = /token|auth|password|secret|cookie|session|e-?mail|phone|api_?key|^key$/i;
  const JWT = /eyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}/g;
  function redact(v) {
    if (Array.isArray(v)) return v.map(redact);
    if (v && typeof v === "object") {
      const o = {};
      for (const [k, x] of Object.entries(v)) o[k] = SECRET_KEY.test(k) ? "[redacted]" : redact(x);
      return o;
    }
    if (typeof v === "string") return v.replace(JWT, "[redacted-jwt]");
    return v;
  }
  function redactedDump(captures) {
    return {
      format: "localcai-raw-debug", version: 1,
      note: "Response bodies only, secrets redacted. Still contains your chat text: share privately.",
      captures: captures.map((c) => ({ kind: c.kind, url: c.url, t: c.t, data: redact(c.data) })),
    };
  }

  const api = { normalize, stats, redact, redactedDump };
  root.LocalCAINormalize = api;
  if (typeof module !== "undefined") module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
