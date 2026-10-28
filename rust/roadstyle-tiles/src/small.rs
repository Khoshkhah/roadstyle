//! A flat layer's shapes at the pixel grid of the zoom (docs/design/tile_speed.md, "The tiles of the low zooms"). A flat layer is one that
//! only `fill` and `line` style layers draw (`Tiles::flat`): the base map's land, water and buildings. Below the last zoom its polygons
//! are cut to the tile and its buffer and simplified to `TOLERANCE`.

use super::*;

/// The distance that the simplification can move a polygon's outline: 1 tile unit, the step of the tile's grid and 1/8 px. A tile of
/// zoom z is drawn at the map zooms z to z + 1, so the move on the screen is up to 1/4 px at the end of that span. 2 units gave 15 % less
/// MapLibre time on Burnaby and 4 times more pixels that differ by more than a little (docs/design/tile_speed.md).
pub(crate) const TOLERANCE: f64 = 1.0;

/// A ring cut to the square [lo, hi]^2 and simplified (the closing edge counts, so no end point stays only for being the first).
pub(crate) fn ring(r: &[P], lo: f64, hi: f64) -> Vec<P> {
    let r = clip_ring(r, lo, hi);
    if r.len() < 4 {
        return r;
    }
    let closed: Vec<P> = r.iter().chain(&r[..1]).copied().collect();
    douglas_peucker_kept(&closed, TOLERANCE).into_iter().filter(|&i| (i as usize) < r.len()).map(|i| r[i as usize]).collect()
}
