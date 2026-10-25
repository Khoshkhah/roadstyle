// zoom read-out next to the scale bar (zoom_readout=False leaves it out)
import {map, O} from "./core.js";
export function initZoom(){
  if(O.zoom_readout){ const zd=document.createElement("div"); zd.className="rs-zoom";
    const uz=()=>{ zd.textContent="z "+map.getZoom().toFixed(1); };
    map.on("zoom",uz); uz(); document.body.appendChild(zd); }
}
