// The overlay layout (docs/design/dashboard_templates.md, 3.1): the map fills the window and the panel floats over it. The map's box never
// changes, so a panel does not resize the map. A box at the edge of the window (the bar, the scale box) slides beside an open panel (no gap, decided 2026-10-29)
// on its side, and goes back when the panel closes.
import {map, O} from "./core.js";

const root = document.documentElement;
const phone = () => root.classList.contains("rs-phone");
// a box beside a panel overlaps it by this many pixels: two boxes that only touch show a hairline between them at a fractional position
const OVERLAP = 1;
// the side of a panel: the half of the window that its box is in (a hidden panel has no box, and the callers skip it). Not by its `left`: the card
// look is 8 px from the edge
const sideOf = p => { const r = p.getBoundingClientRect(); return r.left + r.width / 2 < innerWidth / 2 ? "left" : "right"; };
// `edge`: a function that gives the edge of the box now ("right", "left", "top" or "bottom"); only a box on a side follows a panel
export function followPanels(box, edge){
  const side = () => { const e = typeof edge === "function" ? edge() : edge; return e === "right" || e === "left" ? e : null; };
  const run = () => {
    const s = side();
    box.style.left = box.style.right = "";
    if(!s || phone() || !root.classList.contains("rs-overlay")) { root.style.removeProperty("--rs-tb-off"); return; }
    if(s === "right") box.style.left = "auto";                  // a box at the right edge: its left is free
    let off = 8;
    for(const p of document.querySelectorAll("#sb, .rs-side")){
      if(sideOf(p) !== s) continue;
      const card = p.querySelector(".sb-card");      // the card is what shows: the box has 8 px of space round it (clear in the card look, the translucent frame in the frame look)
      const r = (card || p).getBoundingClientRect();
      if(getComputedStyle(p).display !== "none" && r.width > 0) off = Math.max(off, (s === "right" ? innerWidth - r.left : r.right) - OVERLAP);
    }
    box.style[s] = off + "px";
  };
  const watch = () => {
    for(const p of document.querySelectorAll("#sb, .rs-side")) new MutationObserver(run).observe(p, {attributes: true, attributeFilter: ["style", "class"]});
    new MutationObserver(run).observe(document.body, {attributes: true, attributeFilter: ["class"]});
    new MutationObserver(run).observe(root, {attributes: true, attributeFilter: ["class"]});       // the phone form
    run();
  };
  addEventListener("resize", run);
  box.style.transition = "left .15s, right .15s";
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", watch) : watch();
  return run;
}
// the scale bar and the zoom level: one small box at the bottom left, of a fixed width (so it never jumps on a zoom); its text cannot be
// selected and it ignores the pointer
export function initOverlay(){
  const d = O.dashboard;
  if(!d || d.layout !== "overlay") return;
  const scale = document.querySelector(".maplibregl-ctrl-scale"), zoom = document.querySelector(".rs-zoom");
  if(!scale && !zoom) return;
  const box = document.createElement("div"); box.id = "rs-scalebox"; document.body.appendChild(box);
  if(scale){
    const slot = document.createElement("div"); slot.className = "rs-scale-slot"; slot.appendChild(scale); box.appendChild(slot);
    const ctl = (map._controls || []).find(c => c && c.options && "maxWidth" in c.options && c._onMove);      // the longest bar: 80 px
    if(ctl){ ctl.options.maxWidth = 80; ctl._onMove(); }
  }
  if(zoom){ zoom.classList.add("rs-zoom-slot"); box.appendChild(zoom); }
  followPanels(box, () => root.classList.contains("rs-panel-left") ? "right" : "left");       // always on the side opposite to the panel
}
