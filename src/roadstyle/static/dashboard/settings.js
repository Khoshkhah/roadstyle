// The tool `settings` (docs/design/dashboard_templates.md, 3.2): the person's own choices, kept in this browser only (localStorage, never in the
// page file): where the bar and the panel are, how transparent the layers are, and the keys of Google and CARTO. A key that the person saves is used
// instead of the page's own key (so a person can test another key); "Clear" goes back to the page's key. A saved place is over the template's. A key
// needs a reload: Street View and the Google script read it when the page starts.
import {O} from "./core.js";
import {defineTool, wrap} from "./tools.js";
import {EDGES, layoutNow, savePlace, setPanelSide, setPanelLook, setScaleShown} from "./placement.js";
import {setToolbarEdge} from "./toolbar.js";

const _stGear = '<svg viewBox="0 0 24 24" width="20" height="20" style="display:block;margin:auto" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10.66 5.13 L10.75 2.48 L13.25 2.48 L13.34 5.13 L15.91 6.20 L17.84 4.38 L19.62 6.16 L17.80 8.09 L18.87 10.66 L21.52 10.75 L21.52 13.25 L18.87 13.34 L17.80 15.91 L19.62 17.84 L17.84 19.62 L15.91 17.80 L13.34 18.87 L13.25 21.52 L10.75 21.52 L10.66 18.87 L8.09 17.80 L6.16 19.62 L4.38 17.84 L6.20 15.91 L5.13 13.34 L2.48 13.25 L2.48 10.75 L5.13 10.66 L6.20 8.09 L4.38 6.16 L6.16 4.38 L8.09 6.20Z"/><circle cx="12" cy="12" r="3"/></svg>';
const _stEl = (tag, cls, text) => { const e = document.createElement(tag); if(cls) e.className = cls; if(text) e.textContent = text; return e; };
const _stGet = k => { try{ return localStorage.getItem(k); }catch(e){ return null; } };
const _stPut = (k, v) => { try{ v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); }catch(e){} };

// ---- the keys: the page's own key, else the one that the person saved ----
export const savedKey = name => _stGet("rs-key:" + name) || "";
const _stCarto = () => (O.basemaps || []).some(b => (b.tiles || []).some(t => /cartocdn\.com/.test(t)));
const _stKeys = [
  {name: "google", title: "Google Maps key", note: "Street View (Linked) and Google 3D", page: () => !!O.street_view_key, show: () => O.street_view === "window" || O.google_3d},
  {name: "carto", title: "CARTO key", note: "CARTO base maps", page: () => (O.basemaps || []).some(b => (b.tiles || []).some(t => /cartocdn\.com/.test(t) && /[?&]key=/.test(t))), show: _stCarto},
];

// ---- how transparent: three numbers, the tokens of popup.css (--rs-a-tb: the bar and the panel, --rs-a-box: the boxes, the popup and the tooltip,
// --rs-a-card: the card behind the text). The start values are the CSS ones; a reset takes the saved values away. ----
const _stLayers = [["tb", "Bar and panel"], ["box", "Boxes, popup, tooltip"], ["card", "Card behind the text"]];
const _stRoot = document.documentElement;
const _stApply = () => { try{ const a = JSON.parse(_stGet("rs-settings:appearance")) || {}; for(const [k] of _stLayers) if(a[k] != null) _stRoot.style.setProperty("--rs-a-" + k, a[k]); }catch(e){} };
const _stNow = k => parseFloat(getComputedStyle(_stRoot).getPropertyValue("--rs-a-" + k));

function _stSeg(label, options, current, onPick){
  const row = _stEl("div", "rs-set-row"), seg = _stEl("div", "rs-set-seg");
  row.append(_stEl("span", "rs-set-l", label));
  for(const [v, t] of options){
    const b = _stEl("button", v === current ? "on" : "", t); b.type = "button";
    b.onclick = () => { seg.querySelectorAll("button").forEach(x => x.classList.toggle("on", x === b)); onPick(v); };
    seg.append(b);
  }
  row.append(seg); return row;
}
function _stKeyRow(k){
  const box = _stEl("div", "rs-set-key"), pageKey = k.page(), saved = savedKey(k.name);
  box.append(_stEl("div", "rs-set-l", k.title));
  const inp = _stEl("input"); inp.type = "password"; inp.autocomplete = "off"; inp.spellcheck = false;
  inp.placeholder = saved ? "(a key is saved in this browser)" : pageKey ? "Paste a key to use instead of the page's" : "Paste the key";
  const row = _stEl("div", "rs-set-btns"), save = _stEl("button", "", "Save"), clear = _stEl("button", "", "Clear"), eye = _stEl("button", "", "Show");
  for(const b of [save, clear, eye]) b.type = "button";
  const note = _stEl("div", "rs-set-note", saved ? "Your saved key is used" + (pageKey ? " instead of the page's." : ".") : pageKey ? "The page's own key is used." : "No key. " + k.note + ".");
  const done = text => { note.textContent = text + " Reload the page to use it."; const r = _stEl("button", "rs-set-reload", "Reload"); r.type = "button"; r.onclick = () => location.reload(); note.append(" ", r); };
  save.onclick = () => { const v = inp.value.trim(); if(!v) return; _stPut("rs-key:" + k.name, v); inp.value = ""; done("Saved."); };
  clear.onclick = () => { _stPut("rs-key:" + k.name, null); inp.value = ""; done("Cleared."); };
  eye.onclick = () => { inp.type = inp.type === "password" ? "text" : "password"; eye.textContent = inp.type === "password" ? "Show" : "Hide"; };
  row.append(save, clear, eye); box.append(inp, row, note); return box;
}
export function initSettings(){
  _stApply();
  const d = O.dashboard;
  if(!(d && d.toolbar && d.toolbar.settings)) return;
  const b = _stEl("button"), tool = wrap(b), box = _stEl("div");
  b.type = "button"; b.title = "Settings"; b.innerHTML = _stGear;
  tool.classList.add("rs-set-ctrl"); box.id = "rs-settings-box"; box.hidden = true; tool.append(box);
  const fill = () => {
    box.replaceChildren(_stEl("div", "rs-bm-h", "Settings"));
    const now = layoutNow(), lay = _stEl("div", "rs-set-layout");
    lay.append(_stEl("div", "rs-set-h", "Layout"),
      _stSeg("Toolbar", EDGES.map(e => [e, e[0].toUpperCase() + e.slice(1)]), now.toolbar, e => { savePlace("toolbar", e); setToolbarEdge(e); }));
    if(d.panel) lay.append(_stSeg("Panel", [["left", "Left"], ["right", "Right"]], now.panel, s => { savePlace("panel", s); setPanelSide(s); }));
    if(d.panel && d.layout === "overlay") lay.append(_stSeg("Panel look", [["frame", "Frame"], ["card", "Card"]], now.look, v => { savePlace("look", v); setPanelLook(v); }));
    lay.append(_stSeg("Scale and zoom", [["show", "Show"], ["hide", "Hide"]], now.scale ? "show" : "hide", v => { savePlace("scale", v === "show"); setScaleShown(v === "show"); }));
    box.append(lay, _stEl("hr"), _stEl("div", "rs-set-h", "Transparency"));
    for(const [k, text] of _stLayers){
      const row = _stEl("label", "rs-set-slide"), val = _stEl("b", "", _stNow(k).toFixed(2)), r = _stEl("input");
      r.type = "range"; r.min = "0.1"; r.max = "1"; r.step = "0.05"; r.value = _stNow(k);
      r.oninput = () => { _stRoot.style.setProperty("--rs-a-" + k, r.value); val.textContent = (+r.value).toFixed(2);
        const a = JSON.parse(_stGet("rs-settings:appearance") || "{}"); a[k] = +r.value; _stPut("rs-settings:appearance", JSON.stringify(a)); };
      row.append(_stEl("span", "", text), r, val); box.append(row);
    }
    const reset = _stEl("button", "rs-set-reset", "Reset transparency"); reset.type = "button";
    reset.onclick = () => { for(const [k] of _stLayers) _stRoot.style.removeProperty("--rs-a-" + k); _stPut("rs-settings:appearance", null); fill(); };
    box.append(reset);
    const keys = _stKeys.filter(k => k.show());
    if(keys.length){ box.append(_stEl("hr"), _stEl("div", "rs-set-h", "Keys")); keys.forEach(k => box.append(_stKeyRow(k)));
      box.append(_stEl("div", "rs-set-note", "A key is saved in this browser only. It is never written into the page file.")); }
  };
  const open = () => { fill(); box.hidden = false; };
  b.onclick = e => { e.stopPropagation(); box.hidden ? open() : (box.hidden = true); };
  box.addEventListener("click", e => e.stopPropagation());
  defineTool("settings", "box", tool, {title: b.title, open, close: () => { box.hidden = true; }, isOpen: () => !box.hidden});
  // a window that needs a key asks for it here
  window.rsOpenSettings = () => { const t = tool; box.hidden = false; fill(); };
  const saved = layoutNow();
  if(saved.toolbar !== d.toolbar.position) setToolbarEdge(saved.toolbar);
}
