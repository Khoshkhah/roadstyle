// 2D/3D camera: window.rsSetView3D(on) tilts to the configured camera.pitch_3d (2D also
// squares the bearing back to north); the toggle button is UI over it and follows any pitch
// change — its label shows the view it will switch TO.
import {map, O, _emit} from "./core.js";
export let VIEW_CTRL = null;   // the 2D/3D button's group (features.js puts the 3D buildings' button under it)
export function rsSetView3D(on){
  on ? map.easeTo({pitch:O.pitch_3d, duration:600}) : map.easeTo({pitch:0, bearing:0, duration:600});
  _emit("rs:viewchange", {view3d:!!on});
}
export function initView3D(){
  window.rsSetView3D = rsSetView3D;
  map.addControl({onAdd(m){
    const d=document.createElement("div"); d.className="maplibregl-ctrl maplibregl-ctrl-group";
    const b=document.createElement("button"); b.type="button";
    b.style.cssText="font:700 11px/1 system-ui;letter-spacing:.03em";
    const upd=()=>{ b.textContent = m.getPitch()<5 ? "3D" : "2D";
                    b.title = m.getPitch()<5 ? "Tilt the view" : "Back to flat"; };
    b.onclick=()=>{ rsSetView3D(m.getPitch()<5); };
    m.on("pitchend", upd); m.on("pitch", upd); upd();
    d.appendChild(b); VIEW_CTRL = d; return d;
  }, onRemove(){}});
}
