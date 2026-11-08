// The types of js/levels_sql.js: the level editor's data in a duckOSM file, in duckdb-wasm (the adapter of roadstyle's level-edit part).
interface LevelsDb {
  dropFile(name: string): Promise<unknown>;
  registerFileText(name: string, text: string): Promise<unknown>;
  copyFileToBuffer(name: string): Promise<Uint8Array>;
}
interface LevelsConn { query(sql: string): Promise<{ toArray(): { toJSON(): Record<string, unknown> }[] }>; }
/** `db`: the AsyncDuckDB, `conn`: its connection, `pkg`: the initialised roadstyle module (its `duckosmPlan` gives the SQL), `catalog`: the database name
 *  (readCatalog), `schema`: where duckOSM keeps the levels ("visualization"). `before()` runs first in saveLevels; `after({tables, toParquet})` runs at its
 *  end with the names of the written tables and `toParquet(table)`, a Promise of the table as Parquet bytes. */
export function duckosmLevelsData(o: {
  db: LevelsDb; conn: LevelsConn; pkg: { duckosmPlan(...a: unknown[]): string } | null; catalog?: string; schema?: string;
  before?: (() => unknown) | null; after?: ((r: { tables: string[]; toParquet(table: string): Promise<Uint8Array> }) => unknown) | null;
}): {
  /** The roads of the area as GeoParquet bytes. */
  edges(): Promise<Uint8Array>;
  /** `{csv, edge_hash}` of the stored levels, or null when the file has none. */
  storedLevels(): Promise<{ edge_hash: string; csv: string } | null>;
  /** Writes levels.csv, edits.csv, heads.csv and caps.csv (texts) into the tables. */
  saveLevels(files: Record<string, string>, opts?: { name?: string }): Promise<void>;
};
