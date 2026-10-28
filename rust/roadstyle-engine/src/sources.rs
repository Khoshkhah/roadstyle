//! Stage 1 (docs/rust/architecture.md, "The three stages and the one call"): the roads and the look give the style and its sources,
//! typed in memory: the drawing sources (the roads' lines with their drawing values, the pieces, the names and arrows, the 3D decks,
//! the base map, ...) and the road table (every field of each road, by its row). Nothing here is about tiles: stage 2 (roadstyle-tiles)
//! cuts the sources, from memory or from the files that this output is saved as (GeoJSON or GeoParquet: the facade and roadstyle-io).

use roadstyle_model::mark::Mark;
use crate::features::FeatureSource;
use crate::road::RoadsSource;
use crate::simple::SimpleSource;
use crate::{Parts, Src};
use roadstyle_model::table::JsSafe;
use roadstyle_model::Cell;
use serde_json::Value;
use std::collections::HashSet;

/// One road's row of the road table: its fields and the stage values that the page reads (`road_row`), the middle of its line by length
/// (a popup's anchor, Street View's spot), its box (rsFocus) and its line.
pub struct TableRow<'a> {
    pub props: Vec<(&'a str, Cell<'a>)>,
    pub mid: Option<[f64; 2]>,
    pub bbox: Option<[f64; 4]>,
    pub line: Option<&'a [[f64; 2]]>,
}

/// How the style writer gives the sources' data (docs/design/target_architecture.md (f), T4 step 2): in the style, with render's
/// data_maxzoom (every GeoJSON source) and data_tolerance (every GeoJSON source that has a tolerance), or as the file of each source
/// next to the style (`<name>.<ext>`). The tiled style is stage 2's.
#[derive(Clone, Copy, Debug)]
pub enum SourceMode<'a> {
    Inline { maxzoom: Option<i64>, tolerance: Option<f64> },
    Files(&'a str),
}

impl SourceMode<'static> {
    /// The data in the style, with no data_maxzoom and no data_tolerance.
    pub const INLINE: SourceMode<'static> = SourceMode::Inline { maxzoom: None, tolerance: None };

    /// The data in the style, with the data_maxzoom and data_tolerance of `keys` (render's keywords).
    pub fn inline_of(keys: &serde_json::Map<String, Value>) -> SourceMode<'static> {
        SourceMode::Inline { maxzoom: keys.get("data_maxzoom").and_then(Value::as_f64).map(|z| z as i64),
                             tolerance: keys.get("data_tolerance").and_then(Value::as_f64) }
    }
}

/// One source of the style, borrowed: the roads (`Styled::roads`) or one of `Styled::sources`.
#[derive(Clone, Copy)]
pub enum Source<'a> {
    Roads(&'a RoadsSource),
    Simple(&'a SimpleSource),
    Features(&'a FeatureSource),
    Json(&'a Value),
}

impl<'a> From<&'a Src> for Source<'a> {
    fn from(s: &'a Src) -> Source<'a> {
        match s {
            Src::Simple(p) => Source::Simple(p),
            Src::Features(f) => Source::Features(f),
            Src::Json(v) => Source::Json(v),
        }
    }
}

/// Stage 1's output.
pub struct Styled {
    pub name: Value,
    pub center: Value,
    pub zoom: Value,
    pub layers: Vec<Value>,
    pub metadata: Value,
    pub glyphs: Option<Value>,
    pub state: Option<Value>,
    /// the sources after the roads, in the style's order (audit N15: the roads are not in this list)
    pub sources: Vec<(String, Src)>,
    /// the source `roads`, the first of the style when the style has it (`RoadsSource::in_style`)
    pub roads: RoadsSource,
    /// the metadata that only a saved style has (what stage 2 reads from it: `roadstyle:tiles`, `roadstyle:columns`)
    pub saved: serde_json::Map<String, Value>,
    /// the warnings of the stages, for the caller to give
    pub warnings: Vec<String>,
}

impl Styled {
    pub fn new(p: Parts) -> Styled {
        let mut s = Styled { name: p.name, center: p.center, zoom: p.zoom, layers: p.layers, metadata: p.metadata, glyphs: p.glyphs, state: p.state,
                             sources: p.sources, roads: p.roads, saved: serde_json::Map::new(), warnings: p.warnings };
        s.set_reads();
        let base: Vec<&str> = s.shown().filter(|(_, v)| matches!(v, Source::Features(_))).map(|(k, _)| k).collect();
        if !base.is_empty() {
            s.metadata[roadstyle_model::props::BASE_LAYERS] = base.into();
        }
        s
    }

    /// R1: the drawn features keep only the properties that are read: a piece what the road layer and the page read on it
    /// (props::piece_reads), a road's stage values what any layer reads (`drawn` with no caller's columns). Made again when the layers
    /// change (a view's palette: palettes.rs).
    pub fn set_reads(&mut self) {
        let pieces = roadstyle_model::props::piece_reads(&self.layers);
        for (_, s) in self.sources.iter_mut() {
            if let Src::Simple(p) = s {
                p.read = Some(pieces.clone());
            }
        }
        self.roads.read = Some(self.drawn(&[]));
    }

    /// Stage 3 of a page with inline data (audit N2): its one-way arrows are points that the page puts on each one-way road in the window
    /// (the dashboard's arrows.js, the empty source `arrows`), not symbols along the slots. The metadata says it (`roadstyle:arrows`).
    pub fn page_arrows(&mut self) {
        let Some(l) = self.layers.iter_mut().find(|l| l["id"] == "roads-arrows" && l["source"] == "slots") else { return };
        l["source"] = "arrows".into();
        let old = l["layout"].as_object().cloned().unwrap_or_default();
        let mut layout = serde_json::json!({"symbol-placement": "point", "icon-rotate": ["get", "b"], "icon-allow-overlap": false,
                                            "icon-ignore-placement": true});
        let m = layout.as_object_mut().unwrap();
        m.extend(old.into_iter().filter(|(k, _)| k != "symbol-placement" && k != "symbol-spacing"));
        l["layout"] = layout;
        let at = self.sources.iter().position(|(k, _)| k == "slots").map_or(self.sources.len(), |i| i + 1);
        // render's data_maxzoom: the writer gives it to every GeoJSON source (SourceMode::Inline)
        let arrows = serde_json::json!({"type": "geojson", "data": {"type": "FeatureCollection", "features": []}});
        self.sources.insert(at, ("arrows".into(), Src::Json(arrows)));
        if let Some(m) = self.metadata.as_object_mut().filter(|m| m.contains_key("roadstyle:contract")) {
            m.insert("roadstyle:sources".into(), crate::contract::roles(&self.layers));
            m.insert("roadstyle:arrows".into(), crate::contract::arrow_kind(&self.layers));
        }
    }

    /// The properties that the drawing reads: every text in the layers, the popup and tooltip fields, `name`,
    /// `kind` and `keep`; every `__rs_*` property goes too.
    pub fn drawn(&self, keep: &[String]) -> HashSet<String> {
        roadstyle_model::props::drawn(&self.layers, &self.metadata, keep)
    }

    /// The FeatureCollection of the source `src` (one of `shown`'s) as GeoJSON text, written to `w`. The roads have only the properties of
    /// `drawn` and their marks: their fields are in the road table, and their lines too when no layer draws the roads (`draws_roads`).
    pub fn write_data<W: std::io::Write>(&self, src: Source, drawn: &HashSet<String>, w: &mut W) -> std::io::Result<()> {
        match src {
            Source::Roads(r) => r.write_data(w, Some(drawn), self.draws_roads()),
            Source::Simple(s) => s.write_data(w, &self.roads.roads),
            Source::Features(f) => f.write_data(w),
            Source::Json(v) => serde_json::to_writer(w, &JsSafe(&v["data"])).map_err(std::io::Error::other),
        }
    }

    /// A layer that is shown draws the source `roads` (with no such layer, its features need no lines).
    pub fn draws_roads(&self) -> bool {
        self.layers.iter().any(|l| l["source"] == "roads" && l["layout"]["visibility"] != "none")
    }

    /// The style as one JSON text (export_inline's), with each source's GeoJSON in it (`mode`: SourceMode::Inline) or its file's name,
    /// written to `w` a part at a time. A page's style has no `roads` source (`RoadsSource::in_style`).
    pub fn write_style<W: std::io::Write>(&self, w: &mut W, mode: SourceMode) -> std::io::Result<()> {
        self.write_with(&self.style_with(mode, false), w)
    }

    /// The style as a JSON value, each source's `data` by `mode` (audit D3: no source is copied with its data): null, where `write_with`
    /// writes the source's FeatureCollection (Inline), or the name of its file (Files). `saved`: the metadata has what only a saved style
    /// has (`roadstyle:tiles`, `roadstyle:columns`). The one builder of a style: export_inline's text, the saved style, stage 2's and the
    /// page's.
    pub fn style_with(&self, mode: SourceMode, saved: bool) -> Value {
        let data = |k: &str| match mode { SourceMode::Inline { .. } => Value::Null, SourceMode::Files(ext) => format!("{k}.{ext}").into() };
        let (maxzoom, tolerance) = match mode { SourceMode::Inline { maxzoom, tolerance } => (maxzoom, tolerance), SourceMode::Files(_) => (None, None) };
        let spec = |tolerance: f64, promote: bool, maxzoom: Option<i64>, data: Value| {
            let mut s = serde_json::Map::new();
            s.insert("type".into(), "geojson".into());
            s.insert("data".into(), data);
            s.insert("tolerance".into(), tolerance.into());
            if promote {
                s.insert("promoteId".into(), Mark::Edge.name().into());
            }
            if let Some(z) = maxzoom {
                s.insert("maxzoom".into(), z.into());
            }
            Value::Object(s)
        };
        let sources: serde_json::Map<String, Value> = self.shown().map(|(k, s)| (k.to_string(), match s {
            Source::Roads(r) => spec(tolerance.unwrap_or(r.tolerance), false, maxzoom.or(r.maxzoom), data(k)),
            Source::Simple(s) => spec(tolerance.unwrap_or(s.tolerance), s.promote, maxzoom.or(s.maxzoom), data(k)),
            Source::Features(f) => f.spec(data(k), maxzoom),
            // the source's other members, `data` in its place, and the mode's tolerance (where it has one) and maxzoom (a GeoJSON source)
            Source::Json(v) => v.as_object().map_or_else(|| v.clone(), |o| {
                let mut m: serde_json::Map<String, Value> = o.iter().map(|(m, x)| (m.clone(), match m.as_str() {
                    "data" => data(k),
                    "tolerance" => tolerance.map_or_else(|| x.clone(), Value::from),
                    _ => x.clone(),
                })).collect();
                if let Some(z) = maxzoom.filter(|_| m.get("type").is_some_and(|t| t == "geojson")) {
                    m.insert("maxzoom".into(), z.into());
                }
                Value::Object(m)
            }),
        })).collect();
        let mut metadata = self.metadata.clone();
        if let Some(m) = metadata.as_object_mut().filter(|_| saved) {
            m.extend(self.saved.iter().map(|(k, v)| (k.clone(), v.clone())));
        }
        let mut style = serde_json::json!({"version": 8, "name": self.name, "center": self.center, "zoom": self.zoom, "layers": self.layers,
                                           "sources": sources, "metadata": metadata});
        if let Some(g) = &self.glyphs {
            style["glyphs"] = g.clone();
        }
        if let Some(st) = &self.state {
            style["state"] = st.clone();
        }
        style
    }

    /// The sources that the style shows, in its order, with their names: the roads first when the style has them, then `sources`.
    pub fn shown(&self) -> impl Iterator<Item = (&str, Source<'_>)> {
        let roads = self.roads.in_style.then_some(("roads", Source::Roads(&self.roads)));
        roads.into_iter().chain(self.sources.iter().map(|(k, s)| (k.as_str(), Source::from(s))))
    }

    /// The source `name` that the style shows, or none.
    pub fn source(&self, name: &str) -> Option<Source<'_>> {
        self.shown().find(|(k, _)| *k == name).map(|(_, s)| s)
    }

    /// The FeatureCollection of the source `name` as the style has it (write_style's), written to `w`; false: no such source.
    pub fn write_source_data<W: std::io::Write>(&self, name: &str, w: &mut W) -> std::io::Result<bool> {
        let Some(s) = self.source(name) else { return Ok(false) };
        match s {
            Source::Roads(r) => r.write_data(w, None, true)?,
            Source::Simple(p) => p.write_data(w, &self.roads.roads)?,
            Source::Features(f) => f.write_data(w)?,
            Source::Json(v) => serde_json::to_writer(&mut *w, &JsSafe(&v["data"]))?,
        }
        Ok(true)
    }

    /// `style` (`style_with`'s, perhaps changed: tiled, merged into a page) as JSON text, written to `w` a part at a time: a source of
    /// this Styled whose `data` is null gets its FeatureCollection there (`write_source_data`); all else is written as it is.
    pub fn write_with<W: std::io::Write>(&self, style: &Value, w: &mut W) -> std::io::Result<()> {
        let Some(top) = style.as_object() else { return serde_json::to_writer(w, &JsSafe(style)).map_err(std::io::Error::other) };
        w.write_all(b"{")?;
        for (i, (k, v)) in top.iter().enumerate() {
            if i > 0 {
                w.write_all(b",")?;
            }
            serde_json::to_writer(&mut *w, k)?;
            w.write_all(b":")?;
            match (k.as_str(), v.as_object()) {
                ("sources", Some(srcs)) => {
                    w.write_all(b"{")?;
                    for (j, (name, src)) in srcs.iter().enumerate() {
                        if j > 0 {
                            w.write_all(b",")?;
                        }
                        serde_json::to_writer(&mut *w, name)?;
                        w.write_all(b":")?;
                        self.write_source(name, src, w)?;
                    }
                    w.write_all(b"}")?;
                }
                _ => serde_json::to_writer(&mut *w, &JsSafe(v))?,
            }
        }
        w.write_all(b"}")
    }

    fn write_source<W: std::io::Write>(&self, name: &str, src: &Value, w: &mut W) -> std::io::Result<()> {
        let Some(o) = src.as_object().filter(|o| o.get("data").is_some_and(Value::is_null)) else {
            return serde_json::to_writer(w, &JsSafe(src)).map_err(std::io::Error::other);
        };
        w.write_all(b"{")?;
        for (i, (m, x)) in o.iter().enumerate() {
            if i > 0 {
                w.write_all(b",")?;
            }
            serde_json::to_writer(&mut *w, m)?;
            w.write_all(b":")?;
            if m != "data" || !self.write_source_data(name, w)? {
                serde_json::to_writer(&mut *w, &JsSafe(x))?;
            }
        }
        w.write_all(b"}")
    }

    /// The road table (audit N4): one typed row for each road (its row is its position), which the page's JSON and the Parquet file
    /// encode.
    pub fn table_rows(&self) -> Vec<TableRow<'_>> {
        self.table_rows_of(None)
    }

    /// `table_rows` with only the fields `fields` of each road (None: every field); the cell of another field is not read.
    pub fn table_rows_of(&self, fields: Option<&[String]>) -> Vec<TableRow<'_>> {
        use roadstyle_model::geom::line;
        let keep = |k: &str| roadstyle_model::props::table_keeps(k) && fields.is_none_or(|f| f.iter().any(|n| n == k));
        self.roads.roads.iter().map(|r| {
            let c = r.line();
            TableRow { props: r.iter_where(keep).collect(), mid: c.and_then(line::mid), bbox: c.and_then(line::bbox), line: c.filter(|c| !c.is_empty()) }
        }).collect()
    }

    /// One road's row of the road table: its fields and the stage values that the page reads (R1: props::table_keeps).
    pub fn road_row<'a>(&'a self, r: crate::Road<'a>) -> Vec<(&'a str, Cell<'a>)> {
        r.iter_where(roadstyle_model::props::table_keeps).collect()
    }
}
