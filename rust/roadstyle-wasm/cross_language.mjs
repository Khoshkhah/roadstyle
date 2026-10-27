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
const s = pkg.makeSources(readFileSync(new URL("roads.parquet", data)), look);
const got = {text: text(s.style()), road_table: text(s.roadTable(undefined, true))};
const want = JSON.parse(readFileSync(new URL("rust_style.json", data), "utf8"));
const same = JSON.stringify(got) === JSON.stringify({text: want.text, road_table: want.road_table.text});
console.log(JSON.stringify(got));
if(!same){
  console.error(`wasm differs from the Rust golden: want ${JSON.stringify({text: want.text, road_table: want.road_table.text})}`);
  process.exit(1);
}
