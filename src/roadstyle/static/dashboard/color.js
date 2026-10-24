// "colour by" recolouring: each option's fill is baked per edge (__rs_fill / __rs_fill__1 …), and the road layers' expressions (made
// in Python, render_web._fill_expr) pick the active option from the state rs_co. window.rsSetColorField sets it from your UI.
import {map, O, OVERLAYS, RS_LEAN, RoadTable, _lyr, _src} from "./core.js";
import {_tlHost} from "./panel.js";
import {coUpdateLegend} from "./legend.js";
export let COLOR_OPTIONS = [];
export let _coActive = 0;
let _qColor=null;   // [{ids, color}, ...] the rsColor groups, for the rs:colorchange event
// THE ROADS' COLOURS (audit N8): one colour for each drawn road, the feature state rs_c on its row in the role simple, which the road
// pieces and the items read: rsColor's, else rsColorBase's, else the live data's (live.js). The rows that rsColor painted are also in the
// global state rs_top (a list of rows, no colours), which the sort key reads: a painted road is drawn over the others of its level.
// rsColorBase and the live data (many roads) are not in it. ponytail: the full look (simple=False) keeps the global states rs_colors and
// rs_base (_colorsOf) until N16 removes it.
const _by = {color: new Map(), base: new Map(), live: new Map()};   // the drawing row -> its colour, for each source of colour
let _cNow = new Map();   // the rows that have rs_c now, with the colour
const _cKey = () => (O.live && O.live.color) || "rs_c";
// a road of a two-way pair drawn as one line (__rs_dup) is drawn by its twin's piece (__rs_edge2)
function _drawRow(i){ const p = RoadTable.props(i); return p && p.__rs_dup && p.__rs_edge2 != null ? +p.__rs_edge2 : i; }
// the groups' colours on the drawing rows: an earlier group wins, and a road's own colour wins over its twin's
function _byRow(groups){
  const own = new Map(), twin = new Map();
  (groups||[]).forEach(g => g.ids.forEach(id => { const r = _drawRow(+id), m = r === +id ? own : twin; if(!m.has(r)) m.set(r, g.color); }));
  twin.forEach((c, r) => { if(!own.has(r)) own.set(r, c); });
  return own; }
// write rs_c where it changed (all = true: every row again, for the new sources of a new style) and rs_top
function _applyC(all){
  const s = _src("simple"); if(!s) return;
  const k = _cKey(), now = new Map();
  for(const m of [_by.live, _by.base, _by.color]) m.forEach((c, r) => now.set(r, c));   // the later source wins
  _cNow.forEach((c, r) => { if(!now.has(r)) map.removeFeatureState({...s, id: r}, k); });
  now.forEach((c, r) => { if(all || _cNow.get(r) !== c) map.setFeatureState({...s, id: r}, {[k]: c}); });
  _cNow = now;
  map.setGlobalStateProperty("rs_top", [..._by.color.keys()]);
}
// live.js: the live data's colours by row (null: none)
export function setLiveColors(byRow){ _by.live = byRow || new Map(); _applyC(); }
// the full look's state of rsColor: {edge id: colour}; an earlier group wins where groups share ids
function _colorsOf(groups){
  const out={};
  for(let i=(groups||[]).length-1;i>=0;i--) for(const id of groups[i].ids) out[String(id)]=groups[i].color;
  return out;
}
export function rsSetColorField(nameOrIdx){
  let idx = typeof nameOrIdx==="number" ? nameOrIdx : COLOR_OPTIONS.map(o=>o.name).indexOf(nameOrIdx);
  const o = COLOR_OPTIONS[idx]; if(!o) return;
  _coActive = idx;
  map.setGlobalStateProperty("rs_co", idx);
  const sel=document.getElementById("co-select"); if(sel) sel.value=String(idx);
  coUpdateLegend();
  document.dispatchEvent(new CustomEvent("rs:colorchange",{detail:{option:o,index:idx}}));
}
export function rsColor(ids, color, layer){   // paint an id set one colour; rsColor(null) resets
  const L=_lyr(layer); if(!L) return;
  if(L.ov){      // an overlay's colours: its state rs_ov_<n>, which its layers read (render_web._state_expressions)
    map.setGlobalStateProperty("rs_ov_"+OVERLAYS.indexOf(L.ov), ids!=null && color ? _colorsOf([{ids:Array.from(ids), color:color}]) : {});
    document.dispatchEvent(new CustomEvent("rs:colorchange",
      {detail:{overlay:L.ov.label, ids:ids==null?null:Array.from(ids), color:color||null}}));
    return;
  }
  // one set + colour, or several sets in one call — rsColor([[idsA,"#f80"],[idsB,"#08f"]]);
  // group order decides overlaps (earlier wins). rsColor(null) resets either form.
  if(ids==null) _qColor=null;
  else if(color) _qColor=[{ids:Array.from(ids), color:color}];
  else if(Array.isArray(ids)) _qColor=ids.filter(g=>g&&g[0]!=null&&g[1])
    .map(g=>({ids:Array.from(g[0]), color:g[1]}));
  else _qColor=null;
  if(_qColor && !_qColor.length) _qColor=null;
  if(RS_LEAN){ _by.color = _byRow(_qColor); _applyC(); }
  else map.setGlobalStateProperty("rs_colors", _colorsOf(_qColor));
  document.dispatchEvent(new CustomEvent("rs:colorchange",
    {detail:(!_qColor || _qColor.length===1)
      ? {ids:_qColor && _qColor[0].ids, color:_qColor && _qColor[0].color}
      : {groups:_qColor.map(g=>({ids:g.ids, color:g.color}))}}));
}
// rsColorBase([[ids, colour], ...]): recolour groups under rsColor's own, for a host that paints its own roads (a restricted road, a
// picked road) and must not lose them when another caller uses rsColor; rsColorBase(null) clears them. rsColor(null) does not.
export function rsColorBase(groups){
  const g = Array.isArray(groups) ? groups.filter(g=>g&&g[0]!=null&&g[1]).map(g=>({ids:Array.from(g[0]), color:g[1]})) : [];
  if(RS_LEAN){ _by.base = _byRow(g); _applyC(); }
  else map.setGlobalStateProperty("rs_base", _colorsOf(g));      // the full look's road layers read it, under rs_colors
  document.dispatchEvent(new CustomEvent("rs:colorchange",{detail:{base:true, groups:g.map(x=>({ids:x.ids, color:x.color}))}}));
}
// the road's own fill on or off: window.rsSetRoadFill(on) sets the state rs_fill_on, which the fill layers' opacities read (road_fill=False:
// the casing only, the layers stay for clicks and hovers)
let RS_ROAD_FILL = {on:true, paint:{}};
export function rsSetRoadFill(on){
  map.setGlobalStateProperty("rs_fill_on", !!on);
  RS_ROAD_FILL.on = !!on;
  document.dispatchEvent(new CustomEvent("rs:roadfillchange",{detail:{road_fill:!!on}}));
}
let _coBox = null;   // the Colour by menu
// the colour options and the menu: at the start, and again for a new style (rs.setStyle) in the same place in the stack
export function useColor(){
  COLOR_OPTIONS = O.color_options; _coActive = O.color_active;
  window.RS_COLOR_OPTIONS = COLOR_OPTIONS;
  let w = null;
  if(COLOR_OPTIONS.length > 1){
    w=document.createElement("div"); w.className="co-ctrl";
    w.appendChild(document.createTextNode("Colour by "));
    const sel=document.createElement("select"); sel.id="co-select";
    COLOR_OPTIONS.forEach((o,i)=>{ const op=document.createElement("option");
      op.value=i; op.textContent=o.name; sel.appendChild(op); });
    sel.onchange=()=> rsSetColorField(parseInt(sel.value,10));
    w.appendChild(sel);
  }
  if(_coBox && w) _coBox.replaceWith(w); else if(_coBox) _coBox.remove(); else if(w) _tlHost().prepend(w);   // colour-by sits above the filter in the stack
  _coBox = w;
  if(RS_LEAN && _cNow.size) _applyC(true);   // a new style has new sources, with no feature state
}
export function initColor(){
  window.rsColorBase = rsColorBase;
  window.rsSetColorField = rsSetColorField;
  window.rsColor = rsColor;
  useColor();
  if(_coActive){ const _ap=()=>rsSetColorField(_coActive);   // display the requested option on load
    if(map.isStyleLoaded && map.isStyleLoaded()) _ap(); else map.on("load", _ap); }
  RS_ROAD_FILL = O.road_fill;
  window.rsSetRoadFill = rsSetRoadFill;
}
