// The panel's sections (docs/guides/migrating-dashboard.md): the page adds a block to the panel, hides one of the panel's own, or moves one, with
// `rs.sections` or with the typed option `dashboard.panel.sections` / `hide`, and no longer edits the template's HTML as text. The panel's own
// sections are found by their controls, and wrapped when the first call needs them: a box with no layout of its own (`.sb-sec`, display: contents).
import {O, _emit} from "./core.js";
import {legendRefresh} from "./legend.js";
const _secControl = {base_map: "bm", colour_by: "co", legend: "sb-legend", query: "q", selected_road: "detail"};    // the id of each section's own control
const _secEls = new Map();
let _secWrapped = false;
const _secBody = () => document.querySelector("#sb .sb-body");
// each section: its label and its control (the query: through its table), in a box. A control that the page moved is not a section here
function _secWrap(){
  const body = _secBody();
  if(_secWrapped || !body) return;
  _secWrapped = true;
  for(const [id, control] of Object.entries(_secControl)){
    const own = document.getElementById(control), c = own && (own.parentNode === body ? own : own.closest(".rs-sel"));      // a select is wrapped by selectbox.js
    const last = id === "query" ? document.getElementById("tbl") : id === "legend" ? document.getElementById("sb-legend-extra") || c : c;
    if(!c || !last || c.parentNode !== body || last.parentNode !== body) continue;
    const prev = c.previousElementSibling, first = prev && prev.tagName === "LABEL" ? prev : c;
    const w = document.createElement("div"); w.className = "sb-sec"; w.dataset.rsSection = id;
    first.before(w);
    for(let n = first; n; ){ const next = n.nextSibling; w.appendChild(n); if(n === last) break; n = next; }
    _secEls.set(id, w);
  }
}
const _secNeed = id => { _secWrap(); const w = _secEls.get(id); if(!w) throw new Error("rs.sections: no section '" + id + "' (rs.sections.list())"); return w; };
export const rsSections = {
  // the ids of the sections that are in the panel now, in order
  list(){ _secWrap(); const b = _secBody(); return b ? [...b.querySelectorAll(".sb-sec")].map(e => e.dataset.rsSection) : []; },
  // the box of a section (the page can move it: rs.sections.get("query") into its own tab), or null
  get(id){ _secWrap(); return _secEls.get(id) || null; },
  // a section of the page: {id, html | el, label, after | before}; at the end of the panel when it has neither
  add(spec){
    if(!spec || !spec.id) throw new Error("rs.sections.add: a section needs an id");
    _secWrap();
    if(_secEls.has(spec.id)) throw new Error("rs.sections.add: the section '" + spec.id + "' exists");
    const body = _secBody();
    if(!body) throw new Error("rs.sections.add: the page has no panel");
    const w = document.createElement("div"); w.className = "sb-sec"; w.dataset.rsSection = spec.id; w.dataset.rsAdded = "1";
    if(spec.label){ const l = document.createElement("label"); l.textContent = spec.label; w.appendChild(l); }
    if(spec.html) w.insertAdjacentHTML("beforeend", spec.html);
    if(spec.el) w.appendChild(spec.el);
    if(spec.after) _secNeed(spec.after).after(w); else if(spec.before) _secNeed(spec.before).before(w); else body.appendChild(w);
    _secEls.set(spec.id, w);
    _emit("rs:sectionchange", {id: spec.id, state: "add"});
    return w;
  },
  // a section that the page added goes away (the panel's own sections can only be hidden)
  remove(id){
    const w = _secNeed(id);
    if(!w.dataset.rsAdded) throw new Error("rs.sections.remove: '" + id + "' is one of the panel's own sections: hide it");
    w.remove(); _secEls.delete(id); _emit("rs:sectionchange", {id, state: "remove"});
  },
  hide(id){ _secNeed(id).hidden = true; _emit("rs:sectionchange", {id, state: "hide"}); },
  show(id){ _secNeed(id).hidden = false; _emit("rs:sectionchange", {id, state: "show"}); },
};
// the typed options: the sections that the page added and the panel's own that it hides, and the legend's rows
export function initSections(){
  const p = O.dashboard && O.dashboard.panel;
  if(!p) return;
  const run = () => {
    for(const s of p.sections || []) rsSections.add(s);
    for(const h of p.hide || []) rsSections.hide(h);
    legendRefresh();
  };
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", run) : run();
}
