// views (docs/design/core_model_and_views.md): a name and a set of settings, applied together through the functions above;
// a view sets only what it names. window.rsSetView(name|index) is the API, the View menu is UI over it.
import {map, O, _emit} from "./core.js";
import {_tlHost} from "./panel.js";
import {rsSetColorField, rsSetRoadFill} from "./color.js";
import {FILTER, _fltSw, rsSetClasses, rsSetBridges, rsSetTunnels} from "./filter.js";
import {rsSetOverlay} from "./overlays.js";
import {rsSetBasemap} from "./basemap.js";
import {rsSetView3D} from "./view3d.js";
let VIEWS = [];
let _vwActive = -1;
export function rsSetView(nameOrIdx){
  const i = typeof nameOrIdx==="number" ? nameOrIdx : VIEWS.findIndex(v=>v.name===nameOrIdx);
  const v = VIEWS[i]; if(!v) return;
  const s = v.set;
  if("color" in s) rsSetColorField(s.color);
  if("road_fill" in s) rsSetRoadFill(s.road_fill);
  if("overlays" in s) for(const k in s.overlays) rsSetOverlay(k, s.overlays[k]);
  if("classes" in s) rsSetClasses(s.classes);
  if("bridges" in s) rsSetBridges(s.bridges);
  if("tunnels" in s) rsSetTunnels(s.tunnels);
  if("basemap" in s) rsSetBasemap(s.basemap);
  if("view3d" in s) rsSetView3D(s.view3d);
  if("palette" in s){ map.setGlobalStateProperty("rs_palette", s.palette);     // the page holds every view's palette (render_web._merge_palettes)
    const sw = (FILTER.palettes||{})[s.palette] || {};
    for(const c in _fltSw) if(sw[c]) _fltSw[c].style.background = sw[c]; }
  _vwActive = i;
  const sel=document.getElementById("vw-select"); if(sel) sel.value=String(i);
  _emit("rs:viewselect", {view:v.name, index:i});
}
export function initViews(){
  VIEWS = O.views;
  window.rsSetView = rsSetView;
  window.RS_VIEWS = VIEWS;
  if(VIEWS.length > 1){
    const w=document.createElement("div"); w.className="vw-ctrl";
    w.appendChild(document.createTextNode("View "));
    const sel=document.createElement("select"); sel.id="vw-select";
    VIEWS.forEach((v,i)=>{ const op=document.createElement("option"); op.value=i; op.textContent=v.name; sel.appendChild(op); });
    sel.onchange=()=> rsSetView(parseInt(sel.value,10));
    w.appendChild(sel); _tlHost().prepend(w);   // above Colour by
  }
  if(VIEWS.length){ const _av=()=>rsSetView(0);   // the page opens with the first view
    if(map.isStyleLoaded && map.isStyleLoaded()) _av(); else map.on("load", _av); }
}
