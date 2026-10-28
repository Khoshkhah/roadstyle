//! Stage 2's rules (docs/rust/architecture.md, "The three stages and the one call"): which properties of each source go into the
//! tiles, from which zoom, with which zooms and buffer. They come from the style alone (its layers, its `roadstyle:interaction`, and
//! the `roadstyle:tiles` and `roadstyle:columns` that stage 1 writes into a saved style), so stage 2 needs neither the roads nor the
//! look. The rules are (tile_props, the slots whole from their first zoom) and render(tiles=True)'s page's.

use crate::Error;
use serde_json::Value;
use std::collections::{HashMap, HashSet};

#[derive(Clone, Debug)]
pub struct TileOptions {
    pub min_zoom: u32,
    pub max_zoom: u32,
    pub buffer_px: f64,
    /// the buffer of each zoom 0 to max_zoom in px (crate::buffer::buffers_px: from the style's strokes; `buffer_px` where a stroke's
    /// width cannot be bounded)
    pub buffers: Vec<f64>,
    /// the properties that the drawing reads (props::drawn), with the caller's `keep`
    pub read: HashSet<String>,
    /// the properties that the layers on each source read (props::source_reads)
    pub source_reads: HashMap<String, HashSet<String>>,
    /// the fields of the popup and tooltip, and the caller's `keep`: what a base-map layer keeps besides its layers' reads
    pub shown: HashSet<String>,
    /// the base-map layers (`BASE_LAYERS`): a layer outside it and outside the roads, pieces and slots keeps all its properties
    pub base: HashSet<String>,
    /// the pieces' own columns: the class, lvl, the metre width and the class filter
    pub pieces: HashSet<String>,
    /// render(tiles=True)'s page: the columns of the roads and the pieces (tile_keep)
    pub exact: Option<HashSet<String>>,
    /// render(tiles=True)'s page: the sources in the tiles (tile_layers; the page keeps the others inline)
    pub only: Option<Vec<String>>,
    /// the first zoom of the names and arrows (`slots`), which go whole into the tiles
    pub slots_from: u32,
    /// the pieces of a `simple` source wait for their properties until a tile shows them (`Tiles::add_waiting`; the level editor's map)
    pub wait: bool,
}

/// The tile settings and the column names that stage 1 writes into a saved style: `{"minzoom", "maxzoom", "buffer_px", "extent"}` and
/// `{"class", "filter", "width"}`.
pub const TILES: &str = "roadstyle:tiles";
/// The size of a vector tile on the screen (MapLibre's tileSize of a vector source), in px.
pub const TILE_PX: f64 = 512.0;
pub const COLUMNS: &str = "roadstyle:columns";

impl TileOptions {
    /// The rules of a style: `tiles` the zoom settings (the look's config.tiles, or the style's `roadstyle:tiles`), `columns` the column
    /// names (`roadstyle:columns`), `keep` the caller's columns.
    pub fn new(layers: &[Value], metadata: &Value, tiles: &Value, columns: &Value, keep: &[String]) -> Result<TileOptions, Error> {
        let num = |k: &str| tiles[k].as_f64().ok_or_else(|| Error::Options(format!("tiles.{k} is not a number")));
        if num("extent")? != crate::EXTENT {
            return Err(Error::Options(format!("tiles.extent is {}, the tiles are made with {}", num("extent")?, crate::EXTENT)));
        }
        crate::check_zooms(num("minzoom")?, num("maxzoom")?)?;
        let col = |k: &str| columns[k].as_str().filter(|c| !c.is_empty()).map(String::from);
        let pieces = [col("class").unwrap_or_else(|| "highway".into()), "lvl".into()].into_iter().chain(col("width")).chain(col("filter")).collect();
        let slots_from = layers.iter().filter(|l| l["source"] == "slots").map(|l| l["minzoom"].as_f64().unwrap_or(0.0) as u32).min().unwrap_or(0);
        let (min_zoom, max_zoom, buffer_px) = (num("minzoom")? as u32, num("maxzoom")? as u32, num("buffer_px")?);
        let buffers = crate::buffer::buffers_px(layers, max_zoom, crate::buffer::LIVE_WIDTH_MAX, buffer_px);
        let source_reads = layers.iter().filter_map(|l| l["source"].as_str())
            .map(|k| (k.to_string(), roadstyle_model::props::source_reads(layers, k))).collect();
        let base = metadata[roadstyle_model::props::BASE_LAYERS].as_array().into_iter().flatten().filter_map(Value::as_str).map(String::from).collect();
        let shown = roadstyle_model::props::interaction_fields(metadata).into_iter().chain(keep.iter().cloned()).collect();
        Ok(TileOptions { min_zoom, max_zoom, buffer_px, buffers, read: roadstyle_model::props::drawn(layers, metadata, keep), source_reads, shown, base,
                         pieces, exact: None, only: None, slots_from, wait: false })
    }

    /// The rules of a saved style (stage 1's style.json).
    pub fn from_style(style: &Value, keep: &[String]) -> Result<TileOptions, Error> {
        let layers = style["layers"].as_array().map(Vec::as_slice).unwrap_or_default();
        let m = &style["metadata"];
        if m[TILES].is_null() {
            return Err(Error::Options(format!("the style has no {TILES}: give the tile settings")));
        }
        TileOptions::new(layers, m, &m[TILES], &m[COLUMNS], keep)
    }

    /// The empty tiles of these rules: their zooms, and the buffer of each zoom (`buffers`) as tile units (MapLibre draws a vector
    /// tile at 512 px, so a pixel is EXTENT / 512 units). A road whose line is out of a tile but whose stroke reaches into it is then in
    /// that tile: each tile is drawn only inside its own edges, and with a buffer of 80 units (10 px) a primary road near a tile edge
    /// lost its casing in the next tile from the tiles' last zoom on (Burnaby, z19.6, 2026-10-27).
    pub fn tiles(&self) -> Result<crate::Tiles, Error> {
        crate::Tiles::with_buffers(self.min_zoom, self.max_zoom, self.buffers.iter().map(|b| b * crate::EXTENT / TILE_PX).collect())
    }

    /// The source goes into the tiles.
    pub fn wants(&self, name: &str) -> bool {
        self.only.as_ref().is_none_or(|o| o.iter().any(|n| n == name))
    }

    /// The properties of the source `name` in the tiles (one set for each tile layer: a property outside it is not in any piece), whether
    /// it goes whole (unclipped), and its first zoom. `props`: every property of a GeoJSON source's features (another source keeps
    /// them all: render's export, keep=None).
    pub fn rule(&self, name: &str, props: impl FnOnce() -> HashSet<String>) -> (HashSet<String>, bool, u32) {
        use roadstyle_model::mark::{filter_keys, page_reads, Kind, Mark};
        let reads = |k: &str| self.source_reads.get(k).cloned().unwrap_or_default();
        match name {
            "roads" => (self.exact_or(&self.read), false, 0),
            "simple" => (self.exact_or(&self.pieces).into_iter().chain(reads(name)).chain(page_reads(Kind::Pieces)).collect(), false, 0),
            // the arrows' and names' filters take the twin from `__rs_edge2` (filter.js)
            "slots" => (reads(name).into_iter().chain(page_reads(Kind::Slots)).chain(filter_keys().map(String::from)).chain([Mark::Edge2.name().into()]).collect(), true, self.slots_from),
            _ if self.base.contains(name) => (self.base_keys(name), false, 0),
            _ => (self.read.iter().cloned().chain(props()).collect(), false, 0),
        }
    }

    /// `exact` (the given columns) with the marks that the drawing reads, else `others`.
    fn exact_or(&self, others: &HashSet<String>) -> HashSet<String> {
        match &self.exact {
            Some(e) => e.iter().chain(self.read.iter().filter(|k| k.starts_with(roadstyle_model::mark::PREFIX))).cloned().collect(),
            None => others.clone(),
        }
    }

    /// The properties of a base-map layer `name` in the tiles: those that its layers read, the popup's and the caller's.
    fn base_keys(&self, name: &str) -> HashSet<String> {
        self.source_reads.get(name).into_iter().flatten().chain(&self.shown).cloned().collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn a_base_map_layer_keeps_what_its_layers_and_the_popup_read() {
        let layers = [json!({"id": "b", "source": "ov4", "paint": {"fill-extrusion-height": ["get", "height"], "fill-extrusion-base": ["get", "base"]}}),
                      json!({"id": "o", "source": "ov5", "paint": {"fill-color": ["get", "kind"]}})];
        let tiles = json!({"minzoom": 0, "maxzoom": 15, "buffer_px": 10, "extent": crate::EXTENT});
        let o = TileOptions::new(&layers, &json!({"roadstyle:base": ["ov4", "ov5"]}), &tiles, &Value::Null, &[]).unwrap();
        let want = |k: &[&str]| k.iter().map(|s| s.to_string()).collect::<HashSet<_>>();
        assert_eq!(o.rule("ov4", Default::default).0, want(&["height", "base"]), "no osm_id, kind or name");
        assert_eq!(o.rule("ov5", Default::default).0, want(&["kind"]));
    }
}
