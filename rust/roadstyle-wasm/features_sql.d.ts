// The types of js/features_sql.js: the SQL that writes the base-map input (features.parquet) in duckdb-wasm's file system.
/** q(sql) gives the rows as plain objects; specs: the layers of styles/layers.yaml. false when there is no base-map table. */
export function writeFeatures(q: (sql: string) => Promise<Record<string, unknown>[]>, catalog: string, specs: unknown[]): Promise<boolean>;
