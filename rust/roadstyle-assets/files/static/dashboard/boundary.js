// The area boundary (docs/design/dashboard_templates.md, 3.3): what the dashboard does with the map option `boundary`. The outline is the style's own
// (the source and the dashed line "boundary", with the look of the config files). This shades the outside, and limits the camera to the boundary's
// bounds. The fields of O.dashboard.boundary turn each part on. A page with no `boundary` has neither.
import {map, O} from "./core.js";

const _bdWorld = [[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]];
// the outer rings of the polygons of the style's boundary source, and every coordinate of it
function _bdShape(){
  const src = map.getSource("boundary"), fc = src && src.serialize().data;
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
export function initBoundary(){
  const rules = O.dashboard && O.dashboard.boundary;
  if(!rules || !(rules.dim || rules.limit)) return;
  const start = () => {
    const shape = _bdShape();
    if(!shape) return;                                              // the page has no boundary
    let w = 180, s = 90, e = -180, n = -90;
    for(const [x, y] of shape.all){ w = Math.min(w, x); e = Math.max(e, x); s = Math.min(s, y); n = Math.max(n, y); }
    if(rules.limit){
      // the center stays inside the bounds and their margin; the lowest zoom is `zoom_out` levels under the zoom that fits the boundary
      const px = (e - w) * rules.limit_pad, py = (n - s) * rules.limit_pad, lo = [w - px, s - py], hi = [e + px, n + py];
      const zoomLimit = () => { const c = map.cameraForBounds([[w, s], [e, n]], {padding: 0}); if(c) map.setMinZoom(Math.max(0, c.zoom - rules.zoom_out)); };
      map.on("moveend", () => {
        const c = map.getCenter(), x = Math.min(hi[0], Math.max(lo[0], c.lng)), y = Math.min(hi[1], Math.max(lo[1], c.lat));
        if(x !== c.lng || y !== c.lat) map.easeTo({center: [x, y], duration: 250});
      });
      map.on("resize", zoomLimit);
      zoomLimit();
    }
    if(rules.dim && shape.rings.length){
      const dark = () => document.documentElement.dataset.rsTheme === "dark";
      map.addSource("rs-boundary-dim", {type: "geojson", data: {type: "Feature", properties: {}, geometry: {type: "Polygon", coordinates: [_bdWorld, ...shape.rings]}}});
      // under the roads and under the outline: before the first layer of the page that is not the backdrop, the base map or a layer of the base-map box
      const first = map.getStyle().layers.find(l => l.id !== "bg" && l.id !== "basemap" && !l.id.startsWith("vbm-") && !l.id.startsWith("rs-top-"));
      map.addLayer({id: "rs-boundary-dim", type: "fill", source: "rs-boundary-dim", paint: {"fill-color": "#000000", "fill-opacity": dark() ? rules.dim_dark : rules.dim_light}}, first && first.id);
      document.addEventListener("rs:themechange", () => map.setPaintProperty("rs-boundary-dim", "fill-opacity", dark() ? rules.dim_dark : rules.dim_light));
    }
  };
  map.isStyleLoaded() ? start() : map.once("load", start);
}
