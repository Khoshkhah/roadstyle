//! roadstyle as a Rust library (docs/design/rust_library.md): the facade. It re-exports the crates of the core with the module paths
//! of the old single crate (`roadstyle::props`, `roadstyle::read`, `roadstyle::levels`, `roadstyle::tiles`, `roadstyle::make_style`,
//! ...), and it has the functions that read GeoParquet bytes (roadstyle-io) and call the engine: `make_style` and `make_tiled`, which
//! needs both the engine and the tiles. A Rust user adds only this crate.

pub use roadstyle_engine::*;
pub use roadstyle_io::{crs, duckosm, geojson, read, shp};
#[cfg(feature = "gpkg")]
pub use roadstyle_io::gpkg;
pub mod level_area;
pub mod level_editor;
pub mod page;
pub mod page_options;
pub use roadstyle_levels as levels;
pub use roadstyle_tiles as tiles;

use roadstyle_engine::table::js_value;
use serde_json::{json, Value};

/// The roads, the base map's rows and the route planner's rows.
type Tables = (RoadTable, Option<FeatureTable>, Option<Vec<Row>>);

/// The roads and the other tables from their GeoParquet bytes: the roads' lines and the base map's geometries in the column `geometry`.
fn tables(parquet: Vec<u8>, features: Option<Vec<u8>>, planner: Option<Vec<u8>>) -> Result<Tables, String> {
    Ok((read::read_roads(parquet, "geometry")?,
        features.map(read_features).transpose()?,
        planner.map(|p| read::read_table(p, "")).transpose()?))
}

/// The base map's rows from their GeoParquet bytes (the duckOSM reader's features.parquet), the background's land without the sea
/// (duckosm::cut_sea).
pub fn read_features(features: Vec<u8>) -> Result<FeatureTable, String> {
    Ok(duckosm::cut_sea(read::read_feature_table(features, "geometry")?)?)
}

/// The style as one JSON text (roadstyle's export_inline), from the roads and the other tables as GeoParquet bytes: the engine's
/// `make_style` after roadstyle-io's readers.
pub fn make_style(parquet: Vec<u8>, look: &Look, features: Option<Vec<u8>>, planner: Option<Vec<u8>>, name: Option<String>) -> Result<String, String> {
    let (feats, features, planner) = tables(parquet, features, planner)?;
    roadstyle_engine::make_style(feats, look, features, planner, name)
}

/// Stage 1 from GeoParquet bytes: the style and its sources, typed in memory (docs/rust/architecture.md, "The three stages and the one
/// call"). `save_sources` writes them as files; the saved style has what stage 2 reads (`roadstyle:tiles`: the look's tile settings,
/// `roadstyle:columns`: the class, filter and metre width columns).
pub fn make_sources(parquet: Vec<u8>, look: &Look, features: Option<Vec<u8>>, planner: Option<Vec<u8>>, name: Option<String>) -> Result<sources::Sources, String> {
    let (feats, features, planner) = tables(parquet, features, planner)?;
    sources_of(feats, look, features, planner, name)
}

/// Stage 1 of roads that a reader gave (`read::read_roads`, `geojson::read_roads`, ...), as `make_sources`.
pub fn sources_of(roads: RoadTable, look: &Look, features: Option<FeatureTable>, planner: Option<Vec<Row>>, name: Option<String>)
                  -> Result<sources::Sources, String> {
    let mut s = sources::Sources::new(make_parts(roads, look, features, planner, name)?);
    s.saved.insert(tiles::stage::TILES.into(), look.config["tiles"].clone());
    s.saved.insert(tiles::stage::COLUMNS.into(), columns(look));
    Ok(s)
}

/// `roadstyle:columns`: the user's class, filter and metre width columns (render's highway_col, filter_col, width_m_col).
fn columns(look: &Look) -> Value {
    let arg = |k: &str| look.args[k].as_str().filter(|c| !c.is_empty()).map_or(Value::Null, Value::from);
    json!({"class": arg("highway_col"), "filter": arg("filter_col"), "width": arg("width_m_col")})
}

/// Stage 2 from memory: the tiles of stage 1's sources (`o`: the rules), borrowed (audit N6: `s` stays as it is).
fn tile_sources(s: &sources::Sources, o: &tiles::stage::TileOptions) -> tiles::Tiles {
    let mut tiled = tiles::Tiles::new(o.min_zoom, o.max_zoom, o.buffer_px);
    let keys = |v: &Value| -> std::collections::HashSet<String> {
        v["data"]["features"].as_array().into_iter().flatten().filter_map(|f| f["properties"].as_object()).flat_map(|p| p.keys().cloned()).collect()
    };
    for (k, src) in s.sources.iter().filter(|(k, _)| o.wants(k)) {
        match src {
            // the roads, from the table and the marks (no copy of their properties); a page has none
            Src::Roads(_) if !s.roads.in_style => {}
            Src::Roads(_) => {
                let (keep, whole, from) = o.rule(k, Default::default);
                let r = &s.roads;
                tiled.add_lines(k, r.roads.iter().map(|x| (x.line(), r.props(x, None))), &keep, whole, from)        // the cells, no JSON copy
            }
            Src::Simple(p) => {
                let (keep, whole, from) = o.rule(k, Default::default);
                tiled.add_lines(k, p.features(&s.roads.roads).map(|(_, props, c)| (c, props.into_iter())), &keep, whole, from)
            }
            Src::Json(v) => {
                let (keep, whole, from) = whole_unless_lines(json_lines(v), o.rule(k, || keys(v)), o.min_zoom);
                tiled.add(k, v, &keep, whole, from)
            }
            // a base-map layer, from its table (audit R10)
            Src::Features(f) => {
                use roadstyle_engine::feature_table::GeomType;
                let t = &f.table;
                let lines = (0..t.len()).all(|r| matches!(t.geometries_of().kind(r), Some(GeomType::LineString | GeomType::MultiLineString)));
                let keys = || t.names().iter().filter(|n| (0..t.len()).any(|r| t.has_key(r, n))).cloned().collect();
                let (keep, whole, from) = whole_unless_lines(lines, o.rule(k, keys), o.min_zoom);
                tiled.add_features(k, t, &keep, whole, from)
            }
        }
    }
    tiled
}

/// tiles.py's rule for a source other than the roads, the pieces and the slots: lines are clipped to each tile; points and polygons go
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
/// which properties. The sources that `o` leaves out stay in the style with their data.
pub fn tile_stage(s: &sources::Sources, o: &tiles::stage::TileOptions, at: &Value) -> (Value, tiles::Tiles) {
    let tiles = tile_sources(s, o);
    let mut style = s.style(|_| String::new());
    let mut tiled = Vec::new();
    for (i, (k, _)) in s.sources.iter().enumerate().filter(|(_, (_, src))| !matches!(src, Src::Roads(_)) || s.roads.in_style) {
        if o.wants(k) {
            tiled.push(k.clone());
        } else {
            let mut data = Vec::new();
            s.write_data(i, &s.drawn(&[]), &mut data).expect("a Vec takes every byte");
            style["sources"][k]["data"] = serde_json::from_slice(&data).expect("the engine writes JSON");
        }
    }
    (tiled_style(style, &tiled, at, (o.min_zoom, o.max_zoom)), tiles)
}

/// The style that draws stage 2's tiles: the sources `tiled` become the tile layers of one vector source `roads` (first, at `at`, with the
/// tiles' zooms and the pieces' `promoteId`), and each layer on one of them draws its tile layer (`source-layer`); the other sources stay.
pub fn tiled_style(mut style: Value, tiled: &[String], at: &Value, zooms: (u32, u32)) -> Value {
    let is_tiled = |v: &Value| v.as_str().is_some_and(|s| tiled.iter().any(|t| t == s));
    let promote = if tiled.iter().any(|t| t == "simple") { style["sources"]["simple"]["promoteId"].as_str().map(|p| json!({"simple": p})) } else { None };
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
    if let Some(p) = promote {          // the pieces' row as the feature id, as on the GeoJSON source
        vector.insert("promoteId".into(), p);
    }
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
pub fn tile_files(dir: &std::path::Path, keep: &[String], o: Option<tiles::stage::TileOptions>, at: &Value) -> Result<(Value, tiles::Tiles), String> {
    tile_files_with(|name| std::fs::read(dir.join(name)).map_err(|e| format!("{name}: {e}")), keep, o, at)
}

/// Stage 2 from stage 1's files, each read by `read` (a file name: its bytes), as `tile_files` does.
pub fn tile_files_with(read: impl Fn(&str) -> Result<Vec<u8>, String>, keep: &[String], o: Option<tiles::stage::TileOptions>, at: &Value)
                       -> Result<(Value, tiles::Tiles), String> {
    let style: Value = serde_json::from_slice(&read("style.json")?).map_err(|e| format!("style.json: {e}"))?;
    let o = match o { Some(o) => o, None => tiles::stage::TileOptions::from_style(&style, keep)? };
    let mut tiled = tiles::Tiles::new(o.min_zoom, o.max_zoom, o.buffer_px);
    let mut names = Vec::new();
    for (k, spec) in style["sources"].as_object().into_iter().flatten() {
        if !o.wants(k) || spec["type"] != "geojson" {
            continue;
        }
        names.push(k.clone());
        let file = spec["data"].as_str().ok_or_else(|| format!("source {k}: its data is not a file name"))?;
        // audit N5: a GeoParquet file of lines (the roads, the pieces) goes to the tiles as its Arrow columns, with no JSON per cell
        if let Some((t, json)) = if file.ends_with(".parquet") { read::line_table(read(file)?)? } else { None } {
            let cols: Vec<(usize, &String)> = t.names().iter().enumerate().filter(|(_, n)| *n != roadstyle_io::write::FID).collect();
            // the roads' lines are in the road table when stage 1 left them out (no layer draws the roads)
            let table = if k == "roads" && (0..t.len()).any(|i| t.line(i).is_none()) { Some(read::read_roads(read(ROAD_TABLE)?, "geometry")?) } else { None };
            let (keep, whole, from) = o.rule(k, || cols.iter().map(|(_, n)| n.to_string()).collect());
            let cell = |c: usize, i: usize, n: &str| -> FileValue {
                let v = t.cell(c, i);
                match v.as_str().filter(|_| json.contains(n)) {
                    Some(s) => FileValue::Json(serde_json::from_str(s).unwrap_or(Value::Null)),
                    None => FileValue::Cell(v),
                }
            };
            let feats = (0..t.len()).map(|i| (t.line(i).or_else(|| table.as_ref().and_then(|r| r.line(i))),
                                              cols.iter().map(move |&(c, n)| (n.as_str(), cell(c, i, n)))));
            tiled.add_lines(k, feats, &keep, whole, from);
            continue;
        }
        let mut fc: Value = if file.ends_with(".parquet") { read::features(read(file)?)? }
                            else { serde_json::from_slice(&read(file)?).map_err(|e| format!("{file}: {e}"))? };
        // the roads' lines are in the road table when stage 1 left them out (no layer draws the roads)
        let lineless = |fc: &Value| fc["features"].as_array().is_some_and(|f| f.iter().any(|x| x["geometry"].is_null()));
        if k == "roads" && lineless(&fc) {
            let table = read::features(read(ROAD_TABLE)?)?;
            let lines = table["features"].as_array().map(Vec::as_slice).unwrap_or_default();
            for (f, t) in fc["features"].as_array_mut().into_iter().flatten().zip(lines) {
                if f["geometry"].is_null() {
                    f["geometry"] = t["geometry"].clone();
                }
            }
        }
        let src = json!({"type": "geojson", "data": fc});
        let rule = o.rule(k, || src["data"]["features"].as_array().into_iter().flatten()
            .filter_map(|f| f["properties"].as_object()).flat_map(|p| p.keys().cloned()).collect());
        let (keep, whole, from) = whole_unless_lines(json_lines(&src), rule, o.min_zoom);
        tiled.add(k, &src, &keep, whole, from);
    }
    Ok((tiled_style(style, &names, at, (o.min_zoom, o.max_zoom)), tiled))
}

/// A value of a stage-1 file for the tiles: an Arrow cell, or the JSON value of a `roadstyle:json` column's text.
enum FileValue<'a> {
    Cell(Cell<'a>),
    Json(Value),
}

impl tiles::TileValue for FileValue<'_> {
    fn tile_val(&self) -> Option<tiles::Val> {
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
pub fn file_names(s: &sources::Sources, format: Format) -> Vec<String> {
    let ext = ext(format);
    let shown = s.sources.iter().filter(|(_, src)| !matches!(src, Src::Roads(_)) || s.roads.in_style);
    ["style.json".to_string()].into_iter().chain(shown.map(|(n, _)| format!("{n}.{ext}"))).chain([ROAD_TABLE.to_string()]).collect()
}

fn ext(format: Format) -> &'static str {
    match format { Format::GeoJson => "geojson", Format::GeoParquet => "parquet" }
}

/// One of stage 1's files (a name of `file_names`), in memory (`write_source_file`).
pub fn source_file(s: &sources::Sources, file: &str, format: Format, drawn: &std::collections::HashSet<String>) -> Result<Vec<u8>, String> {
    write_source_file(s, file, format, drawn, Vec::new())
}

/// One of stage 1's files, written to `w` a part at a time: style.json (each source's data at its file), a source (the roads' file has
/// only their drawing values: `drawn`; their lines are in the road table when no layer draws them), or the road table (GeoParquet: every
/// field of each road by its row, its line, its middle, its heading and its box: `road_rows`). Gives `w` back.
pub fn write_source_file<W: std::io::Write + Send>(s: &sources::Sources, file: &str, format: Format, drawn: &std::collections::HashSet<String>,
                                                  mut w: W) -> Result<W, String> {
    let ext = ext(format);
    let io = |e: std::io::Error| format!("{file}: {e}");
    if file == "style.json" {
        serde_json::to_writer(&mut w, &s.style(|n| format!("{n}.{ext}"))).map_err(|e| e.to_string())?;
        return Ok(w);
    }
    if file == ROAD_TABLE {
        return Ok(roadstyle_io::write::parquet_to(w, || road_rows(s), true)?);
    }
    let name = file.strip_suffix(&format!(".{ext}")).ok_or_else(|| format!("{file}: not a .{ext} file"))?;
    let i = s.sources.iter().position(|(n, _)| n == name).ok_or_else(|| format!("{file}: no source {name}"))?;
    if format == Format::GeoJson {
        s.write_data(i, drawn, &mut w).map_err(io)?;
        return Ok(w);
    }
    use roadstyle_io::write::{Geometry, Row as PqRow, Val};
    let lines = s.draws_roads();
    match &s.sources[i].1 {
        // audit N5: the roads' Arrow cells and lines go into the file with no JSON copy; the pieces' values are their own
        Src::Roads(_) => roadstyle_io::write::parquet_to(w, || s.roads.roads.iter().map(|r| PqRow {
            id: Some(r.i as i64),
            props: s.roads.props(r, Some(drawn)).map(|(k, c)| (k.into(), Val::Cell(c))).collect(),
            geometry: r.line().filter(|_| lines).map(Geometry::Line),
        }), true).map_err(String::from),
        Src::Simple(p) => roadstyle_io::write::parquet_to(w, || p.features(&s.roads.roads).map(|(id, props, c)| PqRow {
            id: Some(id as i64), props: props.into_iter().map(|(k, v)| (k.into(), Val::Json(v))).collect(), geometry: c.map(Geometry::Line),
        }), true).map_err(String::from),
        Src::Json(v) => {
            let fs = v["data"]["features"].as_array().map(Vec::as_slice).unwrap_or_default();
            roadstyle_io::write::parquet_to(w, || fs.iter().map(|f| PqRow {
                id: f["id"].as_i64(),
                props: f["properties"].as_object().into_iter().flatten().map(|(k, v)| (k.as_str().into(), Val::Cell(Cell::Json(v)))).collect(),
                geometry: Some(&f["geometry"]).filter(|g| !g.is_null()).map(|g| Geometry::Json(std::borrow::Cow::Borrowed(g))),
            }), true).map_err(String::from)
        }
        // a base-map layer: its table's cells (the keys of each GeoJSON feature) and each feature's geometry (R10)
        Src::Features(f) => {
            let t = &f.table;
            roadstyle_io::write::parquet_to(w, || (0..t.len()).map(|r| PqRow {
                id: None,
                props: t.names().iter().filter(|k| t.has_key(r, k)).filter_map(|k| t.get(r, k).map(|c| (k.as_str().into(), Val::Cell(c)))).collect(),
                geometry: Some(t.geometries_of().to_geojson(r)).filter(|g| !g.is_null()).map(Geometry::from),
            }), true).map_err(String::from)
        }
    }
}

/// The road table's rows as Parquet rows (`Sources::table_rows`): each road's fields, then its middle (`__mid_lon`, `__mid_lat`) and its
/// box (`__bbox_*`), and its line as the geometry.
fn road_rows(s: &sources::Sources) -> impl Iterator<Item = roadstyle_io::write::Row<'_>> + '_ {
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

/// The road table as the page loads it (tiles.sidecar's form, with Python's JSON text; `Sources::table_rows`): `{"props", "mids",
/// "bboxes", "lines"}`, each a list with one item for each road (its row).
pub fn write_road_table<W: std::io::Write>(s: &sources::Sources, w: &mut W) -> std::io::Result<()> {
    use page::pyjson::dumps;
    let rows = s.table_rows();
    let list = |w: &mut W, key: &str, first: bool, item: &dyn Fn(&sources::TableRow) -> String| -> std::io::Result<()> {
        write!(w, "{}\"{key}\":[", if first { "{" } else { "," })?;
        for (i, t) in rows.iter().enumerate() {
            if i > 0 {
                w.write_all(b",")?;
            }
            w.write_all(item(t).as_bytes())?;
        }
        w.write_all(b"]")
    };
    list(w, "props", true, &|t| dumps(&Value::Object(t.props.iter().map(|(k, v)| (k.to_string(), js_value(v.to_value()))).collect()), true))?;
    list(w, "mids", false, &|t| t.mid.map_or("null".into(), |m| dumps(&json!(m), true)))?;
    list(w, "bboxes", false, &|t| t.bbox.map_or("null".into(), |b| dumps(&json!(b), true)))?;
    list(w, "lines", false, &|t| t.line.map_or("null".into(), |c| dumps(&json!(c), true)))?;
    w.write_all(b"}")
}

/// Stage 1's files in `dir` (`file_names`, `source_file`). `keep`: more columns for the roads' file. Gives each file's name and size.
pub fn save_sources(s: &sources::Sources, dir: &std::path::Path, format: Format, keep: &[String]) -> Result<Vec<(String, usize)>, String> {
    std::fs::create_dir_all(dir).map_err(|e| format!("{}: {e}", dir.display()))?;
    let drawn = s.drawn(keep);
    let mut files = Vec::new();
    for name in file_names(s, format) {
        let path = dir.join(&name);
        let f = std::fs::File::create(&path).map_err(|e| format!("{name}: {e}"))?;
        let mut w = write_source_file(s, &name, format, &drawn, std::io::BufWriter::new(f))?;
        std::io::Write::flush(&mut w).map_err(|e| format!("{name}: {e}"))?;
        files.push((name.clone(), std::fs::metadata(&path).map_err(|e| format!("{name}: {e}"))?.len() as usize));
    }
    Ok(files)
}

/// Stage 2 from memory, with the rules of the look that made `s` (make_sources saves them): the tiled style (the tiles in a folder at
/// `prefix`) and the tiles.
pub fn tile_made(s: &sources::Sources, prefix: &str, keep: &[String]) -> Result<(String, tiles::Tiles), String> {
    let o = tiles::stage::TileOptions::new(&s.layers, &s.metadata, &s.saved[tiles::stage::TILES], &s.saved[tiles::stage::COLUMNS], keep)?;
    let (style, tiled) = tile_stage(s, &o, &xyz_at(prefix));
    Ok((style.to_string(), tiled))
}

/// The style with one vector-tile source, `roads` (`<prefix>roads/{z}/{x}/{y}`), and the tiles to answer it with (tiles.rs: the rules of
/// roadstyle's tiles.py, the zooms and the buffer from the look's `config.tiles`). The layers, the metadata and the camera are those of
/// `make_style`; each layer draws the tile layer of its old source (`source-layer`). The tiles keep only the properties that are read:
/// the texts in the layers (all their keys, and more), the popup and tooltip fields of the metadata, the overlays' popup fields (name,
/// kind) and `keep` (the caller's own, for example its popup's). The warnings of stage 1 come back last.
pub fn make_tiled(parquet: Vec<u8>, look: &Look, features: Option<Vec<u8>>, name: Option<String>, prefix: &str, keep: &[String])
                  -> Result<(String, tiles::Tiles, Vec<String>), String> {
    let (feats, features, _) = tables(parquet, features, None)?;
    let s = sources::Sources::new(make_parts(feats, look, features, None, name)?);
    let mut o = tiles::stage::TileOptions::new(&s.layers, &s.metadata, &look.config["tiles"], &columns(look), keep)
        .map_err(|e| format!("look: config.{e}"))?;
    // render(tiles=True)'s page (the Python binding): the columns of its road and simple tiles (`tile_keep`; every __rs_* goes too) and
    // the sources in its tiles (`tile_layers`: roads, simple, slots; the page keeps the others inline)
    o.exact = look.args["tile_keep"].as_array().map(|a| a.iter().filter_map(Value::as_str).map(String::from).collect());
    o.only = look.args["tile_layers"].as_array().map(|a| a.iter().filter_map(Value::as_str).map(String::from).collect());
    let (style, tiled) = tile_stage(&s, &o, &xyz_at(prefix));
    Ok((style.to_string(), tiled, s.warnings))
}

