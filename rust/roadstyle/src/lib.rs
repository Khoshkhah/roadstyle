//! roadstyle as a Rust library (docs/design/rust_library.md): the facade. It re-exports the crates of the core with the module paths
//! of the old single crate (`roadstyle::props`, `roadstyle::read`, `roadstyle::levels`, `roadstyle::tiles`, `roadstyle::make_style`,
//! ...), and it has the functions that read GeoParquet bytes (roadstyle-io) and call the engine: `make_style` and `make_tiled`, which
//! needs both the engine and the tiles. A Rust user adds only this crate.

pub use roadstyle_engine::*;
pub use roadstyle_io::read;
pub mod level_editor;
pub mod page;
pub use roadstyle_levels as levels;
pub use roadstyle_tiles as tiles;

use serde_json::{json, Value};

/// The roads, the base map's rows and the route planner's rows.
type Tables = (RoadTable, Option<Vec<Row>>, Option<Vec<Row>>);

/// The roads and the other tables from their GeoParquet bytes: the roads' lines and the base map's geometries in the column `geometry`.
fn tables(parquet: Vec<u8>, features: Option<Vec<u8>>, planner: Option<Vec<u8>>) -> Result<Tables, String> {
    Ok((read::read_roads(parquet, "geometry")?,
        features.map(|f| read::read_table(f, "geometry")).transpose()?,
        planner.map(|p| read::read_table(p, "")).transpose()?))
}

/// The style as one JSON text (roadstyle's export_inline), from the roads and the other tables as GeoParquet bytes: the engine's
/// `make_style` after roadstyle-io's readers.
pub fn make_style(parquet: Vec<u8>, look: &str, features: Option<Vec<u8>>, planner: Option<Vec<u8>>, name: Option<String>) -> Result<String, String> {
    let (feats, features, planner) = tables(parquet, features, planner)?;
    roadstyle_engine::make_style(feats, look, features, planner, name)
}

/// Stage 1 from GeoParquet bytes: the style and its sources, typed in memory (docs/rust/architecture.md, "The three stages and the one
/// call"). `save_sources` writes them as files; the saved style has what stage 2 reads (`roadstyle:tiles`: the look's tile settings,
/// `roadstyle:columns`: the class, filter and metre width columns).
pub fn make_sources(parquet: Vec<u8>, look: &str, features: Option<Vec<u8>>, planner: Option<Vec<u8>>, name: Option<String>) -> Result<sources::Sources, String> {
    let look_json: Value = serde_json::from_str(look).map_err(|e| format!("look: not JSON: {e}"))?;
    let (feats, features, planner) = tables(parquet, features, planner)?;
    let mut s = sources::Sources::new(make_parts(feats, look, features, planner, name)?);
    s.saved.insert(tiles::stage::TILES.into(), look_json["config"]["tiles"].clone());
    s.saved.insert(tiles::stage::COLUMNS.into(), columns(&look_json));
    Ok(s)
}

/// `roadstyle:columns`: the user's class, filter and metre width columns (render's highway_col, filter_col, width_m_col).
fn columns(look: &Value) -> Value {
    let arg = |k: &str| look["args"][k].as_str().filter(|c| !c.is_empty()).map_or(Value::Null, Value::from);
    json!({"class": arg("highway_col"), "filter": arg("filter_col"), "width": arg("width_m_col")})
}

/// Stage 2 from memory: the tiles of stage 1's sources (`o`: the rules). The JSON sources go into the tiles (and out of `s`); the roads
/// and the pieces stay.
pub fn tile_sources(s: &mut sources::Sources, o: &tiles::stage::TileOptions) -> tiles::Tiles {
    let mut tiled = tiles::Tiles::new(o.min_zoom, o.max_zoom, o.buffer_px);
    let keys = |v: &Value| -> std::collections::HashSet<String> {
        v["data"]["features"].as_array().into_iter().flatten().filter_map(|f| f["properties"].as_object()).flat_map(|p| p.keys().cloned()).collect()
    };
    for (k, src) in s.sources.iter_mut() {
        if !o.wants(k) {
            continue;
        }
        match src {
            // the roads, from the table and the marks (no copy of their properties); a page has none
            Src::Roads(_) if !s.roads.in_style => {}
            Src::Roads(_) => {
                let (keep, whole, from) = o.rule(k, Default::default);
                let r = &s.roads;
                tiled.add_lines(k, r.roads.iter().map(|x| (x.line(), x.iter().map(|(n, c)| (r.out_name(n), c.to_value())))), &keep, whole, from)
            }
            Src::Simple(p) => {
                let (keep, whole, from) = o.rule(k, Default::default);
                tiled.add_lines(k, p.features(&s.roads.roads).map(|(_, props, c)| (c, props.into_iter())), &keep, whole, from)
            }
            Src::Json(v) => {
                let (keep, whole, from) = o.rule(k, || keys(v));
                tiled.add(k, std::mem::take(v), &keep, whole, from) // frees the source's tree
            }
        }
    }
    tiled
}

/// Stage 2 from stage 1's files in `dir` (GeoJSON or GeoParquet, as style.json names them): the saved style and the tiles. `o`: other
/// rules than the style's.
pub fn tile_files(dir: &std::path::Path, keep: &[String], o: Option<tiles::stage::TileOptions>) -> Result<(Value, tiles::Tiles), String> {
    tile_files_with(|name| std::fs::read(dir.join(name)).map_err(|e| format!("{name}: {e}")), keep, o)
}

/// Stage 2 from stage 1's files, each read by `read` (a file name: its bytes), as `tile_files` does.
pub fn tile_files_with(read: impl Fn(&str) -> Result<Vec<u8>, String>, keep: &[String], o: Option<tiles::stage::TileOptions>)
                       -> Result<(Value, tiles::Tiles), String> {
    let style: Value = serde_json::from_slice(&read("style.json")?).map_err(|e| format!("style.json: {e}"))?;
    let o = match o { Some(o) => o, None => tiles::stage::TileOptions::from_style(&style, keep)? };
    let mut tiled = tiles::Tiles::new(o.min_zoom, o.max_zoom, o.buffer_px);
    for (k, spec) in style["sources"].as_object().into_iter().flatten() {
        if !o.wants(k) || spec["type"] != "geojson" {
            continue;
        }
        let file = spec["data"].as_str().ok_or_else(|| format!("source {k}: its data is not a file name"))?;
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
        let (keep, whole, from) = o.rule(k, || src["data"]["features"].as_array().into_iter().flatten()
            .filter_map(|f| f["properties"].as_object()).flat_map(|p| p.keys().cloned()).collect());
        tiled.add(k, src, &keep, whole, from);
    }
    Ok((style, tiled))
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
        return roadstyle_io::write::parquet_to(w, || road_rows(s), true);
    }
    let name = file.strip_suffix(&format!(".{ext}")).ok_or_else(|| format!("{file}: not a .{ext} file"))?;
    let i = s.sources.iter().position(|(n, _)| n == name).ok_or_else(|| format!("{file}: no source {name}"))?;
    if format == Format::GeoJson {
        s.write_data(i, drawn, &mut w).map_err(io)?;
        return Ok(w);
    }
    let line = |c: Option<&[[f64; 2]]>| c.map(|c| json!({"type": "LineString", "coordinates": c}));
    let lines = s.draws_roads();
    match &s.sources[i].1 {
        Src::Roads(_) => roadstyle_io::write::parquet_to(w, || s.roads.roads.iter().map(|r| roadstyle_io::write::Row {
            id: Some(r.i as i64),
            props: r.iter().map(|(k, c)| (s.roads.out_name(k), c)).filter(|(k, _)| k.starts_with("__rs_") || drawn.contains(*k))
                .map(|(k, c)| (k.to_string(), c.to_value())).collect(),
            geometry: line(r.line().filter(|_| lines)),
        }), true),
        Src::Simple(p) => roadstyle_io::write::parquet_to(w, || p.features(&s.roads.roads).map(|(id, props, c)| roadstyle_io::write::Row {
            id: Some(id as i64), props: props.into_iter().map(|(k, v)| (k.to_string(), v)).collect(), geometry: line(c),
        }), true),
        Src::Json(v) => {
            let fs = v["data"]["features"].as_array().map(Vec::as_slice).unwrap_or_default();
            roadstyle_io::write::parquet_to(w, || fs.iter().map(|f| roadstyle_io::write::Row {
                id: f["id"].as_i64(),
                props: f["properties"].as_object().into_iter().flatten().map(|(k, v)| (k.clone(), v.clone())).collect(),
                geometry: Some(f["geometry"].clone()).filter(|g| !g.is_null()),
            }), true)
        }
    }
}

/// The road table's rows: each road's fields with the output's names, then its middle (`__mid_lon`, `__mid_lat`), its heading at the
/// middle (`__heading`) and its box (`__bbox_*`), and its line as the geometry.
fn road_rows(s: &sources::Sources) -> impl Iterator<Item = roadstyle_io::write::Row> + '_ {
    use roadstyle_engine::geom::line;
    s.roads.roads.iter().map(move |r| {
        let c = r.line();
        let mut props: Vec<(String, Value)> = r.iter().map(|(k, v)| (s.roads.out_name(k).to_string(), v.to_value())).collect();
        let mid = c.and_then(line::mid);
        let bb = c.and_then(line::bbox);
        let num = |v: Option<f64>| v.map_or(Value::Null, Value::from);
        props.extend([("__mid_lon".into(), num(mid.map(|m| m[0]))), ("__mid_lat".into(), num(mid.map(|m| m[1]))),
                      ("__heading".into(), num(c.and_then(line::heading)))]);
        props.extend(["__bbox_min_lon", "__bbox_min_lat", "__bbox_max_lon", "__bbox_max_lat"].iter().enumerate()
            .map(|(k, n)| (n.to_string(), num(bb.map(|b| b[k])))));
        roadstyle_io::write::Row { id: None, props, geometry: c.map(|c| json!({"type": "LineString", "coordinates": c})) }
    })
}

/// The road table as the page loads it (tiles.sidecar's form, with Python's JSON text): `{"props", "mids", "bboxes", "headings",
/// "lines"}`, each a list with one item for each road (its row), written to `w` a road at a time.
pub fn write_road_table<W: std::io::Write>(s: &sources::Sources, w: &mut W) -> std::io::Result<()> {
    use page::pyjson::dumps;
    use roadstyle_engine::geom::line;
    let roads = &s.roads.roads;
    let list = |w: &mut W, key: &str, first: bool, item: &dyn Fn(roadstyle_engine::Road) -> String| -> std::io::Result<()> {
        write!(w, "{}\"{key}\":[", if first { "{" } else { "," })?;
        for r in roads.iter() {
            if r.i > 0 {
                w.write_all(b",")?;
            }
            w.write_all(item(r).as_bytes())?;
        }
        w.write_all(b"]")
    };
    let pts = |c: &[[f64; 2]]| dumps(&json!(c), true);
    list(w, "props", true, &|r| dumps(&Value::Object(r.iter().map(|(k, v)| (s.roads.out_name(k).to_string(), v.to_value())).collect()), true))?;
    list(w, "mids", false, &|r| r.line().and_then(line::mid).map_or("null".into(), |m| dumps(&json!(m), true)))?;
    list(w, "bboxes", false, &|r| r.line().and_then(line::bbox).map_or("null".into(), |b| dumps(&json!(b), true)))?;
    list(w, "headings", false, &|r| r.line().and_then(line::heading).map_or("null".into(), |h| dumps(&json!(h), true)))?;
    list(w, "lines", false, &|r| r.line().filter(|c| !c.is_empty()).map_or("null".into(), pts))?;
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

/// A style of stage 1 (its sources GeoJSON) for stage 2's tiles: one vector source, `<prefix>roads/{z}/{x}/{y}` with the tiles' zooms,
/// and each layer on the tile layer of its old source (`source-layer`).
pub fn vector_style(style: &Value, prefix: &str, zooms: (u32, u32)) -> Value {
    let mut style = style.clone();
    let promote = style["sources"]["simple"]["promoteId"].as_str().map(|p| json!({"simple": p}));
    for l in style["layers"].as_array_mut().into_iter().flatten() {
        if let Some(src) = l.get("source").cloned() {
            l["source-layer"] = src;
            l["source"] = tiles::SOURCE.into();
        }
    }
    style["sources"] = json!({tiles::SOURCE: {"type": "vector", "tiles": [format!("{prefix}{}/{{z}}/{{x}}/{{y}}", tiles::SOURCE)],
                                              "minzoom": zooms.0, "maxzoom": zooms.1}});
    if let Some(p) = promote {          // the pieces' row as the feature id, as on the GeoJSON source
        style["sources"][tiles::SOURCE]["promoteId"] = p;
    }
    style
}

/// Stage 2 from memory, with the rules of the look that made `s` (make_sources saves them): the tiled style and the tiles.
pub fn tile_made(mut s: sources::Sources, prefix: &str, keep: &[String]) -> Result<(String, tiles::Tiles), String> {
    let o = tiles::stage::TileOptions::new(&s.layers, &s.metadata, &s.saved[tiles::stage::TILES], &s.saved[tiles::stage::COLUMNS], keep)?;
    let tiled = tile_sources(&mut s, &o);
    let style = vector_style(&s.style(|_| String::new()), prefix, tiled.zooms());
    Ok((style.to_string(), tiled))
}

/// The style with one vector-tile source, `roads` (`<prefix>roads/{z}/{x}/{y}`), and the tiles to answer it with (tiles.rs: the rules of
/// roadstyle's tiles.py, the zooms and the buffer from `look["config"]["tiles"]`). The layers, the metadata and the camera are those of
/// `make_style`; each layer draws the tile layer of its old source (`source-layer`). The tiles keep only the properties that are read:
/// the texts in the layers (all their keys, and more), the popup and tooltip fields of the metadata, the overlays' popup fields (name,
/// kind) and `keep` (the caller's own, for example its popup's).
pub fn make_tiled(parquet: Vec<u8>, look: &str, features: Option<Vec<u8>>, name: Option<String>, prefix: &str, keep: &[String])
                  -> Result<(String, tiles::Tiles), String> {
    let cfg_all: Value = serde_json::from_str(look).map_err(|e| format!("look: not JSON: {e}"))?;
    let (feats, features, _) = tables(parquet, features, None)?;
    let mut s = sources::Sources::new(make_parts(feats, look, features, None, name)?);
    let mut o = tiles::stage::TileOptions::new(&s.layers, &s.metadata, &cfg_all["config"]["tiles"], &columns(&cfg_all), keep)
        .map_err(|e| format!("look: config.{e}"))?;
    // render(tiles=True)'s page (the Python binding): the columns of its road and simple tiles (`tile_keep`; every __rs_* goes too) and
    // the sources in its tiles (`tile_layers`: roads, simple, slots; the page keeps the others inline)
    o.exact = cfg_all["args"]["tile_keep"].as_array().map(|a| a.iter().filter_map(Value::as_str).map(String::from).collect());
    o.only = cfg_all["args"]["tile_layers"].as_array().map(|a| a.iter().filter_map(Value::as_str).map(String::from).collect());
    let tiled = tile_sources(&mut s, &o);
    Ok((vector_style(&s.style(|_| String::new()), prefix, (o.min_zoom, o.max_zoom)).to_string(), tiled))
}

