// The base map's layers (mapstyle's page scripts, docs/design/mapstyle_page_scripts.md): the 3D buildings and each layer's clicks,
// tooltip and popup. The layers are found by their roles in the style's metadata (audit R7): the 3D buildings are the layers with
// roadstyle:group "buildings 3D", which belong to the overlay with their source; a layer's start switches are its entry in
// roadstyle:controls.overlays (interactive, tooltip, popup_window).
import {map, O, OVERLAYS, RS_PREFIX, _emit} from "./core.js";
import {_ovCbs} from "./overlays.js";
import {VIEW_CTRL} from "./view3d.js";
let _b3d = [], _b3dOv = null, _b3dOn = false;     // the 3D layers' ids, their overlay, the switch
// the 3D buildings show while the switch is on and their overlay (the buildings) is shown
function _show3d(){
  const on = _b3dOn && !!_b3dOv && _b3dOv.visible !== false;
  _b3d.forEach(id => { if(map.getLayer(id)) map.setLayoutProperty(id, "visibility", on ? "visible" : "none"); });
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
  const layers = (O.style && O.style.layers) || [];
  const b3d = layers.filter(l => (l.metadata || {})["roadstyle:group"] === "buildings 3D");
  _b3d = b3d.map(l => RS_PREFIX + l.id);
  _b3dOv = b3d.length ? OVERLAYS.find(ov => ov.source === RS_PREFIX + b3d[0].source) || null : null;
  window.rsSetBuildings3D = rsSetBuildings3D;
  window.rsGetBuildings3D = () => _b3dOn;
  if(!_b3d.length) return;
  document.addEventListener("rs:overlaychange", e => { if(_b3dOv && e.detail.overlay === _b3dOv.label) _show3d(); });
  // its button, right under the 2D/3D button
  map.addControl({onAdd(){
    const d = document.createElement("div"), bt = document.createElement("button");
    d.className = "maplibregl-ctrl maplibregl-ctrl-group";
    bt.type = "button"; bt.id = "rs-b3d-btn"; bt.title = "Buildings in 3D";
    bt.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" style="display:block;margin:auto" fill="none" stroke="currentColor" stroke-width="2" ' +
      'stroke-linejoin="round"><path d="M3 21h18M5 21V8l6-3v16M11 21V10l8 2v9"/><path d="M8 10v1M8 14v1M14 14v1M17 14v1"/></svg>';
    bt.onclick = () => rsSetBuildings3D(!_b3dOn);
    d.appendChild(bt);
    if(VIEW_CTRL) setTimeout(() => VIEW_CTRL.after(d));      // after MapLibre has put it at the end of its corner
    return d;
  }, onRemove(){}});
  // its row in the Layers box, under the buildings' row
  const row = _b3dOv && _ovCbs[_b3dOv.label] && _ovCbs[_b3dOv.label].parentNode;
  if(row){
    const lab = document.createElement("label"), cb = document.createElement("input");
    cb.type = "checkbox"; cb.id = "rs-b3d"; cb.onchange = () => rsSetBuildings3D(cb.checked);
    lab.style.paddingLeft = "18px";
    lab.append(cb, document.createTextNode(" Buildings 3D"));
    row.after(lab);
  }
}
