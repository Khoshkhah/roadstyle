//! Stage 2's rules (docs/rust/architecture.md, "The three stages and the one call"): which properties of each source go into the
//! tiles, from which zoom, with which zooms and buffer. They come from the style alone (its layers, its `roadstyle:interaction`, and
//! the `roadstyle:tiles` and `roadstyle:columns` that stage 1 writes into a saved style), so stage 2 needs neither the roads nor the
//! look. The rules are tiles.py's (tile_props, the slots whole from their first zoom) and render(tiles=True)'s page's.

use crate::Error;
use serde_json::Value;
use std::collections::HashSet;

#[derive(Clone, Debug)]
pub struct TileOptions {
    pub min_zoom: u32,
    pub max_zoom: u32,
    pub buffer_px: f64,
    /// the properties that the drawing reads (props::drawn), with the caller's `keep`; every `__rs_*` one goes too
    pub read: HashSet<String>,
    /// the pieces' own columns: the class, lvl, the metre width and the class filter
    pub pieces: HashSet<String>,
    /// render(tiles=True)'s page: the columns of the roads and the pieces (tile_keep; every __rs_* goes too)
    pub exact: Option<HashSet<String>>,
    /// render(tiles=True)'s page: the sources in the tiles (tile_layers; the page keeps the others inline)
    pub only: Option<Vec<String>>,
    /// the first zoom of the names and arrows (`slots`), which go whole into the tiles (tiles.py: 14, their symbols' minzoom)
    pub slots_from: u32,
}

/// The tile settings and the column names that stage 1 writes into a saved style: `{"minzoom", "maxzoom", "buffer_px", "extent"}` and
/// `{"class", "filter", "width"}`.
pub const TILES: &str = "roadstyle:tiles";
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
        Ok(TileOptions { min_zoom: num("minzoom")? as u32, max_zoom: num("maxzoom")? as u32, buffer_px: num("buffer_px")?,
                         read: roadstyle_model::props::drawn(layers, metadata, keep), pieces, exact: None, only: None, slots_from })
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

    /// The source goes into the tiles.
    pub fn wants(&self, name: &str) -> bool {
        self.only.as_ref().is_none_or(|o| o.iter().any(|n| n == name))
    }

    /// The properties of the source `name` in the tiles, whether it goes whole, and its first zoom. `props`: every property of its
    /// features (another GeoJSON source keeps them all: render's export, keep=None).
    pub fn rule(&self, name: &str, props: impl FnOnce() -> HashSet<String>) -> (HashSet<String>, bool, u32) {
        match name {
            "roads" => (self.exact.clone().unwrap_or_else(|| self.read.clone()), false, 0),
            "simple" => (self.exact.clone().unwrap_or_else(|| self.pieces.clone()), false, 0),
            "slots" => (self.read.clone(), true, self.slots_from),
            _ => (self.read.iter().cloned().chain(props()).collect(), false, 0),
        }
    }
}
