// The tool `legend` (docs/design/dashboard_templates.md, 3.2 and 3.3): "Colour by" and the legend in one box of the bar. The list sets the colour
// option (rsSetColorField), and below it the classes of that option, in two columns. The box is built at each opening, so a later style
// (rs.setStyle) shows its own options. A page with no colour option has no such tool. The map's own "Colour by" and legend are hidden when
// the page has a bar (dashboard.css).
import {_esc} from "../popup.js";
import {O, _emit} from "./core.js";
import {COLOR_OPTIONS, _coActive, rsSetColorField} from "./color.js";
import {coLegendNow, coLegendExtra} from "./legend.js";
import {replaceTool, greyTool, getTool, wrap, LEGEND_ICON} from "./tools.js";

// the colour option of the road class bakes no legend: its classes come from the Roads box (the style's filter facts), each with its fill color
function _cbClasses(){
  const f = O.filter || {}, sw = f.swatches || {};
  return (f.classes || []).map(c => '<div class="lg-row"><span class="lg-sw" style="background:' + _esc(sw[c] || "#888") + '"></span>' + _esc(c) + "</div>").join("");
}
let _cb = null;                // the box of the tool now: {box, fill}
let _cbModes = null;             // the page's own colour modes (rs.colorModes): {names, active, onChange}; they take the place of the style's colour options in the box
const _cbOptList = () => _cbModes ? _cbModes.names.map(name => ({name})) : COLOR_OPTIONS, _cbOptActive = () => _cbModes ? _cbModes.active : _coActive;
const _cbHasOpts = () => !!(COLOR_OPTIONS.length || _cbModes);
// the tool for the style of now: made when the page has colour options, colour modes or live data, greyed out when it has none. At the start, and again for a
// new style (rs.setStyle); the tool keeps its place in the bar
export function useColorBox(){
  if(!(O.dashboard && O.dashboard.toolbar)) return;
  const want = _cbHasOpts() || O.live, has = getTool("legend") && !getTool("legend").disabled;       // a live-data page has the legend of its data, with no colour option
  if(!want){ _cb = null; if(has) greyTool("legend"); return; }
  if(has){ const t = getTool("legend"); t.title = t.el.querySelector("button").title = _cbHasOpts() ? "Colour by and legend" : "Legend"; return; }
  const b = document.createElement("button"), d = wrap(b), box = document.createElement("div");
  b.type = "button"; b.title = _cbHasOpts() ? "Colour by and legend" : "Legend"; b.innerHTML = LEGEND_ICON;
  d.classList.add("rs-color-ctrl"); box.id = "rs-color-box"; box.hidden = true; d.appendChild(box);
  const fill = () => {
    const list = _cbOptList(), now = _cbOptActive();
    const opts = list.map((o, i) => '<button type="button" class="rs-cb-opt' + (i === now ? " on" : "") + '" role="radio" aria-checked="' + (i === now) + '" data-i="' + i +
                                    '">' + _esc(o.name) + "</button>").join("");
    const lg = (coLegendNow() || _cbClasses()) + coLegendExtra();
    box.innerHTML = (list.length ? '<div class="rs-bm-h">Colour by</div><div class="rs-cb-opts" role="radiogroup">' + opts + "</div>" : "") +
      (lg ? (list.length ? "<hr>" : "") + '<div class="rs-bm-h">Legend</div><div class="rs-cb-lg">' + lg + "</div>" : "");
    box.querySelectorAll(".rs-cb-opt").forEach(o => { o.onclick = () => { const i = parseInt(o.dataset.i, 10); if(_cbModes) _cbPickMode(i); else rsSetColorField(i); fill(); }; });
  };
  const open = () => { fill(); box.hidden = false; };
  b.onclick = e => { e.stopPropagation(); box.hidden ? open() : (box.hidden = true); };
  box.addEventListener("click", e => e.stopPropagation());                 // a click inside the box does not close it
  _cb = {box, fill};
  replaceTool("legend", "box", d, {title: b.title, open, close: () => { box.hidden = true; }, isOpen: () => !box.hidden});
}
const _cbRefill = () => { if(_cb && !_cb.box.hidden) _cb.fill(); };
function _cbPickMode(i){
  _cbModes.active = i;
  _emit("rs:colormode", {name: _cbModes.names[i], index: i});
  if(_cbModes.onChange) _cbModes.onChange(_cbModes.names[i], i);
}
// rs.colorModes: the page's own "Colour by" list for the legend box (a live-data page has no colour options of the style: its modes are the page's own,
// for example Traffic, Counted, How sure). `set(names, {active, onChange})`, `select(name)`, `clear()`, `active`
export const rsColorModes = {
  set(names, opts){
    if(!Array.isArray(names) || !names.length || names.some(n => typeof n !== "string" || !n)) throw new Error("rs.colorModes.set: names must be a list of texts");
    const at = opts && opts.active != null ? names.indexOf(opts.active) : 0;
    if(at < 0) throw new Error("rs.colorModes.set: active '" + opts.active + "' is not one of the names");
    _cbModes = {names: [...names], active: at, onChange: opts && opts.onChange};
    useColorBox(); _cbRefill();
  },
  select(name){
    const i = _cbModes ? _cbModes.names.indexOf(name) : -1;
    if(i < 0) throw new Error("rs.colorModes.select: no mode '" + name + "'");
    _cbPickMode(i); _cbRefill();
  },
  clear(){ _cbModes = null; useColorBox(); _cbRefill(); },
  get active(){ return _cbModes ? _cbModes.names[_cbModes.active] : null },
};
export function initColorBox(){
  document.addEventListener("rs:colorchange", () => { if(_cb && !_cb.box.hidden) _cb.fill(); });
  document.addEventListener("rs:datachange", () => { if(_cb && !_cb.box.hidden) _cb.fill(); });                // live data: a new day, a new legend
  useColorBox();
}
