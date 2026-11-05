// The panel's sections (docs/guides/dashboard-panel.md): the panel starts empty, and the page adds each section, with `rs.sections` or with the
// typed option `dashboard.panel.sections`. A section holds the page's own HTML (`html` or `el`) or a part of roadstyle (`part`: "query",
// "road_card"), at the end of the panel or beside an earlier section. A section with a `label` is a card: the label is its title row, `fold` makes it
// fold, `open` makes the card one button that opens something, `note` is one line of state under the title, `background: false` takes its colour away. A section without a label is a block of the page's own, with no box: the card gap above and below.
import {O, _emit} from "./core.js";
import {legendRefresh} from "./legend.js";
import {queryPart} from "./query.js";
import {roadCardPart} from "./roadcard.js";
const _secEls = new Map();
const _secBody = () => document.querySelector("#sb .sb-body");
// the parts of roadstyle that a section can hold: each makes its element from the section's options
const _SEC_PARTS = {query: queryPart, road_card: roadCardPart};
// A card that folds (`fold: true`): its title is a button, the row has a chevron, and a click hides the body. The state of each is kept
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
  const tt = w.querySelector(":scope > .rs-sec-hd > .rs-sec-title"); if(tt) tt.setAttribute("aria-expanded", String(!on));
  _fdSet(w.dataset.rsSection, on);
  _emit("rs:sectionchange", {id: w.dataset.rsSection, state: on ? "fold" : "unfold"});
}
// a section with a label is a card: the title row (the title, a "?" of rs.help.button, then the chevron of a card that folds at the end), and the body.
// A card that folds has its title as a button (for the keyboard and a screen reader), and a click anywhere in the row folds it.
function _cardMake(w, spec){
  w.dataset.rsCard = spec.background === false ? "no-bg" : "bg";
  const hd = document.createElement("div"); hd.className = "rs-sec-hd";
  const tt = document.createElement(spec.fold || spec.open ? "button" : "div"); tt.className = "rs-sec-title"; tt.textContent = spec.label;
  hd.append(tt);
  const note = document.createElement("p"); note.className = "rs-sec-note"; note.textContent = spec.note || "";
  const body = document.createElement("div"); body.className = "rs-sec-body";
  w.append(hd, note, body);
  if(spec.fold) _fdMake(w, spec, hd, tt);
  if(spec.open) _opMake(w, spec, hd, tt);
  return body;
}
// A card that folds keeps its title row in its place on the screen (under the pointer). Without this, a card near the end of a scrolled panel jumps:
// the panel gets shorter than its scroll position, and the browser pulls the scroll back. The panel gets room under its last card for that
// (`--rs-fold-room`), and the room goes as the panel scrolls up again, by the part of it that is out of view, so nothing moves.
const _fdRoom = sc => parseFloat(sc.style.getPropertyValue("--rs-fold-room")) || 0;
function _fdTrim(sc){
  const room = _fdRoom(sc), need = Math.max(0, sc.scrollTop + sc.clientHeight - (sc.scrollHeight - room));
  if(need < room) sc.style.setProperty("--rs-fold-room", need + "px");
}
function _fdKeep(w, on){
  const sc = w.closest(".sb-body"), hd = w.querySelector(":scope > .rs-sec-hd");
  if(!sc || !hd || !sc.clientHeight){ _fdSetOne(w, on); return; }
  if(!sc.dataset.rsFoldRoom){ sc.dataset.rsFoldRoom = "1"; sc.addEventListener("scroll", () => _fdTrim(sc), {passive: true}); }
  const y = hd.getBoundingClientRect().top;
  _fdSetOne(w, on);
  const dy = hd.getBoundingClientRect().top - y;                  // more than 0: the browser pulled the scroll back
  if(dy > 0.5){ sc.style.setProperty("--rs-fold-room", (_fdRoom(sc) + dy) + "px"); sc.scrollTop += dy; }
  _fdTrim(sc);
}
function _fdMake(w, spec, hd, tt){
  w.dataset.rsFold = "1"; tt.type = "button";
  hd.insertAdjacentHTML("beforeend", _fdChev);
  hd.onclick = () => { _fdKeep(w, !w.classList.contains("folded")); _fdPaint(); };
  w.classList.toggle("folded", _fdGet(spec.id)); tt.setAttribute("aria-expanded", String(!w.classList.contains("folded")));
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
}
// A card that opens (`open: fn`): the card is one button that runs fn(card), for a card whose only work is to open the page's own panel, editor or
// dialog. Its title is a button (for the keyboard and a screen reader), the row ends with a pencil in place of the chevron (a chevron would say that it folds), the card has a light tint of the accent colour, and a click anywhere on
// the card (not in its body) runs fn. It never folds, so "collapse all" leaves it. A card whose title button is disabled does not open.
const _opIcon = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.17 6.81a1 1 0 0 0-3.99-3.99L3.84 16.17a2 2 0 0 0-.5.83l-1.32 4.35a.5.5 0 0 0 .62.62l4.35-1.32a2 2 0 0 0 .83-.5z"/><path d="m15 5 4 4"/></svg>';
function _opMake(w, spec, hd, tt){
  w.dataset.rsOpen = "1"; tt.type = "button";
  hd.insertAdjacentHTML("beforeend", _opIcon);
  w.onclick = e => { if(!tt.disabled && !e.target.closest(".rs-sec-body, .rs-help-btn")) spec.open(w); };
}
const _secNeed = id => { const w = _secEls.get(id); if(!w) throw new Error("rs.sections: no section '" + id + "' (rs.sections.list())"); return w; };
export const rsSections = {
  // the ids of the sections that are in the panel now, in order
  list(){ const b = _secBody(); return b ? [...b.querySelectorAll(".sb-sec")].map(e => e.dataset.rsSection) : []; },
  // the box of a section (the page can move it into its own tab), or null
  get(id){ return _secEls.get(id) || null; },
  // a section of the page: {id, html | el | part, label, after | before, fold | open, note, background}; at the end of the panel when it has neither. A part has its
  // options in the section: `text` (query), `fields` (road_card)
  add(spec){
    if(!spec || !spec.id) throw new Error("rs.sections.add: a section needs an id");
    if(spec.part != null && !_SEC_PARTS[spec.part]) throw new Error("rs.sections.add: no part '" + spec.part + "' (the parts: " + Object.keys(_SEC_PARTS).join(", ") + ")");
    if(_secEls.has(spec.id)) throw new Error("rs.sections.add: the section '" + spec.id + "' exists");
    const body = _secBody();
    if(!body) throw new Error("rs.sections.add: the page has no panel");
    const w = document.createElement("div"); w.className = "sb-sec"; w.dataset.rsSection = spec.id;
    if(spec.part) w.dataset.rsPart = spec.part;
    const card = spec.fold ? "fold" : spec.open ? "open" : spec.note != null ? "note" : spec.background === false ? "background: false" : "";
    if(!spec.label && card) throw new Error("rs.sections.add: '" + spec.id + "' has " + card + ": it needs a label (its title), because a section is a card only with a label");
    if(spec.open && spec.fold) throw new Error("rs.sections.add: '" + spec.id + "' has fold and open: a card that opens something does not fold");
    if(spec.open && typeof spec.open !== "function") throw new Error("rs.sections.add: '" + spec.id + "': open is a function, which runs when the card is clicked");
    const host = spec.label ? _cardMake(w, spec) : w;              // the body of a card, else the section itself
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
    _fdKeep(w, !!on); _fdPaint();
  },
  // fold (true) or unfold (false) every section that folds and is shown now: the button in the panel's title row does this. A hidden section keeps its state
  foldAll(on = true){ for(const w of _fdActive()) _fdSetOne(w, !!on); _fdPaint(); },
  // the line of state under a card's title (empty text: no line)
  note(id, text){
    const n = _secNeed(id).querySelector(":scope > .rs-sec-note");
    if(!n) throw new Error("rs.sections.note: '" + id + "' is not a card (add it with a label)");
    n.textContent = text == null ? "" : String(text);
  },
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
