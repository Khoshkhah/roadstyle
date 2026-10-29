// base-layer switching: window.rsSetBasemap(key|index) is the API (swaps the raster source's
// tiles; the road layers stay put); the dropdown is just UI over it and stays in sync.
// A tile-less entry (blank) hides the raster layer and shows the plain background colour.
import {map, style, O, _emit} from "./core.js";
import {defineTool, BUILDINGS_ICON, LAYERS_ICON} from "./tools.js";
import {buildBox} from "./basemapbox.js";
import {savedKey} from "./settings.js";
let BASEMAPS = [];
// A VECTOR STYLE as a base map (Basemap.style_url, e.g. OpenFreeMap): its sources and layers are merged into the page's map with the prefix
// "vbm-", under the roads, and the raster base map is hidden. Its building extrusion (a fill-extrusion layer) moves to the end, so a road
// behind a building is hidden as in reality; it shows in 3D (pitch above 0) and the flat building layer shows in 2D. window.rsBuildings(on)
// hides or shows the buildings in both modes.
let vec = null, buildingsOn = true, glyphs0 = null;
const clearVector = ()=>{
  if(!vec) return;
  for(const l of map.getStyle().layers.filter(x=>x.id.startsWith("vbm-"))) map.removeLayer(l.id);
  for(const k of Object.keys(map.getStyle().sources).filter(x=>x.startsWith("vbm-"))) map.removeSource(k);
  if(glyphs0) map.setGlyphs(glyphs0);
  vec = null;
  if(map.getLayer("basemap")) map.setLayoutProperty("basemap", "visibility", "visible");
};
const paintBuildings = ()=>{
  if(!vec) return;
  const solid = map.getPitch() > 0.5, vis = on=>on && buildingsOn ? "visible" : "none";
  for(const l of vec.layers){
    if(l.type === "fill-extrusion") map.setLayoutProperty("vbm-"+l.id, "visibility", vis(solid));
    else if(/building/.test(l.id) && l.type === "fill") map.setLayoutProperty("vbm-"+l.id, "visibility", vis(!solid));
  }
};
// A style with flat buildings and no 3D layer (OpenFreeMap Bright, Positron, Dark, Fiord; only Liberty has one) gets one made from the same
// building data: the heights `render_height` and `render_min_height`, the color of the flat layer (an extrusion takes no alpha: its opacity is the layer's).
const noAlpha = c=>typeof c === "string" ? c.replace(/^(hsl|rgb)a\(([^)]*),[^,)]*\)$/, "$1($2)") : c;
// a CARTO tile URL takes the key that the person saved in the settings, instead of the page's own
const keyed = u=>{
  const k = savedKey("carto");
  if(!k || !/cartocdn\.com/.test(u)) return u;
  const bare = u.replace(/([?&])key=[^&]*&?/, "$1").replace(/[?&]$/, "");                // the saved key replaces the page's
  return bare + (bare.includes("?") ? "&" : "?") + "key=" + encodeURIComponent(k);
};
const addExtrusion = s=>{
  if(s.layers.some(l=>l.type === "fill-extrusion")) return;
  const flat = s.layers.find(l=>l.type === "fill" && l["source-layer"] === "building");
  if(!flat) return;
  s.layers.push({id:"building-3d", type:"fill-extrusion", source:flat.source, "source-layer":"building", minzoom:14, filter:["!", ["has", "hide_3d"]],
                 paint:{"fill-extrusion-base":["get", "render_min_height"], "fill-extrusion-height":["get", "render_height"],
                        "fill-extrusion-color":noAlpha((flat.paint || {})["fill-color"]) || "#cccccc", "fill-extrusion-opacity":0.8}});
};
const mergeVector = async b=>{
  const s = await (await fetch(b.style_url)).json();
  addExtrusion(s);
  clearVector();
  glyphs0 = glyphs0 || map.getStyle().glyphs;
  if(map.getLayer("basemap")) map.setLayoutProperty("basemap", "visibility", "none");
  if(s.glyphs) map.setGlyphs(s.glyphs);
  for(const [k, v] of Object.entries(s.sources)) map.addSource("vbm-"+k, v);
  const before = map.getStyle().layers.find(l=>l.id !== "bg" && l.id !== "basemap" && !l.id.startsWith("vbm-"));       // under the roads
  for(const l of s.layers){ const m = {...l, id:"vbm-"+l.id}; if(l.source) m.source = "vbm-"+l.source; map.addLayer(m, before && before.id); }
  vec = s;
  paintBuildings();
  for(const l of s.layers) if(l.type === "fill-extrusion") map.moveLayer("vbm-"+l.id);        // after the roads and the page's layers
  _emit("rs:basemapready", {key:b.key, vector:true});      // a page puts its own top layers back on top
};
export function rsBuildings(on){
  if(on === undefined) return buildingsOn;
  buildingsOn = !!on; paintBuildings();
  _emit("rs:buildingschange", {on:buildingsOn, vector:!!vec});
  return buildingsOn;
}
export function rsSetBasemap(keyOrIdx){
  const idx = typeof keyOrIdx==="number" ? keyOrIdx
    : BASEMAPS.findIndex(b=>b.key===keyOrIdx || b.label===keyOrIdx);
  const b = BASEMAPS[idx]; if(!b) return;
  if(!b.style_url) clearVector();
  if(b.style_url){ mergeVector(b); }
  else if(b.tiles.length && map.getLayer("basemap")){
    // rebuild the source, not setTiles: a raster source's maxzoom (past it the last level is
    // scaled up) and its attribution are fixed when it is created. Same ids, same place in the
    // layer order: back under the layer that followed it in the page's style.
    const def = style.layers.find(l=>l.id==="basemap");
    const after = style.layers.slice(style.layers.indexOf(def)+1).map(l=>l.id).find(id=>map.getLayer(id));
    map.removeLayer("basemap"); map.removeSource("bm");
    map.addSource("bm", {type:"raster", tiles:b.tiles.map(keyed), tileSize:256, maxzoom:b.maxzoom||19, attribution:b.attr||""});
    map.addLayer({...def, layout:{...(def.layout||{}), visibility:"visible"}}, after);
  } else if(map.getLayer("basemap")) map.setLayoutProperty("basemap","visibility","none");
  map.setPaintProperty("bg","background-color", b.bg);
  const m = document.querySelector(".bm-menu");
  if(m) m.querySelectorAll("[data-i]").forEach(el=>el.classList.toggle("on", +el.dataset.i===idx));
  _emit("rs:basemapchange", {basemap:b.key, index:idx, dark:!!b.is_dark});
}
export function initBasemap(){
  BASEMAPS = O.basemaps;
  window.rsSetBasemap = rsSetBasemap;
  window.rsBuildings = rsBuildings;
  map.on("pitchend", paintBuildings);
  window.RS_BASEMAPS = BASEMAPS;
  // a page that starts on a CARTO map with no key, and a key saved in the settings: the map starts again with it
  if(BASEMAPS[0] && (BASEMAPS[0].tiles || []).some(t=>keyed(t) !== t)) map.once("load", ()=>rsSetBasemap(0));
  // a page that starts on a vector style (basemap="ofm_liberty") merges it as soon as the style is in, as a click on its row would
  if(BASEMAPS[0] && BASEMAPS[0].style_url){ let done = false; const go = ()=>{ if(done || !map.isStyleLoaded()) return; done = true; rsSetBasemap(0); };
    if(map.isStyleLoaded()) go(); else { map.on("load", go); map.on("styledata", go); } }
  // the tool `buildings` of a page with a vector base map: the buildings of the vector style (features.js defines it again for a page with
  // buildings of its own, which then win); greyed on a raster base map
  if(BASEMAPS.some(b=>b.style_url)){
    const d=document.createElement("div"), bt=document.createElement("button");
    d.className="maplibregl-ctrl maplibregl-ctrl-group"; bt.type="button"; bt.id="rs-b3d-btn"; bt.innerHTML=BUILDINGS_ICON; d.appendChild(bt);
    const sync=()=>{ bt.disabled=!vec; bt.classList.toggle("rs-on", !!vec && buildingsOn);
                     bt.title=vec ? "Buildings in 3D" : "3D buildings need a vector base map (OpenFreeMap)"; };
    bt.onclick=()=>rsBuildings(!buildingsOn);
    for(const ev of ["rs:buildingschange", "rs:basemapready", "rs:basemapchange"]) document.addEventListener(ev, ()=>setTimeout(sync, 0));
    sync();
    defineTool("buildings", "toggle", d, {title: bt.title, isOpen: ()=>!!vec && buildingsOn});
  }
  if(O.basemap_switcher && BASEMAPS.length > 1){
    const menu=document.createElement("div"); menu.className="bm-menu";
    BASEMAPS.forEach((b,i)=>{ const o=document.createElement("div"); o.textContent=b.label;
      if(i===0) o.className="on";
      o.dataset.i=i; o.onclick=()=>{ rsSetBasemap(i); menu.classList.remove("open"); };
      menu.appendChild(o); });
    menu.addEventListener("click", (e)=>e.stopPropagation());
    document.addEventListener("click", ()=>menu.classList.remove("open"));
    // the tool `basemap`: a button and its box
    const d=document.createElement("div"); d.className="maplibregl-ctrl maplibregl-ctrl-group bm-ctrl";
    const w=document.createElement("button"); w.type="button"; w.className="bm-icon"; w.title="Base map and layers";
    w.innerHTML=LAYERS_ICON;
    w.onclick=(e)=>{ e.stopPropagation(); menu.classList.toggle("open"); };
    d.appendChild(w); d.appendChild(menu);
    buildBox(menu);
    defineTool("basemap", "box", d, {title: w.title, open: ()=>menu.classList.add("open"), close: ()=>menu.classList.remove("open"),
                                     isOpen: ()=>menu.classList.contains("open")});
  }
}
