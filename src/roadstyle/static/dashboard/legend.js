// the legend of the active "colour by" option: COLOR_OPTIONS[i].legend, {title, kind: "categorical", entries: [[label, colour, count?], ...]}
// or {title, kind: "continuous", ramp: [colour, ...], vmin, vmax, stepped} (stylers.bake_color_options; stepped: rs.setData's nearest stops, with
// a hard edge half-way between two stops). An option with no legend hides the box.
import {_esc} from "../popup.js";
import {_popupMode, _sideCtl, _box} from "./panel.js";
import {COLOR_OPTIONS, _coActive} from "./color.js";
import {O} from "./core.js";
let _coLegendEl = null, _coLegendBox = null, _liveLegend = null;   // _liveLegend: the legend of rs.setData, over the colour option's
// the rows that the page adds after the legend's own ({id, color, label}, or {id, html}: the page's own HTML): the typed `dashboard.legend.rows`, and rs.legend
const _lgExtra = [];
let _lgLoaded = false;
// the rows: the typed ones are read at the first use (O is set by initCore, after the modules are loaded)
const _lgRows = () => {
  if(!_lgLoaded){ _lgLoaded = true; _lgExtra.push(...((O.dashboard && O.dashboard.legend && O.dashboard.legend.rows) || []).map((r, i) => ({id: "row" + i, ...r}))); }
  return _lgExtra;
};
// the mark of a row: a square (the default), a circle or a line (the css class; a name that is not one of them is an error)
const _shape = r => { const k = r.shape || "square"; if(!["square", "circle", "line"].includes(k)) throw new Error("legend row '" + r.id + "': shape must be square, circle or line, not '" + k + "'"); return k; };
// the colour box's rows (.lg-row) or the panel's (.sb-lgrow: the panel has its own style, in the theme of the panel)
const _lgExtraHtml = panel => _lgRows().map(r => r.html || (panel
  ? '<div class="sb-lgrow"><i class="' + _shape(r) + '" style="background:' + _esc(r.color) + '"></i>' + _esc(r.label) + "</div>"
  : '<div class="lg-row"><span class="lg-sw ' + _shape(r) + '" style="background:' + _esc(r.color) + '"></span>' + _esc(r.label) + "</div>")).join("");
export function coLegendHtml(lg){
  if(!lg) return "";
  let h = lg.title ? '<div class="lg-title">'+_esc(lg.title)+'</div>' : "";
  if(lg.kind==="categorical"){ (lg.entries||[]).forEach(e=>{
    h+='<div class="lg-row"><span class="lg-sw" style="background:'+_esc(e[1])+'"></span><span class="lg-t">'+_esc(e[0])+'</span>'+(e[2]!=null ? '<b class="lg-n">'+Number(e[2]).toLocaleString("en")+'</b>' : '')+'</div>'; }); }
  else if(lg.kind==="continuous"){
    const r = lg.ramp||[], n = r.length, at = k => (100*(k-0.5)/(n-1)).toFixed(2)+"%";
    const bar = lg.stepped && n > 1 ? r.map((c,k)=>c+" "+(k ? at(k) : "0%")+" "+(k<n-1 ? at(k+1) : "100%")).join(",") : r.join(",");
    h+='<div class="lg-bar" style="background:linear-gradient(90deg,'+_esc(bar)+')"></div>'
      +'<div class="lg-ends"><span>'+_esc(lg.vmin)+'</span><span>'+_esc(lg.vmax)+'</span></div>'; }
  return h;
}
// the legend html of now: the live data's, else the active colour option's ("" when there is none)
export function coLegendNow(){ return coLegendHtml(_liveLegend || (COLOR_OPTIONS[_coActive]||{}).legend); }
// the rows that the page adds, after the legend's own (the colour box puts them after its class list too)
export const coLegendExtra = () => _lgExtraHtml();
export function coUpdateLegend(){
  if(!_coLegendEl) return;
  const h = coLegendNow() + coLegendExtra();
  _coLegendEl.innerHTML = h;
  if(_coLegendBox) _coLegendBox.style.display = h ? "" : "none";
}
// the box once an option has a legend (at the start, or with a later style: rs.setStyle), then the active option's legend
export function useLegend(){
  if(!_coLegendBox && O.legend !== false && (_liveLegend || _lgRows().length || COLOR_OPTIONS.some(o=>o.legend))){   // legend: the page option
    const b=_box("co-lg", "co-lg", "Legend", _popupMode==="panel");      // panel: folded to save space
    _coLegendBox=b.box; _coLegendEl=b.body;
    (_sideCtl||document.body).appendChild(_coLegendBox);
  }
  coUpdateLegend();
}
// live data (rs.setData): its legend in the box, in place of the colour option's; null: the colour option's again
export function setLiveLegend(lg){ _liveLegend = lg; useLegend(); }
// the rows of the page in the panel's legend too: a box after its list (the template fills the list again at each colour option)
export function legendRefresh(){
  const list = document.getElementById("sb-legend");
  if(list){
    let x = document.getElementById("sb-legend-extra");
    if(!x){ x = document.createElement("div"); x.id = "sb-legend-extra"; list.after(x); }
    x.innerHTML = _lgExtraHtml(true);
  }
  useLegend();
}
// rs.legend: the page's own rows
export const rsLegend = {
  add(row){
    if(!row || !row.id || !(row.html || (row.color && row.label))) throw new Error("rs.legend.add: a row needs an id and {color, label, shape} or {html}");
    if(_lgRows().some(r => r.id === row.id)) throw new Error("rs.legend.add: the row '" + row.id + "' exists");
    _lgExtra.push({...row}); legendRefresh();
  },
  remove(id){ const i = _lgRows().findIndex(r => r.id === id); if(i < 0) throw new Error("rs.legend.remove: no row '" + id + "'"); _lgExtra.splice(i, 1); legendRefresh(); },
  list: () => _lgRows().map(r => r.id),
};
