//! The SQL that reads a duckOSM file (docs/design/rust_library.md, the mapstyle merge): the roads of every mode (mapstyle's
//! `_roads_union` and `load_roads`, with the stored levels and the columns that render_map adds) and the base map's tables
//! (`features.*`, the queries of mapstyle's `load_layers`). One copy of the SQL: the browser (duckdb-wasm), Python (duckdb) and a
//! native caller run the same statements on their own connection. The SQL is the SQL of rust/roadstyle-wasm/js/roads_sql.js and
//! features_sql.js. The caller reads the catalog first (`Catalog`, from `information_schema`), then runs the statements in order;
//! the outputs are the engine's inputs (roads.parquet, features.parquet).

use crate::Error;
use roadstyle_model::feature_table::{FeatureTable, GeomType, Geometries};
use roadstyle_model::Cell;
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

/// _roads_union: every mode's edges and private_edges (`only`: one mode's), NULL for an optional column that the file does not have.
fn roads_union(cat: &Catalog, only: Option<&str>) -> Result<String, Error> {
    if let Some(m) = only.filter(|m| !MODES.contains(m)) {
        return Err(Error::Options(format!("only: a map of one mode needs the mode driving, walking or cycling, not {m}")));
    }
    let modes: Vec<&str> = MODES.iter().copied().filter(|m| cat.has_table(m, "edges") && only.is_none_or(|o| o == *m)).collect();
    if modes.is_empty() {
        return Err(Error::Options(format!("no <mode>.edges table (modes: {})", only.map_or_else(|| MODES.join(", "), String::from))));
    }
    let mut private: Vec<&str> = modes.iter().copied().filter(|m| cat.has_table(m, "private_edges")).collect();
    private.sort();
    let optional = |m: &str, t: &str, skip: &[&str]| OPTIONAL_COLS.iter().map(|c| {
        let v = if cat.has_column(m, t, c) && !skip.contains(c) { c.to_string() }
                else if *c == "edge_ref" { "CAST(NULL AS VARCHAR)".into() } else { "NULL".into() };
        format!("{v} AS {c}")
    }).collect::<Vec<_>>().join(", ");
    // pmode and access as text where the branch has none: with no private_edges they are NULL only, which DuckDB types as an integer
    Ok(modes.iter().map(|m| format!("SELECT {COLS}, {}, '{m}' AS mode, CAST(NULL AS VARCHAR) AS pmode, CAST(NULL AS VARCHAR) AS access FROM {m}.edges",
                                    optional(m, "edges", &[])))
        .chain(private.iter().map(|m| format!("SELECT {COLS}, {}, NULL AS mode, '{m}' AS pmode, access FROM {m}.private_edges",
                                               optional(m, "private_edges", &["walk_type"]))))
        .collect::<Vec<_>>().join(" UNION ALL "))
}

/// The SQL of the stored levels' metadata: one row (source, n_edges, edge_hash). The caller checks it with `levels_keyword`.
pub const LEVELS_META_SQL: &str = "SELECT source, n_edges, edge_hash FROM visualization.edge_levels_meta";

/// The look's keyword `levels` of the stored levels: {edge_hash, n_edges}, which the engine checks against the roads. `row`: the row of
/// `LEVELS_META_SQL` (source, n_edges, edge_hash), or None when the file has no such table or row.
pub fn levels_keyword(row: Option<(&str, i64, &str)>) -> Result<Value, Error> {
    let (source, n, hash) = row.ok_or_else(|| Error::Levels("no visualization.edge_levels_meta in this file: make and solve its level area (duckosm levels)".into()))?;
    if !["area", "tags", "solve"].contains(&source) {
        return Err(Error::Levels("the stored levels are not from a level area: make and solve its level area again".into()));
    }
    Ok(serde_json::json!({"edge_hash": hash, "n_edges": n}))
}

/// The roads of `r` (after `roads_sql`) that have no stored levels: (their number, the smallest edge_id of them), for a map of one mode.
pub const SUBSET_SQL: &str = "SELECT count(*), min(edge_id) FROM r WHERE NOT EXISTS (SELECT 1 FROM visualization.edge_levels lv WHERE lv.edge_id = r.edge_id)";

/// The edge_ids of the roads of `r`, for `subset_levels_keyword`.
pub const IDS_SQL: &str = "SELECT edge_id FROM r";

/// The look's keyword `levels` of the stored levels for a map of one mode (roadstyle's load_area_levels(subset=True)): the levels were
/// solved for the roads of every mode together, so each road of the map must have its stored row (`missing`, `example`: `SUBSET_SQL`'s
/// row). Then the keyword names these roads (`ids`: their edge_ids), so that the engine's check of the roads holds for them.
pub fn subset_levels_keyword(row: Option<(&str, i64, &str)>, missing: i64, example: Option<i64>, ids: &[i64]) -> Result<Value, Error> {
    levels_keyword(row)?;
    if missing > 0 {
        return Err(Error::Levels(format!("{missing} of the edges are not edges the stored levels were solved for (for example {}): make and solve the \
                            level area again (duckosm levels)", example.map_or_else(|| "?".into(), |e| e.to_string()))));
    }
    Ok(serde_json::json!({"edge_hash": roadstyle_levels::edge_hash(ids), "n_edges": ids.len()}))
}

const NO_LEVELS: &str = "CAST(NULL AS INTEGER) AS casing_start, CAST(NULL AS INTEGER) AS casing_level, CAST(NULL AS INTEGER) AS casing_end, \
    CAST(NULL AS INTEGER) AS fill_level, CAST(NULL AS DOUBLE) AS head_start_m, CAST(NULL AS DOUBLE) AS head_end_m, \
    CAST(NULL AS VARCHAR) AS cap_start, CAST(NULL AS VARCHAR) AS cap_end";

/// The statements that make the temporary table `r` (one row for each edge of every mode, with its stored levels; `tags`: no stored
/// levels, the engine computes them with the tags rule), in order. Run them one time for each file; then `roads_select` for each mode.
/// Before the second statement the caller reads `LEVELS_META_SQL` (not with `tags`). `only`: the edges and private_edges of that mode
/// alone (render_map(only=True): a driving map has no walking paths); then the stored levels are checked with `SUBSET_SQL` and
/// `subset_levels_keyword`, and `roads_select` takes that mode.
pub fn roads_sql(cat: &Catalog, tags: bool, only: Option<&str>) -> Result<[String; 3], String> {
    let union = roads_union(cat, only)?;
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
pub fn roads_select(mode: &str) -> Result<String, Error> {
    if mode != "all" && !MODES.contains(&mode) {
        return Err(Error::Options(format!("unknown mode {mode}")));
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
pub fn cut_sea(t: FeatureTable) -> Result<FeatureTable, Error> {
    use i_overlay::core::{fill_rule::FillRule, overlay_rule::OverlayRule};
    use i_overlay::float::single::SingleFloatOverlay;
    let is = |r: usize, layer: &str, kind: Option<&str>| t.get(r, "layer").and_then(Cell::as_str) == Some(layer)
        && kind.is_none_or(|k| t.get(r, "kind").and_then(Cell::as_str) == Some(k));
    let g = t.geometries_of();
    let sea: Vec<Vec<[f64; 2]>> = (0..t.len()).filter(|&r| is(r, "ocean", None)).map(|r| rings(g, r))
        .collect::<Result<Vec<_>, _>>()?.into_iter().flatten().collect();
    if sea.is_empty() || !(0..t.len()).any(|r| is(r, "landcover", Some("background"))) {
        return Ok(t);
    }
    let mut out = FeatureTable::geometries();
    for r in 0..t.len() {
        if !is(r, "landcover", Some("background")) {
            out.push_copy(g, r);
            continue;
        }
        let parts = rings(g, r)?.overlay(&sea, OverlayRule::Difference, FillRule::NonZero);
        let closed: Vec<Vec<Vec<[f64; 2]>>> = parts.into_iter().map(|rings| rings.into_iter().map(|mut r| {
            if r.first() != r.last() {
                r.push(r[0]);
            }
            r
        }).collect()).collect();
        out.push(GeomType::MultiPolygon, &closed);
    }
    t.with_geometries(out).map_err(Error::Data)
}

/// Every ring of the Polygon or MultiPolygon `row`.
fn rings(g: &Geometries, row: usize) -> Result<Vec<Vec<[f64; 2]>>, Error> {
    match g.kind(row) {
        Some(GeomType::Polygon | GeomType::MultiPolygon) => Ok(g.parts(row).flatten().map(<[_]>::to_vec).collect()),
        k => Err(Error::Data(format!("the base map: a background or sea row is a {}, not a polygon", k.map_or("geometry of no type", GeomType::name)))),
    }
}

/// The optional columns of a level area's edges (duckOSM's levels.OPTIONAL).
const LEVEL_OPTIONAL: [&str; 5] = ["walk_type", "junction", "name", "edge_ref", "lanes"];

/// The edges of a level area of a duckOSM file (duckOSM's levels.load_roads, the input of `duckosm levels` and of make_area): one row for
/// each edge_id of every mode's edges and private_edges, in edge_id order, the attributes of its first row (the modes in the order
/// driving, walking, cycling, `edges` before `private_edges`); `driving` and `cycling` (in that mode's network); `oneway` (the driving
/// network's, NULL off it); `modes` ("driving + walking"; a cycling edge where bikes are pushed is walked; a private road only: its
/// modes with " (private)"; "bus" where a bus route runs); `bus_lines` (the refs of bus.route_edges, "1, 2, 5"); the line as WKB in
/// `geometry`. A SELECT: a page writes it as Parquet (`COPY (...) TO`) for makeArea.
pub fn level_edges_sql(cat: &Catalog) -> Result<String, Error> {
    let modes: Vec<&str> = MODES.iter().copied().filter(|m| cat.has_table(m, "edges")).collect();
    if modes.is_empty() {
        return Err(Error::Options(format!("no <mode>.edges table in this file (modes: {})", MODES.join(", "))));
    }
    let col = |m: &str, t: &str, c: &str| if cat.has_column(m, t, c) { c.to_string() } else { "NULL".into() };
    let part = |m: &str, t: &str, mode: &str, pmode: &str, rank: usize| format!(
        "SELECT edge_id, highway, layer, bridge, tunnel, geometry, {}, {} AS oneway, {} AS dismount, {mode} AS mode, {pmode} AS pmode, {rank} AS rank FROM {m}.{t}",
        LEVEL_OPTIONAL.iter().map(|c| format!("{} AS {c}", col(m, t, c))).collect::<Vec<_>>().join(", "), col(m, t, "oneway"), col(m, t, "dismount"));
    let union = modes.iter().enumerate().map(|(i, m)| part(m, "edges", &format!("'{m}'"), "NULL", i))
        .chain(modes.iter().enumerate().filter(|(_, m)| cat.has_table(m, "private_edges"))
               .map(|(i, m)| part(m, "private_edges", "NULL", &format!("'{m}'"), MODES.len() + i)))
        .collect::<Vec<_>>().join(" UNION ALL ");
    // a cycling edge where bikes are pushed (dismount) is walked
    let walked = |c: &str| format!("CASE WHEN {c} = 'cycling' AND coalesce(dismount, false) THEN 'walking' ELSE {c} END");
    let has = |list: &str, m: &str, suffix: &str| format!("CASE WHEN list_contains({list}, '{m}') THEN '{m}{suffix}' END");
    let joined = |list: &str, suffix: &str| format!("NULLIF(concat_ws(' + ', {}), '')", MODES.iter().map(|m| has(list, m, suffix)).collect::<Vec<_>>().join(", "));
    let (bus_join, bus) = if cat.has_table("bus", "route_edges") {
        // the bus lines in natural order: numbers before letters, 2 before 11
        ("LEFT JOIN (SELECT edge_id, string_agg(x, ', ' ORDER BY NOT regexp_full_match(x, '[0-9]+'), \
          CASE WHEN regexp_full_match(x, '[0-9]+') THEN CAST(x AS BIGINT) ELSE 0 END, x) AS bus_lines \
          FROM (SELECT DISTINCT edge_id, coalesce(ref, CAST(route_id AS VARCHAR)) AS x FROM bus.route_edges) GROUP BY edge_id) b USING (edge_id)", "b.bus_lines")
    } else {
        ("", "CAST(NULL AS VARCHAR)")
    };
    Ok(format!("SELECT edge_id, highway, layer, bridge, tunnel, {}, driving, cycling, oneway,
       NULLIF(concat_ws(' + ', coalesce({}, {}), CASE WHEN {bus} IS NOT NULL THEN 'bus' END), '') AS modes, {bus} AS bus_lines, geometry
FROM (SELECT edge_id, first(highway ORDER BY rank) AS highway, first(layer ORDER BY rank) AS layer, first(bridge ORDER BY rank) AS bridge,
             first(tunnel ORDER BY rank) AS tunnel, {},
             list(DISTINCT {}) FILTER (WHERE mode IS NOT NULL) AS mode_list,
             list(DISTINCT {}) FILTER (WHERE pmode IS NOT NULL) AS private_list,
             coalesce(bool_or(mode = 'driving'), false) AS driving, coalesce(bool_or(mode = 'cycling'), false) AS cycling,
             bool_or(oneway) FILTER (WHERE mode = 'driving') AS oneway, ST_AsWKB(first(geometry ORDER BY rank)) AS geometry
      FROM ({union}) GROUP BY edge_id) {bus_join}
ORDER BY edge_id",
        LEVEL_OPTIONAL.join(", "), joined("mode_list", ""), joined("private_list", " (private)"),
        LEVEL_OPTIONAL.iter().map(|c| format!("first({c} ORDER BY rank) AS {c}")).collect::<Vec<_>>().join(", "),
        walked("mode"), walked("pmode")))
}

#[cfg(test)]
mod tests {
    use super::*;
    use arrow_array::{ArrayRef, StringArray};
    use std::sync::Arc;

    fn square(x0: f64, y0: f64, x1: f64, y1: f64) -> Vec<Vec<Vec<[f64; 2]>>> {
        vec![vec![vec![[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]]
    }

    #[test]
    fn the_land_is_the_boundary_less_the_sea() {
        // a 2 x 2 boundary, the sea over its right half: the land is the left half, closed, its outer ring counter-clockwise (RFC 7946)
        let mut g = FeatureTable::geometries();
        for sq in [square(0.0, 0.0, 2.0, 2.0), square(1.0, -1.0, 3.0, 3.0), square(0.0, 0.0, 2.0, 2.0)] {
            g.push(GeomType::MultiPolygon, &sq);
        }
        let col = |v: [&str; 3]| -> ArrayRef { Arc::new(StringArray::from(v.to_vec())) };
        let t = FeatureTable::new(vec!["layer".into(), "kind".into()], vec![col(["landcover", "ocean", "landcover"]), col(["background", "ocean", "park"])], g)
            .unwrap();
        let t = cut_sea(t).unwrap();
        let land = t.geometries_of().to_geojson(0);
        assert_eq!(land["coordinates"].as_array().unwrap().len(), 1);
        let r: Vec<[f64; 2]> = serde_json::from_value(land["coordinates"][0][0].clone()).unwrap();
        assert_eq!(r.first(), r.last());
        let area2: f64 = (0..r.len() - 1).map(|i| r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1]).sum();
        assert!((area2 / 2.0 - 2.0).abs() < 1e-9, "area {}", area2 / 2.0);
        assert_eq!(t.geometries_of().to_geojson(2), serde_json::json!({"type": "MultiPolygon", "coordinates": square(0.0, 0.0, 2.0, 2.0)}),
                   "only the background changes");
    }
}
