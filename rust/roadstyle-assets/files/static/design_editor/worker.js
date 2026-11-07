// The design editor's engine in a Web Worker (app.js), so that the page does not stop while it makes the map: it keeps the roads of the file
// and the tiles of the map (roadstyle-wasm's LiveMap). The calls (../dashboard/worker/call.js):
//   init {pkgUrl}; open {kind: "parquet" | "geojson" | "shp", bytes, dbf, prj, name, options} -> {look}: the roads and the look of `options`
//   (resolveLook) as JSON text; draw {text, prefix} -> {style, table}: a new map with the look `text` (null: the look of open); setLook {text}
//   -> {style}: the look on the same tiles (LiveMap.setLook), null when it needs new tiles; tile {url} -> {bytes}.
import {answer} from "../dashboard/worker/call.js";

let pkg = null, roads = null, base = null, name = "", live = null, gen = 0, prefix = "";

answer({
  async init({pkgUrl}){
    pkg = await import(pkgUrl);
    await pkg.default();
  },
  open(m){
    const b = (x) => new Uint8Array(x);
    roads = m.kind === "shp" ? pkg.readShp(b(m.bytes), b(m.dbf), m.prj, m.name)
          : (m.kind === "geojson" ? pkg.readGeoJson : pkg.readGeoParquet)(b(m.bytes));
    base = pkg.resolveLook(JSON.stringify(m.options));
    name = m.name;
    return {look: base.toJson(), roads: roads.length};
  },
  draw({text}){
    const look = text ? pkg.Look.fromJson(text) : base;
    const src = roads.sources(look, undefined, undefined, name);
    const table = src.roadTable(undefined, true);               // every field of each road (the popup) and its line
    if(live) live.free();
    prefix = `dz://${++gen}/`;
    live = new pkg.LiveMap(src, look, prefix, []);              // takes `src`
    return {style: live.style(), table, transfer: [table.buffer]};
  },
  setLook({text}){
    const style = live ? live.setLook(pkg.Look.fromJson(text)) : undefined;
    return {style: style ?? null};
  },
  tile({url}){
    if(!url.startsWith(prefix)) return {bytes: new Uint8Array()};   // a tile of an older map
    const [source, z, x, y] = url.slice(prefix.length).split("?")[0].split("/");
    const bytes = live.tile(source, +z, +x, +y);
    return {bytes, transfer: [bytes.buffer]};
  },
});
