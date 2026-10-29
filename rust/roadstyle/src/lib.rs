//! roadstyle as a Rust library (docs/design/rust_library.md): the facade. It re-exports the crates of the core with the module paths
//! of the old single crate (`roadstyle::props`, `roadstyle::read`, `roadstyle::levels`, `roadstyle::tiles`, `roadstyle::inline_style`,
//! ...), and it has the functions that read GeoParquet bytes (roadstyle-io) and call the engine: `inline_style` and `tiled_from_parquet`, which
//! needs both the engine and the tiles. A Rust user adds only this crate.

pub use roadstyle_engine::*;
pub use roadstyle_io::{crs, duckosm, geojson, read, shp};
/// roadstyle's files by name (the look, the base map, the dashboard, the page templates, MapLibre): `assets::text!("vendor/maplibre-gl.js")`
pub use roadstyle_assets as assets;
#[cfg(feature = "gpkg")]
pub use roadstyle_io::gpkg;
pub mod error;
pub use error::Error;
pub use roadstyle_engine::Error as EngineError;
pub mod dashboard;
pub mod level_area;
pub mod level_editor;
pub mod options;
pub mod page;
pub mod page_options;
pub mod relevel;
pub use roadstyle_levels as levels;
pub use roadstyle_tiles as tiles;

use roadstyle_engine::sources::Source;
use roadstyle_engine::table::js_value;
use serde_json::{json, Value};

/// The roads, the base map's rows and the route planner's rows.
type Tables = (RoadTable, Option<FeatureTable>, Option<Vec<Row>>);

/// The roads and the other tables from their GeoParquet bytes: the roads' lines and the base map's geometries in the column `geometry`.
fn tables(parquet: Vec<u8>, features: Option<Vec<u8>>, planner: Option<Vec<u8>>) -> Result<Tables, crate::Error> {
    Ok((read::read_roads(parquet, "geometry")?,
        features.map(read_features).transpose()?,
        planner.map(|p| read::read_table(p, "")).transpose()?))
}

/// The base map's rows from their GeoParquet bytes (the duckOSM reader's features.parquet), clipped to the area's boundary
/// (duckosm::clip_to_boundary), the background's land without the sea (duckosm::cut_sea).
pub fn read_features(features: Vec<u8>) -> Result<FeatureTable, crate::Error> {
    features_of(read::read_feature_table(features, "geometry")?)
}

/// The base map's rows that a reader gave (`read::feature_table_from`, ...), as `read_features`.
pub fn features_of(t: FeatureTable) -> Result<FeatureTable, crate::Error> {
    Ok(duckosm::cut_sea(duckosm::clip_to_boundary(t)?)?)
}

/// The style as one JSON text (roadstyle's export_inline), from the roads and the other tables as GeoParquet bytes: the engine's
/// `inline_style` after roadstyle-io's readers.
pub fn inline_style(parquet: Vec<u8>, look: &Look, features: Option<Vec<u8>>, planner: Option<Vec<u8>>, name: Option<String>) -> Result<String, crate::Error> {
    let (feats, features, planner) = tables(parquet, features, planner)?;
    Ok(roadstyle_engine::inline_style(feats, look, features, planner, name)?)
}

/// Stage 1 from GeoParquet bytes: the style and its sources, typed in memory (docs/rust/architecture.md, "The three stages and the one
/// call"). `write_sources` writes them as files; the saved style has what stage 2 reads (`roadstyle:tiles`: the look's tile settings,
/// `roadstyle:columns`: the class, filter and metre width columns).
pub fn style_sources(parquet: Vec<u8>, look: &Look, features: Option<Vec<u8>>, planner: Option<Vec<u8>>, name: Option<String>) -> Result<sources::Styled, crate::Error> {
    let (feats, features, planner) = tables(parquet, features, planner)?;
    sources_of(feats, look, features, planner, name)
}

/// Stage 1 of roads that a reader gave (`read::read_roads`, `geojson::read_roads`, ...), as `style_sources`.
pub fn sources_of(roads: RoadTable, look: &Look, features: Option<FeatureTable>, planner: Option<Vec<Row>>, name: Option<String>)
                  -> Result<sources::Styled, crate::Error> {
    let mut s = sources::Styled::new(make_parts(roads, look, features, planner, name)?);
    s.saved.insert(tiles::stage::TILES.into(), serde_json::json!(look.sections.tiles));
    s.saved.insert(tiles::stage::COLUMNS.into(), columns(look));
    Ok(s)
}

/// `roadstyle:columns`: the user's class, filter and metre width columns (render's highway_col, filter_col, width_m_col).
fn columns(look: &Look) -> Value {
    let c = &look.map.columns;
    let given = |v: Option<&String>| v.filter(|c| !c.is_empty()).map_or(Value::Null, |c| Value::from(c.as_str()));
    json!({"class": given(Some(&c.class).filter(|c| *c != "highway")), "filter": given(c.filter.as_ref()), "width": given(c.width_m.as_ref())})
}

/// The first zoom of a source's tiles: the first zoom at which a layer of the style draws it (a layer without `minzoom` draws from 0),
/// and not past the tiles' last zoom (MapLibre scales that zoom up for the layers after it). Below it no layer draws a feature of the
/// source, so the tiles leave them out (2026-10-25: Tartu's buildings, drawn from zoom 15, were 455 KB of a 3 MB tile at zoom 12).
/// A source that no layer draws keeps `from` (a page can read it).
fn first_drawn(layers: &[Value], k: &str, from: u32, last: u32) -> u32 {
    let drawn = layers.iter().filter(|l| l["source"] == k).map(|l| l["minzoom"].as_f64().map_or(0, |z| z.floor() as u32)).min();
    drawn.map_or(from, |z| from.max(z.min(last)))
}

/// Stage 2 from memory: the tiles of stage 1's sources (`o`: the rules), borrowed (audit N6: `s` stays as it is).
fn tile_sources(s: &sources::Styled, o: &tiles::stage::TileOptions) -> Result<tiles::Tiles, tiles::Error> {
    let mut tiled = o.tiles()?;
    tiled.drawn_by(&s.layers);
    for (k, src) in s.shown().filter(|(k, _)| o.wants(k)) {
        tile_source(&mut tiled, s, o, k, src);
    }
    Ok(tiled)
}

/// One source of stage 1 as the tile layer `k` (`tile_sources`; the level editor's redraw adds a source again with it).
fn tile_source(tiled: &mut tiles::Tiles, s: &sources::Styled, o: &tiles::stage::TileOptions, k: &str, src: Source) {
    let keys = |v: &Value| -> std::collections::HashSet<String> {
        v["data"]["features"].as_array().into_iter().flatten().filter_map(|f| f["properties"].as_object()).flat_map(|p| p.keys().cloned()).collect()
    };
    match src {
        // the roads, from the table and the marks (no copy of their properties); a page has none
        Source::Roads(r) => {
            let (keep, whole, from) = o.rule(k, Default::default);
            tiled.add_lines(k, r.roads.iter().map(|x| (x.line(), r.props(x, None))), &keep, whole, first_drawn(&s.layers, k, from, o.max_zoom))        // the cells, no JSON copy
        }
        // the level editor's map (relevel.rs): each piece's box and first zoom now, its properties when a tile shows it
        Source::Simple(p) if o.wait && p.items.is_empty() => {
            let (keep, whole, from) = o.rule(k, Default::default);
            let keys = tiled.rule_keys(k);
            let feats = p.pieces.iter().zip(p.pieces_with(&s.roads.roads, &keys))
                .map(|((_, q), (id, props, c))| (c, props.into_iter(), roadstyle_engine::road::key(q.edge as usize).get(), id as u64));
            tiled.add_waiting(k, feats, &keep, whole, first_drawn(&s.layers, k, from, o.max_zoom))
        }
        Source::Simple(p) => {
            let (keep, whole, from) = o.rule(k, Default::default);
            tiled.add_lines(k, p.features(&s.roads.roads).map(|(_, props, c)| (c, props.into_iter())), &keep, whole, first_drawn(&s.layers, k, from, o.max_zoom))
        }
        Source::Json(v) => {
            let (keep, whole, from) = whole_unless_lines(json_lines(v), o.rule(k, || keys(v)), o.min_zoom);
            tiled.add(k, v, &keep, whole, first_drawn(&s.layers, k, from, o.max_zoom));
            let features = v["data"]["features"].as_array().into_iter().flatten();
            props_file(tiled, o, k, features.map(|f| f["properties"].clone()));
        }
        // a base-map layer, from its table (audit R10)
        Source::Features(f) => {
            use roadstyle_engine::feature_table::GeomType;
            let t = &f.table;
            let lines = (0..t.len()).all(|r| matches!(t.geometries_of().kind(r), Some(GeomType::LineString | GeomType::MultiLineString)));
            let keys = || t.names().iter().filter(|n| (0..t.len()).any(|r| t.has_key(r, n))).cloned().collect();
            let (keep, whole, from) = whole_unless_lines(lines, o.rule(k, keys), o.min_zoom);
            tiled.add_features(k, t, &keep, whole, first_drawn(&s.layers, k, from, o.max_zoom));
            props_file(tiled, o, k, (0..t.len()).map(|r| t.to_geojson(r)["properties"].clone()));
        }
    }
}

/// The props file of the layer `k`, if it has popup fields: for each row (the tiles' feature id), the fields, as JSON. The tile has none
/// of them (`TileOptions::rule`).
fn props_file(tiled: &mut tiles::Tiles, o: &tiles::stage::TileOptions, k: &str, rows: impl Iterator<Item = Value>) {
    let Some(fields) = o.popups.get(k) else { return };
    let rows: Vec<Value> = rows.map(|p| Value::Object(fields.iter().filter_map(|f| Some((f.clone(), p.get(f)?.clone()))).collect())).collect();
    let mut text = Vec::new();
    serde_json::to_writer(&mut text, &roadstyle_model::table::JsSafe(&Value::Array(rows))).expect("a Vec takes every byte");
    tiled.props_files.push((k.to_string(), String::from_utf8(text).expect("JSON text is UTF-8")));
}

/// rule for a source other than the roads, the pieces and the slots: lines are clipped to each tile; points and polygons go
/// whole into every tile their box touches, from the first zoom (its extra layers). A polygon at a tile's edge whose clipped part has
/// no area was left out of that tile before (the sea at Monaco's west edge, 2026-10-24).
fn whole_unless_lines(lines: bool, rule: (std::collections::HashSet<String>, bool, u32), first: u32) -> (std::collections::HashSet<String>, bool, u32) {
    if rule.1 || lines { rule } else { (rule.0, true, first) }
}

/// Every feature of a GeoJSON source is a line.
fn json_lines(src: &Value) -> bool {
    src["data"]["features"].as_array().into_iter().flatten().all(|f| matches!(f["geometry"]["type"].as_str(), Some("LineString" | "MultiLineString")))
}

/// Stage 2 from memory (audit N3): the tiles of stage 1's sources and the one style that draws them (`tiled_style`), the tiles at `at`
/// (`{"url": "pmtiles://roads"}` for an archive, `{"tiles": ["<prefix>roads/{z}/{x}/{y}"]}` for a folder). `o`: which sources and
/// which properties. The sources that `o` leaves out stay in the style with a null `data` (audit D3: not copied), which
/// `Styled::write_with` fills as it writes the style; `inline`: their data_maxzoom and data_tolerance (SourceMode::Inline). An error for
/// zooms in `o` that are not tile zooms.
pub fn tile_stage(s: &sources::Styled, o: &tiles::stage::TileOptions, at: &Value, inline: sources::SourceMode)
                  -> Result<(Value, tiles::Tiles), tiles::Error> {
    let tiles = tile_sources(s, o)?;
    let mut style = s.style_with(inline, true);
    without_roads(&mut style);
    let tiled: Vec<String> = s.shown().filter(|(k, _)| o.wants(k)).map(|(k, _)| k.to_string()).collect();
    Ok((tiled_style(style, &tiled, at, (o.min_zoom, o.max_zoom)), tiles))
}

/// An export's style without the whole roads (the source `roads` and the layers on it: the pick and the highlight): the pieces pick and
/// glow, and a click reads the road's row in the road table (D5).
fn without_roads(style: &mut Value) {
    if let Some(s) = style["sources"].as_object_mut() {
        s.shift_remove("roads");
    }
    if let Some(l) = style["layers"].as_array_mut() {
        l.retain(|l| l["source"] != "roads");
    }
}

/// A style of this Styled (`tile_stage`'s, `style_with`'s) as JSON text, each null `data` with its source's FeatureCollection.
pub fn style_text(s: &sources::Styled, style: &Value) -> String {
    let mut out = Vec::new();
    s.write_with(style, &mut out).expect("a Vec takes every byte");
    String::from_utf8(out).expect("JSON text is UTF-8")
}

/// The style that draws stage 2's tiles: the sources `tiled` become the tile layers of one vector source `roads` (first, at `at`, with the
/// tiles' zooms), and each layer on one of them draws its tile layer (`source-layer`); the other sources stay.
pub fn tiled_style(mut style: Value, tiled: &[String], at: &Value, zooms: (u32, u32)) -> Value {
    let is_tiled = |v: &Value| v.as_str().is_some_and(|s| tiled.iter().any(|t| t == s));
    for l in style["layers"].as_array_mut().into_iter().flatten() {
        if let Some(src) = l.get("source").cloned().filter(is_tiled) {
            l["source-layer"] = src;
            l["source"] = tiles::SOURCE.into();
        }
    }
    let mut vector = serde_json::Map::new();
    vector.insert("type".into(), "vector".into());
    vector.extend(at.as_object().into_iter().flatten().map(|(k, v)| (k.clone(), v.clone())));
    vector.insert("minzoom".into(), zooms.0.into());
    vector.insert("maxzoom".into(), zooms.1.into());
    // the generation of the road set is in the tile URL: a row is valid in one generation only (and the browser's cache keeps no old tile)
    if let Some(g) = style["metadata"][roadstyle_model::props::GENERATION].as_str() {
        for t in vector.get_mut("tiles").and_then(Value::as_array_mut).into_iter().flatten() {
            *t = format!("{}?g={g}", t.as_str().unwrap_or_default()).into();
        }
    }
    style["metadata"][roadstyle_model::props::CONTRACT_KEY] = roadstyle_model::props::CONTRACT.into();
    let mut sources = serde_json::Map::new();
    sources.insert(tiles::SOURCE.into(), Value::Object(vector));
    for (k, v) in style["sources"].as_object().into_iter().flatten() {
        if !tiled.iter().any(|t| t == k) {
            sources.insert(k.clone(), v.clone());
        }
    }
    style["sources"] = Value::Object(sources);
    contract::describe(&mut style);        // the roles now name the tile layers
    style
}

/// The location of an XYZ folder of tiles at `prefix` (`<prefix>roads/{z}/{x}/{y}`), as `tile_stage`'s `at`.
pub fn xyz_at(prefix: &str) -> Value {
    json!({"tiles": [format!("{prefix}{}/{{z}}/{{x}}/{{y}}", tiles::SOURCE)]})
}

/// Stage 2 from stage 1's files in `dir` (GeoJSON or GeoParquet, as style.json names them): the style that draws the tiles
/// (`tiled_style`, the tiles at `at`) and the tiles. `o`: other rules than the style's.
pub fn tiles_of_files(dir: &std::path::Path, keep: &[String], o: Option<tiles::stage::TileOptions>, at: &Value) -> Result<(Value, tiles::Tiles), crate::Error> {
    tiles_of_files_with(|name| std::fs::read(dir.join(name)), keep, o, at)
}

/// Stage 2 from stage 1's files, each read by `read` (a file name: its bytes; its error is an `Error::File` of that name), as
/// `tiles_of_files` does.
pub fn tiles_of_files_with<E: std::fmt::Display>(read: impl Fn(&str) -> Result<Vec<u8>, E>, keep: &[String], o: Option<tiles::stage::TileOptions>,
                                             at: &Value) -> Result<(Value, tiles::Tiles), crate::Error> {
    let read = |name: &str| read(name).map_err(|e| crate::error::file(name, e));
    let style: Value = serde_json::from_slice(&read("style.json")?).map_err(|e| crate::error::file("style.json", e))?;
    let o = match o { Some(o) => o, None => tiles::stage::TileOptions::from_style(&style, keep)? };
    let mut tiled = o.tiles()?;
    let mut style = style;
    without_roads(&mut style);
    let layers = style["layers"].as_array().map(Vec::as_slice).unwrap_or_default();
    tiled.drawn_by(layers);
    let mut names = Vec::new();
    for (k, spec) in style["sources"].as_object().into_iter().flatten() {
        if !o.wants(k) || spec["type"] != "geojson" {
            continue;
        }
        names.push(k.clone());
        let file = spec["data"].as_str().ok_or_else(|| crate::error::file("style.json", format!("source {k}: its data is not a file name")))?;
        // audit N5: a GeoParquet file of lines (the roads, the pieces) goes to the tiles as its Arrow columns, with no JSON per cell
        if let Some((t, json)) = if file.ends_with(".parquet") { read::line_table(read(file)?)? } else { None } {
            let cols: Vec<(usize, &String)> = t.names().iter().enumerate().filter(|(_, n)| *n != roadstyle_io::write::FID).collect();
            let (keep, whole, from) = o.rule(k, || cols.iter().map(|(_, n)| n.to_string()).collect());
            let cell = |c: usize, i: usize, n: &str| -> FileValue {
                let v = t.cell(c, i);
                match v.as_str().filter(|_| json.contains(n)) {
                    Some(s) => FileValue::Json(serde_json::from_str(s).unwrap_or(Value::Null)),
                    None => FileValue::Cell(v),
                }
            };
            // a slot has its road's key as the file's feature id (`__fid`), the pieces as the property `__rs_edge`
            let fid = t.names().iter().position(|n| n == roadstyle_io::write::FID).filter(|_| k == "slots");
            let edge = roadstyle_model::mark::Mark::Edge.name();
            let feats = (0..t.len()).map(|i| (t.line(i),
                                              cols.iter().map(move |&(c, n)| (n.as_str(), cell(c, i, n)))
                                                  .chain(fid.map(|c| (edge, FileValue::Cell(t.cell(c, i)))))));
            tiled.add_lines(k, feats, &keep, whole, first_drawn(layers, k, from, o.max_zoom));
            continue;
        }
        let fc: Value = if file.ends_with(".parquet") { read::features(read(file)?)? }
                            else { serde_json::from_slice(&read(file)?).map_err(|e| crate::error::file(file, e))? };
        let src = json!({"type": "geojson", "data": fc});
        let rule = o.rule(k, || src["data"]["features"].as_array().into_iter().flatten()
            .filter_map(|f| f["properties"].as_object()).flat_map(|p| p.keys().cloned()).collect());
        let (keep, whole, from) = whole_unless_lines(json_lines(&src), rule, o.min_zoom);
        tiled.add(k, &src, &keep, whole, first_drawn(layers, k, from, o.max_zoom));
    }
    Ok((tiled_style(style, &names, at, (o.min_zoom, o.max_zoom)), tiled))
}

/// A value of a stage-1 file for the tiles: an Arrow cell, or the JSON value of a `roadstyle:json` column's text.
enum FileValue<'a> {
    Cell(Cell<'a>),
    Json(Value),
}

impl tiles::TileValue for FileValue<'_> {
    fn tile_val(&self) -> Option<tiles::Val<'_>> {
        match self {
            FileValue::Cell(c) => c.tile_val(),
            FileValue::Json(v) => v.tile_val(),
        }
    }
}

/// The file format of stage 1's sources.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Format {
    /// `<name>.geojson`: a FeatureCollection, for MapLibre and to read
    GeoJson,
    /// `<name>.parquet`: GeoParquet, smaller, for large areas and DuckDB
    GeoParquet,
}

/// The file of the road table, next to the sources.
pub const ROAD_TABLE: &str = "road_table.parquet";

/// The names of stage 1's files: style.json, one file for each source (`<name>.geojson` or `<name>.parquet`) and the road table.
pub fn source_file_names(s: &sources::Styled, format: Format) -> Vec<String> {
    let ext = ext(format);
    ["style.json".to_string()].into_iter().chain(s.shown().map(|(n, _)| format!("{n}.{ext}"))).chain([ROAD_TABLE.to_string()]).collect()
}

fn ext(format: Format) -> &'static str {
    match format { Format::GeoJson => "geojson", Format::GeoParquet => "parquet" }
}

/// One of stage 1's files (a name of `source_file_names`), in memory (`write_source_file`).
pub fn source_file(s: &sources::Styled, file: &str, format: Format, drawn: &std::collections::HashSet<String>) -> Result<Vec<u8>, crate::Error> {
    write_source_file(s, file, format, drawn, Vec::new())
}

/// One of stage 1's files, written to `w` a part at a time: style.json (each source's data at its file), a source (the roads' file has
/// only their drawing values: `drawn`; their lines are in the road table when no layer draws them), or the road table (GeoParquet: every
/// field of each road by its row, its line, its middle, its heading and its box: `road_rows`). Gives `w` back.
pub fn write_source_file<W: std::io::Write + Send>(s: &sources::Styled, file: &str, format: Format, drawn: &std::collections::HashSet<String>,
                                                  mut w: W) -> Result<W, crate::Error> {
    let ext = ext(format);
    let io = |e: std::io::Error| crate::error::file(file, e);
    if file == "style.json" {
        serde_json::to_writer(&mut w, &s.style_with(sources::SourceMode::Files(ext), true)).map_err(|e| crate::error::file(file, e))?;
        return Ok(w);
    }
    if file == ROAD_TABLE {
        return Ok(roadstyle_io::write::parquet_to(w, || road_rows(s), true)?);
    }
    let name = file.strip_suffix(&format!(".{ext}")).ok_or_else(|| crate::error::file(file, format!("not a .{ext} file")))?;
    let src = s.source(name).ok_or_else(|| crate::error::file(file, format!("no source {name}")))?;
    if format == Format::GeoJson {
        s.write_data(src, drawn, &mut w).map_err(io)?;
        return Ok(w);
    }
    use roadstyle_io::write::{Geometry, Row as PqRow, Val};
    let lines = s.draws_roads();
    match src {
        // audit N5: the roads' Arrow cells and lines go into the file with no JSON copy; the pieces' values are their own
        Source::Roads(roads) => roadstyle_io::write::parquet_to(w, || roads.roads.iter().map(|r| PqRow {
            id: Some(r.i as i64),
            props: roads.props(r, Some(drawn)).map(|(k, c)| (k.into(), Val::Cell(c))).collect(),
            geometry: r.line().filter(|_| lines).map(Geometry::Line),
        }), true).map_err(crate::Error::from),
        Source::Simple(p) => roadstyle_io::write::parquet_to(w, || p.features(&s.roads.roads).map(|(id, props, c)| PqRow {
            id: Some(id as i64), props: props.into_iter().map(|(k, v)| (k, Val::Json(v))).collect(), geometry: c.map(Geometry::Line),
        }), true).map_err(crate::Error::from),
        Source::Json(v) => {
            let fs = v["data"]["features"].as_array().map(Vec::as_slice).unwrap_or_default();
            roadstyle_io::write::parquet_to(w, || fs.iter().map(|f| PqRow {
                id: f["id"].as_i64(),
                props: f["properties"].as_object().into_iter().flatten().map(|(k, v)| (k.as_str().into(), Val::Cell(Cell::Json(v)))).collect(),
                geometry: Some(&f["geometry"]).filter(|g| !g.is_null()).map(|g| Geometry::Json(std::borrow::Cow::Borrowed(g))),
            }), true).map_err(crate::Error::from)
        }
        // a base-map layer: its table's cells (the keys of each GeoJSON feature) and each feature's geometry (R10)
        Source::Features(f) => {
            let t = &f.table;
            roadstyle_io::write::parquet_to(w, || (0..t.len()).map(|r| PqRow {
                id: None,
                props: t.names().iter().filter(|k| t.has_key(r, k)).filter_map(|k| t.get(r, k).map(|c| (k.as_str().into(), Val::Cell(c)))).collect(),
                geometry: Some(t.geometries_of().to_geojson(r)).filter(|g| !g.is_null()).map(Geometry::from),
            }), true).map_err(crate::Error::from)
        }
    }
}

/// The road table's rows as Parquet rows (`Styled::table_rows`): each road's fields, then its middle (`__mid_lon`, `__mid_lat`) and its
/// box (`__bbox_*`), and its line as the geometry.
fn road_rows(s: &sources::Styled) -> impl Iterator<Item = roadstyle_io::write::Row<'_>> + '_ {
    use roadstyle_io::write::{Geometry, Row as PqRow, Val};
    s.table_rows().into_iter().map(|t| {
        let num = |v: Option<f64>| Val::Cell(v.map_or(Cell::Null, Cell::Float));
        let mut props: Vec<(std::borrow::Cow<str>, Val)> = t.props.into_iter().map(|(k, v)| (k.into(), Val::Cell(v))).collect();
        props.extend([("__mid_lon".into(), num(t.mid.map(|m| m[0]))), ("__mid_lat".into(), num(t.mid.map(|m| m[1])))]);
        props.extend(["__bbox_min_lon", "__bbox_min_lat", "__bbox_max_lon", "__bbox_max_lat"].iter().enumerate()
            .map(|(k, n)| ((*n).into(), num(t.bbox.map(|b| b[k])))));
        PqRow { id: None, props, geometry: t.line.map(Geometry::Line) }
    })
}

/// The road table as the page loads it (tiles.sidecar's form; `Styled::table_rows`): `{"props", "mids", "bboxes"}`, with `lines` also
/// `"lines"`, each a list with one item for each road (its row). `fields`: only these fields of each road (the level editor's lean
/// table: what its page reads); None: every field. A page that has the engine gets the table without lines (the lines are most of
/// its bytes) and asks for a road's line when it needs it (`write_road_lines`); a static page has no engine and gets the lines.
pub fn write_road_table<W: std::io::Write>(s: &sources::Styled, fields: Option<&[String]>, lines: bool, w: &mut W) -> std::io::Result<()> {
    let rows = s.table_rows_of(fields);
    // each value written straight to `w` (audit D11: no JSON tree for each row)
    type Item<W> = dyn Fn(&mut W, &sources::TableRow) -> serde_json::Result<()>;
    let list = |w: &mut W, key: &str, first: bool, item: &Item<W>| -> std::io::Result<()> {
        write!(w, "{}\"{key}\":[", if first { "{" } else { "," })?;
        for (i, t) in rows.iter().enumerate() {
            if i > 0 {
                w.write_all(b",")?;
            }
            item(w, t)?;
        }
        w.write_all(b"]")
    };
    list(w, "props", true, &|w, t| {
        w.write_all(b"{").map_err(serde_json::Error::io)?;
        for (i, (k, v)) in t.props.iter().enumerate() {
            if i > 0 {
                w.write_all(b",").map_err(serde_json::Error::io)?;
            }
            serde_json::to_writer(&mut *w, k)?;
            w.write_all(b":").map_err(serde_json::Error::io)?;
            // a cell is written as it is (its text is to_value's, a large integer as text); a JSON number through js_value
            match v {
                Cell::Json(j @ Value::Number(_)) => serde_json::to_writer(&mut *w, &js_value((*j).clone()))?,
                _ => serde_json::to_writer(&mut *w, v)?,
            }
        }
        w.write_all(b"}").map_err(serde_json::Error::io)
    })?;
    list(w, "mids", false, &|w, t| serde_json::to_writer(w, &t.mid))?;
    list(w, "bboxes", false, &|w, t| serde_json::to_writer(w, &t.bbox))?;
    if lines {
        list(w, "lines", false, &|w, t| serde_json::to_writer(w, &t.line))?;
    }
    w.write_all(b"}")
}

/// The lines of these roads (rows of the road table) as a JSON list, one item for each id: the road's line (`[[lon, lat], ...]`), or
/// null for a row that has no line or is not in the table (the table's `lines` item of that row).
pub fn write_road_lines<W: std::io::Write>(s: &sources::Styled, ids: &[u32], w: &mut W) -> std::io::Result<()> {
    let roads = &s.roads.roads;
    let line = |i: u32| Some(i as usize).filter(|&i| i < roads.len()).and_then(|i| roads.line(i)).filter(|c| !c.is_empty());
    serde_json::to_writer(w, &ids.iter().map(|&i| line(i)).collect::<Vec<_>>()).map_err(std::io::Error::from)
}

/// The two end points of each row's line (the level editor's end marks), 4 numbers for each row: the first point's lon and lat, then
/// the last point's; NaN for a row without a line.
pub fn road_ends(s: &sources::Styled) -> Vec<f64> {
    let roads = &s.roads.roads;
    (0..roads.len()).flat_map(|i| match roads.line(i).filter(|c| !c.is_empty()) {
        Some(c) => [c[0][0], c[0][1], c[c.len() - 1][0], c[c.len() - 1][1]],
        None => [f64::NAN; 4],
    }).collect()
}

/// Stage 1's files in `dir` (`source_file_names`, `source_file`). `keep`: more columns for the roads' file. Gives each file's name and size.
pub fn write_sources(s: &sources::Styled, dir: &std::path::Path, format: Format, keep: &[String]) -> Result<Vec<(String, usize)>, crate::Error> {
    std::fs::create_dir_all(dir).map_err(|e| crate::error::file(dir.display(), e))?;
    let drawn = s.drawn(keep);
    let mut files = Vec::new();
    for name in source_file_names(s, format) {
        let path = dir.join(&name);
        let f = std::fs::File::create(&path).map_err(|e| crate::error::file(&name, e))?;
        let mut w = write_source_file(s, &name, format, &drawn, std::io::BufWriter::new(f))?;
        std::io::Write::flush(&mut w).map_err(|e| crate::error::file(&name, e))?;
        files.push((name.clone(), std::fs::metadata(&path).map_err(|e| crate::error::file(&name, e))?.len() as usize));
    }
    Ok(files)
}

/// Stage 2 from memory, with the rules of the look that made `s` (style_sources saves them): the tiled style (the tiles in a folder at
/// `prefix`) and the tiles.
pub fn tiles_of_sources(s: &sources::Styled, prefix: &str, keep: &[String]) -> Result<(String, tiles::Tiles), crate::Error> {
    let o = tiles::stage::TileOptions::new(&s.layers, &s.metadata, &s.saved[tiles::stage::TILES], &s.saved[tiles::stage::COLUMNS], keep)?;
    let (style, tiled) = tile_stage(s, &o, &xyz_at(prefix), sources::SourceMode::INLINE)?;
    Ok((style_text(s, &style), tiled))
}

/// The style with one vector-tile source, `roads` (`<prefix>roads/{z}/{x}/{y}`), and the tiles to answer it with (tiles.rs: the rules of
///, the zooms and the buffer from the look's `config.tiles`). The layers, the metadata and the camera are those of
/// `inline_style`; each layer draws the tile layer of its old source (`source-layer`). The tiles keep only the properties that are read:
/// the texts in the layers (all their keys, and more), the popup and tooltip fields of the metadata, the overlays' popup fields (name,
/// kind) and `keep` (the caller's own, for example its popup's). The warnings of stage 1 come back last.
pub fn tiled_from_parquet(parquet: Vec<u8>, look: &Look, features: Option<Vec<u8>>, name: Option<String>, prefix: &str, keep: &[String])
                  -> Result<(String, tiles::Tiles, Vec<String>), crate::Error> {
    let (feats, features, _) = tables(parquet, features, None)?;
    tiled_of(feats, look, features, name, prefix, keep)
}

/// The map with vector tiles of roads and base-map rows that a reader gave, as `tiled_from_parquet`.
pub fn tiled_of(roads: RoadTable, look: &Look, features: Option<FeatureTable>, name: Option<String>, prefix: &str, keep: &[String])
                -> Result<(String, tiles::Tiles, Vec<String>), crate::Error> {
    let s = sources::Styled::new(make_parts(roads, look, features, None, name)?);
    let mut o = tiles::stage::TileOptions::new(&s.layers, &s.metadata, &serde_json::json!(look.sections.tiles), &columns(look), keep)?;
    // render(tiles=True)'s page (the Python binding): the columns of its road and simple tiles (`tile_keep`; every __rs_* goes too) and
    // the sources in its tiles (`tile_layers`: roads, simple, slots; the page keeps the others inline)
    // keys of stage 2, read from the look's `other` until T4 moves them to TileOptions
    let list = |k: &str| look.other.get(k).and_then(Value::as_array).map(|a| a.iter().filter_map(Value::as_str).map(String::from));
    o.exact = list("tile_keep").map(Iterator::collect);
    o.only = list("tile_layers").map(Iterator::collect);
    // the call's data_maxzoom and data_tolerance for the sources that stay in the style (the look's `other` until the bindings give it)
    let (style, tiled) = tile_stage(&s, &o, &xyz_at(prefix), sources::SourceMode::inline_of(&look.other))?;
    Ok((style_text(&s, &style), tiled, s.warnings))
}

