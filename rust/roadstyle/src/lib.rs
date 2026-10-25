//! roadstyle as a Rust library (docs/design/rust_library.md): the facade. It re-exports the crates of the core with the module paths
//! of the old single crate (`roadstyle::props`, `roadstyle::read`, `roadstyle::levels`, `roadstyle::tiles`, `roadstyle::make_style`,
//! ...), and it has the functions that read GeoParquet bytes (roadstyle-io) and call the engine: `make_style` and `make_tiled`, which
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
pub mod level_area;
pub mod level_editor;
pub mod options;
pub mod page;
pub mod page_options;
pub mod tiled;
pub use tiled::{tile, xyz_at, TileInput, TileOptions, Tiled};
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

/// The base map's rows from their GeoParquet bytes (the duckOSM reader's features.parquet), the background's land without the sea
/// (duckosm::cut_sea).
pub fn read_features(features: Vec<u8>) -> Result<FeatureTable, crate::Error> {
    features_of(read::read_feature_table(features, "geometry")?)
}

/// The base map's rows that a reader gave (`read::feature_table_from`, ...), as `read_features`.
pub fn features_of(t: FeatureTable) -> Result<FeatureTable, crate::Error> {
    Ok(duckosm::cut_sea(t)?)
}

/// The style as one JSON text (roadstyle's export_inline), from the roads and the other tables as GeoParquet bytes: the engine's
/// `make_style` after roadstyle-io's readers.
pub fn make_style(parquet: Vec<u8>, look: &Look, features: Option<Vec<u8>>, planner: Option<Vec<u8>>, name: Option<String>) -> Result<String, crate::Error> {
    let (feats, features, planner) = tables(parquet, features, planner)?;
    Ok(roadstyle_engine::make_style(feats, look, features, planner, name)?)
}

/// Stage 1 from GeoParquet bytes: the style and its sources, typed in memory (docs/rust/architecture.md, "The three stages and the one
/// call"). `save_sources` writes them as files; the saved style has what stage 2 reads (`roadstyle:tiles`: the look's tile settings,
/// `roadstyle:columns`: the class, filter and metre width columns).
pub fn make_sources(parquet: Vec<u8>, look: &Look, features: Option<Vec<u8>>, planner: Option<Vec<u8>>, name: Option<String>) -> Result<sources::Styled, crate::Error> {
    let (feats, features, planner) = tables(parquet, features, planner)?;
    sources_of(feats, look, features, planner, name)
}

/// Stage 1 of roads that a reader gave (`read::read_roads`, `geojson::read_roads`, ...), as `make_sources`.
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
pub fn file_names(s: &sources::Styled, format: Format) -> Vec<String> {
    let ext = ext(format);
    ["style.json".to_string()].into_iter().chain(s.shown().map(|(n, _)| format!("{n}.{ext}"))).chain([ROAD_TABLE.to_string()]).collect()
}

fn ext(format: Format) -> &'static str {
    match format { Format::GeoJson => "geojson", Format::GeoParquet => "parquet" }
}

/// One of stage 1's files (a name of `file_names`), in memory (`write_source_file`).
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

/// The road table as the page loads it (tiles.sidecar's form; `Styled::table_rows`): `{"props", "mids", "bboxes", "lines"}`, each a
/// list with one item for each road (its row). `fields`: only these fields of each road (the level editor's lean table: what its page
/// reads); None: every field.
pub fn write_road_table<W: std::io::Write>(s: &sources::Styled, fields: Option<&[String]>, w: &mut W) -> std::io::Result<()> {
    let mut rows = s.table_rows();
    if let Some(f) = fields {
        rows.iter_mut().for_each(|t| t.props.retain(|(k, _)| f.iter().any(|n| n == k)));
    }
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
            serde_json::to_writer(&mut *w, &js_value(v.to_value()))?;
        }
        w.write_all(b"}").map_err(serde_json::Error::io)
    })?;
    list(w, "mids", false, &|w, t| serde_json::to_writer(w, &t.mid))?;
    list(w, "bboxes", false, &|w, t| serde_json::to_writer(w, &t.bbox))?;
    list(w, "lines", false, &|w, t| serde_json::to_writer(w, &t.line))?;
    w.write_all(b"}")
}

/// Stage 1's files in `dir` (`file_names`, `source_file`). `keep`: more columns for the roads' file. Gives each file's name and size.
pub fn save_sources(s: &sources::Styled, dir: &std::path::Path, format: Format, keep: &[String]) -> Result<Vec<(String, usize)>, crate::Error> {
    std::fs::create_dir_all(dir).map_err(|e| crate::error::file(dir.display(), e))?;
    let drawn = s.drawn(keep);
    let mut files = Vec::new();
    for name in file_names(s, format) {
        let path = dir.join(&name);
        let f = std::fs::File::create(&path).map_err(|e| crate::error::file(&name, e))?;
        let mut w = write_source_file(s, &name, format, &drawn, std::io::BufWriter::new(f))?;
        std::io::Write::flush(&mut w).map_err(|e| crate::error::file(&name, e))?;
        files.push((name.clone(), std::fs::metadata(&path).map_err(|e| crate::error::file(&name, e))?.len() as usize));
    }
    Ok(files)
}


