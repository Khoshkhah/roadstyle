//! roadstyle as a Rust library (docs/design/rust_library.md): the facade. It re-exports the crates of the core with the module paths
//! of the old single crate (`roadstyle::props`, `roadstyle::read`, `roadstyle::levels`, `roadstyle::tiles`, `roadstyle::make_style`,
//! ...), and it has the functions that read GeoParquet bytes (roadstyle-io) and call the engine: `make_style` and `make_tiled`, which
//! needs both the engine and the tiles. A Rust user adds only this crate.

pub use roadstyle_engine::*;
pub use roadstyle_io::read;
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
            // the roads, from the table and the marks (no copy of their properties)
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
    let read = |name: &str| std::fs::read(dir.join(name)).map_err(|e| format!("{name}: {e}"));
    let style: Value = serde_json::from_slice(&read("style.json")?).map_err(|e| format!("style.json: {e}"))?;
    let o = match o { Some(o) => o, None => tiles::stage::TileOptions::from_style(&style, keep)? };
    let mut tiled = tiles::Tiles::new(o.min_zoom, o.max_zoom, o.buffer_px);
    for (k, spec) in style["sources"].as_object().into_iter().flatten() {
        if !o.wants(k) || spec["type"] != "geojson" {
            continue;
        }
        let file = spec["data"].as_str().ok_or_else(|| format!("source {k}: its data is not a file name"))?;
        let fc: Value = if file.ends_with(".parquet") { read::features(read(file)?)? }
                        else { serde_json::from_slice(&read(file)?).map_err(|e| format!("{file}: {e}"))? };
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

/// Stage 1's files in `dir`: `style.json` (each source's data at its file), one file for each source, and the road table (every field
/// of each road, by its row; the roads' file has only their drawing values). `keep`: more columns for the roads' file. Gives each
/// file's name and size.
pub fn save_sources(s: &sources::Sources, dir: &std::path::Path, format: Format, keep: &[String]) -> Result<Vec<(String, usize)>, String> {
    let ext = match format { Format::GeoJson => "geojson", Format::GeoParquet => "parquet" };
    let drawn = s.drawn(keep);
    let mut files = Vec::new();
    let mut put = |name: String, bytes: Vec<u8>| -> Result<(), String> {
        std::fs::write(dir.join(&name), &bytes).map_err(|e| format!("{name}: {e}"))?;
        files.push((name, bytes.len()));
        Ok(())
    };
    std::fs::create_dir_all(dir).map_err(|e| format!("{}: {e}", dir.display()))?;
    for (i, (name, src)) in s.sources.iter().enumerate() {
        let bytes = match format {
            Format::GeoJson => s.data(i, &drawn),
            Format::GeoParquet => {
                let line = |c: Option<&[[f64; 2]]>| c.map(|c| json!({"type": "LineString", "coordinates": c}));
                match src {
                    Src::Roads(_) => roadstyle_io::write::parquet(|| s.roads.roads.iter().map(|r| roadstyle_io::write::Row {
                        id: Some(r.i as i64),
                        props: r.iter().map(|(k, c)| (s.roads.out_name(k), c)).filter(|(k, _)| k.starts_with("__rs_") || drawn.contains(*k))
                            .map(|(k, c)| (k.to_string(), c.to_value())).collect(),
                        geometry: line(r.line()),
                    }), true)?,
                    Src::Simple(p) => roadstyle_io::write::parquet(|| p.features(&s.roads.roads).map(|(id, props, c)| roadstyle_io::write::Row {
                        id: Some(id as i64), props: props.into_iter().map(|(k, v)| (k.to_string(), v)).collect(), geometry: line(c),
                    }), true)?,
                    Src::Json(v) => {
                        let fs = v["data"]["features"].as_array().map(Vec::as_slice).unwrap_or_default();
                        roadstyle_io::write::parquet(|| fs.iter().map(|f| roadstyle_io::write::Row {
                            id: f["id"].as_i64(),
                            props: f["properties"].as_object().into_iter().flatten().map(|(k, v)| (k.clone(), v.clone())).collect(),
                            geometry: Some(f["geometry"].clone()).filter(|g| !g.is_null()),
                        }), true)?
                    }
                }
            }
        };
        put(format!("{name}.{ext}"), bytes)?;
    }
    let table = roadstyle_io::write::parquet(|| s.road_rows().map(|r| roadstyle_io::write::Row {
        id: None, props: r.into_iter().map(|(k, c)| (k.to_string(), c.to_value())).collect(), geometry: None,
    }), false)?;
    put(ROAD_TABLE.into(), table)?;
    let style = s.style(|n| format!("{n}.{ext}"));
    put("style.json".into(), serde_json::to_vec(&style).map_err(|e| e.to_string())?)?;
    Ok(files)
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
    let (min_zoom, max_zoom) = (o.min_zoom, o.max_zoom);
    let sources::Sources { name, center, zoom, mut layers, metadata, glyphs, state, .. } = s;
    for l in layers.iter_mut() {
        if let Some(src) = l.get("source").cloned() {
            l["source-layer"] = src;
            l["source"] = tiles::SOURCE.into();
        }
    }
    let vector = json!({tiles::SOURCE: {"type": "vector", "tiles": [format!("{prefix}{}/{{z}}/{{x}}/{{y}}", tiles::SOURCE)],
                                        "minzoom": min_zoom, "maxzoom": max_zoom}});
    let mut style = json!({"version": 8, "name": name, "center": center, "zoom": zoom, "layers": layers, "sources": vector, "metadata": metadata});
    if let Some(g) = glyphs {
        style["glyphs"] = g;
    }
    if let Some(st) = state {
        style["state"] = st;
    }
    Ok((style.to_string(), tiled))
}

