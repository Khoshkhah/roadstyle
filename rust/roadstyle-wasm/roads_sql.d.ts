// The types of js/roads_sql.js: the SQL that writes the engine's roads input (roads.parquet) in duckdb-wasm's file system.
/** q(sql) gives the rows as plain objects; catalog: the duckOSM file's catalog name. mode: "all", "driving", "walking" or "cycling".
 *  opts.levels: "stored" (the solved level area's levels) or "tags" (the levels from the bridge, tunnel and layer tags). */
export function writeRoads(q: (sql: string) => Promise<Record<string, unknown>[]>, catalog: string,
                           mode?: "all" | "driving" | "walking" | "cycling", opts?: { levels?: "stored" | "tags" }): Promise<void>;
