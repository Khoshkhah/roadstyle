// The bar (docs/design/dashboard_templates.md, 3.2 and 3.3): the tools of the registry on one bar at an edge of the window, in the look of the
// theme. The template gives the edge (`dashboard.toolbar.position`, and `phone.toolbar` on a phone). Two tools are the bar's own: `theme`, the
// first, and `attribution`, the last. A box (the base map, the attribution) opens toward the map's center, and one box is open at a time.
import {map, O} from "./core.js";
import {closeBoxes, defineTool, fillToolbox, mountTools, setOnReplace, toolList, wrap} from "./tools.js";
import {rsSetTheme} from "./theme.js";
import {followPanels} from "./overlay.js";
import {layoutNow} from "./placement.js";

const ICON = {
  sun: '<svg viewBox="0 0 24 24" width="20" height="20" style="display:block;margin:auto" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
  moon: '<svg viewBox="0 0 24 24" width="20" height="20" style="display:block;margin:auto" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M20 14.5A8.5 8.5 0 0 1 9.5 4 8.5 8.5 0 1 0 20 14.5z"/></svg>',
  // the attribution: an italic serif "i" in a ring (the filled "info" icon looked like the help's "?" of a page)
  info: '<svg viewBox="0 0 24 24" width="20" height="20" style="display:block;margin:auto"><circle cx="12" cy="12" r="9.2" fill="none" stroke="currentColor" stroke-width="1.8"/><text x="12" y="16.7" text-anchor="middle" font-family="Georgia,serif" font-style="italic" font-weight="700" font-size="13.5" fill="currentColor">i</text></svg>',
};
const el = (tag, cls, text) => { const e = document.createElement(tag); if(cls) e.className = cls; if(text) e.textContent = text; return e; };
const button = (title, html) => { const b = el("button"); b.type = "button"; b.title = title; b.innerHTML = html; return b; };

// `theme`: the first button; it sets the page's theme (theme.js), and the sidebar's own switch is hidden
function themeTool(){
  const b = button("Light / dark", ICON.sun), d = wrap(b);
  const paint = () => { const dark = document.documentElement.dataset.rsTheme === "dark"; b.innerHTML = dark ? ICON.moon : ICON.sun; };
  b.onclick = () => rsSetTheme(document.documentElement.dataset.rsTheme === "dark" ? "light" : "dark");
  document.addEventListener("rs:themechange", paint); paint();
  document.documentElement.classList.add("rs-theme-in-bar");
  defineTool("theme", "toggle", d, {title: b.title});
}
// `attribution`: the credits of the map (MapLibre's own text, which is hidden), one row for each, and Google's where a Google window is open.
// A credit is a link with the words before it ("Data from" + OpenStreetMap); the page builds the rows from the text, never from its HTML.
const _tbOut = '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></svg>';
const _tbCredits = () => {
  const inner = map.getContainer().querySelector(".maplibregl-ctrl-attrib-inner"), rows = [];
  let pre = "";
  // MapLibre puts the credits of the sources in one line, with " | " between them: a text before a "|" is a row of its own
  for(const n of inner ? inner.childNodes : []){
    if(n.nodeType === 3) n.textContent.split("|").forEach((t, i) => {
      if(i > 0){ if(pre.trim()) rows.push({text: pre.replace(/\s+/g, " ").trim()}); pre = ""; }
      pre += t;
    });
    else if(n.tagName === "A"){ rows.push({text: (pre + " " + n.textContent).replace(/\s+/g, " ").trim(), href: n.href}); pre = ""; }
  }
  if(pre.trim()) rows.push({text: pre.replace(/\s+/g, " ").trim()});
  // MapLibre lists the credit of a source only while its tiles are on screen: a page with the blank base map shows nothing, though its data is OpenStreetMap's.
  // With no row from MapLibre, the credits that the style's sources carry are the rows (read as text with DOMParser: nothing of them runs).
  if(!rows.length) for(const s of Object.values(map.getStyle().sources || {})){
    if(!s.attribution) continue;
    const doc = new DOMParser().parseFromString(s.attribution, "text/html"), a = doc.querySelector("a");
    const text = doc.body.textContent.replace(/\s+/g, " ").trim();
    // the credit of OpenStreetMap's data is the same row as the vector styles give: "Data from" and the link to the copyright page
    /OpenStreetMap/.test(text) && !a ? rows.push({text: "Data from OpenStreetMap", href: "https://www.openstreetmap.org/copyright"}) : rows.push({text, href: a && a.href});
  }
  if([".rs-g3d", ".rs-svw:not(.rs-g3d)"].some(s => { const w = document.querySelector(s); return w && !w.hidden; }))
    rows.push({text: "Map data \u00a9 Google", href: "https://www.google.com/help/terms_maps/"});
  rows.push({text: "MapLibre", href: "https://maplibre.org"});         // the library that draws the map (BSD license)
  return rows.filter((r, i) => rows.findIndex(x => x.text === r.text) === i);
};
function attributionTool(){
  const b = button("", ICON.info), box = el("div"), d = wrap(b);
  b.setAttribute("aria-label", "Attribution");               // no tooltip: the icon and the click on it are clear (a screen reader reads the label)
  d.classList.add("rs-attr-ctrl"); box.id = "rs-attr-box"; box.hidden = true; d.appendChild(box);
  const open = () => {
    box.replaceChildren(el("div", "rs-bm-h", "Attribution"));
    for(const r of _tbCredits()){
      const web = r.href && /^https?:/.test(r.href), row = el(web ? "a" : "div", "rs-attr-row");
      row.append(el("span", "", r.text));
      if(web){ row.href = r.href; row.target = "_blank"; row.rel = "noopener noreferrer"; const o = el("span", "rs-attr-out"); o.innerHTML = _tbOut; row.append(o); }
      box.append(row);
    }
    box.hidden = false;
  };
  b.onclick = e => { e.stopPropagation(); box.hidden ? open() : (box.hidden = true); };
  defineTool("attribution", "box", d, {title: "Attribution", open, close: () => { box.hidden = true; }, isOpen: () => !box.hidden});
}
// one box is open at a time: a click outside the open box and the Escape key close it, and so does the click on another box's button
function boxRules(bar){
  const boxes = () => toolList().filter(t => t.kind === "box" && t.isOpen && t.isOpen());
  document.addEventListener("click", e => {
    for(const t of boxes()) if(!t.el.contains(e.target)) t.close();
  }, true);
  document.addEventListener("keydown", e => { if(e.key === "Escape") boxes().forEach(t => t.close()); }, true);
  bar.addEventListener("click", e => { const own = e.target.closest(".maplibregl-ctrl"); setTimeout(() => boxes().filter(t => t.el !== own).forEach(t => t.close()), 0); });
}
// a box keeps 12 px from the edge of the window: it moves up, down, left or right by what it overhangs, at each opening and each change of its size
const _tbGap = 12;
const _tbShift = (lo, hi, size) => { const over = hi - (size - _tbGap), under = _tbGap - lo; return over > 0 ? -over : under > 0 ? under : 0; };
function keepInside(box){
  const fit = () => {
    if(box.hidden || (box.classList.contains("bm-menu") && !box.classList.contains("open"))) return;
    box.style.translate = "0 0";                // a box is anchored at its top or at its bottom edge: it moves with `translate`, which works for both
    const r = box.getBoundingClientRect();
    box.style.translate = _tbShift(r.left, r.right, innerWidth) + "px " + _tbShift(r.top, r.bottom, innerHeight) + "px";
  };
  new MutationObserver(fit).observe(box, {attributes: true, attributeFilter: ["hidden", "class"]});
  new ResizeObserver(fit).observe(box);
  addEventListener("resize", fit);
}
let _tbPlace = null, _tbRerun = null, _tbEdge = null;
// the edge that the person chose (settings.js); the phone form is the template's
// the open box (the settings, from where the person chose the edge) closes first: it opened toward the map from the old edge
export function setToolbarEdge(edge){
  closeBoxes();
  _tbEdge = edge; if(_tbPlace) _tbPlace(); if(_tbRerun) _tbRerun();
}
export function initToolbar(){
  const d = O.dashboard;
  if(!d || !d.toolbar) return false;
  themeTool(); attributionTool();
  fillToolbox();                          // the places of the tools that this page cannot use: greyed out
  const bar = el("div"); bar.id = "rs-toolbar"; document.body.appendChild(bar);
  if(d.toolbar.hold){                       // a page that adds tools of its own: no bar without them at the load; rs.tools.ready() shows it, 6 s at the latest
    bar.dataset.held = "1";                  // an attribute, not a class: the bar's class is set again at each change of its edge
    const show = () => { delete bar.dataset.held; };
    document.addEventListener("rs:toolsready", show, {once: true}); setTimeout(show, 6000);
  }
  const phone = matchMedia("(max-width:" + d.phone.max_width_px + "px)");
  const place = () => { bar.className = "rs-tb-" + (phone.matches ? d.phone.toolbar : (_tbEdge || layoutNow().toolbar)); bar.dataset.edge = bar.className.slice(6); };
  _tbPlace = place; place(); phone.addEventListener("change", place);
  // on a phone the full sheet and the windows start under the bar: its lower edge (the bar has one row or two) is the css variable --rs-top
  const under = () => document.documentElement.style.setProperty("--rs-top", (phone.matches && bar.dataset.edge === "top" ? Math.ceil(bar.getBoundingClientRect().bottom) + 8 : 52) + "px");
  new ResizeObserver(under).observe(bar); phone.addEventListener("change", under); under();
  let attr = null;
  mountTools(list => {
    for(const t of list){
      if(t.id === "panel_show"){                // the chevron that brings a hidden panel back is not a tool of the bar
        const f = el("div"); f.id = "rs-show-right"; f.appendChild(t.el); document.body.appendChild(f); t.el.style.display = "none";
        new MutationObserver(() => { f.style.display = t.el.style.display === "none" ? "none" : "block"; }).observe(t.el, {attributes: true, attributeFilter: ["style"]});
        continue;
      }
      const w = wrap(t.el);
      if(t.id === "attribution") attr = w;
      attr && attr.parentNode === bar && t.id !== "attribution" ? bar.insertBefore(w, attr) : bar.appendChild(w);       // the credits can be in the corner box (overlay.js)
    }
  });
  boxRules(bar);
  const fitBox = t => { if(t.kind === "box"){ const box = t.el.querySelector("#rs-attr-box, #rs-color-box, #rs-nav-box, #rs-roads-box, #rs-settings-box, .bm-menu"); if(box) keepInside(box); } };
  toolList().forEach(fitBox); setOnReplace(fitBox);
  _tbRerun = followPanels(bar, () => bar.dataset.edge);
  return true;
}
