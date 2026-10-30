//! The format of a tile: Mapbox Vector Tile (MVT, the default) or MapLibre Tile (MLT). The one option (`stage::TileOptions::format`).

use crate::Error;
use serde_json::Value;

/// The one format of the tiles of every path (a page's archive, the map worker, a server's files): MLT. MVT is the cut itself, and a caller asks for it with `"mvt"`.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash)]
pub enum TileFormat {
    Mvt,
    #[default]
    Mlt,
}

impl TileFormat {
    /// `"mvt"` or `"mlt"`, as `name` gives them.
    pub fn parse(s: &str) -> Result<TileFormat, Error> {
        match s {
            "mvt" => Ok(TileFormat::Mvt),
            "mlt" => Ok(TileFormat::Mlt),
            _ => Err(Error::Options(format!("the tile format is {s:?}: give \"mvt\" or \"mlt\""))),
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            TileFormat::Mvt => "mvt",
            TileFormat::Mlt => "mlt",
        }
    }

    /// The file extension of a tile in an XYZ folder.
    pub fn extension(self) -> &'static str {
        match self {
            TileFormat::Mvt => ".pbf",
            TileFormat::Mlt => ".mlt",
        }
    }

    /// The `encoding` of the style's vector source (MapLibre GL JS 5.12 or later); MVT is the source's default and has none.
    pub fn encoding(self) -> Option<&'static str> {
        (self == TileFormat::Mlt).then_some("mlt")
    }

    /// The tile type of a PMTiles v3 header: 1 MVT, 6 MapLibre Vector Tile.
    pub fn pmtiles_type(self) -> u8 {
        match self {
            TileFormat::Mvt => 1,
            TileFormat::Mlt => 6,
        }
    }

    /// Set the `encoding` of a style's vector source to this format's (MVT: none).
    pub fn set_encoding(self, source: &mut Value) {
        match self.encoding() {
            Some(e) => source["encoding"] = e.into(),
            None => {
                source.as_object_mut().map(|o| o.remove("encoding"));
            }
        }
    }
}
