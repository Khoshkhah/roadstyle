//! Stage 2 (docs/design/target_architecture.md (f), T4 step 3): the vector tiles of stage 1's sources, from memory (`Styled`) or from
//! stage 1's files, and the style that draws them. One function, `tile`; the caller's choices are `TileOptions`, and the rules (the
//! zooms, the buffer, the properties that the drawing reads) come from the input: its layers and its saved metadata (`TileRules`).

use crate::sources::{self, Source, SourceMode, Styled};
use crate::tiles::stage::TileRules;
use crate::{contract, read, tiles, Cell, ROAD_TABLE};
use serde_json::{json, Value};

/// What stage 2 cuts: stage 1's output in memory (made by `sources_of` or `make_sources`, which save the look's tile settings in it), or
/// stage 1's files, each read by its name (style.json and the files that it names; an error is an `Error::File` of that name).
pub enum TileInput<'a> {
    Styled(&'a Styled),
    Files(&'a dyn Fn(&str) -> Result<Vec<u8>, String>),
}

/// The caller's choices of stage 2.
#[derive(Clone, Debug, Default)]
pub struct TileOptions {
    /// more properties of the features in the tiles (the caller's own, for example its popup's)
    pub keep: Vec<String>,
    /// only these columns of the roads and the pieces (render(tiles=True)'s tile_keep; every `__rs_*` one goes too)
    pub exact: Option<Vec<String>>,
    /// only these sources in the tiles (render(tiles=True)'s tile_layers); the others stay in the style
    pub layers: Option<Vec<String>>,
}

impl TileOptions {
    /// The choices of render's keywords `keys` (tile_keep, tile_layers) and `keep`: the bindings give them so (the look's `other`) until
    /// they give TileOptions themselves (the T4 binding plan).
    pub fn of(keys: &serde_json::Map<String, Value>, keep: &[String]) -> TileOptions {
        let list = |k: &str| keys.get(k).and_then(Value::as_array).map(|a| a.iter().filter_map(Value::as_str).map(String::from).collect());
        TileOptions { keep: keep.to_vec(), exact: list("tile_keep"), layers: list("tile_layers") }
    }
}

/// Stage 2's output: the tiles, and what the style that draws them needs (the input, the tiled sources, the tiles' zooms).
pub struct Tiled<'a> {
    pub tiles: tiles::Tiles,
    input: Input<'a>,
    tiled: Vec<String>,
    zooms: (u32, u32),
}

/// The input as `Tiled` keeps it: stage 1 in memory, or the saved style of its files.
enum Input<'a> {
    Styled(&'a Styled),
    Saved(Value),
}

/// Stage 2 of `input` with the caller's choices `o`. An error for zooms that are not tile zooms.
pub fn tile<'a>(input: TileInput<'a>, o: &TileOptions) -> Result<Tiled<'a>, crate::Error> {
    match input {
        TileInput::Styled(s) => {
            let mut r = TileRules::new(&s.layers, &s.metadata, &s.saved[tiles::stage::TILES], &s.saved[tiles::stage::COLUMNS], &o.keep)?;
            choose(&mut r, o);
            let tiles = tile_sources(s, &r)?;
            let tiled = s.shown().filter(|(k, _)| r.wants(k)).map(|(k, _)| k.to_string()).collect();
            Ok(Tiled { tiles, input: Input::Styled(s), tiled, zooms: (r.min_zoom, r.max_zoom) })
        }
        TileInput::Files(read) => tile_files(read, o),
    }
}

/// The caller's choices in the rules.
fn choose(r: &mut TileRules, o: &TileOptions) {
    r.exact = o.exact.as_ref().map(|e| e.iter().cloned().collect());
    r.only = o.layers.clone();
}

impl Tiled<'_> {
    /// The style that draws the tiles at `at` (`{"url": "pmtiles://roads"}` for an archive, `xyz_at(prefix)` for a folder): the tiled
    /// sources become the tile layers of one vector source `roads`. The other sources stay: stage 1's in memory with a null `data`
    /// (`inline`: their data_maxzoom and data_tolerance; `write_style` fills the data), the files' with their file names.
    /// The style has no `roadstyle:tiles` and no `roadstyle:columns`: they are what stage 2 reads from a saved style, and a tiled style
    /// is not stage 2's input (2026-10-25; before, a style tiled from memory had them and one tiled by make_tiled had not).
    pub fn style(&self, at: &Value, inline: SourceMode) -> Value {
        let mut style = match &self.input {
            Input::Styled(s) => s.style_with(inline, false),
            Input::Saved(v) => v.clone(),
        };
        if let Some(m) = style["metadata"].as_object_mut() {
            m.shift_remove(tiles::stage::TILES);
            m.shift_remove(tiles::stage::COLUMNS);
        }
        tiled_style(style, &self.tiled, at, self.zooms)
    }

    /// `style` written to `w` a part at a time, each null `data` with its source's FeatureCollection.
    pub fn write_style<W: std::io::Write>(&self, w: &mut W, at: &Value, inline: SourceMode) -> std::io::Result<()> {
        let style = self.style(at, inline);
        match &self.input {
            Input::Styled(s) => s.write_with(&style, w),
            Input::Saved(_) => serde_json::to_writer(w, &style).map_err(std::io::Error::other),
        }
    }

    /// `write_style` as JSON text.
    pub fn style_text(&self, at: &Value, inline: SourceMode) -> String {
        let mut out = Vec::new();
        self.write_style(&mut out, at, inline).expect("a Vec takes every byte");
        String::from_utf8(out).expect("JSON text is UTF-8")
    }
}

/// The location of an XYZ folder of tiles at `prefix` (`<prefix>roads/{z}/{x}/{y}`), as `tile_stage`'s `at`.
pub fn xyz_at(prefix: &str) -> Value {
    json!({"tiles": [format!("{prefix}{}/{{z}}/{{x}}/{{y}}", tiles::SOURCE)]})
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
fn tile_sources(s: &sources::Styled, o: &TileRules) -> Result<tiles::Tiles, tiles::Error> {
    let mut tiled = tiles::Tiles::new(o.min_zoom, o.max_zoom, o.buffer_px)?;
    tiled.drawn_by(&s.layers);
    let keys = |v: &Value| -> std::collections::HashSet<String> {
        v["data"]["features"].as_array().into_iter().flatten().filter_map(|f| f["properties"].as_object()).flat_map(|p| p.keys().cloned()).collect()
    };
    for (k, src) in s.shown().filter(|(k, _)| o.wants(k)) {
        match src {
            // the roads, from the table and the marks (no copy of their properties); a page has none
            Source::Roads(r) => {
                let (keep, whole, from) = o.rule(k, Default::default);
                tiled.add_lines(k, r.roads.iter().map(|x| (x.line(), r.props(x, None))), &keep, whole, first_drawn(&s.layers, k, from, o.max_zoom))        // the cells, no JSON copy
            }
            Source::Simple(p) => {
                let (keep, whole, from) = o.rule(k, Default::default);
                tiled.add_lines(k, p.features(&s.roads.roads).map(|(_, props, c)| (c, props.into_iter())), &keep, whole, first_drawn(&s.layers, k, from, o.max_zoom))
            }
            Source::Json(v) => {
                let (keep, whole, from) = whole_unless_lines(json_lines(v), o.rule(k, || keys(v)), o.min_zoom);
                tiled.add(k, v, &keep, whole, first_drawn(&s.layers, k, from, o.max_zoom))
            }
            // a base-map layer, from its table (audit R10)
            Source::Features(f) => {
                use roadstyle_engine::feature_table::GeomType;
                let t = &f.table;
                let lines = (0..t.len()).all(|r| matches!(t.geometries_of().kind(r), Some(GeomType::LineString | GeomType::MultiLineString)));
                let keys = || t.names().iter().filter(|n| (0..t.len()).any(|r| t.has_key(r, n))).cloned().collect();
                let (keep, whole, from) = whole_unless_lines(lines, o.rule(k, keys), o.min_zoom);
                tiled.add_features(k, t, &keep, whole, first_drawn(&s.layers, k, from, o.max_zoom))
            }
        }
    }
    Ok(tiled)
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

/// The style that draws stage 2's tiles: the sources `tiled` become the tile layers of one vector source `roads` (first, at `at`, with the
/// tiles' zooms and the pieces' `promoteId`), and each layer on one of them draws its tile layer (`source-layer`); the other sources stay.
fn tiled_style(mut style: Value, tiled: &[String], at: &Value, zooms: (u32, u32)) -> Value {
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

/// Stage 2 from stage 1's files, each read by `read`: the saved style's rules with the caller's choices.
fn tile_files<'a>(read: &dyn Fn(&str) -> Result<Vec<u8>, String>, o: &TileOptions) -> Result<Tiled<'a>, crate::Error> {
    let read = |name: &str| read(name).map_err(|e| crate::error::file(name, e));
    let style: Value = serde_json::from_slice(&read("style.json")?).map_err(|e| crate::error::file("style.json", e))?;
    let mut o2 = TileRules::from_style(&style, &o.keep)?;
    choose(&mut o2, o);
    let o = &o2;
    let mut tiled = tiles::Tiles::new(o.min_zoom, o.max_zoom, o.buffer_px)?;
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
            tiled.add_lines(k, feats, &keep, whole, first_drawn(layers, k, from, o.max_zoom));
            continue;
        }
        let mut fc: Value = if file.ends_with(".parquet") { read::features(read(file)?)? }
                            else { serde_json::from_slice(&read(file)?).map_err(|e| crate::error::file(file, e))? };
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
        tiled.add(k, &src, &keep, whole, first_drawn(layers, k, from, o.max_zoom));
    }
    let zooms = (o.min_zoom, o.max_zoom);
    Ok(Tiled { tiles: tiled, input: Input::Saved(style), tiled: names, zooms })
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
