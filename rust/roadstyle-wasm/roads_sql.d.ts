// The types of js/roads_sql.js: the SQL that writes the engine's roads input (roads.parquet) in duckdb-wasm's file system.
type Query = (sql: string) => Promise<Record<string, unknown>[]>;
/** The catalog of the database `catalog`, as duckosmPlan reads it. The module must be loaded (init()) before. */
export function readCatalog(q: Query, catalog: string):
  Promise<{ name: string; tables: [string, string][]; columns: [string, string, string][] }>;
/** One time for each file: the temporary table r, one row for each edge of all modes with its levels. q(sql) gives the rows as plain
 *  objects; catalog: the duckOSM file's catalog name. opts.levels: "stored" (the solved level area's levels) or "tags" (no levels: the
 *  engine computes them from the bridge, tunnel and layer tags). Returns the look's args.levels: "tags", or the stored levels'
 *  {edge_hash, n_edges}, which the engine checks. */
export function makeRoads(q: Query, catalog: string, opts?: { levels?: "stored" | "tags" }):
  Promise<"tags" | { edge_hash: string; n_edges: number }>;
/** For each mode, after makeRoads: roads.parquet. mode: "all", "driving", "walking" or "cycling". */
export function writeRoads(q: Query, mode?: "all" | "driving" | "walking" | "cycling"): Promise<void>;
