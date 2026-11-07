// The 3D walls by type (docs/guides/design-panel.md, "3D buildings"): the page gives the walls of its buildings (rsSetWalls), and each wall shows
// in the colour of its type (front, back, side, party, court) over the area's 3D buildings (the overlay with a 3D layer, features.js). The roof of
// a building with walls is a thin slab on top, in the roof colour. A building with no walls keeps its own 3D look.
//
//   rsSetWalls(fc)        fc: a GeoJSON FeatureCollection, or null to remove the walls. A LineString is one wall: {type, height, base, azimuth}
//                         (azimuth: the compass direction of the wall's outward normal, 0 north, 90 east); a Polygon is the roof of a building:
//                         {height, base}. height and base are in metres, by the rule of the tiles (roadstyle-wasm's buildingHeights).
//   rsSetWallStyle(s)     s: {on, front, back, side, party, court, roof, roof_dark} (the design panel's `walls`); no argument: the style now.
//
// A wall is a strip of WALL_M along the outside of its line, from the base to the roof's top: it hides the face of the building's own extrusion.
// The data is a GeoJSON source of the page, not a tile layer: the tiles stay as they are.
import {map, OVERLAYS, RS_PREFIX} from "./core.js";
const WALL_M = 0.4, ROOF_M = 0.25, M_DEG = 111319.49;
const _wallTypes = ["front", "back", "side", "party", "court"];
let _walls = null, _wallStyle = {on: false, front: "#16a34a", back: "#dc2626", side: "#6b7280", party: "#7c3aed", court: "#0891b2", roof: "#a8a29e", roof_dark: "#57534e"};
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
const _wallData = () => ({type: "FeatureCollection", features: (_walls ? _walls.features : []).map(f => f.geometry.type === "LineString" ? _wallStrip(f)
  : {type: "Feature", properties: {t: "roof", b: +f.properties.height || 0, h: (+f.properties.height || 0) + ROOF_M}, geometry: f.geometry})});
function _wallPaint(){
  const s = _wallStyle;
  return {"fill-extrusion-color": ["match", ["get", "t"], ..._wallTypes.flatMap(t => [t, s[t]]),
                                   "roof", ["case", ["==", ["global-state", "rs_theme"], "dark"], s.roof_dark, s.roof], s.side],
          "fill-extrusion-base": ["get", "b"], "fill-extrusion-height": ["get", "h"]};
}
// the source and the layer, right after the buildings' 3D layer (each new style of the page removes them); shown while the 3D buildings show
export function useWalls(){
  const id = _wallId(), host = _wallHost();
  if(!_walls || !host){ if(map.getLayer(id)) map.removeLayer(id); if(map.getSource(id)) map.removeSource(id); return; }
  if(map.getSource(id)) map.getSource(id).setData(_wallData());
  else map.addSource(id, {type: "geojson", data: _wallData(), tolerance: 0});        // no simplification: a strip is less than a pixel wide
  if(!map.getLayer(id)){
    const ls = map.getStyle().layers, next = ls[ls.findIndex(l => l.id === host.extrude) + 1];
    const hl = map.getLayer(host.extrude);
    map.addLayer({id, type: "fill-extrusion", source: id, ...(hl.minzoom != null ? {minzoom: hl.minzoom} : {}), paint: _wallPaint()}, next && next.id);
  }
  map.setPaintProperty(id, "fill-extrusion-opacity", map.getPaintProperty(host.extrude, "fill-extrusion-opacity") ?? 1);
  map.setLayoutProperty(id, "visibility", _wallStyle.on && map.getLayoutProperty(host.extrude, "visibility") !== "none" ? "visible" : "none");
}
export function rsSetWalls(fc){
  if(fc && !(fc.type === "FeatureCollection" && Array.isArray(fc.features))) throw new Error("rsSetWalls: give a GeoJSON FeatureCollection or null");
  _walls = fc || null; useWalls();
}
export function rsSetWallStyle(s){
  if(s === undefined) return {..._wallStyle};
  _wallStyle = {..._wallStyle, ...s};
  if(map.getLayer(_wallId())) for(const [k, v] of Object.entries(_wallPaint())) map.setPaintProperty(_wallId(), k, v);
  useWalls();
}
export function initWalls(){
  window.rsSetWalls = rsSetWalls; window.rsSetWallStyle = rsSetWallStyle;
  window.rsHasWalls = () => !!(_walls && _walls.features.length);
  for(const ev of ["rs:buildings3dchange", "rs:overlaychange", "rs:stylechange"]) document.addEventListener(ev, () => { if(_walls) useWalls(); });
}
