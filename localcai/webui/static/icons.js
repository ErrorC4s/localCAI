// localCAI icon set — drawn for this app: 24×24 grid, 1.8px rounded strokes, colour from the text.
// Usage: <i data-ic="name"></i> in HTML (filled in on load), or ic("name") in JS.
const ICON_PATHS = {
  refresh: '<path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3"/><path d="M19.5 4.5v4h-4"/>',
  engine: '<rect x="6.5" y="6.5" width="11" height="11" rx="2.5"/><path d="M10 10h4v4h-4z"/>'
    + '<path d="M9.5 3.5v3M14.5 3.5v3M9.5 17.5v3M14.5 17.5v3M3.5 9.5h3M3.5 14.5h3M17.5 9.5h3M17.5 14.5h3"/>',
  settings: '<path d="M4 7h8.5M16.5 7H20M4 12h2.5M10.5 12H20M4 17h10.5M18.5 17H20"/>'
    + '<circle cx="14.5" cy="7" r="2"/><circle cx="8.5" cy="12" r="2"/><circle cx="16.5" cy="17" r="2"/>',
  upload: '<path d="M12 15.5V4.5M7.5 9 12 4.5 16.5 9"/><path d="M4.5 15v3a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-3"/>',
  download: '<path d="M12 4.5v11M7.5 11l4.5 4.5 4.5-4.5"/><path d="M4.5 15v3a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-3"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  image: '<rect x="3.5" y="5" width="17" height="14" rx="2.5"/><circle cx="9" cy="10" r="1.6"/>'
    + '<path d="M4 17l5-4.5 3.5 3 3-2.5 4.5 4"/>',
  pencil: '<path d="M15.5 5.5l3 3L9 18H6v-3z"/><path d="M13.5 7.5l3 3"/>',
  learn: '<path d="M5 6.5A2.5 2.5 0 0 1 7.5 4h9A2.5 2.5 0 0 1 19 6.5v6a2.5 2.5 0 0 1-2.5 2.5H11l-4 3.5V15h0A2.5 2.5 0 0 1 5 12.5z"/>'
    + '<path d="M9 8.3v4M12 6.8v7M15 8.8v3"/>',
  book: '<path d="M12 6.5c-1.8-1.3-4.5-2-7.5-2v13c3 0 5.7.7 7.5 2 1.8-1.3 4.5-2 7.5-2v-13c-3 0-5.7.7-7.5 2z"/><path d="M12 6.5v13"/>',
  trash: '<path d="M4.5 7h15M10 4.5h4M6.5 7l.9 11.2a2 2 0 0 0 2 1.8h5.2a2 2 0 0 0 2-1.8L17.5 7"/><path d="M10.2 10.5v6M13.8 10.5v6"/>',
  stop: '<rect x="7" y="7" width="10" height="10" rx="2"/>',
  bolt: '<path d="M13 3.5 6 13h5l-1 7.5L17 11h-5z"/>',
  folder: '<path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/>',
  sparkle: '<path d="M11 3.5c.6 3.9 2.1 5.4 6 6-3.9.6-5.4 2.1-6 6-.6-3.9-2.1-5.4-6-6 3.9-.6 5.4-2.1 6-6z"/>'
    + '<path d="M18 15c.3 1.6.9 2.2 2.5 2.5-1.6.3-2.2.9-2.5 2.5-.3-1.6-.9-2.2-2.5-2.5 1.6-.3 2.2-.9 2.5-2.5z"/>',
  prev: '<path d="M14.5 6 8.5 12l6 6"/>',
  next: '<path d="M9.5 6l6 6-6 6"/>',
  pin: '<path d="M9 4.5h6l-1 5 3 3H7l3-3z"/><path d="M12 12.5V20"/>',
  pinned: '<path d="M9 4.5h6l-1 5 3 3H7l3-3z" fill="currentColor"/><path d="M12 12.5V20"/>',
  rewind: '<path d="M9 7.5 4.5 12 9 16.5"/><path d="M4.5 12h9.5a5 5 0 0 1 5 5v1.5"/>',
  warn: '<path d="M12 4.5 20.5 19h-17z"/><path d="M12 10v4M12 16.8v.2"/>',
  memory: '<path d="M12 4.5c-3.5 0-6 2.4-6 5.3 0 1.6.7 2.7 1.7 3.6.6.6.8 1.2.8 2v1.1h7v-1.1c0-.8.2-1.4.8-2 1-.9 1.7-2 1.7-3.6 0-2.9-2.5-5.3-6-5.3z"/>'
    + '<path d="M9.5 19.5h5"/>',
};

function ic(name, cls = "") {
  return `<svg class="ic ${cls}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${ICON_PATHS[name] || ""}</svg>`;
}

function hydrateIcons(root = document) {
  for (const el of root.querySelectorAll("i[data-ic]")) el.outerHTML = ic(el.dataset.ic, el.className);
}
document.addEventListener("DOMContentLoaded", () => hydrateIcons());
