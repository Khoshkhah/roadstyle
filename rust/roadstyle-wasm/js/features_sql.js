// The only copy of this file (docs/design/rust_engine.md): geolibre-roadstyle and duckosm-rust take it from the same roadstyle commit as
// the engine, roadstyle-rs. Change it here, not in a copy.
//
// The base-map tables of a duckOSM file as features.parquet, the input of the engine's base map. The SQL is not here: it is roadstyle-io's
// duckosm.rs (duckosmPlan, duckosmFeaturesSelect), the queries of mapstyle.map.load_layers, the one copy that Python runs too; this file
// runs them on the caller's connection. The background is the whole boundary: the engine cuts the sea out of it when it reads
// features.parquet (the land in Rust), so no DuckDB spatial extension is needed. The caller has loaded the module (init()) before.
import {duckosmPlan, duckosmFeaturesSelect} from "../pkg/roadstyle_wasm.js";
import {readCatalog} from "./roads_sql.js";

// q(sql) -> rows as plain objects. specs: layers.yaml's layers. Writes features.parquet in duckdb-wasm's file system; false when there is none.
export async function writeFeatures(q, catalog, specs) {
  const cat = await readCatalog(q, catalog);
  const made = [];
  // each layer: f<spec> from its first query that runs (the next ones are mapstyle's fallbacks); none runs: the layer is skipped, as
  // load_layers does
  for (const l of JSON.parse(duckosmPlan(JSON.stringify(cat), "all", true, JSON.stringify(specs))).layers || []) {
    let error = null;
    for (const [k, sql] of l.sql.entries()) {
      try {
        await q(`CREATE OR REPLACE TEMP TABLE f${l.spec} AS ${sql}`);
        if (k) console.warn(`base-map layer ${l.name}: its query ${k + 1} (an older file: ${error})`);
        made.push(l.spec); error = null;
        break;
      } catch (e) { error = e.message || String(e); }
    }
    if (error) console.warn(`base-map layer ${l.name} skipped: ${error}`);
  }
  const select = duckosmFeaturesSelect(Uint32Array.from(made));
  if (!select) return false;
  await q(`COPY (${select}) TO 'features.parquet' (FORMAT parquet)`);
  return true;
}
