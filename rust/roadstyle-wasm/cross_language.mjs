// The cross-language test (docs/design/target_architecture.md, (i) item 6): the wasm package in Node gives Monaco's style and road
// table with the size and hash of the Rust golden roadstyle-rs/tests/data/monaco/rust_style.json. The native engine makes that golden
// (tests/areas.rs), and the Python binding is checked against it too (tests/test_binding.py): one fixture, three languages, one hash.
//
//   node rust/roadstyle-wasm/cross_language.mjs <roadstyle_wasm.js of a --target web package>
import {readFileSync} from "node:fs";
import {gunzipSync} from "node:zlib";
import {createHash} from "node:crypto";
import {pathToFileURL} from "node:url";

const pkgJs = process.argv[2];
if(!pkgJs) throw new Error("give the package's roadstyle_wasm.js");
const pkg = await import(pathToFileURL(pkgJs).href);
pkg.initSync({module: readFileSync(pkgJs.replace(/\.js$/, "_bg.wasm"))});

const data = new URL("../roadstyle-rs/tests/data/monaco/", import.meta.url);
const text = t => { const b = Buffer.from(t); return {bytes: b.length, sha16: createHash("sha256").update(b).digest("hex").slice(0, 16)}; };
// areas.rs's look: the area's options, resolved, as an export (args.export = true after the resolution)
const look = pkg.resolveLook(gunzipSync(readFileSync(new URL("golden_options.json.gz", data))).toString()).withArg("export", "true");
const s = pkg.styleSources(readFileSync(new URL("roads.parquet", data)), look);
const got = {text: text(s.style()), road_table: text(s.roadTable(undefined, true))};
const want = JSON.parse(readFileSync(new URL("rust_style.json", data), "utf8"));
const same = JSON.stringify(got) === JSON.stringify({text: want.text, road_table: want.road_table.text});
console.log(JSON.stringify(got));
if(!same){
  console.error(`wasm differs from the Rust golden: want ${JSON.stringify({text: want.text, road_table: want.road_table.text})}`);
  process.exit(1);
}

// MLT, the default tile format (MVT when asked for): the same call gives a tile in MLT, the style names the encoding, and a format that is not known is an error
{
  const tiler = new pkg.Tiler(readFileSync(new URL("roads.parquet", data)), look, undefined, undefined, "rs://", []);
  const n = 2 ** 15, lon = 7.4243, lat = 43.7384;
  const [x, y] = [Math.floor((lon + 180) / 360 * n), Math.floor((1 - Math.asinh(Math.tan(lat * Math.PI / 180)) / Math.PI) / 2 * n)];
  const mvt = tiler.tile("roads", 15, x, y, "mvt"), mlt = tiler.tile("roads", 15, x, y);
  const encoding = f => JSON.parse(tiler.style(f)).sources.roads.encoding;
  const ok = mvt.length > 0 && mlt.length > 0 && mlt.length < mvt.length && encoding() === "mlt" && encoding("mvt") === undefined && encoding("mlt") === "mlt";
  let refused = false;
  try { tiler.tile("roads", 15, x, y, "pbf"); } catch { refused = true; }
  console.log(JSON.stringify({mvt: mvt.length, mlt: mlt.length, refused}));
  if(!ok || !refused){
    console.error("the wasm Tiler does not give the MLT tile and style");
    process.exit(1);
  }
}

// Way C and way D give the same tile bytes: the wasm Tiler's tile of three addresses has the size and hash that `roadstyle local` (roadstyle-local, the native
// program) gives for them. The file is made by rust/roadstyle-local/tests/local.rs (ROADSTYLE_BLESS=1), which checks the program against it.
{
  const tiler = new pkg.Tiler(readFileSync(new URL("roads.parquet", data)), look, undefined, undefined, "rs://", []);
  const want = JSON.parse(readFileSync(new URL("way_d_tiles.json", data), "utf8"));
  const got = {};
  for(const key of Object.keys(want)){
    const [z, x, y] = key.split("/").map(Number);
    got[key] = text(tiler.tile("roads", z, x, y));
  }
  console.log(JSON.stringify(got));
  if(JSON.stringify(got) !== JSON.stringify(want)){
    console.error(`the wasm Tiler's tiles differ from way D's: want ${JSON.stringify(want)}`);
    process.exit(1);
  }
}

// The adapter of way C (dashboard/ways.js, engineAdapter): the dashboard's four requests over the engine in the page give the engine's own answers:
// the style with the Tiler's tile addresses, the Tiler's tile, the fields of a road (Sources.roadTable) and the line of a road (Sources.roadLines).
{
  const {engineAdapter} = await import(new URL("../roadstyle-assets/files/static/dashboard/ways.js", import.meta.url).href);
  const tiler = new pkg.Tiler(readFileSync(new URL("roads.parquet", data)), look, undefined, "Monaco", "rs://1/", ["name", "highway"]);
  const a = engineAdapter({tiler, sources: s});
  const n = 2 ** 15, lon = 7.4243, lat = 43.7384;
  const [x, y] = [Math.floor((lon + 180) / 360 * n), Math.floor((1 - Math.asinh(Math.tan(lat * Math.PI / 180)) / Math.PI) / 2 * n)];
  const style = await a.style(), tile = await a.tile("roads", 15, x, y), none = await a.tile("roads", 15, 0, 0);
  const rows = await a.rows("roads", [0, 1]), lines = await a.lines([0, 1]);
  const got = {tiles: style.sources.roads.tiles[0], tile: text(tile), none, row: Object.keys(rows[0]).sort(), line: lines[0].length >= 2 && lines[0][0].length === 2};
  console.log(JSON.stringify(got));
  const same = got.tiles.startsWith("rs://1/roads/") && Buffer.compare(Buffer.from(tile), Buffer.from(tiler.tile("roads", 15, x, y))) === 0 && none === null
    && JSON.stringify(rows[1]) === JSON.stringify(JSON.parse(new TextDecoder().decode(s.roadTable(undefined, false))).props[1]) && got.row.includes("highway") && got.line === true;
  if(!same){
    console.error("the adapter of way C does not give the engine's answers");
    process.exit(1);
  }
  let refused = false;
  try { engineAdapter({}); } catch { refused = true; }
  if(!refused){ console.error("engineAdapter with no Tiler is not an error"); process.exit(1); }
}
