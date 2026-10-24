// the legend of the active "colour by" option: COLOR_OPTIONS[i].legend, {title, kind: "categorical", entries: [[label, colour], ...]}
// or {title, kind: "continuous", ramp: [colour, ...], vmin, vmax, stepped} (stylers.bake_color_options; stepped: rs.setData's nearest stops, with
// a hard edge half-way between two stops). An option with no legend hides the box.
import {_esc} from "../popup.js";
import {_popupMode, _sideCtl, _box} from "./panel.js";
import {COLOR_OPTIONS, _coActive} from "./color.js";
let _coLegendEl = null, _coLegendBox = null, _liveLegend = null;   // _liveLegend: the legend of rs.setData, over the colour option's
export function coLegendHtml(lg){
  if(!lg) return "";
  let h = lg.title ? '<div class="lg-title">'+_esc(lg.title)+'</div>' : "";
  if(lg.kind==="categorical"){ (lg.entries||[]).forEach(e=>{
    h+='<div class="lg-row"><span class="lg-sw" style="background:'+_esc(e[1])+'"></span>'+_esc(e[0])+'</div>'; }); }
  else if(lg.kind==="continuous"){
    const r = lg.ramp||[], n = r.length, at = k => (100*(k-0.5)/(n-1)).toFixed(2)+"%";
    const bar = lg.stepped && n > 1 ? r.map((c,k)=>c+" "+(k ? at(k) : "0%")+" "+(k<n-1 ? at(k+1) : "100%")).join(",") : r.join(",");
    h+='<div class="lg-bar" style="background:linear-gradient(90deg,'+_esc(bar)+')"></div>'
      +'<div class="lg-ends"><span>'+_esc(lg.vmin)+'</span><span>'+_esc(lg.vmax)+'</span></div>'; }
  return h;
}
export function coUpdateLegend(){
  if(!_coLegendEl) return;
  const h = coLegendHtml(_liveLegend || (COLOR_OPTIONS[_coActive]||{}).legend);
  _coLegendEl.innerHTML = h;
  if(_coLegendBox) _coLegendBox.style.display = h ? "" : "none";
}
// the box once an option has a legend (at the start, or with a later style: rs.setStyle), then the active option's legend
export function useLegend(){
  if(!_coLegendBox && (_liveLegend || COLOR_OPTIONS.some(o=>o.legend))){
    const b=_box("co-lg", "co-lg", "Legend", _popupMode==="panel");      // panel: folded to save space
    _coLegendBox=b.box; _coLegendEl=b.body;
    (_sideCtl||document.body).appendChild(_coLegendBox);
  }
  coUpdateLegend();
}
// live data (rs.setData): its legend in the box, in place of the colour option's; null: the colour option's again
export function setLiveLegend(lg){ _liveLegend = lg; useLegend(); }
