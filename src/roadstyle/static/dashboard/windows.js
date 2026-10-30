// The window rules (docs/design/dashboard_templates.md, 3.3). A floating window (Street View, Google 3D) opens in the middle of the free part of the
// map, the part that no panel and no bar covers (float.js asks `freeArea`). With `windows.clamp` (the template `dashboard`) it also stays inside that part
// at every change: a drag, a resize, a panel that opens or closes, a bar that moves. It keeps the size that the person gave it (`__want`), shrinks to
// the free part, and grows back when the part grows. On a phone a window is a bottom sheet, and one sheet is open at a time.
import {map, O} from "./core.js";
import {getTool} from "./tools.js";
import {setSheet} from "./template.js";

const _wGap = 12;
export const _wPhone = () => document.documentElement.classList.contains("rs-phone");
const _wVis = e => !!e && getComputedStyle(e).display !== "none" && e.getBoundingClientRect().width > 0;
// the part of the map that no panel and no bar covers, in window coordinates: {lo, hi} across, {top, bottom} down. On a phone the bar is at the top and
// the sheet is at the bottom: its upper edge is the grip (a closed sheet has the grip alone).
export function freeArea(){
  const m = map.getContainer().getBoundingClientRect();
  let lo = m.left, hi = m.right, top = m.top, bottom = m.bottom;
  const bar = document.getElementById("rs-toolbar");
  if(_wPhone()){
    const grip = document.querySelector(".rs-grip"), sb = document.getElementById("sb"), edge = _wVis(grip) ? grip : _wVis(sb) ? sb : null;
    if(edge) bottom = Math.min(bottom, edge.getBoundingClientRect().top);
    if(_wVis(bar)) top = Math.max(top, bar.getBoundingClientRect().bottom + 8);
    return {lo, hi, top, bottom};
  }
  for(const p of document.querySelectorAll("#sb, .rs-side")){
    if(!_wVis(p)) continue;
    const r = p.getBoundingClientRect();
    (r.left + r.right) / 2 < innerWidth / 2 ? lo = Math.max(lo, r.right) : hi = Math.min(hi, r.left);
  }
  if(_wVis(bar)){
    const r = bar.getBoundingClientRect(), e = bar.dataset.edge;
    if(e === "right") hi = Math.min(hi, r.left - 8); else if(e === "left") lo = Math.max(lo, r.right + 8);
    else if(e === "top") top = Math.max(top, r.bottom + 8); else if(e === "bottom") bottom = Math.min(bottom, r.top - 8);
  }
  return {lo, hi, top, bottom};
}
const _wClamp = (v, a, b) => Math.max(a, Math.min(v, Math.max(a, b)));
function _wFit(w){
  if(!w || w.hidden) return;
  const f = freeArea();
  // the size that the person gave it: a change that is not ours (w.__set) is the person's
  if(!w.__want || (w.__set && (Math.abs(w.offsetWidth - w.__set.w) > 1 || Math.abs(w.offsetHeight - w.__set.h) > 1))) w.__want = {w: w.offsetWidth, h: w.offsetHeight};
  const W = Math.min(w.__want.w, f.hi - f.lo - 2 * _wGap), H = Math.min(w.__want.h, f.bottom - f.top - 2 * _wGap);
  w.__set = {w: W, h: H};
  Object.assign(w.style, {width: W + "px", height: H + "px"});
  const r = w.getBoundingClientRect();
  Object.assign(w.style, {left: _wClamp(r.left, f.lo + _wGap, f.hi - W - _wGap) + "px", top: _wClamp(r.top, f.top + _wGap, f.bottom - H - _wGap) + "px", right: "auto", bottom: "auto"});
}
export function initWindows(){
  const D = O.dashboard;
  if(!D) return;
  const wins = () => [...document.querySelectorAll(".rs-svw:not(.rs-svw-dock)")];
  // a phone: one sheet is open at a time (the panel's, the Street View window, the Google 3D window)
  const close = id => { const t = getTool(id); if(t && t.isOpen && t.isOpen()) t.close(); };
  document.addEventListener("rs:streetviewchange", e => { if(e.detail.open && _wPhone()){ close("google_3d"); setSheet(0); } });
  document.addEventListener("rs:google3dchange", e => { if(e.detail.open && _wPhone()){ close("street_view"); setSheet(0); } });
  document.addEventListener("rs:sheetchange", e => { if(e.detail.height > 0 && _wPhone()){ close("street_view"); close("google_3d"); } });
  if(!D.windows.clamp) return;
  const keep = () => { if(!_wPhone()) wins().forEach(_wFit); };
  // the free part changes: a panel opens or closes (with its slide), the bar moves or slides, the window is resized, the layout changes
  const watch = () => {
    const mo = new MutationObserver(keep);
    for(const e of document.querySelectorAll("#sb, .rs-side, #rs-toolbar")) mo.observe(e, {attributes: true, attributeFilter: ["style", "class", "data-edge"]});
    mo.observe(document.documentElement, {attributes: true, attributeFilter: ["class"]});
    mo.observe(document.body, {attributes: true, attributeFilter: ["class"]});
    const slide = () => { const t0 = performance.now(); (function f(){ keep(); if(performance.now() - t0 < 500) requestAnimationFrame(f); })(); };
    for(const e of document.querySelectorAll("#sb, .rs-side, #rs-toolbar")) e.addEventListener("transitionrun", slide);
    const ro = new ResizeObserver(keep); wins().forEach(w => ro.observe(w));
    // a window being dragged is clamped at each move; one that ended without a pointerup does not stay in the drag state
    document.addEventListener("pointermove", () => document.querySelectorAll(".rs-svw.rs-drag").forEach(_wFit), true);
    document.addEventListener("pointerup", () => setTimeout(keep, 0), true);
    const opened = new MutationObserver(l => l.forEach(x => setTimeout(() => _wFit(x.target), 120)));
    wins().forEach(w => opened.observe(w, {attributes: true, attributeFilter: ["hidden"]}));
    addEventListener("resize", keep); map.on("resize", () => setTimeout(keep, 0)); document.addEventListener("rs:layoutchange", keep);
  };
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", watch) : watch();
}
