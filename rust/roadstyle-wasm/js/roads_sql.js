// The only copy of this file (docs/design/rust_engine.md): geolibre-roadstyle and duckosm-rust take it from the same roadstyle commit as
// the engine, roadstyle-rs. Change it here, not in a copy.
//
// The roads table that the engine reads, made by duckdb-wasm from a duckOSM file and written as roads.parquet. The SQL is not here: it is
// roadstyle-io's duckosm.rs (duckosmPlan), the one copy that Python runs too; this file runs its statements on the caller's connection, in
// order. The caller has loaded the module (init()) before. The option {levels: "tags"}: the engine computes the drawing levels with the
// tags rule, not from visualization.edge_levels.
import {duckosmPlan, duckosmLevels} from "../pkg/roadstyle_wasm.js";

let plan = null;            // {cat, tags}: the catalog of the last makeRoads (writeRoads asks the plan for a mode's SELECT)

// the catalog of `catalog` as duckosmPlan reads it: {name, tables: [[schema, table]], columns: [[schema, table, column]]}
export async function readCatalog(q, catalog) {
  const [tables, columns] = JSON.parse(duckosmPlan(JSON.stringify({name: catalog}), "all", true, "[]")).catalog;
  return {name: catalog, tables: (await q(tables)).map((r) => [r.s, r.t]), columns: (await q(columns)).map((r) => [r.s, r.t, r.c])};
}

// Once for each file: the temp table r, one row for each edge with its stored levels. q(sql) -> rows as plain objects. opts.levels:
// "stored" (visualization.edge_levels of a solved level area) or "tags" (no levels: the engine computes them with the tags rule).
// Returns the keyword `levels` of the engine's look: "tags", or the stored levels' {edge_hash, n_edges}, which the engine checks.
export async function makeRoads(q, catalog, opts = {}) {
  const tags = opts.levels === "tags", cat = await readCatalog(q, catalog);
  const [e, r, drop] = JSON.parse(duckosmPlan(JSON.stringify(cat), "all", tags, "[]")).roads;
  await q(e);
  let levels = "tags";
  if (!tags) {
    let row = null;
    try { row = (await q(JSON.parse(duckosmPlan(JSON.stringify(cat), "all", false, "[]")).meta))[0] || null; }
    catch (err) { row = null; }                        // no table: duckosmLevels says what to do
    levels = JSON.parse(duckosmLevels(row ? row.source : undefined, row ? Number(row.n_edges) : undefined, row ? row.edge_hash : undefined));
  }
  await q(r);
  await q(drop);
  plan = {cat, tags};
  return levels;
}

// For each mode, after makeRoads: roads.parquet in duckdb-wasm's file system. mode: "all", "driving", "walking" or "cycling".
export async function writeRoads(q, mode = "all") {
  if (!plan) throw new Error("writeRoads: call makeRoads first");
  const select = JSON.parse(duckosmPlan(JSON.stringify(plan.cat), mode, plan.tags, "[]")).select;
  await q(`COPY (${select}) TO 'roads.parquet' (FORMAT parquet)`);
}
