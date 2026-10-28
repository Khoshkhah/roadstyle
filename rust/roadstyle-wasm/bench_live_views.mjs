// The level editor's map (LiveMap) in WebAssembly, measured in Node: the first tiles of each view on a new map (the page's
// styleSources and LiveMap), with their size and a hash of their bytes. The views: 1280 x 800 at the roads' centre, z11-z15 flat and
// z14 at pitch 60 (MapLibre's rule for the tiles of a tilted view). [views.json]: the views' tiles, for examples/bench_live.rs.
//
//   node roadstyle-wasm/bench_live_views.mjs roadstyle-wasm/pkg <roads.parquet> <levels.json> <look.json> [views.json]
import { readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { resolve, join } from "node:path";
import { pathToFileURL } from "node:url";
// The tiles of a 1280 x 800 view (512 px tiles) at the centre [lon, lat]: pitch 0 at z, or pitch 60 (tiles of lower zooms far away).
function views(lon, lat, W = 1280, H = 800) {
  const F = 0.5 / Math.tan(36.87 / 2 * Math.PI / 180) * H;
  const px = (z) => [(lon + 180) / 360 * 512 * 2 ** z, (1 - Math.asinh(Math.tan(lat * Math.PI / 180)) / Math.PI) / 2 * 512 * 2 ** z];
  const flat = (z) => {
    const [cx, cy] = px(z), out = [];
    for (let x = Math.floor((cx - W / 2) / 512); x <= Math.floor((cx + W / 2) / 512); x++)
      for (let y = Math.floor((cy - H / 2) / 512); y <= Math.floor((cy + H / 2) / 512); y++) out.push([z, x, y]);
    return out;
  };
  const pitched = (z0, pitch) => {
    const p = pitch * Math.PI / 180, h = F * Math.cos(p), back = F * Math.sin(p), [cx, cy] = px(z0), seen = new Set(), out = [];
    for (let sy = -H / 2; sy <= H / 2; sy += 8) for (let sx = -W / 2; sx <= W / 2; sx += 8) {
      const a = p - Math.atan(sy / F);           // the ray's angle from the vertical (sy > 0: lower on the screen, nearer)
      if (a >= Math.PI / 2 - 0.05) continue;
      const fwd = h * Math.tan(a) - back, d = h / Math.cos(a), lat_ = sx * d / Math.hypot(F, sy);
      // MapLibre's rule (coveringTiles): a tile of zoom z is split while its distance from the camera's ground point, in tiles of z0, is
      // under 3 * 2^(z0 - z)
      const dt = Math.hypot(fwd + back, lat_) / 512, z = dt <= 3 ? z0 : Math.max(0, z0 - Math.ceil(Math.log2(dt / 3)));
      const s = 2 ** (z0 - z), t = [z, Math.floor((cx + lat_) / 512 / s), Math.floor((cy - fwd) / 512 / s)], k = t.join("/");
      if (!seen.has(k)) { seen.add(k); out.push(t); }
    }
    return out;
  };
  const v = {};
  for (const z of [11, 12, 13, 14, 15]) v[`z${z}`] = flat(z);
  v["pitch60 z14"] = pitched(14, 60);
  return v;
}

const [pkg, roadsPath, levelsPath, lookPath, out] = process.argv.slice(2);
const rs = await import(pathToFileURL(resolve(pkg, "roadstyle_wasm.js")));
rs.initSync({ module: readFileSync(join(pkg, "roadstyle_wasm_bg.wasm")) });
const look = rs.Look.fromJson(readFileSync(lookPath, "utf8")).withArg("levels", readFileSync(levelsPath, "utf8").trim());
const roads = readFileSync(roadsPath);
const live = () => new rs.LiveMap(rs.styleSources(new Uint8Array(roads), look, undefined, undefined, undefined), look, "", []);
let m = live();
const [lon, lat] = JSON.parse(m.style()).center;
const vs = views(lon, lat);
if (out) writeFileSync(out, JSON.stringify(Object.entries(vs)));
for (const [name, tiles] of Object.entries(vs)) {
  m ??= live();
  let bytes = 0;
  const h = createHash("sha256");
  const t = performance.now();
  for (const [z, x, y] of tiles) { const b = m.tile("roads", z, x, y); bytes += b.length; h.update(b); }
  const ms = performance.now() - t;
  const zs = [...new Set(tiles.map((t) => t[0]))].join(",");
  console.log(`${name.padEnd(12)} ${String(tiles.length).padStart(3)} tiles (z ${zs})  ${ms.toFixed(0).padStart(5)} ms  ${(bytes / 1e6).toFixed(2)} MB  ${h.digest("hex").slice(0, 12)}`);
  m.free(); m = null;
}
