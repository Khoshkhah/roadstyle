// The studio's engine, in a Web Worker so the page does not freeze: roadstyle's Rust engine (rust/roadstyle-wasm, `npm run build`). It keeps
// the roads (a GeoJSON or GeoParquet file, read once into a Roads handle) and makes, for each set of knobs, the whole page in one call
// (Roads.page: page_from, as render_edges(backend="web") with the Rust engine). Every call of the look is here (resolveLook, rampStops):
// the page sends only plain options.
// Messages: {type: "roads", bytes, kind: "geojson" | "parquet" | "shp", dbf, prj, name} -> {columns} (the file's own columns; a Shapefile
// is its .shp bytes, its .dbf bytes and its .prj text); {type: "page", options, given}
// -> {html} (MapLibre still a placeholder); {type: "ramp", cmap, n} -> {stops}. Every answer has the message's id, and ok or error.
import init, {resolveLook, rampStops, readGeoJson, readGeoParquet, readShp} from "../../rust/roadstyle-wasm/pkg/roadstyle_wasm.js";
import {answer} from "../../rust/roadstyle-assets/files/static/dashboard/worker/call.js";

let roads = null;

answer({
  roads(m){
    roads = m.kind === "shp" ? readShp(new Uint8Array(m.bytes), new Uint8Array(m.dbf), m.prj, m.name)
          : (m.kind === "geojson" ? readGeoJson : readGeoParquet)(new Uint8Array(m.bytes));
    return {columns: roads.columns()};
  },
  ramp: (m) => ({stops: rampStops(m.cmap, m.n)}),
  page(m){
    const t0 = performance.now(), options = JSON.stringify(m.options);
    const html = roads.page(resolveLook(options), options, JSON.stringify(m.given || {}));
    return {html, ms: performance.now() - t0};
  },
}, init());
