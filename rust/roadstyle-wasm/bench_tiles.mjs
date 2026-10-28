// The time of the tiles of one view in WebAssembly, measured in Node (review: the page's tiles come slowly on a large area): after
// styleSources and tilesOfSources (the page's map worker), tile() for each tile that a 1280 x 800 view at the roads' centre shows, at
// zooms 10 to 15 (the tiles' last zoom; MapLibre scales z15 up), cold (the first time) and warm (again: the tile cache).
//
//   node roadstyle-wasm/bench_tiles.mjs <pkg> roadstyle-rs/tests/data/tartu

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join, resolve } from "node:path";

const [pkg, area] = process.argv.slice(2);
const rs = createRequire(import.meta.url)(resolve(pkg, "roadstyle_wasm.js"));
const look = rs.Look.fromJson(readFileSync(join(area, "..", "look.json"), "utf8"));
const roads = new Uint8Array(readFileSync(join(area, "roads.parquet")));
const features = new Uint8Array(readFileSync(join(area, "features.parquet")));
const sources = rs.styleSources(roads, look, features, undefined, undefined);
const tiler = rs.tilesOfSources(sources, "", []);
const [lon, lat] = JSON.parse(tiler.style()).center;      // the roads' centre (the wasm Tiler has no bounds())
const tileOf = (z) => [(lon + 180) / 360 * 2 ** z, (1 - Math.asinh(Math.tan(lat * Math.PI / 180)) / Math.PI) / 2 * 2 ** z];
for (const z of [10, 11, 12, 13, 14, 15]) {
  const [cx, cy] = tileOf(z), hx = 1280 / 512 / 2 + 1, hy = 800 / 512 / 2 + 1;   // tiles of 512 px, and the one beyond each side
  const ids = [];
  for (let x = Math.floor(cx - hx); x <= Math.floor(cx + hx); x++) for (let y = Math.floor(cy - hy); y <= Math.floor(cy + hy); y++) ids.push([x, y]);
  for (const pass of ["cold", "warm"]) {
    let total = 0, max = 0, bytes = 0, big = 0;
    for (const [x, y] of ids) {
      const t = performance.now();
      const b = tiler.tile("roads", z, x, y);
      const ms = performance.now() - t;
      total += ms; max = Math.max(max, ms); bytes += b.length; big = Math.max(big, b.length);
    }
    console.log(`z${z} ${pass}: ${ids.length} tiles, ${total.toFixed(0)} ms in all, the slowest ${max.toFixed(0)} ms, ${(bytes / 1e6).toFixed(1)} MB, the largest ${(big / 1e3).toFixed(0)} KB`);
  }
}
