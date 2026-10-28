// The memory of the browser's path in WebAssembly, measured in Node (examples/bench.rs measures the native path): the calls of the
// duckosm-rust page's map worker, styleSources then tilesOfSources with the base map, and the module's memory after each (memoryBytes: the
// size of the wasm memory, which only grows). One area for each run, as each run starts with a new module.
//
//   cargo build --release --target wasm32-unknown-unknown -p roadstyle-wasm
//   wasm-bindgen --target nodejs --out-dir <pkg> target/wasm32-unknown-unknown/release/roadstyle_wasm.wasm
//   node roadstyle-wasm/bench.mjs <pkg> roadstyle-rs/tests/data/monaco      # or .../tartu (tests/get_goldens.sh)

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join, resolve } from "node:path";

const [pkg, area] = process.argv.slice(2);
const rs = createRequire(import.meta.url)(resolve(pkg, "roadstyle_wasm.js"));
const mb = (b) => (b / 2 ** 20).toFixed(0);
const look = rs.Look.fromJson(readFileSync(join(area, "..", "look.json"), "utf8"));
const roads = new Uint8Array(readFileSync(join(area, "roads.parquet")));
const features = new Uint8Array(readFileSync(join(area, "features.parquet")));
const start = rs.memoryBytes();
let t = performance.now();
const sources = rs.styleSources(roads, look, features, undefined, undefined);
const ms1 = performance.now() - t;
const [live1, peak1] = rs.liveBytes();          // what the program holds; the memory's size grows in steps ahead (lib.rs `grow`)
const n = JSON.parse(new TextDecoder().decode(sources.roadTable())).props.length;      // the road table is bytes (JSON text)
const afterSources = rs.memoryBytes();
console.log(`${area}: ${n} roads; module at start ${mb(start)} MiB`);
console.log(`  styleSources   ${ms1.toFixed(0)} ms, memory ${mb(afterSources)} MiB, live ${mb(live1)} MiB (peak ${mb(peak1)} MiB)`);
rs.liveBytesReset();
t = performance.now();
const tiler = rs.tilesOfSources(sources, "", []);
const afterTiles = rs.memoryBytes();
const [live2, peak2] = rs.liveBytes();
console.log(`  tilesOfSources   ${(performance.now() - t).toFixed(0)} ms, memory ${mb(afterTiles)} MiB, live ${mb(live2)} MiB (peak ${mb(peak2)} MiB)`);
console.log(`  growth steps: ${rs.growSteps()}`);
console.log(`  per road: ${((afterTiles - start) / n / 1024).toFixed(1)} KiB (the memory after both calls, less the module's start)`);
tiler.free?.();
