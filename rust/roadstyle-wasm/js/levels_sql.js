// The level editor's data in a duckOSM file, for the level-edit part (docs/design/level_part.md, step f): the adapter `levelEditPart` needs, from a
// duckdb-wasm connection. Like roads_sql.js, this file is the only copy: duckosm-rust takes it from the same roadstyle commit as the engine.
//
//   const data = duckosmLevelsData({db, conn, pkg, catalog: "memory", before: () => forgetRoads(), after: ({tables, toParquet}) => keepTables(tables, toParquet)});
//   levelEditPart({dashboard: rs, map, pkgUrl, data: {...data, relevel, roadsStyle}})    // relevel and roadsStyle use the host's own map worker
//
// `db`: the AsyncDuckDB, `conn`: its connection, `pkg`: the roadstyle WebAssembly module (initialised: its SQL is `duckosmPlan`, the one copy that Python runs
// too). `catalog`: the name of the database in duckdb (readCatalog). The tables are duckOSM's: <mode>.edges (the roads of the area) and, in `schema`
// ("visualization"), edge_levels, edge_levels_meta and the area's own input: level_edits, level_heads, level_caps.
//   edges()               the roads of the area as GeoParquet bytes (duckosmPlan's "level_edges")
//   storedLevels()        {csv, edge_hash} of visualization.edge_levels, or null when the file has none
//   saveLevels(files, {name})  writes levels.csv into edge_levels (the build's edges must be the same: an error says how many differ), the meta row
//                         (source "area", `name`, the time), and edits.csv, heads.csv and caps.csv into their tables
// `before()` runs first in saveLevels (the host drops what it drew from the old levels); `after({tables, toParquet})` runs at the end with the names of the
// tables that were written and `toParquet(table)` (a Promise of the table as Parquet bytes: the host keeps them for its downloads).
import {readCatalog} from "./roads_sql.js";

const INPUTS = {"edits.csv": ["level_edits", ["a", "b"]], "heads.csv": ["level_heads", ["road"]], "caps.csv": ["level_caps", ["road"]]};

export function duckosmLevelsData({db, conn, pkg, catalog = "memory", schema = "visualization", before = null, after = null}){
  const rows = async (sql) => (await conn.query(sql)).toArray().map((r) => r.toJSON());
  const withFile = async (name, work) => {                         // duckdb-wasm does not see a second COPY to a kept file name: drop the file around each use
    await db.dropFile(name).catch(() => {});
    try { return await work(); } finally { await db.dropFile(name).catch(() => {}); }
  };
  async function edges(){
    const plan = JSON.parse(pkg.duckosmPlan(JSON.stringify(await readCatalog(rows, catalog)), "all", true, "[]"));
    if(!plan.level_edges) throw new Error("this file has no <mode>.edges table: the level editor has no roads");
    try { return await withFile("edges.parquet", async () => { await conn.query(`COPY (${plan.level_edges}) TO 'edges.parquet' (FORMAT parquet)`); return db.copyFileToBuffer("edges.parquet"); }); }
    finally { if(plan.drop) await conn.query(plan.drop); }          // the run's tables (none for level_edges: a plain query)
  }
  async function storedLevels(){
    const have = await rows(`SELECT 1 AS x FROM information_schema.tables WHERE table_schema = '${schema}' AND table_name = 'edge_levels_meta'`);
    if(!have.length) return null;
    const [meta] = await rows(`SELECT edge_hash FROM ${schema}.edge_levels_meta`);
    if(!meta) return null;
    return withFile("levels.csv", async () => {
      await conn.query(`COPY (SELECT edge_id AS edge, casing_start, casing_level, casing_end, fill_level FROM ${schema}.edge_levels) TO 'levels.csv' (HEADER)`);
      return {edge_hash: String(meta.edge_hash), csv: new TextDecoder().decode(await db.copyFileToBuffer("levels.csv"))};
    });
  }
  async function saveLevels(files, {name = "this browser"} = {}){
    if(before) await before();
    const [meta] = await rows(`SELECT n_edges FROM ${schema}.edge_levels_meta`);
    await db.registerFileText("levels.csv", files["levels.csv"]);
    const [{n}] = await rows("SELECT count(*) AS n FROM read_csv('levels.csv', header = true)");
    if(Number(n) !== Number(meta.n_edges)) throw new Error(`levels.csv has ${n} edges, the build has ${meta.n_edges}: open the editor again`);
    await conn.query(`DELETE FROM ${schema}.edge_levels; INSERT INTO ${schema}.edge_levels BY NAME
      SELECT * EXCLUDE (edge) REPLACE (CAST(cap_start AS VARCHAR) AS cap_start, CAST(cap_end AS VARCHAR) AS cap_end), edge AS edge_id
      FROM read_csv('levels.csv', header = true, types = {'edge': 'BIGINT'})`);
    await conn.query(`UPDATE ${schema}.edge_levels_meta SET source = 'area', area = '${String(name).replaceAll("'", "''")}', created = '${new Date().toISOString().slice(0, 19)}+00:00'`);
    const tables = ["edge_levels", "edge_levels_meta"];
    for(const [file, [table, ids]] of Object.entries(INPUTS)){
      if(!files[file]?.trim()) continue;
      await db.registerFileText(file, files[file]);
      const cast = ids.map((c) => `CAST(NULLIF("${c}", '') AS BIGINT) AS "${c}"`).join(", ");
      await conn.query(`CREATE OR REPLACE TABLE ${schema}.${table} AS SELECT * REPLACE (${cast}) FROM read_csv('${file}', header = true, all_varchar = true)`);
      tables.push(table);
    }
    const toParquet = (table) => withFile(`${table}_${schema}.parquet`, async () => {
      await conn.query(`COPY ${schema}.${table} TO '${table}_${schema}.parquet' (FORMAT parquet)`);
      return db.copyFileToBuffer(`${table}_${schema}.parquet`);
    });
    if(after) await after({tables, toParquet});
  }
  return {edges, storedLevels, saveLevels};
}
