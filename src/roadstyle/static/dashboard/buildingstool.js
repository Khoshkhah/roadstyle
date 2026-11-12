// The tool `buildings`: one button for the 3D buildings of every source that the page has. A source is
//   scene  the part `buildings` of the 3D scene (scene_3d, scene3d.js),
//   own    the area's own buildings, an overlay with a 3D layer (features.js),
//   ofm    the buildings of the vector base map (OpenFreeMap, basemap.js).
// The button is on while any source shows its buildings, and a click switches every source that the page has. The own buildings win over the base map's
// (core.js `_ownBuildings`), so a page with both draws one set. The button is grey, with its reason in the title, on a page with no source.
// No row of the base-map box and no row of the scene repeats it. The calls of the sources stay: rsBuildings, rsSetBuildings3D, rsScene3dKind("buildings").
import {O, OVERLAYS, _ownBuildings} from "./core.js";
import {replaceTool, getTool, BUILDINGS_ICON} from "./tools.js";
import {rsBuildings, rsBuildingsByPerson, _bmHasVector, _bmHasVectorStyle} from "./basemap.js";
import {rsSetBuildings3D, _b3dHas, _b3dIsOn} from "./features.js";
import {rsScene3d, rsScene3dKind, _s3HasBuildings, _s3BuildingsShown} from "./scene3d.js";

let _btEl = null;                       // the button, once the tool is defined
const _btSources = () => ({scene: _s3HasBuildings(), own: _b3dHas(), ofm: _bmHasVector()});
// a source shows its buildings now (the base map's only where the page has none of its own: core.js)
const _btShown = () => { const s = _btSources(); return (s.scene && _s3BuildingsShown()) || (s.own && _b3dIsOn()) || (s.ofm && !_ownBuildings() && rsBuildings()); };
function _btSet(on){
  const s = _btSources(), solo = s.ofm && !s.scene && !s.own;
  if(s.scene){ rsScene3dKind("buildings", on); if(on) rsScene3d(true); }
  if(s.own) rsSetBuildings3D(on);
  if(s.ofm) solo ? rsBuildingsByPerson(on) : rsBuildings(on);        // the person's switch tilts a flat map to show the base map's buildings (basemap.js); another source does not need it
}
function _btSync(){
  if(!_btEl) return;
  const s = _btSources(), any = s.scene || s.own || s.ofm, on = any && _btShown();
  _btEl.disabled = !any;
  _btEl.classList.toggle("rs-on", on);
  _btEl.title = !any ? "3D buildings need a vector base map (OpenFreeMap), buildings of the area, or a 3D scene with buildings" : on ? "Flat buildings" : "Buildings in 3D";
  const t = getTool("buildings"); if(t) t.title = _btEl.title;
}
// the tool of the page, made once (a later style does not make it again), and its state read again
export function useBuildingsTool(){
  const wanted = (O.dashboard && O.dashboard.toolbar) || _bmHasVectorStyle() || !!O.scene_3d || OVERLAYS.some(o => o.extrude);
  if(!_btEl && wanted){
    const d = document.createElement("div"), b = document.createElement("button");
    d.className = "maplibregl-ctrl maplibregl-ctrl-group";
    b.type = "button"; b.id = "rs-b3d-btn"; b.innerHTML = BUILDINGS_ICON; d.appendChild(b);
    b.onclick = () => _btSet(!_btShown());
    _btEl = b;
    replaceTool("buildings", "toggle", d, {title: "", isOpen: () => _btShown()});
  }
  _btSync();
}
export function initBuildingsTool(){
  useBuildingsTool();
  for(const ev of ["rs:buildingschange", "rs:buildings3dchange", "rs:scene3dchange", "rs:scene3dstatus", "rs:terrainchange", "rs:basemapready", "rs:basemapchange", "rs:overlaychange", "rs:overlayschange"])
    document.addEventListener(ev, () => setTimeout(_btSync, 0));
}
