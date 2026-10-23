// base-layer switching: window.rsSetBasemap(key|index) is the API (swaps the raster source's
// tiles; the road layers stay put); the dropdown is just UI over it and stays in sync.
// A tile-less entry (blank) hides the raster layer and shows the plain background colour.
import {map, style, O} from "./core.js";
let BASEMAPS = [];
export function rsSetBasemap(keyOrIdx){
  const idx = typeof keyOrIdx==="number" ? keyOrIdx
    : BASEMAPS.findIndex(b=>b.key===keyOrIdx || b.label===keyOrIdx);
  const b = BASEMAPS[idx]; if(!b) return;
  if(b.tiles.length && map.getLayer("basemap")){
    // rebuild the source, not setTiles: a raster source's maxzoom (past it the last level is
    // scaled up) and its attribution are fixed when it is created. Same ids, same place in the
    // layer order: back under the layer that followed it in the page's style.
    const def = style.layers.find(l=>l.id==="basemap");
    const after = style.layers.slice(style.layers.indexOf(def)+1).map(l=>l.id).find(id=>map.getLayer(id));
    map.removeLayer("basemap"); map.removeSource("bm");
    map.addSource("bm", {type:"raster", tiles:b.tiles, tileSize:256, maxzoom:b.maxzoom||19, attribution:b.attr||""});
    map.addLayer({...def, layout:{...(def.layout||{}), visibility:"visible"}}, after);
  } else if(map.getLayer("basemap")) map.setLayoutProperty("basemap","visibility","none");
  map.setPaintProperty("bg","background-color", b.bg);
  const m = document.querySelector(".bm-menu");
  if(m) Array.from(m.children).forEach((el,i)=>el.classList.toggle("on", i===idx));
  document.dispatchEvent(new CustomEvent("rs:basemapchange",{detail:{basemap:b.key, index:idx}}));
}
export function initBasemap(){
  BASEMAPS = O.basemaps;
  window.rsSetBasemap = rsSetBasemap;
  window.RS_BASEMAPS = BASEMAPS;
  if(O.basemap_switcher && BASEMAPS.length > 1){
    const menu=document.createElement("div"); menu.className="bm-menu";
    BASEMAPS.forEach((b,i)=>{ const o=document.createElement("div"); o.textContent=b.label;
      if(i===0) o.className="on";
      o.onclick=()=>{ rsSetBasemap(i); menu.classList.remove("open"); };
      menu.appendChild(o); });
    menu.addEventListener("click", (e)=>e.stopPropagation());
    document.addEventListener("click", ()=>menu.classList.remove("open"));
    // a control like 2D/3D and Street View, last in the top-right column
    map.addControl({onAdd(){
      const d=document.createElement("div"); d.className="maplibregl-ctrl maplibregl-ctrl-group bm-ctrl";
      const w=document.createElement("button"); w.type="button"; w.className="bm-icon"; w.title="Base map";
      w.innerHTML="&#9638;";
      w.onclick=(e)=>{ e.stopPropagation(); menu.classList.toggle("open"); };
      d.appendChild(w); d.appendChild(menu); return d;
    }, onRemove(){}});
  }
}
