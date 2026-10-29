// The tool `legend` (docs/design/dashboard_templates.md, 3.2 and 3.3): "Colour by" and the legend in one box of the bar. The list sets the colour
// option (rsSetColorField), and below it the classes of that option, in two columns. The box is built at each opening, so a later style
// (rs.setStyle) shows its own options. A page with no colour option has no such tool. The map's own "Colour by" and legend are hidden when
// the page has a bar (dashboard.css).
import {_esc} from "../popup.js";
import {O} from "./core.js";
import {COLOR_OPTIONS, _coActive, rsSetColorField} from "./color.js";
import {coLegendNow, coLegendExtra} from "./legend.js";
import {defineTool, wrap} from "./tools.js";

const _cbIcon = '<svg viewBox="0 0 24 24" width="20" height="20" style="display:block;margin:auto" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><rect x="4" y="4" width="6" height="6" rx="1.5" fill="currentColor"/><rect x="4" y="14" width="6" height="6" rx="1.5"/><path d="M14 7h6M14 17h6"/></svg>';
// the colour option of the road class bakes no legend: its classes come from the Roads box (the style's filter facts), each with its fill color
function _cbClasses(){
  const f = O.filter || {}, sw = f.swatches || {};
  return (f.classes || []).map(c => '<div class="lg-row"><span class="lg-sw" style="background:' + _esc(sw[c] || "#888") + '"></span>' + _esc(c) + "</div>").join("");
}
export function initColorBox(){
  if(!(O.dashboard && O.dashboard.toolbar) || !(COLOR_OPTIONS.length || O.live)) return;       // a live-data page has the legend of its data, with no colour option
  const b = document.createElement("button"), d = wrap(b), box = document.createElement("div");
  b.type = "button"; b.title = COLOR_OPTIONS.length ? "Colour by and legend" : "Legend"; b.innerHTML = _cbIcon;
  d.classList.add("rs-color-ctrl"); box.id = "rs-color-box"; box.hidden = true; d.appendChild(box);
  const fill = () => {
    const opts = COLOR_OPTIONS.map((o, i) => '<button type="button" class="rs-cb-opt' + (i === _coActive ? " on" : "") + '" role="radio" aria-checked="' + (i === _coActive) + '" data-i="' + i +
                                           '">' + _esc(o.name) + "</button>").join("");
    const lg = (coLegendNow() || _cbClasses()) + coLegendExtra();
    box.innerHTML = (COLOR_OPTIONS.length ? '<div class="rs-bm-h">Colour by</div><div class="rs-cb-opts" role="radiogroup">' + opts + "</div>" : "") +
      (lg ? (COLOR_OPTIONS.length ? "<hr>" : "") + '<div class="rs-bm-h">Legend</div><div class="rs-cb-lg">' + lg + "</div>" : "");
    box.querySelectorAll(".rs-cb-opt").forEach(o => { o.onclick = () => { rsSetColorField(parseInt(o.dataset.i, 10)); fill(); }; });
  };
  const open = () => { fill(); box.hidden = false; };
  b.onclick = e => { e.stopPropagation(); box.hidden ? open() : (box.hidden = true); };
  box.addEventListener("click", e => e.stopPropagation());                 // a click inside the box does not close it
  document.addEventListener("rs:colorchange", () => { if(!box.hidden) fill(); });
  document.addEventListener("rs:datachange", () => { if(!box.hidden) fill(); });                // live data: a new day, a new legend
  defineTool("legend", "box", d, {title: b.title, open, close: () => { box.hidden = true; }, isOpen: () => !box.hidden});
}
