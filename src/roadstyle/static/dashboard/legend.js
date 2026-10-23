// the legend of the active "colour by" option: COLOR_OPTIONS[i].legend, {title, kind: "categorical", entries: [[label, colour], ...]}
// or {title, kind: "continuous", ramp: [colour, ...], vmin, vmax} (stylers.bake_color_options). An option with no legend hides the box.
import {_popupMode, _sideCtl} from "./panel.js";
import {COLOR_OPTIONS, _coActive} from "./color.js";
let _coLegendEl = null, _coLegendBox = null;
export function coLegendHtml(lg){
  if(!lg) return "";
  let h = lg.title ? '<div class="lg-title">'+lg.title+'</div>' : "";
  if(lg.kind==="categorical"){ (lg.entries||[]).forEach(e=>{
    h+='<div class="lg-row"><span class="lg-sw" style="background:'+e[1]+'"></span>'+e[0]+'</div>'; }); }
  else if(lg.kind==="continuous"){
    h+='<div class="lg-bar" style="background:linear-gradient(90deg,'+(lg.ramp||[]).join(",")+')"></div>'
      +'<div class="lg-ends"><span>'+lg.vmin+'</span><span>'+lg.vmax+'</span></div>'; }
  return h;
}
export function coUpdateLegend(){
  if(!_coLegendEl) return;
  const h = coLegendHtml((COLOR_OPTIONS[_coActive]||{}).legend);
  _coLegendEl.innerHTML = h;
  if(_coLegendBox) _coLegendBox.style.display = h ? "" : "none";
}
// the box once an option has a legend (at the start, or with a later style: rs.setStyle), then the active option's legend
export function useLegend(){
  if(!_coLegendBox && COLOR_OPTIONS.some(o=>o.legend)){
    _coLegendBox=document.createElement("div"); _coLegendBox.className="co-lg";
    const hd=document.createElement("div"); hd.className="co-lg-hd"; hd.textContent="Legend ▾";
    hd.onclick=()=>{ const c=_coLegendBox.classList.toggle("collapsed"); hd.textContent="Legend "+(c?"▸":"▾"); };
    _coLegendEl=document.createElement("div"); _coLegendEl.className="co-lg-body";
    _coLegendBox.appendChild(hd); _coLegendBox.appendChild(_coLegendEl);
    if(_popupMode==="panel"){ _coLegendBox.classList.add("collapsed"); hd.textContent="Legend ▸"; }  // panel: collapse to save space
    (_sideCtl||document.body).appendChild(_coLegendBox);
  }
  coUpdateLegend();
}
