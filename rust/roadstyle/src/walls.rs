//! The 3D walls by type as a tile layer (dashboard/walls.js, docs/design/memory_budget.md): the page's walls of its buildings become
//! strips and roof slabs, cut into tiles by the one tile rule (`roadstyle-tiles`), so that the map holds only the tiles in view. The map
//! worker cuts them only when the page asks (`LiveTiles::set_walls`, when "Walls by type" is on).
//!
//! The input is the GeoJSON FeatureCollection of `rsSetWalls`: a LineString is one wall `{type, height, base, azimuth}` (azimuth: the
//! compass direction of the wall's outward normal); a Polygon or a MultiPolygon is the roof of a building `{height}`. A wall is a strip of
//! `WALL_M` along the outer side of its line, longer by `WALL_M` at each end, from the base to `ROOF_M` over the height; a roof is a slab
//! of `ROOF_M` on the height. walls.js makes the same strips for a page that gives the walls as GeoJSON.

use crate::tiles::{TileFormat, Tiles};
use serde::Deserialize;
use serde_json::{json, Value};

/// The width of a wall strip, and the thickness of a roof slab, in metres.
pub const WALL_M: f64 = 0.4;
pub const ROOF_M: f64 = 0.25;
/// The tile source and its one tile layer.
pub const SOURCE: &str = "walls";
/// The first zoom of the wall tiles: a strip of 0.4 m is less than a tile unit below it.
pub const MIN_ZOOM: u32 = 14;
/// The buffer round a tile, in tile units: a polygon cut at the tile's edge has its cut edge outside the tile, where the map draws no wall.
const BUFFER: f64 = 64.0;
const M_DEG: f64 = 111_319.49;

#[derive(Deserialize)]
struct Walls {
    features: Vec<Wall>,
}

#[derive(Deserialize)]
struct Wall {
    geometry: Option<Geometry>,
    #[serde(default)]
    properties: Props,
}

#[derive(Deserialize)]
struct Geometry {
    #[serde(rename = "type")]
    kind: String,
    coordinates: Coords,
}

#[derive(Deserialize)]
#[serde(untagged)]
enum Coords {
    Line(Vec<Vec<f64>>),
    Polygon(Vec<Vec<Vec<f64>>>),
    Polygons(Vec<Vec<Vec<Vec<f64>>>>),
}

#[derive(Deserialize, Default)]
struct Props {
    #[serde(rename = "type")]
    kind: Option<String>,
    height: Option<f64>,
    base: Option<f64>,
    azimuth: Option<f64>,
}

type Ring = Vec<[f64; 2]>;
/// A strip or a roof as the tiles take it: its polygons and its keys `t`, `b`, `h`.
type Piece = (Vec<Vec<Ring>>, [(&'static str, Value); 3]);

/// A wall's line as a strip on its outer side (from the first to the last point), as one ring.
fn strip(c: &[Vec<f64>], azimuth: f64) -> Option<Ring> {
    let (a, b) = (c.first()?, c.last()?);
    let (a, b) = ([*a.first()?, *a.get(1)?], [*b.first()?, *b.get(1)?]);
    let k = a[1].to_radians().cos();
    let az = azimuth.to_radians();
    let (ox, oy) = (az.sin() * WALL_M / (M_DEG * k), az.cos() * WALL_M / M_DEG);          // outward, in degrees
    let (dx, dy) = ((b[0] - a[0]) * k, b[1] - a[1]);
    let n = match dx.hypot(dy) { n if n > 0.0 => n, _ => 1.0 };
    let (ex, ey) = (dx / n * WALL_M / (M_DEG * k), dy / n * WALL_M / M_DEG);                // along the wall, in degrees
    let (a0, b0) = ([a[0] - ex, a[1] - ey], [b[0] + ex, b[1] + ey]);
    Some(vec![a0, b0, [b0[0] + ox, b0[1] + oy], [a0[0] + ox, a0[1] + oy], a0])
}

fn ring(r: &[Vec<f64>]) -> Ring {
    r.iter().filter(|p| p.len() >= 2).map(|p| [p[0], p[1]]).collect()
}

/// The tiles of the walls `fc` (the GeoJSON text of `rsSetWalls`), zooms `MIN_ZOOM` to `max_zoom`, in the format `format`: one layer
/// `walls` whose features have `t` (the wall's type, or `roof`), `b` (the base) and `h` (the top), in metres. A feature with no geometry
/// is left out. Returns the tiles and the number of features.
pub fn wall_tiles(fc: &[u8], format: TileFormat, max_zoom: u32) -> Result<(Tiles, usize), crate::Error> {
    let walls: Walls = serde_json::from_slice(fc).map_err(|e| crate::Error::Options(format!("the walls are not a GeoJSON FeatureCollection: {e}")))?;
    let mut feats: Vec<Piece> = Vec::with_capacity(walls.features.len());
    for w in &walls.features {
        let Some(g) = &w.geometry else { continue };
        let p = &w.properties;
        let height = p.height.unwrap_or(0.0);
        let (polys, t, b) = match (g.kind.as_str(), &g.coordinates) {
            ("LineString", Coords::Line(c)) => match strip(c, p.azimuth.unwrap_or(0.0)) {
                Some(r) => (vec![vec![r]], p.kind.clone().map(Value::from).unwrap_or(Value::Null), p.base.unwrap_or(0.0)),
                None => continue,
            },
            ("Polygon", Coords::Polygon(rs)) => (vec![rs.iter().map(|r| ring(r)).collect()], "roof".into(), height),
            ("MultiPolygon", Coords::Polygons(ps)) => (ps.iter().map(|rs| rs.iter().map(|r| ring(r)).collect()).collect(), "roof".into(), height),
            (k, _) => return Err(crate::Error::Options(format!("a wall is a LineString and a roof a Polygon or a MultiPolygon, not a {k}"))),
        };
        feats.push((polys, [("t", t), ("b", b.into()), ("h", (height + ROOF_M).into())]));
    }
    drop(walls);
    let n = feats.len();
    let mut tiles = Tiles::new(MIN_ZOOM.min(max_zoom), max_zoom, BUFFER)?;
    tiles.format = format;
    let keep = ["t", "b", "h"].map(String::from).into_iter().collect();
    tiles.add_polygons(SOURCE, feats.into_iter().map(|(g, p)| (g, p.into_iter())), &keep, false, 0);
    Ok((tiles, n))
}

/// The vector source of the wall tiles at `prefix` (the roads' prefix: `<prefix>walls/{z}/{x}/{y}`), for MapLibre.
pub fn wall_source(prefix: &str, format: TileFormat, max_zoom: u32) -> Value {
    let mut s = json!({"type": "vector", "tiles": [format!("{prefix}{SOURCE}/{{z}}/{{x}}/{{y}}")], "minzoom": MIN_ZOOM.min(max_zoom), "maxzoom": max_zoom});
    format.set_encoding(&mut s);
    s
}

#[cfg(test)]
mod tests {
    use super::*;

    const WALLS: &str = r#"{"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"type": "front", "height": 12, "base": 0, "azimuth": 90},
         "geometry": {"type": "LineString", "coordinates": [[7.4200, 43.7300], [7.4200, 43.7302]]}},
        {"type": "Feature", "properties": {"height": 12},
         "geometry": {"type": "Polygon", "coordinates": [[[7.4195, 43.7300], [7.4200, 43.7300], [7.4200, 43.7302], [7.4195, 43.7302], [7.4195, 43.7300]]]}},
        {"type": "Feature", "properties": {}, "geometry": null}]}"#;

    #[test]
    fn a_wall_is_a_strip_on_its_outer_side() {
        // a wall to the north, its outer side to the east: the strip is WALL_M wide to the east and WALL_M longer at each end
        let r = strip(&[vec![0.0, 0.0], vec![0.0, 0.001]], 90.0).unwrap();
        let m = |d: f64| d * M_DEG;
        assert!((m(r[0][1]) + WALL_M).abs() < 1e-9 && (m(r[1][1]) - (m(0.001) + WALL_M)).abs() < 1e-6, "{r:?}");
        assert!((m(r[2][0]) - WALL_M).abs() < 1e-9 && r[0][0].abs() < 1e-15 && r[4] == r[0], "{r:?}");
    }

    #[test]
    fn the_walls_are_one_tile_layer_from_min_zoom() {
        let (t, n) = wall_tiles(WALLS.as_bytes(), TileFormat::Mvt, 16).unwrap();
        assert_eq!(n, 2, "the feature with no geometry is left out");
        assert_eq!(t.layer_names(), vec![SOURCE.to_string()]);
        assert_eq!(t.props(SOURCE, 0), r#"{"t":"front","b":0.0,"h":12.25}"#);
        assert_eq!(t.props(SOURCE, 1), r#"{"t":"roof","b":12.0,"h":12.25}"#);
        // Monaco's tile of zoom 16 has the walls; zoom 13 has no tile
        let (x, y) = (34118, 23898);      // lon 7.42, lat 43.7301
        assert!(!t.tile(16, x, y).is_empty() && t.tile(13, x >> 3, y >> 3).is_empty());
        assert!(!wall_tiles(WALLS.as_bytes(), TileFormat::Mlt, 16).unwrap().0.tile_in(TileFormat::Mlt, 16, x, y).unwrap().is_empty());
        assert!(wall_tiles(br#"{"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [7.4, 43.7]}}]}"#,
                           TileFormat::Mvt, 16).is_err(), "a point is not a wall");
    }

    #[test]
    fn the_source_has_the_roads_prefix() {
        let s = wall_source("rs://3/", TileFormat::Mlt, 16);
        assert_eq!(s["tiles"][0], "rs://3/walls/{z}/{x}/{y}");
        assert_eq!((s["minzoom"].as_u64(), s["maxzoom"].as_u64(), s["encoding"].as_str()), (Some(14), Some(16), Some("mlt")));
    }
}
