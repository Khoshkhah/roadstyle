// The place of the bar and of the panel (docs/design/dashboard_templates.md, 3.1). The template gives the start (`toolbar.position`, `panel.side`);
// the person's choice, kept in this browser (settings.js), is over it. The panel's side is the class `rs-panel-left` of <html> (dashboard.css).
import {O} from "./core.js";
import {closeBoxes} from "./tools.js";
const _plKey = "rs-settings:layout";
const _plRead = () => { try{ return JSON.parse(localStorage.getItem(_plKey)) || {}; }catch(e){ return {}; } };
export const EDGES = ["left", "top", "right", "bottom"];
// the place now: the person's choice, else the template's
export function layoutNow(){
  const d = O.dashboard, s = _plRead();
  return {toolbar: s.toolbar || (d && d.toolbar && d.toolbar.position), panel: s.panel || (d && d.panel && d.panel.side), scale: s.scale !== false, look: s.look || (d && d.panel && d.panel.look)};
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
