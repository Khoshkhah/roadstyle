//! Stage 1 (docs/rust/architecture.md, "The three stages and the one call"): the roads and the look give the style and its sources,
//! typed in memory: the drawing sources (the roads' lines with their drawing values, the pieces, the names and arrows, the 3D decks,
//! the base map, ...) and the road table (every field of each road, by its row). Nothing here is about tiles: stage 2 (roadstyle-tiles)
//! cuts the sources, from memory or from the files that this output is saved as (GeoJSON or GeoParquet: the facade and roadstyle-io).

use crate::road::RoadsSource;
use crate::{take_roads, Parts, Roads, RoadTable, Src};
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

/// Stage 1's output.
pub struct Sources {
    pub name: Value,
    pub center: Value,
    pub zoom: Value,
    pub layers: Vec<Value>,
    pub metadata: Value,
    pub glyphs: Option<Value>,
    pub state: Option<Value>,
    /// the sources in the style's order; the roads' place holds an empty `Src::Roads`
    pub sources: Vec<(String, Src)>,
    pub roads: RoadsSource,
    /// the metadata that only a saved style has (what stage 2 reads from it: `roadstyle:tiles`, `roadstyle:columns`)
    pub saved: serde_json::Map<String, Value>,
}

impl Sources {
    pub fn new(p: Parts) -> Sources {
        let (sources, roads) = take_roads(p.sources);
        let roads = roads.unwrap_or_else(|| RoadsSource { roads: Roads::new(RoadTable::empty()), tolerance: 0.05, maxzoom: None, names: Vec::new(),
                                                          in_style: false, read: None });
        let mut s = Sources { name: p.name, center: p.center, zoom: p.zoom, layers: p.layers, metadata: p.metadata, glyphs: p.glyphs, state: p.state,
                              sources, roads, saved: serde_json::Map::new() };
        s.set_reads();
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
        let mut arrows = serde_json::json!({"type": "geojson", "data": {"type": "FeatureCollection", "features": []}});
        // render's data_maxzoom, as every GeoJSON source of the page has it (stage 1 gave it to the pieces)
        if let Some(z) = self.sources.iter().find_map(|(_, s)| if let Src::Simple(p) = s { p.maxzoom } else { None }) {
            arrows["maxzoom"] = z.into();
        }
        self.sources.insert(at, ("arrows".into(), Src::Json(arrows)));
        if let Some(m) = self.metadata.as_object_mut().filter(|m| m.contains_key("roadstyle:contract")) {
            m.insert("roadstyle:sources".into(), crate::contract::roles(&self.layers));
            m.insert("roadstyle:arrows".into(), crate::contract::arrow_kind(&self.layers));
        }
    }

    /// The properties that the drawing reads (tiles.py's tile_props): every text in the layers, the popup and tooltip fields, `name`,
    /// `kind` and `keep`; every `__rs_*` property goes too.
    pub fn drawn(&self, keep: &[String]) -> HashSet<String> {
        roadstyle_model::props::drawn(&self.layers, &self.metadata, keep)
    }

    /// The FeatureCollection of the source `i` as GeoJSON text, written to `w`. The roads have only the properties of `drawn` and their
    /// marks: their fields are in the road table, and their lines too when no layer draws the roads (`draws_roads`).
    pub fn write_data<W: std::io::Write>(&self, i: usize, drawn: &HashSet<String>, w: &mut W) -> std::io::Result<()> {
        match &self.sources[i].1 {
            Src::Roads(_) => self.roads.write_data(w, Some(drawn), self.draws_roads()),
            Src::Simple(s) => s.write_data(w, &self.roads.roads),
            Src::Json(v) => serde_json::to_writer(w, &JsSafe(&v["data"])).map_err(std::io::Error::other),
        }
    }

    /// A layer that is shown draws the source `roads` (with no such layer, its features need no lines).
    pub fn draws_roads(&self) -> bool {
        self.layers.iter().any(|l| l["source"] == "roads" && l["layout"]["visibility"] != "none")
    }

    /// The style as one JSON text (export_inline's), with each source's GeoJSON in it, written to `w` a part at a time. A page's style
    /// has no `roads` source (`RoadsSource::in_style`).
    pub fn write_style<W: std::io::Write>(&self, w: &mut W) -> std::io::Result<()> {
        write!(w, r#"{{"version":8,"name":{},"center":{},"zoom":{},"layers":"#, self.name, self.center, self.zoom)?;
        serde_json::to_writer(&mut *w, &self.layers.iter().map(JsSafe).collect::<Vec<_>>())?;
        w.write_all(br#","sources":{"#)?;
        let shown = self.sources.iter().filter(|(_, s)| !matches!(s, Src::Roads(_)) || self.roads.in_style);
        for (i, (k, s)) in shown.enumerate() {
            if i > 0 {
                w.write_all(b",")?;
            }
            serde_json::to_writer(&mut *w, k)?;
            w.write_all(b":")?;
            match s {
                Src::Roads(_) => self.roads.write_json(w)?,
                Src::Simple(p) => p.write_json(w, &self.roads.roads)?,
                Src::Json(v) => serde_json::to_writer(&mut *w, &JsSafe(v))?,
            }
        }
        w.write_all(br#"},"metadata":"#)?;
        serde_json::to_writer(&mut *w, &JsSafe(&self.metadata))?;
        if let Some(g) = &self.glyphs {
            write!(w, r#","glyphs":{g}"#)?;
        }
        if let Some(st) = &self.state {
            write!(w, r#","state":{st}"#)?;
        }
        w.write_all(b"}")
    }

    /// The style with each source's data at `url(name)` (a GeoJSON source can name its data by URL), in place of the data.
    pub fn style(&self, url: impl Fn(&str) -> String) -> Value {
        let spec = |tolerance: f64, promote: bool, maxzoom: Option<i64>, url: String| {
            let mut s = serde_json::Map::new();
            s.insert("type".into(), "geojson".into());
            s.insert("data".into(), url.into());
            s.insert("tolerance".into(), tolerance.into());
            if promote {
                s.insert("promoteId".into(), "__rs_edge".into());
            }
            if let Some(z) = maxzoom {
                s.insert("maxzoom".into(), z.into());
            }
            Value::Object(s)
        };
        let sources: serde_json::Map<String, Value> = self.sources.iter().filter(|(_, s)| !matches!(s, Src::Roads(_)) || self.roads.in_style)
            .map(|(k, s)| (k.clone(), match s {
            Src::Roads(_) => spec(self.roads.tolerance, false, self.roads.maxzoom, url(k)),
            Src::Simple(s) => spec(s.tolerance, s.promote, s.maxzoom, url(k)),
            Src::Json(v) => {
                let mut v = v.clone();
                v["data"] = url(k).into();
                v
            }
        })).collect();
        let mut metadata = self.metadata.clone();
        if let Some(m) = metadata.as_object_mut() {
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

    /// The road table (audit N4): one typed row for each road (its row is its position), which the page's JSON and the Parquet file
    /// encode.
    pub fn table_rows(&self) -> Vec<TableRow<'_>> {
        use roadstyle_model::geom::line;
        self.roads.roads.iter().map(|r| {
            let c = r.line();
            TableRow { props: self.road_row(r), mid: c.and_then(line::mid), bbox: c.and_then(line::bbox), line: c.filter(|c| !c.is_empty()) }
        }).collect()
    }

    /// One road's row of the road table: its fields and the stage values that the page reads (R1: props::table_keeps), with the
    /// output's names.
    pub fn road_row<'a>(&'a self, r: crate::Road<'a>) -> Vec<(&'a str, Cell<'a>)> {
        r.iter().filter(|(k, _)| roadstyle_model::props::table_keeps(k)).map(|(k, c)| (self.roads.out_name(k), c)).collect()
    }
}
