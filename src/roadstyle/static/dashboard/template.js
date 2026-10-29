// The dashboard template's phone form (roadstyle::dashboard, docs/design/dashboard_templates.md): the class `rs-phone` on <html> at the
// phone width or less (the first paint sets it; this keeps it current), and the bottom sheet of a sidebar (three heights: closed, 40 %, full).
// The rules are in dashboard.css, under `html.rs-phone`.
import {map, O} from "./core.js";
const SHEETS = 3;
let _sheet = null;                                  // the function that sets the sheet's height (0: closed, 1: 40 %, 2: full)
export function setSheet(n){ if(_sheet) _sheet(n); }
export function initTemplate(){
  const d = O.dashboard;
  if(!d) return;
  const q = matchMedia("(max-width:" + d.phone.max_width_px + "px)");
  const set = ()=>{ document.documentElement.classList.toggle("rs-phone", q.matches); };
  set(); q.addEventListener("change", set);
  new ResizeObserver(()=>map.resize()).observe(map.getContainer());       // the map's box changes with the form (the sheet, the report below)
  if(d.panel && d.phone.panel === "sheet"){
    // the sidebar is injected after this script runs: the grip is made when the page is parsed
    const grip = ()=>makeGrip();
    document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", grip) : grip();
  }
}
// the grip above the sheet: a tap goes to the next height, a drag of 30 px or more goes one height up or down
function makeGrip(){
  const root = document.documentElement, g = document.createElement("div");
  g.className = "rs-grip"; g.title = "Panel"; g.innerHTML = "<i></i>";
  let h = 1, y0 = null;
  const show = n=>{ h = n; for(let i = 0; i < SHEETS; i++) root.classList.toggle("rs-sheet-" + i, i === h); document.dispatchEvent(new CustomEvent("rs:sheetchange", {detail: {height: h}})); };
  _sheet = show;
  g.addEventListener("pointerdown", e=>{ y0 = e.clientY; g.setPointerCapture(e.pointerId); });
  g.addEventListener("pointerup", e=>{
    if(y0 == null) return;
    const dy = e.clientY - y0; y0 = null;
    show(Math.abs(dy) < 30 ? (h + 1) % SHEETS : Math.max(0, Math.min(SHEETS - 1, h + (dy < 0 ? 1 : -1))));
  });
  g.addEventListener("pointercancel", ()=>{ y0 = null; });
  document.body.appendChild(g);
  show(1);
}
