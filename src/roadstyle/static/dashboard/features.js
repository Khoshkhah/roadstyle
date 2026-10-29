// The base map's layers (mapstyle's page scripts, docs/design/mapstyle_page_scripts.md): the 3D buildings and each layer's clicks,
// tooltip and popup. Each comes from the layer's entry in roadstyle:controls.overlays (audit R7; a page's layers have no metadata):
// its 3D layer (extrude: the layer id), its start switches (interactive, tooltip, popup_window).
import {map, OVERLAYS, _emit} from "./core.js";
import {_ovCbs} from "./overlays.js";
import {defineTool, BUILDINGS_ICON} from "./tools.js";
import {_check} from "./panel.js";
let _b3d = [], _b3dOn = false;     // the overlays with a 3D layer (ov.extrude), the switch
// a 3D layer shows while the switch is on and its overlay (the buildings) is shown
function _show3d(){
  _b3d.forEach(ov => { if(map.getLayer(ov.extrude))
    map.setLayoutProperty(ov.extrude, "visibility", _b3dOn && ov.visible !== false ? "visible" : "none"); });
}
export function rsSetBuildings3D(on){
  _b3dOn = !!on; _show3d();
  const cb = document.getElementById("rs-b3d"); if(cb) cb.checked = _b3dOn;
  const bt = document.getElementById("rs-b3d-btn");
  if(bt){ bt.classList.toggle("rs-on", _b3dOn); bt.title = _b3dOn ? "Flat buildings" : "Buildings in 3D"; }
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
export function initFeatures(){
  OVERLAYS.forEach(ov => { if(ov.tooltip) _tips[ov.label] = ov.tooltip; });
  window.rsSetInteraction = rsSetInteraction;
  window.rsGetInteraction = rsGetInteraction;
  _b3d = OVERLAYS.filter(ov => ov.extrude);
  window.rsSetBuildings3D = rsSetBuildings3D;
  window.rsGetBuildings3D = () => _b3dOn;
  if(!_b3d.length) return;
  document.addEventListener("rs:overlaychange", e => { if(_b3d.some(ov => ov.label === e.detail.overlay)) _show3d(); });
  // its button: the tool `buildings`
  const d = document.createElement("div"), bt = document.createElement("button");
  d.className = "maplibregl-ctrl maplibregl-ctrl-group";
  bt.type = "button"; bt.id = "rs-b3d-btn"; bt.title = "Buildings in 3D";
  bt.innerHTML = BUILDINGS_ICON;
  bt.onclick = () => rsSetBuildings3D(!_b3dOn);
  d.appendChild(bt);
  defineTool("buildings", "toggle", d, {title: bt.title, isOpen: () => _b3dOn});
  // its row in the Layers box, under the buildings' row
  const row = _ovCbs[_b3d[0].label] && _ovCbs[_b3d[0].label].parentNode;
  if(row){
    const {lab} = _check("Buildings 3D", false, rsSetBuildings3D, {id: "rs-b3d"});
    lab.style.paddingLeft = "18px";
    row.after(lab);
  }
}
