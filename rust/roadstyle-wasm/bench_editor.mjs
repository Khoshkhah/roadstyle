// The time of the level editor's open in Node (level_editor.js with the levels of the host's map, the option `levels`): the worker's
// calls and the page's own work on their answers, step by step, as the editor does them before it draws the map. The levels given
// are those of a first solve (not timed).
//
//   node roadstyle-wasm/bench_editor.mjs <pkg (wasm-bindgen --target nodejs)> <area folder: roads.parquet, pairs.csv>

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join, resolve } from "node:path";
import { createHash } from "node:crypto";

const [pkg, dir] = process.argv.slice(2);
const rs = createRequire(import.meta.url)(resolve(pkg, "roadstyle_wasm.js"));
const roads = new Uint8Array(readFileSync(join(dir, "roads.parquet"))), pairsText = readFileSync(join(dir, "pairs.csv"), "utf8");
const sha = d => createHash("sha256").update(d).digest("hex");

// the levels of the host's map: a first solve's levels.csv
const first = new rs.LevelArea(roads, pairsText);
const given = {csv: first.levelsCsv(Int32Array.from(JSON.parse(first.solve("relation,a,b,a_end,b_end,enabled\n")).levels.flat()), "", ""),
               edge_hash: first.edgeHash()};
first.free();

const steps = [];
let t = performance.now();
const step = (name) => { const now = performance.now(); steps.push([name, now - t]); t = now; };
const area = new rs.LevelArea(roads, pairsText);                 step("new LevelArea");
const order = area.roadIds();                                    step("roadIds (open)");
const pairLines = pairsText.split(/\r?\n/).filter(l => l.trim());
const roadOf = Object.fromEntries(order.map(r => [r, r]));       step("pairs.csv lines, roadOf");
const areaKey = `${sha(roads)}:${sha(pairsText)}`;               step("areaKey (SHA-256)");
if(area.edgeHash() !== given.edge_hash) throw new Error("edge_hash");   step("edgeHash");
const l = area.levelsOf(given.csv);
const levels = order.map((_, i) => Array.from(l.subarray(4 * i, 4 * i + 4)));   step("levelsOf (given levels.csv)");
const at = pairLines[0].split(",").indexOf("relation");
const n = rel => pairLines.reduce((k, x, i) => k + (i > 0 && x.split(",")[at] === rel), 0);
const counts = [n("stack"), n("meet"), n("order")];              step("pair counts");
area.startFrom(Int32Array.from(levels.flat()), [], 0, 0, 0);     step("startFrom");
area.levelsCsv(Int32Array.from(levels.flat()), "", "");          step("save: levelsCsv");
const shown = JSON.parse(area.factsOf(order.slice(0, 2), "", "")); step("facts of 2 roads (a pick)");
const total = steps.reduce((s, [, ms]) => s + ms, 0);
for(const [name, ms] of steps) console.log(`${name.padEnd(32)} ${ms.toFixed(0).padStart(6)} ms`);
console.log(`${"in all".padEnd(32)} ${total.toFixed(0).padStart(6)} ms (${order.length} roads, ${pairLines.length - 1} pairs: ${counts}; ` +
            `${Object.keys(roadOf).length} ids, ${shown.length} facts, key ${areaKey.length})`);
