//! Stage 1 (docs/rust/architecture.md, "The three stages and the one call"): the roads and the look give the style and its sources,
//! typed in memory: the drawing sources (the roads' lines with their drawing values, the pieces, the names and arrows, the 3D decks,
//! the base map, ...) and the road table (every field of each road, by its row). Nothing here is about tiles: stage 2 (roadstyle-tiles)
//! cuts the sources, from memory or from the files that this output is saved as (GeoJSON or GeoParquet: the facade and roadstyle-io).

use crate::road::RoadsSource;
use crate::{take_roads, Parts, Roads, RoadTable, Src};
use roadstyle_model::Cell;
use serde_json::Value;
use std::collections::HashSet;

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
        let roads = roads.unwrap_or_else(|| RoadsSource { roads: Roads::new(RoadTable::empty()), tolerance: 0.05, maxzoom: None, names: Vec::new() });
        Sources { name: p.name, center: p.center, zoom: p.zoom, layers: p.layers, metadata: p.metadata, glyphs: p.glyphs, state: p.state, sources, roads,
                  saved: serde_json::Map::new() }
    }

    /// The properties that the drawing reads (tiles.py's tile_props): every text in the layers, the popup and tooltip fields, `name`,
    /// `kind` and `keep`; every `__rs_*` property goes too.
    pub fn drawn(&self, keep: &[String]) -> HashSet<String> {
        roadstyle_model::props::drawn(&self.layers, &self.metadata, keep)
    }

    /// The FeatureCollection of the source `i` as GeoJSON text. The roads have only the properties of `drawn` and their marks: their
    /// fields are in the road table.
    pub fn data(&self, i: usize, drawn: &HashSet<String>) -> Vec<u8> {
        let mut out = Vec::new();
        match &self.sources[i].1 {
            Src::Roads(_) => self.roads.write_data(&mut out, Some(drawn)),
            Src::Simple(s) => s.write_data(&mut out, &self.roads.roads),
            Src::Json(v) => serde_json::to_writer(&mut out, &v["data"]).unwrap(),
        }
        out
    }

    /// The style with each source's data at `url(name)` (a GeoJSON source can name its data by URL), in place of the data.
    pub fn style(&self, url: impl Fn(&str) -> String) -> Value {
        let spec = |tolerance: f64, maxzoom: Option<i64>, url: String| {
            let mut s = serde_json::Map::new();
            s.insert("type".into(), "geojson".into());
            s.insert("data".into(), url.into());
            s.insert("tolerance".into(), tolerance.into());
            if let Some(z) = maxzoom {
                s.insert("maxzoom".into(), z.into());
            }
            Value::Object(s)
        };
        let sources: serde_json::Map<String, Value> = self.sources.iter().map(|(k, s)| (k.clone(), match s {
            Src::Roads(_) => spec(self.roads.tolerance, self.roads.maxzoom, url(k)),
            Src::Simple(s) => spec(s.tolerance, s.maxzoom, url(k)),
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

    /// The road table: the properties of each road (its row is its position), with the output's names.
    pub fn road_rows(&self) -> impl Iterator<Item = Vec<(&str, Cell<'_>)>> + '_ {
        self.roads.roads.iter().map(|r| r.iter().map(|(k, c)| (self.roads.out_name(k), c)).collect())
    }
}
