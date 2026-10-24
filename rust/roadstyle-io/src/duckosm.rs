//! The SQL that reads a duckOSM file (docs/design/rust_library.md, the mapstyle merge): the roads of every mode (mapstyle's
//! `_roads_union` and `load_roads`, with the stored levels and the columns that render_map adds) and the base map's tables
//! (`features.*`, the queries of mapstyle's `load_layers`). One copy of the SQL: the browser (duckdb-wasm), Python (duckdb) and a
//! native caller run the same statements on their own connection. The SQL is the SQL of rust/roadstyle-wasm/js/roads_sql.js and
//! features_sql.js. The caller reads the catalog first (`Catalog`, from `information_schema`), then runs the statements in order;
//! the outputs are the engine's inputs (roads.parquet, features.parquet).

use serde_json::Value;

/// The networks of a duckOSM file, in order.
pub const MODES: [&str; 3] = ["driving", "walking", "cycling"];
const OPTIONAL_COLS: [&str; 4] = ["walk_type", "junction", "edge_ref", "lanes"];
const PATH_CLASSES: [&str; 7] = ["footway", "path", "cycleway", "steps", "pedestrian", "bridleway", "corridor"];
const COLS: &str = "edge_id, source, target, osm_id, highway, name, bridge, tunnel, layer, oneway, geometry";

/// The SQL that reads the catalog: the tables (schema, table) and the columns (schema, table, column) of the database `catalog`.
pub fn catalog_sql(catalog: &str) -> [String; 2] {
    let c = catalog.replace('\'', "''");
    [format!("SELECT table_schema AS s, table_name AS t FROM information_schema.tables WHERE table_catalog = '{c}'"),
     format!("SELECT table_schema AS s, table_name AS t, column_name AS c FROM information_schema.columns WHERE table_catalog = '{c}'")]
}

/// The tables and the columns of a duckOSM file (the rows of `catalog_sql`).
#[derive(Clone, Debug, Default)]
pub struct Catalog {
    pub tables: Vec<(String, String)>,
    pub columns: Vec<(String, String, String)>,
}

impl Catalog {
    fn has_table(&self, s: &str, t: &str) -> bool {
        self.tables.iter().any(|(a, b)| a == s && b == t)
    }

    fn has_column(&self, s: &str, t: &str, c: &str) -> bool {
        self.columns.iter().any(|(a, b, x)| a == s && b == t && x == c)
    }
}

/// _roads_union: every mode's edges and private_edges, NULL for an optional column that the file does not have.
fn roads_union(cat: &Catalog) -> Result<String, String> {
    let modes: Vec<&str> = MODES.iter().copied().filter(|m| cat.has_table(m, "edges")).collect();
    if modes.is_empty() {
        return Err(format!("no <mode>.edges table (modes: {})", MODES.join(", ")));
    }
    let mut private: Vec<&str> = modes.iter().copied().filter(|m| cat.has_table(m, "private_edges")).collect();
    private.sort();
    let optional = |m: &str, t: &str, skip: &[&str]| OPTIONAL_COLS.iter().map(|c| {
        let v = if cat.has_column(m, t, c) && !skip.contains(c) { c.to_string() }
                else if *c == "edge_ref" { "CAST(NULL AS VARCHAR)".into() } else { "NULL".into() };
        format!("{v} AS {c}")
    }).collect::<Vec<_>>().join(", ");
    Ok(modes.iter().map(|m| format!("SELECT {COLS}, {}, '{m}' AS mode, NULL AS pmode, NULL AS access FROM {m}.edges", optional(m, "edges", &[])))
        .chain(private.iter().map(|m| format!("SELECT {COLS}, {}, NULL AS mode, '{m}' AS pmode, access FROM {m}.private_edges",
                                               optional(m, "private_edges", &["walk_type"]))))
        .collect::<Vec<_>>().join(" UNION ALL "))
}

/// The SQL of the stored levels' metadata: one row (source, n_edges, edge_hash). The caller checks it with `levels_keyword`.
pub const LEVELS_META_SQL: &str = "SELECT source, n_edges, edge_hash FROM visualization.edge_levels_meta";

/// The look's keyword `levels` of the stored levels: {edge_hash, n_edges}, which the engine checks against the roads. `row`: the row of
/// `LEVELS_META_SQL` (source, n_edges, edge_hash), or None when the file has no such table or row.
pub fn levels_keyword(row: Option<(&str, i64, &str)>) -> Result<Value, String> {
    let (source, n, hash) = row.ok_or("no visualization.edge_levels_meta in this file: make and solve its level area (duckosm levels)")?;
    if !["area", "tags", "solve"].contains(&source) {
        return Err("the stored levels are not from a level area: make and solve its level area again".into());
    }
    Ok(serde_json::json!({"edge_hash": hash, "n_edges": n}))
}

const NO_LEVELS: &str = "CAST(NULL AS INTEGER) AS casing_start, CAST(NULL AS INTEGER) AS casing_level, CAST(NULL AS INTEGER) AS casing_end, \
    CAST(NULL AS INTEGER) AS fill_level, CAST(NULL AS DOUBLE) AS head_start_m, CAST(NULL AS DOUBLE) AS head_end_m, \
    CAST(NULL AS VARCHAR) AS cap_start, CAST(NULL AS VARCHAR) AS cap_end";

/// The statements that make the temporary table `r` (one row for each edge of every mode, with its stored levels; `tags`: no stored
/// levels, the engine computes them with the tags rule), in order. Run them one time for each file; then `roads_select` for each mode.
/// Before the second statement the caller reads `LEVELS_META_SQL` (not with `tags`).
pub fn roads_sql(cat: &Catalog, tags: bool) -> Result<[String; 3], String> {
    let union = roads_union(cat)?;
    let first = |c: &str| format!("first({c} ORDER BY mode IS NULL, mode, pmode)");
    let e = format!("CREATE OR REPLACE TEMP TABLE e AS
    SELECT edge_id, any_value(source) AS source, any_value(target) AS target,
           {} AS osm_id, {} AS highway, COALESCE({}, '') AS name,
           {} AS bridge, {} AS tunnel, {} AS layer, bool_or(oneway) AS oneway,
           any_value(walk_type) AS walk_type,
           {},
           {},
           {},
           {} AS geom
    FROM ({union}) GROUP BY edge_id",
        first("osm_id"), first("highway"), first("name"), first("bridge"), first("tunnel"), first("layer"),
        OPTIONAL_COLS[1..].iter().map(|c| format!("{} AS {c}", first(c))).collect::<Vec<_>>().join(", "),
        MODES.iter().map(|m| format!("COALESCE(bool_or(mode = '{m}'), false) AS {m}")).collect::<Vec<_>>().join(", "),
        MODES.iter().map(|m| format!("max(CASE WHEN pmode = '{m}' THEN access END) AS access_{m}")).collect::<Vec<_>>().join(", "),
        first("geometry"));
    let path = format!("coalesce(highway IN ({}), false)", PATH_CLASSES.iter().map(|c| format!("'{c}'")).collect::<Vec<_>>().join(", "));
    let levels = if tags { NO_LEVELS.to_string() }
                 else { "lv.casing_start, lv.casing_level, lv.casing_end, lv.fill_level, lv.head_start_m, lv.head_end_m, lv.cap_start, lv.cap_end".into() };
    let r = format!("CREATE OR REPLACE TEMP TABLE r AS
    SELECT e.* EXCLUDE (geom), ST_AsWKB(e.geom) AS geometry,
           NOT driving AND NOT cycling AND NOT {path} AND osm_id IN (SELECT osm_id FROM e WHERE driving OR cycling) AS und,
           {path} AS path,
           {levels}
    FROM e {}", if tags { "" } else { "LEFT JOIN visualization.edge_levels lv ON lv.edge_id = e.edge_id" });
    Ok([e, r, "DROP TABLE e".into()])
}

/// The roads of the map of `mode` ("all", or one network) from the table `r` of `roads_sql`, in the order of mapstyle's load_roads (an
/// undirected edge on a street's own directed edge first, then by edge_id), with the columns that render_map adds: `access` (_access),
/// `is_directed` (_is_directed) and `has_arrows`. A SELECT: the browser writes it as roads.parquet (`COPY (...) TO`).
pub fn roads_select(mode: &str) -> Result<String, String> {
    if mode != "all" && !MODES.contains(&mode) {
        return Err(format!("unknown mode {mode}"));
    }
    let access = if mode != "all" { format!("CASE WHEN NOT {mode} THEN access_{mode} END") } else {
        "CASE WHEN access_driving = 'bus' THEN access_driving
    WHEN NOT (driving OR walking OR cycling) AND (access_driving IS NOT NULL OR access_walking IS NOT NULL OR access_cycling IS NOT NULL)
    THEN coalesce(access_driving, access_walking, access_cycling) END".into()
    };
    let restricted = "coalesce(access IN ('private', 'bus'), false)";
    Ok(format!("WITH a AS (SELECT *, {access} AS access FROM r)
    SELECT a.* EXCLUDE (und, path, access_driving, access_walking, access_cycling),
           (driving OR cycling OR {restricted}) AND NOT path AS is_directed,
           driving OR {restricted} AS has_arrows
    FROM a ORDER BY NOT und, edge_id"))
}

/// One base-map layer's query (`features_sql`): the layer's index in layers.yaml, its name, and its SELECT with the height tags of a
/// building and without them (an older file has no tags). The caller makes `f<spec>` from the first that runs (`CREATE OR REPLACE TEMP
/// TABLE f<spec> AS <select>`), and skips the layer when neither runs, as load_layers does.
pub struct LayerSql {
    pub spec: usize,
    pub name: String,
    pub with_tags: String,
    pub without_tags: String,
}

/// The queries of the base map's layers (`specs`: the look's features.layers_yaml.layers) that the file has, in layers.yaml's order.
pub fn features_sql(cat: &Catalog, specs: &[Value]) -> Vec<LayerSql> {
    // _network_ways: the OSM ids of the ways that a mode network holds; a layer of the ways outside them is skipped when there is none
    let nets = cat.tables.iter().filter(|(s, t)| MODES.contains(&s.as_str()) && ["edges", "private_edges", "edge_id_map"].contains(&t.as_str()))
        .map(|(s, t)| format!("SELECT osm_id FROM \"{s}\".\"{t}\"")).collect::<Vec<_>>().join(" UNION ");
    let q = |s: &str| s.replace('\'', "''");
    let mut out = Vec::new();
    for (i, s) in specs.iter().enumerate() {
        let (table, schema) = (s["table"].as_str().unwrap_or_default(), s["schema"].as_str());
        if s["show"] == false || !cat.has_table(schema.unwrap_or("features"), table) || (s["outside_networks"] == true && nets.is_empty()) {
            continue;
        }
        let name = s["name"].as_str().unwrap_or_default();
        let layer = q(s["merge_into"].as_str().unwrap_or(name));
        // a table outside features.* (the boundary): the kind is the layer's name
        let kind = if schema.is_some() { format!("'{}'", q(name)) } else { "kind".into() };
        let bearing = if s["bearing"] == true { "CAST(bearing AS DOUBLE)" } else { "CAST(NULL AS DOUBLE)" };
        let sql = |tag: &dyn Fn(&str) -> String| format!("SELECT {i} AS spec, '{layer}' AS layer, rowid AS rid, CAST(osm_id AS VARCHAR) AS osm_id, {kind} AS kind,
        COALESCE(name, '') AS name, {bearing} AS bearing, CAST({} AS VARCHAR) AS levels,
        CAST({} AS VARCHAR) AS roof_levels, CAST({} AS VARCHAR) AS height, CAST({} AS VARCHAR) AS min_height,
        CAST({} AS VARCHAR) AS min_level, ST_AsWKB(geom) AS geometry FROM {}.{table} WHERE geom IS NOT NULL
        {}{}", tag("building:levels"), tag("roof:levels"), tag("height"), tag("min_height"), tag("building:min_level"),
            schema.unwrap_or("features"), s["where"].as_str().map(|w| format!(" AND ({w})")).unwrap_or_default(),
            if s["outside_networks"] == true { format!(" AND osm_id NOT IN ({nets})") } else { String::new() });
        let none = |_: &str| "NULL".to_string();
        let tags = |k: &str| format!("tags['{k}'][1]");
        out.push(LayerSql { spec: i, name: name.to_string(), with_tags: if s["height"] == true { sql(&tags) } else { sql(&none) }, without_tags: sql(&none) });
    }
    out
}

/// The base map's rows from the tables `f<spec>` that the caller made (`specs`: the spec numbers of those tables), in load_layers'
/// order: the layers in layers.yaml's order, each table in its rowid order. A SELECT: the browser writes it as features.parquet.
pub fn features_select(specs: &[usize]) -> Option<String> {
    (!specs.is_empty()).then(|| format!("{} ORDER BY spec, rid", specs.iter().map(|i| format!("SELECT * FROM f{i}")).collect::<Vec<_>>().join(" UNION ALL ")))
}
