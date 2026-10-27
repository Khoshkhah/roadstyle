// The time of the level editor's map in WebAssembly, measured in Node: new LiveMap (the map worker's start), then the first tiles of
// a 1280 x 800 view at the roads' centre at zoom 11 and zoom 14, and the tiles of the next view to the east at zoom 14.
//
//   node roadstyle-wasm/bench_live.mjs <pkg> roadstyle-rs/tests/data/tartu

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join, resolve } from "node:path";

const [pkg, area] = process.argv.slice(2);
const rs = createRequire(import.meta.url)(resolve(pkg, "roadstyle_wasm.js"));
const look = rs.Look.fromJson(readFileSync(join(area, "..", "look.json"), "utf8"));
const roads = new Uint8Array(readFileSync(join(area, "roads.parquet")));
const features = new Uint8Array(readFileSync(join(area, "features.parquet")));
let t = performance.now();
const sources = rs.makeSources(roads, look, features, undefined, undefined);
console.log(`makeSources: ${(performance.now() - t).toFixed(0)} ms`);
t = performance.now();
const live = new rs.LiveMap(sources, look, "", []);
console.log(`new LiveMap: ${(performance.now() - t).toFixed(0)} ms`);
const [lon, lat] = JSON.parse(live.style()).center;
const tileOf = (z) => [(lon + 180) / 360 * 2 ** z, (1 - Math.asinh(Math.tan(lat * Math.PI / 180)) / Math.PI) / 2 * 2 ** z];
const view = (z, dx) => {
  const [cx, cy] = tileOf(z), hx = 1280 / 512 / 2 + 1, hy = 800 / 512 / 2 + 1;
  let bytes = 0;
  const t = performance.now();
  for (let x = Math.floor(cx + dx - hx); x <= Math.floor(cx + dx + hx); x++)
    for (let y = Math.floor(cy - hy); y <= Math.floor(cy + hy); y++) bytes += live.tile("roads", z, x, y).length;
  console.log(`z${z}${dx ? " next view" : ""}: ${(performance.now() - t).toFixed(0)} ms, ${(bytes / 1e6).toFixed(2)} MB`);
};
view(11, 0);
view(14, 0);
view(14, 4);
