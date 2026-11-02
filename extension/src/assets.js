// Downloads avatars and backgrounds and embeds them in the .lcai.json document,
// so the export is complete and works offline. Runs in the extension popup,
// whose host permissions let it read images from C.ai's CDN.
//
//   avatars     → converted to PNG (Character Card PNGs must be PNG) → *.avatar_png
//   backgrounds → kept in their original format                     → *.background
// Both are data: URLs. Failures are recorded in doc.asset_errors, never fatal.
(function (root) {
  const MAX_BYTES = 15 * 1024 * 1024;

  async function fetchBlob(url) {
    const res = await fetch(url, { credentials: "omit" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    if (!blob.type.startsWith("image/")) throw new Error(`not an image (${blob.type || "unknown"})`);
    if (blob.size > MAX_BYTES) throw new Error("image too large");
    return blob;
  }

  // Try a sharper version of C.ai avatars first, fall back to the URL we were given.
  const candidates = (url) => {
    const big = url.replace("/i/400/", "/i/800/");
    return big !== url ? [big, url] : [url];
  };

  const blobToDataUrl = (blob) => new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = () => reject(r.error);
    r.readAsDataURL(blob);
  });

  async function toPng(blob) {
    if (blob.type === "image/png") return blobToDataUrl(blob);
    const bmp = await createImageBitmap(blob);
    const canvas = new OffscreenCanvas(bmp.width, bmp.height);
    canvas.getContext("2d").drawImage(bmp, 0, 0);
    bmp.close();
    return blobToDataUrl(await canvas.convertToBlob({ type: "image/png" }));
  }

  async function grab(url, asPng) {
    let lastErr;
    for (const u of candidates(url)) {
      try {
        const blob = await fetchBlob(u);
        return asPng ? await toPng(blob) : await blobToDataUrl(blob);
      } catch (e) { lastErr = e; }
    }
    throw lastErr;
  }

  async function embed(doc, onProgress = () => {}) {
    const jobs = [];
    const add = (obj, urlKey, outKey, asPng, label) => {
      if (obj && obj[urlKey]) jobs.push({ obj, url: obj[urlKey], outKey, asPng, label });
    };
    for (const c of doc.characters || []) {
      add(c, "avatar_url", "avatar_png", true, `${c.name} avatar`);
      add(c, "background_url", "background", false, `${c.name} background`);
    }
    for (const p of doc.personas || []) {
      add(p, "avatar_url", "avatar_png", true, `${p.name} avatar`);
      add(p, "background_url", "background", false, `${p.name} background`);
    }
    for (const ch of doc.chats || []) add(ch, "background_url", "background", false, `chat background`);

    doc.asset_errors = [];
    const cache = new Map(); // same image used twice → fetch once
    let done = 0;
    for (const j of jobs) {
      onProgress(done, jobs.length);
      try {
        const key = j.url + (j.asPng ? "#png" : "");
        if (!cache.has(key)) cache.set(key, grab(j.url, j.asPng));
        j.obj[j.outKey] = await cache.get(key);
      } catch (e) {
        doc.asset_errors.push(`${j.label}: ${e.message}`);
      }
      done++;
    }
    onProgress(done, jobs.length);
    return doc;
  }

  const api = { embed };
  root.LocalCAIAssets = api;
  if (typeof module !== "undefined") module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
