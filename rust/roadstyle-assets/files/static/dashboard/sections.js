// The panel's sections (docs/guides/dashboard-panel.md): the panel starts empty, and the page adds each section, with `rs.sections` or with the
// typed option `dashboard.panel.sections`. A section holds the page's own HTML (`html` or `el`) or a part of roadstyle (`part`: "query",
// "road_card"), with an optional label, at the end of the panel or beside an earlier section.
import {O, _emit} from "./core.js";
import {legendRefresh} from "./legend.js";
import {queryPart} from "./query.js";
import {roadCardPart} from "./roadcard.js";
const _secEls = new Map();
const _secBody = () => document.querySelector("#sb .sb-body");
// the parts of roadstyle that a section can hold: each makes its element from the section's options
const _SEC_PARTS = {query: queryPart, road_card: roadCardPart};
// A section that folds (`fold: true`, with a `label`): its label is a button with a chevron, and what follows the label is its body, which a click hides. The state of each is kept
// in this browser. One button in the panel's title row (`#rs-fold-all`) folds or unfolds all the sections that fold and are shown now (not the hidden ones).
const _fdKey = id => "rs-fold:" + location.pathname + ":" + id;
const _fdGet = id => { try { return localStorage.getItem(_fdKey(id)) === "1"; } catch(e){ return false; } };
const _fdSet = (id, on) => { try { localStorage.setItem(_fdKey(id), on ? "1" : "0"); } catch(e){ /* no storage: the state is not kept */ } };
const _fdChev = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>';
const _fdAllIcon = up => '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' +
  (up ? '<path d="m7 8 5-5 5 5"/><path d="m7 16 5 5 5-5"/>' : '<path d="m7 4 5 5 5-5"/><path d="m7 20 5-5 5 5"/>') + "</svg>";
let _fdBtn = null;
const _fdActive = () => [..._secEls.values()].filter(w => w.dataset.rsFold && !w.hidden);
function _fdPaint(){
  if(!_fdBtn) return;
  const act = _fdActive(), open = act.some(w => !w.classList.contains("folded"));
  _fdBtn.hidden = !act.length;
  _fdBtn.title = open ? "Collapse all" : "Expand all"; _fdBtn.setAttribute("aria-label", _fdBtn.title); _fdBtn.innerHTML = _fdAllIcon(open);
}
function _fdSetOne(w, on){
  w.classList.toggle("folded", on);
  const hd = w.querySelector(":scope > .rs-sec-hd"); if(hd) hd.setAttribute("aria-expanded", String(!on));
  _fdSet(w.dataset.rsSection, on);
  _emit("rs:sectionchange", {id: w.dataset.rsSection, state: on ? "fold" : "unfold"});
}
function _fdMake(w, spec){
  if(!spec.label) throw new Error("rs.sections.add: a section that folds needs a label");
  w.dataset.rsFold = "1";
  const hd = document.createElement("button"); hd.type = "button"; hd.className = "rs-sec-hd"; hd.innerHTML = "<span></span>" + _fdChev; hd.firstChild.textContent = spec.label;
  const body = document.createElement("div"); body.className = "rs-sec-body";
  w.append(hd, body);
  hd.onclick = () => { _fdSetOne(w, !w.classList.contains("folded")); _fdPaint(); };
  w.classList.toggle("folded", _fdGet(spec.id)); hd.setAttribute("aria-expanded", String(!w.classList.contains("folded")));
  if(!_fdBtn){
    const top = document.querySelector("#sb .sb-top");
    if(top){
      _fdBtn = document.createElement("button"); _fdBtn.type = "button"; _fdBtn.id = "rs-fold-all";
      // the button goes BEFORE the hide-panel button, or before the box that holds it in the title row (the template wraps it in a span)
      let hide = document.getElementById("sb-hide"); while(hide && hide.parentNode !== top) hide = hide.parentNode;
      hide ? hide.before(_fdBtn) : top.append(_fdBtn);
      _fdBtn.onclick = () => rsSections.foldAll(_fdActive().some(x => !x.classList.contains("folded")));
    }
  }
  return body;
}
const _secNeed = id => { const w = _secEls.get(id); if(!w) throw new Error("rs.sections: no section '" + id + "' (rs.sections.list())"); return w; };
export const rsSections = {
  // the ids of the sections that are in the panel now, in order
  list(){ const b = _secBody(); return b ? [...b.querySelectorAll(".sb-sec")].map(e => e.dataset.rsSection) : []; },
  // the box of a section (the page can move it into its own tab), or null
  get(id){ return _secEls.get(id) || null; },
  // a section of the page: {id, html | el | part, label, after | before, fold}; at the end of the panel when it has neither. A part has its
  // options in the section: `text` (query), `fields` (road_card)
  add(spec){
    if(!spec || !spec.id) throw new Error("rs.sections.add: a section needs an id");
    if(spec.part != null && !_SEC_PARTS[spec.part]) throw new Error("rs.sections.add: no part '" + spec.part + "' (the parts: " + Object.keys(_SEC_PARTS).join(", ") + ")");
    if(_secEls.has(spec.id)) throw new Error("rs.sections.add: the section '" + spec.id + "' exists");
    const body = _secBody();
    if(!body) throw new Error("rs.sections.add: the page has no panel");
    const w = document.createElement("div"); w.className = "sb-sec"; w.dataset.rsSection = spec.id;
    if(spec.part) w.dataset.rsPart = spec.part;
    const host = spec.fold ? _fdMake(w, spec) : w;                 // the body of a section that folds, else the section itself
    if(spec.label && !spec.fold){ const l = document.createElement("label"); l.textContent = spec.label; w.appendChild(l); }
    if(spec.html) host.insertAdjacentHTML("beforeend", spec.html);
    if(spec.el) host.appendChild(spec.el);
    if(spec.part) host.appendChild(_SEC_PARTS[spec.part](spec));
    if(spec.after) _secNeed(spec.after).after(w); else if(spec.before) _secNeed(spec.before).before(w); else body.appendChild(w);
    _secEls.set(spec.id, w);
    _fdPaint();
    _emit("rs:sectionchange", {id: spec.id, state: "add"});
    return w;
  },
  // a section goes away
  remove(id){
    const w = _secNeed(id);
    w.remove(); _secEls.delete(id); _fdPaint(); _emit("rs:sectionchange", {id, state: "remove"});
  },
  hide(id){ _secNeed(id).hidden = true; _fdPaint(); _emit("rs:sectionchange", {id, state: "hide"}); },
  show(id){ _secNeed(id).hidden = false; _fdPaint(); _emit("rs:sectionchange", {id, state: "show"}); },
  // fold or unfold one section that folds (`fold: true`); the state is kept
  fold(id, on = true){
    const w = _secNeed(id);
    if(!w.dataset.rsFold) throw new Error("rs.sections.fold: '" + id + "' does not fold (add it with fold: true)");
    _fdSetOne(w, !!on); _fdPaint();
  },
  // fold (true) or unfold (false) every section that folds and is shown now: the button in the panel's title row does this. A hidden section keeps its state
  foldAll(on = true){ for(const w of _fdActive()) _fdSetOne(w, !!on); _fdPaint(); },
  // whether a section that folds is folded
  folded(id){ const w = _secNeed(id); return w.classList.contains("folded"); },
};
// the typed options: the sections that the page added, and the legend's rows
export function initSections(){
  const p = O.dashboard && O.dashboard.panel;
  if(!p) return;
  const run = () => {
    for(const s of p.sections || []) rsSections.add(s);
    legendRefresh();
  };
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", run) : run();
}
