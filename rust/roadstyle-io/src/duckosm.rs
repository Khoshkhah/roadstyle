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

/// One base-map layer's queries (`features_sql`): the layer's index in layers.yaml, its name, and its SELECTs in order: the first is
/// mapstyle's query; the next one is mapstyle's fallback (a file with no `tags` column: no height tags, the height of the kind). The
/// caller makes `f<spec>` from the first that runs (`CREATE OR REPLACE TEMP TABLE f<spec> AS <select>`), says so when it is not the
/// first, and skips the layer when none runs, as load_layers does. The background is the whole boundary here: `cut_sea` makes its land.
pub struct LayerSql {
    pub spec: usize,
    pub name: String,
    pub sql: Vec<String>,
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
        let sql = |geom: &str, tag: &dyn Fn(&str) -> String| format!("SELECT {i} AS spec, '{layer}' AS layer, rowid AS rid, CAST(osm_id AS VARCHAR) AS osm_id, {kind} AS kind,
        COALESCE(name, '') AS name, {bearing} AS bearing, CAST({} AS VARCHAR) AS levels,
        CAST({} AS VARCHAR) AS roof_levels, CAST({} AS VARCHAR) AS height, CAST({} AS VARCHAR) AS min_height,
        CAST({} AS VARCHAR) AS min_level, ST_AsWKB({geom}) AS geometry FROM {}.{table} WHERE geom IS NOT NULL
        {}{}", tag("building:levels"), tag("roof:levels"), tag("height"), tag("min_height"), tag("building:min_level"),
            schema.unwrap_or("features"), s["where"].as_str().map(|w| format!(" AND ({w})")).unwrap_or_default(),
            if s["outside_networks"] == true { format!(" AND osm_id NOT IN ({nets})") } else { String::new() });
        let none = |_: &str| "NULL".to_string();
        let tags = |k: &str| format!("tags['{k}'][1]");
        let queries = if s["height"] == true { vec![sql("geom", &tags), sql("geom", &none)] } else { vec![sql("geom", &none)] };
        out.push(LayerSql { spec: i, name: name.to_string(), sql: queries });
    }
    out
}

/// The base map's rows from the tables `f<spec>` that the caller made (`specs`: the spec numbers of those tables), in load_layers'
/// order: the layers in layers.yaml's order, each table in its rowid order. A SELECT: the browser writes it as features.parquet.
pub fn features_select(specs: &[usize]) -> Option<String> {
    (!specs.is_empty()).then(|| format!("{} ORDER BY spec, rid", specs.iter().map(|i| format!("SELECT * FROM f{i}")).collect::<Vec<_>>().join(" UNION ALL ")))
}

/// The background of the base map's rows (`features_select`: the layer `landcover`, kind `background`, the whole boundary) as the land:
/// the boundary less the sea (the rows of the layer `ocean`), as mapstyle's load_layers makes it with ST_Difference, so that a map with
/// no sea layer does not paint the sea as land. In Rust (i_overlay), so that no reader needs DuckDB's spatial extension. The rings are
/// closed (WKB and GeoJSON need it), in i_overlay's orientation, which is RFC 7946's (outer rings counter-clockwise, holes clockwise).
/// Nothing changes when the rows have no background or no sea.
pub fn cut_sea(rows: &mut [roadstyle_model::Row]) -> Result<(), String> {
    use i_overlay::core::{fill_rule::FillRule, overlay_rule::OverlayRule};
    use i_overlay::float::single::SingleFloatOverlay;
    let is = |r: &roadstyle_model::Row, layer: &str, kind: Option<&str>| r.cols.get("layer").and_then(Value::as_str) == Some(layer)
        && kind.is_none_or(|k| r.cols.get("kind").and_then(Value::as_str) == Some(k));
    let sea: Vec<Vec<[f64; 2]>> = rows.iter().filter(|r| is(r, "ocean", None))
        .map(|r| polygons(r.blob.as_deref())).collect::<Result<Vec<_>, _>>()?.into_iter().flatten().flatten().collect();
    if sea.is_empty() {
        return Ok(());
    }
    for r in rows.iter_mut().filter(|r| is(r, "landcover", Some("background"))) {
        let land: Vec<Vec<[f64; 2]>> = polygons(r.blob.as_deref())?.into_iter().flatten().collect();
        let parts = land.overlay(&sea, OverlayRule::Difference, FillRule::NonZero);
        let closed: Vec<Vec<Vec<[f64; 2]>>> = parts.into_iter().map(|rings| rings.into_iter().map(|mut r| {
            if r.first() != r.last() {
                r.push(r[0]);
            }
            r
        }).collect()).collect();
        r.blob = Some(multipolygon_wkb(&closed));
    }
    Ok(())
}

/// The polygons of a WKB Polygon or MultiPolygon (each a list of rings, the outer ring first).
fn polygons(wkb: Option<&[u8]>) -> Result<Vec<Vec<Vec<[f64; 2]>>>, String> {
    let g = wkb.and_then(crate::read::wkb_geometry).ok_or("the base map: a background or sea row with no polygon")?;
    let ring = |r: &Value| r.as_array().into_iter().flatten().filter_map(|p| Some([p[0].as_f64()?, p[1].as_f64()?])).collect::<Vec<_>>();
    let poly = |p: &Value| p.as_array().into_iter().flatten().map(ring).collect::<Vec<_>>();
    match g["type"].as_str() {
        Some("Polygon") => Ok(vec![poly(&g["coordinates"])]),
        Some("MultiPolygon") => Ok(g["coordinates"].as_array().into_iter().flatten().map(poly).collect()),
        t => Err(format!("the base map: a background or sea row is a {}, not a polygon", t.unwrap_or("geometry of no type"))),
    }
}

/// A WKB MultiPolygon (little-endian, 2D).
fn multipolygon_wkb(parts: &[Vec<Vec<[f64; 2]>>]) -> Vec<u8> {
    let mut w = vec![1u8];
    w.extend(6u32.to_le_bytes());
    w.extend((parts.len() as u32).to_le_bytes());
    for rings in parts {
        w.push(1);
        w.extend(3u32.to_le_bytes());
        w.extend((rings.len() as u32).to_le_bytes());
        for r in rings {
            w.extend((r.len() as u32).to_le_bytes());
            r.iter().for_each(|p| { w.extend(p[0].to_le_bytes()); w.extend(p[1].to_le_bytes()); });
        }
    }
    w
}

#[cfg(test)]
mod tests {
    use super::*;
    use roadstyle_model::Row;

    fn square(x0: f64, y0: f64, x1: f64, y1: f64) -> Vec<u8> {
        multipolygon_wkb(&[vec![vec![[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]])
    }

    fn row(layer: &str, kind: &str, wkb: Vec<u8>) -> Row {
        let mut r = Row { cols: serde_json::Map::new(), blob: Some(wkb) };
        r.cols.insert("layer".into(), layer.into());
        r.cols.insert("kind".into(), kind.into());
        r
    }

    #[test]
    fn the_land_is_the_boundary_less_the_sea() {
        // a 2 x 2 boundary, the sea over its right half: the land is the left half, closed, its outer ring counter-clockwise (RFC 7946)
        let mut rows = vec![row("landcover", "background", square(0.0, 0.0, 2.0, 2.0)), row("ocean", "ocean", square(1.0, -1.0, 3.0, 3.0)),
                            row("landcover", "park", square(0.0, 0.0, 2.0, 2.0))];
        cut_sea(&mut rows).unwrap();
        let land = polygons(rows[0].blob.as_deref()).unwrap();
        assert_eq!(land.len(), 1);
        let r = &land[0][0];
        assert_eq!(r.first(), r.last());
        let area2: f64 = (0..r.len() - 1).map(|i| r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1]).sum();
        assert!((area2 / 2.0 - 2.0).abs() < 1e-9, "area {}", area2 / 2.0);
        assert_eq!(rows[2].blob, Some(square(0.0, 0.0, 2.0, 2.0)), "only the background changes");
    }
}
