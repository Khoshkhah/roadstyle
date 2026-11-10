// The 3D walls by type (docs/guides/design-panel.md, "3D buildings"): the page gives the walls of its buildings (rsSetWalls), and each wall shows
// in the colour of its type (front, back, side, party, court) over the area's 3D buildings (the overlay with a 3D layer, features.js). The roof of
// a building with walls is a thin slab on top, in the roof colour. A building with no walls keeps its own 3D look.
//
//   rsSetWalls(w)         w: the walls, or null to remove them. A GeoJSON FeatureCollection: a LineString is one wall: {type, height, base,
//                         azimuth} (azimuth: the compass direction of the wall's outward normal, 0 north, 90 east); a Polygon or a MultiPolygon
//                         is the roof of a building: {height}. height and base are in metres, by the rule of the tiles (roadstyle-wasm's
//                         buildingHeights). Or a function that gives them (or a Promise of them): it runs once, when the walls first show
//                         ("Walls by type" on and the 3D buildings in the map), and gives a FeatureCollection, null (no walls) or the
//                         vector source of wall tiles (roadstyle-wasm's LiveMap.setWalls: the engine cuts the walls into tiles, and the
//                         map holds only the tiles in view; docs/design/memory_budget.md). A large area gives a function: then nothing
//                         of the walls is in the page until they show.
//   rsSetWallStyle(s)     s: {on, front, back, side, party, court, roof, roof_dark} (the design panel's `walls`); no argument: the style now.
//   rsHasWalls()          true when the page gave walls (a function: until it gave none).
//
// A wall is a strip of WALL_M along the outside of its line, from the base to the roof's top: it hides the face of the building's own extrusion.
// The strip rule is the engine's (rust/roadstyle/src/walls.rs); a FeatureCollection gets the same strips here, as a GeoJSON source.
import {map, OVERLAYS, RS_PREFIX} from "./core.js";
const WALL_M = 0.4, ROOF_M = 0.25, M_DEG = 111319.49;
const _wallTypes = ["front", "back", "side", "party", "court"];
// _given: the page's walls (a FeatureCollection or a function); _walls: what the map draws (a FeatureCollection or a vector source), null until a
// function gave it; _calls: the number of rsSetWalls calls; _asked: the call whose function ran (a newer call drops the answer of an older one)
let _given = null, _walls = null, _asked = 0, _calls = 0, _wallStyle = {on: false, front: "#16a34a", back: "#dc2626", side: "#6b7280", party: "#7c3aed", court: "#0891b2", roof: "#a8a29e", roof_dark: "#57534e"};
const _wallId = () => RS_PREFIX + "walls";
const _wallHost = () => OVERLAYS.find(o => o.extrude && map.getLayer(o.extrude));
// a wall's line as a strip on its outer side, longer by WALL_M at each end so that two walls meet at a corner
function _wallStrip(f){
  const c = f.geometry.coordinates, p = f.properties, a = c[0], b = c[c.length - 1];
  const k = Math.cos(a[1] * Math.PI / 180), az = (+p.azimuth || 0) * Math.PI / 180;
  const ox = Math.sin(az) * WALL_M / (M_DEG * k), oy = Math.cos(az) * WALL_M / M_DEG;              // outward, in degrees
  const dx = (b[0] - a[0]) * k, dy = b[1] - a[1], n = Math.hypot(dx, dy) || 1;
  const ex = dx / n * WALL_M / (M_DEG * k), ey = dy / n * WALL_M / M_DEG;                           // along the wall, in degrees
  const a0 = [a[0] - ex, a[1] - ey], b0 = [b[0] + ex, b[1] + ey];
  return {type: "Feature", properties: {t: p.type, b: +p.base || 0, h: (+p.height || 0) + ROOF_M},
          geometry: {type: "Polygon", coordinates: [[a0, b0, [b0[0] + ox, b0[1] + oy], [a0[0] + ox, a0[1] + oy], a0]]}};
}
const _isFc = w => w && w.type === "FeatureCollection" && Array.isArray(w.features);
const _tiled = () => _walls && _walls.type === "vector";
const _wallData = () => ({type: "FeatureCollection", features: (_walls ? _walls.features : []).map(f => f.geometry.type === "LineString" ? _wallStrip(f)
  : {type: "Feature", properties: {t: "roof", b: +f.properties.height || 0, h: (+f.properties.height || 0) + ROOF_M}, geometry: f.geometry})});
function _wallPaint(){
  const s = _wallStyle;
  return {"fill-extrusion-color": ["match", ["get", "t"], ..._wallTypes.flatMap(t => [t, s[t]]),
                                   "roof", ["case", ["==", ["global-state", "rs_theme"], "dark"], s.roof_dark, s.roof], s.side],
          "fill-extrusion-base": ["get", "b"], "fill-extrusion-height": ["get", "h"]};
}
// the walls of a function, when they first show
function _ask(){
  const n = _asked = _calls;
  Promise.resolve().then(_given).then(w => {
    if(n !== _calls) return;
    if(w && !(w.type === "vector" || _isFc(w)))
      throw new Error("give a GeoJSON FeatureCollection, a vector source or null");
    _walls = w || {type: "FeatureCollection", features: []}; useWalls();
  }).catch(e => { if(n === _calls) console.warn("rsSetWalls: the walls were not loaded:", e && e.message || e); });
}
function _drop(){ const id = _wallId(); if(map.getLayer(id)) map.removeLayer(id); if(map.getSource(id)) map.removeSource(id); }
// the source and the layer, right after the buildings' 3D layer (each new style of the page removes them); shown while the 3D buildings show
export function useWalls(){
  const id = _wallId(), host = _wallHost();
  if(!_walls && typeof _given === "function" && _asked !== _calls && host && _wallStyle.on && map.getLayoutProperty(host.extrude, "visibility") !== "none") _ask();
  if(!_walls || !host){ _drop(); return; }
  if(!map.getSource(id)) map.addSource(id, _tiled() ? _walls : {type: "geojson", data: _wallData(), tolerance: 0});   // no simplification: a strip is less than a pixel wide
  if(!map.getLayer(id)){
    const ls = map.getStyle().layers, next = ls[ls.findIndex(l => l.id === host.extrude) + 1];
    const hl = map.getLayer(host.extrude);
    map.addLayer({id, type: "fill-extrusion", source: id, ...(_tiled() ? {"source-layer": "walls"} : {}), ...(hl.minzoom != null ? {minzoom: hl.minzoom} : {}),
                  paint: _wallPaint()}, next && next.id);
  }
  map.setPaintProperty(id, "fill-extrusion-opacity", map.getPaintProperty(host.extrude, "fill-extrusion-opacity") ?? 1);
  map.setLayoutProperty(id, "visibility", _wallStyle.on && map.getLayoutProperty(host.extrude, "visibility") !== "none" ? "visible" : "none");
}
export function rsSetWalls(w){
  if(w && typeof w !== "function" && !_isFc(w)) throw new Error("rsSetWalls: give a GeoJSON FeatureCollection, a function that gives the walls, or null");
  _calls++; _given = w || null; _walls = typeof w === "function" ? null : _given;
  _drop(); useWalls();
}
export function rsSetWallStyle(s){
  if(s === undefined) return {..._wallStyle};
  _wallStyle = {..._wallStyle, ...s};
  if(map.getLayer(_wallId())) for(const [k, v] of Object.entries(_wallPaint())) map.setPaintProperty(_wallId(), k, v);
  useWalls();
}
export function initWalls(){
  window.rsSetWalls = rsSetWalls; window.rsSetWallStyle = rsSetWallStyle;
  window.rsHasWalls = () => !_walls ? typeof _given === "function" : _tiled() || _walls.features.length > 0;
  for(const ev of ["rs:buildings3dchange", "rs:overlaychange", "rs:stylechange"]) document.addEventListener(ev, () => { if(_given) useWalls(); });
}
