// The dashboard template's phone form (roadstyle::dashboard, docs/design/dashboard_templates.md): the class `rs-phone` on <html> at the
// phone width or less (the first paint sets it; this keeps it current), and the bottom sheet of a sidebar (three heights: closed, 40 %, full).
// The rules are in dashboard.css, under `html.rs-phone`.
import {map, O} from "./core.js";
const SHEETS = 3;
let _sheet = null;                                  // the function that sets the sheet's height (0: closed, 1: 40 %, 2: full)
export function setSheet(n){ if(_sheet) _sheet(n); }
// the sheet's height now (0: closed, 1: 40 %, 2: full), or null where the page has no sheet (not a phone, or no panel)
export function getSheet(){
  const c = document.documentElement.classList, i = [...Array(SHEETS).keys()].find(i => c.contains("rs-sheet-" + i));
  return c.contains("rs-phone") && i !== undefined ? i : null;
}
// The first paint of a host page that writes its own HTML: the `first_paint` of `data/host_options.json` (the classes of <html>, the panel's width, the
// phone width). Call it before the first paint, as the script that a page of roadstyle writes does; initTemplate keeps `rs-phone` current after it.
export function rsFirstPaint(first){
  const root = document.documentElement;
  root.classList.add(...first.classes);
  if(first.panel_width_px != null) root.style.setProperty("--rs-panel-w", first.panel_width_px + "px");
  if(matchMedia("(max-width:" + first.phone_max_width_px + "px)").matches) root.classList.add("rs-phone");
}
export function initTemplate(){
  const d = O.dashboard;
  if(!d) return;
  const q = matchMedia("(max-width:" + d.phone.max_width_px + "px)");
  const set = ()=>{ document.documentElement.classList.toggle("rs-phone", q.matches); };
  set(); q.addEventListener("change", set);
  new ResizeObserver(()=>map.resize()).observe(map.getContainer());       // the map's box changes with the form (the sheet)
  if(d.panel){
    // the sidebar is injected after this script runs: the grip is made when the page is parsed
    const grip = ()=>makeGrip();
    document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", grip) : grip();
  }
}
// the grip above the sheet: a tap goes to the next height, a drag of 30 px or more goes one height up or down
function makeGrip(){
  const root = document.documentElement, g = document.createElement("div");
  g.className = "rs-grip"; g.title = "Panel";
  g.innerHTML = '<i></i><button type="button" class="rs-grip-btn" aria-label="Lower or raise the panel"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg></button>';
  let h = 1, y0 = null;
  const show = n=>{ h = n; for(let i = 0; i < SHEETS; i++) root.classList.toggle("rs-sheet-" + i, i === h); document.dispatchEvent(new CustomEvent("rs:sheetchange", {detail: {height: h}})); };
  _sheet = show;
  // the button goes one height down, and up from closed (a tap on the strip steps round the three heights, a drag of 30 px moves one)
  g.querySelector(".rs-grip-btn").addEventListener("click", ()=>show(h > 0 ? h - 1 : 1));
  g.addEventListener("pointerdown", e=>{ if(e.target.closest(".rs-grip-btn")) return; y0 = e.clientY; g.setPointerCapture(e.pointerId); });
  g.addEventListener("pointerup", e=>{
    if(y0 == null || e.target.closest(".rs-grip-btn")) return;
    const dy = e.clientY - y0; y0 = null;
    show(Math.abs(dy) < 30 ? (h + 1) % SHEETS : Math.max(0, Math.min(SHEETS - 1, h + (dy < 0 ? 1 : -1))));
  });
  g.addEventListener("pointercancel", ()=>{ y0 = null; });
  document.body.appendChild(g);
  show(1);
}
