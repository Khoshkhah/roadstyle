// The editor frame (docs/guides/dashboard-parts.md, "An editor in the panel"): the frame of an editor that uses the whole panel, as Edit design does. It draws into
// the host's standard dashboard panel (#sb > .sb-card with .sb-top and .sb-body). open() hides the host's title, body and "Collapse all" (#rs-fold-all) and shows the
// frame: the title line in .sb-top (before the host's hide button), the head row that does not scroll (roadstyle's tab row, the editor's own row, or both), one
// body that scrolls by the panel's protocol (rs-pbody) and a bar at the bottom edge, outside the body. close() shows the host's panel again. The editor fills
// `head`, `body` and `bar`; an empty head row or bar does not show. Each <select> in the frame gets roadstyle's select box, also one that the editor adds
// later. On a phone the panel's sheet opens to its full height while the frame is open, and the tab row is one row that scrolls sideways.
//
//   editorFrame({ panel, title, back, tabs, head, id, label }) -> EventTarget + { root, top, head, body, bar, open(tab), close(), isOpen(), tab(name) }
//   events: "back" when the person clicks the back button; "tab" {tab} when the person clicks a tab
import {initPanelScroll} from "./panelscroll.js";
import {rsSelectBoxes} from "./selectbox.js";

const _efEsc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

export function editorFrame({ panel, title, back = null, tabs = [], head: own = null, id = "rs-frame", label = title }) {
  const hostCard = panel?.querySelector?.(".sb-card"), hostBar = hostCard?.querySelector(".sb-top"), hostBody = hostCard?.querySelector(".sb-body");
  if (!hostBar?.firstElementChild || !hostBody)
    throw new Error("editor frame: give `panel`, the host's dashboard panel: an element with .sb-card, in it .sb-top (the title first, then the hide button) and .sb-body");
  const events = new EventTarget();
  // the title line: "← back" (back: null gives no button), the title; the editor can add more after it (top)
  const top = document.createElement("div");
  top.className = "rs-frame-title";
  top.innerHTML = `${back == null ? "" : `<button type="button" class="rs-frame-back" id="${id}-back">← ${_efEsc(back)}</button>`}<span class="t">${_efEsc(title)}</span>`;
  const root = document.createElement("div");
  root.className = "rs-frame"; root.setAttribute("aria-label", label);
  // the head row: the tab row, then the editor's own element (`head`). It does not scroll, and it is the body's header (data-head): a line shows under it while
  // the body is scrolled
  root.innerHTML = `<div class="rs-frame-head rs-phead" id="${id}-head">${tabs.length ? `<nav class="rs-tabs" id="${id}-tabs" role="tablist" aria-label="${_efEsc(label)}">${tabs.map(([t, n]) =>
      `<button type="button" class="rs-tab" role="tab" id="${id}-tab-${t}" data-tab="${t}" aria-controls="${id}-body" aria-selected="false">${_efEsc(n)}</button>`).join("")}</nav>` : ""}</div>`
    + `<div class="rs-pbody rs-frame-body" id="${id}-body"${tabs.length ? ' role="tabpanel"' : ""}></div><div class="rs-frame-bar"></div>`;
  const head = root.querySelector(".rs-frame-head"), body = root.querySelector(".rs-frame-body"), bar = root.querySelector(".rs-frame-bar");
  if (own) head.append(own);
  let current = null;
  /** Mark the tab `name` as the selected one (no event: the editor draws its content). */
  function tab(name) {
    if (name === undefined) return current;
    current = name;
    for (const b of root.querySelectorAll("[data-tab]")) {
      const on = b.dataset.tab === name;
      b.setAttribute("aria-selected", String(on)); b.classList.toggle("on", on);
      const row = b.parentElement;                                       // a row that scrolls sideways (a phone): the selected tab comes into view
      if (on && row.scrollWidth > row.clientWidth) { const r = row.getBoundingClientRect(), t = b.getBoundingClientRect(); row.scrollLeft += t.left - r.left - (r.width - t.width) / 2; }
    }
    if (tabs.length) body.setAttribute("aria-labelledby", `${id}-tab-${name}`);
    return current;
  }
  for (const b of root.querySelectorAll("[data-tab]")) b.addEventListener("click", () => { tab(b.dataset.tab); events.dispatchEvent(new CustomEvent("tab", { detail: { tab: b.dataset.tab } })); });
  top.querySelector(".rs-frame-back")?.addEventListener("click", () => events.dispatchEvent(new CustomEvent("back")));
  // ---- open and close: the host's title, body and "Collapse all" are kept and hidden (the "Collapse all" is for the host's cards) ----
  let hostWas = null;
  const isOpen = () => root.isConnected;
  const selects = () => { rsSelectBoxes(top); rsSelectBoxes(root); };
  const watch = new MutationObserver(selects);                             // a select that the editor adds later gets the select box too
  function open(name) {
    if (!isOpen()) {
      const hostTitle = hostBar.firstElementChild, foldAll = hostBar.querySelector("#rs-fold-all");
      hostWas = { title: hostTitle, foldAll, display: [hostTitle.style.display, hostBody.style.display, foldAll?.style.display], scroll: hostBody.scrollTop,
                  sheet: window.rs?.sheet?.() ?? null };                   // the phone's sheet: null where the page has none
      hostTitle.style.display = hostBody.style.display = "none";
      if (foldAll) foldAll.style.display = "none";
      hostBar.prepend(top); hostCard.appendChild(root);
      // the header of the body: the head row, or the host's .sb-top when the head row is empty (it does not show). The scroll protocol reads it once.
      if (!body.dataset.head) body.dataset.head = head.firstChild ? `#${id}-head` : ".sb-top";
      initPanelScroll();
      selects();
      watch.observe(root, { childList: true, subtree: true }); watch.observe(top, { childList: true, subtree: true });
      if (hostWas.sheet != null && hostWas.sheet !== 2) window.rs.sheet(2);     // the editor gets the full height
    }
    if (name !== undefined) tab(name);
  }
  function close() {
    if (!isOpen()) return;
    watch.disconnect();
    top.remove(); root.remove();
    [hostWas.title.style.display, hostBody.style.display] = hostWas.display;
    if (hostWas.foldAll) hostWas.foldAll.style.display = hostWas.display[2];
    hostBody.scrollTop = hostWas.scroll;
    if (hostWas.sheet != null && window.rs.sheet() !== hostWas.sheet) window.rs.sheet(hostWas.sheet);
  }
  return Object.assign(events, { root, top, head, body, bar, open, close, isOpen, tab });
}
