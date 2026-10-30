// The place of the bar and of the panel (docs/design/dashboard_templates.md, 3.1). The template gives the start (`toolbar.position`, `panel.side`);
// the person's choice, kept in this browser (settings.js), is over it. The panel's side is the class `rs-panel-left` of <html> (dashboard.css).
import {O} from "./core.js";
import {closeBoxes} from "./tools.js";
const _plKey = "rs-settings:layout";
const _plRead = () => { try{ return JSON.parse(localStorage.getItem(_plKey)) || {}; }catch(e){ return {}; } };
export const EDGES = ["left", "top", "right", "bottom"];
// the place now: the person's choice, else the template's
export function layoutNow(){
  const d = O.dashboard, s = d && d.toolbar && d.toolbar.settings ? _plRead() : {};       // no settings button: no saved choice (an old one would still win)
  return {toolbar: s.toolbar || (d && d.toolbar && d.toolbar.position), panel: s.panel || (d && d.panel && d.panel.side), scale: s.scale != null ? s.scale : !d || d.scale_box !== false, look: s.look || (d && d.panel && d.panel.look)};
}
// the place of the panel and the scale box at the start: the page's, or the person's saved choice. Always, not only with the settings button
// The free part of the window, as the padding of a camera: what covers the map is the panel (a card, a frame or the sheet of a phone) and the bar. A box that is
// taller than it is wide stands on the left or the right (the nearer edge), a box that is wider than it is tall stands on the top or the bottom. The first view fits
// into what is left (web_template.html calls `window.rsFreePad`).
export function freePad(){
  const pad = {top: 30, right: 30, bottom: 30, left: 30};
  for(const el of document.querySelectorAll("#sb, #rs-toolbar")){
    if(getComputedStyle(el).display === "none" || getComputedStyle(el).visibility === "hidden") continue;
    const r = el.getBoundingClientRect();
    if(!r.width || !r.height) continue;
    const tall = r.height >= r.width, near = (a, b) => a <= b;
    if(tall) { if(near(r.left, innerWidth - r.right)) pad.left = Math.max(pad.left, r.right + 8); else pad.right = Math.max(pad.right, innerWidth - r.left + 8); }
    else if(near(r.top, innerHeight - r.bottom)) pad.top = Math.max(pad.top, r.bottom + 8);
    else pad.bottom = Math.max(pad.bottom, innerHeight - r.top + 8);
  }
  return pad;
}
export function initPlacement(){
  window.rsFreePad = freePad;
  const p = layoutNow();
  setPanelSide(p.panel); setPanelLook(p.look); setScaleShown(p.scale);
}
export function savePlace(part, value){
  const s = _plRead(); s[part] = value;
  try{ localStorage.setItem(_plKey, JSON.stringify(s)); }catch(e){}
}
export function setPanelSide(side){
  closeBoxes();
  document.documentElement.classList.toggle("rs-panel-left", side === "left");
  document.dispatchEvent(new CustomEvent("rs:layoutchange", {detail: {panel: side}}));
}
// the scale bar and the zoom number: shown, or hidden by the person
export function setScaleShown(on){ document.documentElement.classList.toggle("rs-hide-scale", !on); }
// the look of the overlay panel: "frame" (full height, its translucent frame, curved corners on the map side) or "card" (a floating card, curved all round)
export function setPanelLook(look){ closeBoxes(); document.documentElement.classList.toggle("rs-panel-card", look === "card"); document.dispatchEvent(new CustomEvent("rs:layoutchange", {detail: {look}})); }
