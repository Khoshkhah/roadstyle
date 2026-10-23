// "colour by" recolouring: each option's fill is baked per edge (__rs_fill / __rs_fill__1 …), and the road layers' expressions (made
// in Python, render_web._fill_expr) pick the active option from the state rs_co. window.rsSetColorField sets it from your UI.
import {map, O, OVERLAYS, _lyr} from "./core.js";
import {_tlHost} from "./panel.js";
import {coUpdateLegend} from "./legend.js";
export let COLOR_OPTIONS = [];
export let _coActive = 0;
let _qColor=null;   // [{ids, color}, ...] the rsColor groups, for the rs:colorchange event
// the state of rsColor: {edge id: colour}; the road layers read it (render_web._fill_expr, the sort key: a painted road over the
// others of its level), and an earlier group wins where groups share ids
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
  map.setGlobalStateProperty("rs_colors", _colorsOf(_qColor));
  document.dispatchEvent(new CustomEvent("rs:colorchange",
    {detail:(!_qColor || _qColor.length===1)
      ? {ids:_qColor && _qColor[0].ids, color:_qColor && _qColor[0].color}
      : {groups:_qColor.map(g=>({ids:g.ids, color:g.color}))}}));
}
// rsColorBase([[ids, colour], ...]): recolour groups under rsColor's own, for a host that paints its own roads (a restricted road, a
// picked road) and must not lose them when another caller uses rsColor; rsColorBase(null) clears them. rsColor(null) does not.
export function rsColorBase(groups){
  const g = Array.isArray(groups) ? groups.filter(g=>g&&g[0]!=null&&g[1]).map(g=>({ids:Array.from(g[0]), color:g[1]})) : [];
  map.setGlobalStateProperty("rs_base", _colorsOf(g));      // the road layers read it (render_web._fill_expr), under rs_colors
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
