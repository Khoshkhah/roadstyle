// 2D/3D camera: window.rsSetView3D(on) tilts to the configured camera.pitch_3d (2D also
// squares the bearing back to north); the toggle button is UI over it and follows any pitch
// change — its label shows the view it will switch TO.
import {map, O, _emit} from "./core.js";
import {defineTool} from "./tools.js";
export function rsSetView3D(on){
  on ? map.easeTo({pitch:O.pitch_3d, duration:600}) : map.easeTo({pitch:0, bearing:0, duration:600});
  _emit("rs:viewchange", {view3d:!!on});
}
export function initView3D(){
  window.rsSetView3D = rsSetView3D;
  const d=document.createElement("div"); d.className="maplibregl-ctrl maplibregl-ctrl-group";
  const b=document.createElement("button"); b.type="button";
  b.style.cssText="font:700 11px/1 system-ui;letter-spacing:.03em";
  const upd=()=>{ b.textContent = map.getPitch()<5 ? "3D" : "2D";
                  b.title = map.getPitch()<5 ? "Tilt the view" : "Back to flat"; };
  b.onclick=()=>{ rsSetView3D(map.getPitch()<5); };
  map.on("pitchend", upd); map.on("pitch", upd); upd();
  d.appendChild(b);
  defineTool("view3d", "toggle", d, {isOpen: ()=>map.getPitch()>=5});
}
