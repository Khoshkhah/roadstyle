// The tool `legend` (docs/design/dashboard_templates.md, 3.2 and 3.3): "Colour by" and the legend in one box of the bar. The list sets the colour
// option (rsSetColorField), and below it the classes of that option, in two columns. The box is built at each opening, so a later style
// (rs.setStyle) shows its own options. A page with no colour option has no such tool. The map's own "Colour by" and legend are hidden when
// the page has a bar (dashboard.css).
import {_esc} from "../popup.js";
import {O} from "./core.js";
import {COLOR_OPTIONS, _coActive, rsSetColorField} from "./color.js";
import {coLegendNow, coLegendExtra} from "./legend.js";
import {replaceTool, greyTool, getTool, wrap, LEGEND_ICON} from "./tools.js";

// the colour option of the road class bakes no legend: its classes come from the Roads box (the style's filter facts), each with its fill color
function _cbClasses(){
  const f = O.filter || {}, sw = f.swatches || {};
  return (f.classes || []).map(c => '<div class="lg-row"><span class="lg-sw" style="background:' + _esc(sw[c] || "#888") + '"></span>' + _esc(c) + "</div>").join("");
}
let _cb = null;                // the box of the tool now: {box, fill}
// the tool for the style of now: made when the page has colour options or live data, greyed out when it has none. At the start, and again for a
// new style (rs.setStyle); the tool keeps its place in the bar
export function useColorBox(){
  if(!(O.dashboard && O.dashboard.toolbar)) return;
  const want = COLOR_OPTIONS.length || O.live, has = getTool("legend") && !getTool("legend").disabled;       // a live-data page has the legend of its data, with no colour option
  if(!want){ _cb = null; if(has) greyTool("legend"); return; }
  if(has){ const t = getTool("legend"); t.title = t.el.querySelector("button").title = COLOR_OPTIONS.length ? "Colour by and legend" : "Legend"; return; }
  const b = document.createElement("button"), d = wrap(b), box = document.createElement("div");
  b.type = "button"; b.title = COLOR_OPTIONS.length ? "Colour by and legend" : "Legend"; b.innerHTML = LEGEND_ICON;
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
  _cb = {box, fill};
  replaceTool("legend", "box", d, {title: b.title, open, close: () => { box.hidden = true; }, isOpen: () => !box.hidden});
}
export function initColorBox(){
  document.addEventListener("rs:colorchange", () => { if(_cb && !_cb.box.hidden) _cb.fill(); });
  document.addEventListener("rs:datachange", () => { if(_cb && !_cb.box.hidden) _cb.fill(); });                // live data: a new day, a new legend
  useColorBox();
}
