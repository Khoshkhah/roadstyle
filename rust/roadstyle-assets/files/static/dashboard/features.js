// The base map's layers (mapstyle's page scripts, docs/design/mapstyle_page_scripts.md): the 3D buildings and each layer's clicks,
// tooltip and popup. Each comes from the layer's entry in roadstyle:controls.overlays (audit R7; a page's layers have no metadata):
// its 3D layer (extrude: the layer id), its start switches (interactive, tooltip, popup_window).
import {map, OVERLAYS, RS_PREFIX, _emit} from "./core.js";
import {_ownOpacity} from "./basemap.js";
let _b3d = [], _b3dOn = false;     // the overlays with a 3D layer (ov.extrude), the switch
// a 3D layer shows while the switch is on and its overlay (the buildings) is shown
function _show3d(){
  _b3d.forEach(ov => { if(map.getLayer(ov.extrude))
    map.setLayoutProperty(ov.extrude, "visibility", _b3dOn && ov.visible !== false ? "visible" : "none"); });
  if(_b3dOn) _over3d();
  _ownOpacity();
}
// the 3D buildings over the names of the streets: a text layer draws over every layer under it, so a building that stands in front of a street
// name must be above that name's layer. The 3D layers go just above the last text layer of the roads (the selection's layers stay above them).
function _over3d(){
  const ls = map.getStyle().layers, lastText = ls.map(l => l.type === "symbol" && l.id.startsWith(RS_PREFIX)).lastIndexOf(true);
  if(lastText < 0) return;
  const next = ls.slice(lastText + 1).find(l => !_b3d.some(ov => ov.extrude === l.id));
  for(const ov of _b3d) if(map.getLayer(ov.extrude) && ls.findIndex(l => l.id === ov.extrude) < lastText) map.moveLayer(ov.extrude, next ? next.id : undefined);
}
export function rsSetBuildings3D(on){
  _b3dOn = !!on; _show3d();
  _emit("rs:buildings3dchange", {on: _b3dOn});
}
// rsSetInteraction(label, {clickable, tooltip, popup}): a base-map layer's clicks (its hover and select colour), its hover tooltip (its
// field list, else its popup's, else every field: true) and its click popup
const _tips = {};   // label -> the tooltip's field list when it is on
export function rsSetInteraction(label, opts){
  const ov = OVERLAYS.find(o => o.label === label); if(!ov) return;
  const o = opts || {};
  if("clickable" in o) ov.interactive = !!o.clickable;
  if("tooltip" in o) ov.tooltip = o.tooltip ? (_tips[ov.label] || (ov.popup && ov.popup.length ? ov.popup : true)) : null;
  if("popup" in o) ov.popup_window = !!o.popup;
  _emit("rs:interactionchange", {overlay: ov.label, ...rsGetInteraction(label)});
}
export function rsGetInteraction(label){
  const ov = OVERLAYS.find(o => o.label === label);
  return ov ? {clickable: !!ov.interactive, tooltip: ov.tooltip !== null && ov.tooltip !== undefined, popup: ov.popup_window !== false} : null;
}
// what buildingstool.js asks: the style of the moment has overlays with a 3D layer, and whether the person or the page has them on
export const _b3dHas = () => _b3d.length > 0;
export const _b3dIsOn = () => _b3dOn;
export function useFeatures(){
  _b3d = OVERLAYS.filter(ov => ov.extrude);
  for(const k in _tips) delete _tips[k];
  OVERLAYS.forEach(ov => { if(ov.tooltip) _tips[ov.label] = ov.tooltip; });
  if(!_b3d.length) return;
  _show3d();
}
export function initFeatures(){
  window.rsSetInteraction = rsSetInteraction;
  window.rsGetInteraction = rsGetInteraction;
  window.rsSetBuildings3D = rsSetBuildings3D;
  window.rsGetBuildings3D = () => _b3dOn;
  document.addEventListener("rs:overlaychange", e => { if(_b3d.some(ov => ov.label === e.detail.overlay)) _show3d(); });
  useFeatures();
}
