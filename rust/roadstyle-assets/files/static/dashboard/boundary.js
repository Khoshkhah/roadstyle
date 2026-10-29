// The area boundary (docs/design/dashboard_templates.md, 3.3): what the dashboard does with the map option `boundary`. The outline is the style's own
// (the source and the dashed line "boundary", with the look of the config files). This shades the outside, and limits the camera to the boundary's
// bounds. The fields of O.dashboard.boundary turn each part on. A page with no `boundary` has neither.
import {map, O, RS_LOADED, _src} from "./core.js";

const _bdWorld = [[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]];
// the outer rings of the polygons of the style's boundary source, and every coordinate of it
function _bdShape(){
  const role = _src("boundary"), src = role && map.getSource(role.source), fc = src && src.serialize().data;
  if(!fc || !fc.features) return null;
  const rings = [], all = [];
  const walk = c => Array.isArray(c[0]) ? c.forEach(walk) : all.push(c);
  for(const f of fc.features){
    const g = f.geometry; if(!g) continue;
    walk(g.coordinates);
    if(g.type === "Polygon") rings.push(g.coordinates[0]);
    else if(g.type === "MultiPolygon") g.coordinates.forEach(p => rings.push(p[0]));
  }
  return all.length ? {rings, all} : null;
}
// The boundary of the style of the moment: at the start, and again for a new style (rs.setStyle). The shade and the limits of the old style go, and
// the new style's own come if it has a boundary source. The handlers are made once and read the limits of the moment.
let _bdBound = false, _bdLim = null, _bdZoom = null;
export function initBoundary(){
  const rules = O.dashboard && O.dashboard.boundary;
  if(!rules || !(rules.dim || rules.limit)) return;
  const dark = () => document.documentElement.dataset.rsTheme === "dark";
  const dimOpacity = () => dark() ? rules.dim_dark : rules.dim_light;
  if(!_bdBound){
    _bdBound = true;
    map.on("moveend", () => {
      if(!_bdLim) return;
      const c = map.getCenter(), x = Math.min(_bdLim.hi[0], Math.max(_bdLim.lo[0], c.lng)), y = Math.min(_bdLim.hi[1], Math.max(_bdLim.lo[1], c.lat));
      if(x !== c.lng || y !== c.lat) map.easeTo({center: [x, y], duration: 250});
    });
    map.on("resize", () => { if(_bdZoom) _bdZoom(); });
    document.addEventListener("rs:themechange", () => { if(map.getLayer("rs-boundary-dim")) map.setPaintProperty("rs-boundary-dim", "fill-opacity", dimOpacity()); });
  }
  const start = () => {
    if(map.getLayer("rs-boundary-dim")) map.removeLayer("rs-boundary-dim");
    if(map.getSource("rs-boundary-dim")) map.removeSource("rs-boundary-dim");
    if(_bdLim){ _bdLim = null; _bdZoom = null; map.setMinZoom(null); }
    const shape = _bdShape();
    if(!shape) return;                                              // the style has no boundary
    let w = 180, s = 90, e = -180, n = -90;
    for(const [x, y] of shape.all){ w = Math.min(w, x); e = Math.max(e, x); s = Math.min(s, y); n = Math.max(n, y); }
    if(rules.limit){
      // the center stays inside the bounds and their margin; the lowest zoom is `zoom_out` levels under the zoom that fits the boundary
      const px = (e - w) * rules.limit_pad, py = (n - s) * rules.limit_pad;
      _bdLim = {lo: [w - px, s - py], hi: [e + px, n + py]};
      _bdZoom = () => { const c = map.cameraForBounds([[w, s], [e, n]], {padding: 0}); if(c) map.setMinZoom(Math.max(0, c.zoom - rules.zoom_out)); };
      _bdZoom();
    }
    if(rules.dim && shape.rings.length){
      map.addSource("rs-boundary-dim", {type: "geojson", data: {type: "Feature", properties: {}, geometry: {type: "Polygon", coordinates: [_bdWorld, ...shape.rings]}}});
      // under the roads and under the outline: before the first layer of the page that is not the backdrop, the base map or a layer of the base-map box
      const first = map.getStyle().layers.find(l => l.id !== "bg" && l.id !== "basemap" && !l.id.startsWith("vbm-") && !l.id.startsWith("rs-top-") && l.id !== "rs-boundary-dim");
      map.addLayer({id: "rs-boundary-dim", type: "fill", source: "rs-boundary-dim", paint: {"fill-color": "#000000", "fill-opacity": dimOpacity()}}, first && first.id);
    }
  };
  RS_LOADED ? start() : map.once("load", start);
}
