//! roadstyle-camera: the road surface under a vehicle, and (in later phases) the obstacles and the follow camera.
//! docs/design/vehicles_spec.md, section 8.
//!
//! P2 step 1, the ground: the height of the drawn terrain under a vehicle, and its pitch and roll from the heights under its front,
//! back, left and right. The ground comes from the host (a roadstyle page asks MapLibre's terrain, which includes the exaggeration),
//! one grid point at a time; the grid keeps each answer, so only new points cross to the host.

mod roads;
pub use roads::{GroundAt, LineOf, RoadHeights};

use roadstyle_sim::geo::{delta_m, offset};
use std::collections::HashMap;

/// The ground on a square grid of `cell_m` metres around an origin, filled on demand from the host's ground function.
pub struct GroundGrid {
    origin: [f64; 2],
    cell_m: f64,
    heights: HashMap<(i32, i32), f32>,
}

/// A vehicle's height and tilt: `z` the ground under its middle (m above sea level, times the map's exaggeration), `pitch` (radians,
/// + = the front up) and `roll` (radians, + = the right side up).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Pose {
    pub z: f64,
    pub pitch: f64,
    pub roll: f64,
}

impl GroundGrid {
    pub fn new(origin: [f64; 2], cell_m: f64) -> GroundGrid {
        GroundGrid { origin, cell_m, heights: HashMap::new() }
    }

    /// Forgets every height: the map's terrain changed (on, off, another exaggeration).
    pub fn clear(&mut self) {
        self.heights.clear();
    }

    /// The number of grid points known.
    pub fn len(&self) -> usize {
        self.heights.len()
    }

    pub fn is_empty(&self) -> bool {
        self.heights.is_empty()
    }

    fn point(&mut self, i: i32, j: i32, sample: &mut impl FnMut(f64, f64) -> Option<f64>) -> Option<f64> {
        if let Some(&h) = self.heights.get(&(i, j)) {
            return Some(h as f64);
        }
        let p = offset(self.origin, i as f64 * self.cell_m, j as f64 * self.cell_m);
        // a height that the host does not know yet (a terrain tile that has not come) is not kept: it is asked again next time
        let h = sample(p[0], p[1]).filter(|h| h.is_finite())?;
        self.heights.insert((i, j), h as f32);
        Some(h)
    }

    /// The ground at lon/lat `p`: bilinear between the four grid points around it. None while one of them is not known.
    pub fn at(&mut self, p: [f64; 2], sample: &mut impl FnMut(f64, f64) -> Option<f64>) -> Option<f64> {
        let d = delta_m(self.origin, p);
        let (x, y) = (d[0] / self.cell_m, d[1] / self.cell_m);
        let (i, j) = (x.floor() as i32, y.floor() as i32);
        let (u, v) = (x - i as f64, y - j as f64);
        let h00 = self.point(i, j, sample)?;
        let h10 = self.point(i + 1, j, sample)?;
        let h01 = self.point(i, j + 1, sample)?;
        let h11 = self.point(i + 1, j + 1, sample)?;
        Some(h00 * (1.0 - u) * (1.0 - v) + h10 * u * (1.0 - v) + h01 * (1.0 - u) * v + h11 * u * v)
    }

    /// The pose of a vehicle whose middle is at `mid`, heading `heading_deg` (0 = north, clockwise), `length` and `width` m.
    pub fn pose(&mut self, mid: [f64; 2], heading_deg: f64, length: f64, width: f64,
                sample: &mut impl FnMut(f64, f64) -> Option<f64>) -> Option<Pose> {
        let h = heading_deg.to_radians();
        let (fe, fn_) = (h.sin(), h.cos());          // forward, in east and north
        let (re, rn) = (h.cos(), -h.sin());          // right
        let at = |s: &mut Self, k: f64, e: f64, n: f64, sample: &mut dyn FnMut(f64, f64) -> Option<f64>| {
            s.at(offset(mid, e * k, n * k), &mut |a, b| sample(a, b))
        };
        let z = self.at(mid, sample)?;
        let front = at(self, length * 0.5, fe, fn_, sample)?;
        let back = at(self, -length * 0.5, fe, fn_, sample)?;
        let right = at(self, width * 0.5, re, rn, sample)?;
        let left = at(self, -width * 0.5, re, rn, sample)?;
        Some(Pose { z, pitch: (front - back).atan2(length), roll: (right - left).atan2(width) })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use roadstyle_sim::geo::M_PER_DEG;

    const O: [f64; 2] = [7.42, 43.73];

    /// A plane: 10 m + 0.10 per metre east + 0.05 per metre north.
    fn plane(lon: f64, lat: f64) -> Option<f64> {
        let d = delta_m(O, [lon, lat]);
        Some(10.0 + 0.10 * d[0] + 0.05 * d[1])
    }

    #[test]
    fn bilinear_is_exact_on_a_plane() {
        let mut g = GroundGrid::new(O, 5.0);
        for (e, n) in [(0.0, 0.0), (2.5, 1.0), (-7.3, 12.9), (101.0, -33.3)] {
            let p = offset(O, e, n);
            let h = g.at(p, &mut plane).unwrap();
            assert!((h - plane(p[0], p[1]).unwrap()).abs() < 1e-4, "{e} {n}: {h}");
        }
    }

    #[test]
    fn pitch_and_roll_on_a_slope() {
        let mut g = GroundGrid::new(O, 5.0);
        // heading east: the front climbs 0.10 per metre, the right (south) side is 0.05 per metre lower
        let p = g.pose(offset(O, 20.0, 20.0), 90.0, 5.0, 1.8, &mut plane).unwrap();
        assert!((p.pitch - 0.10f64.atan()).abs() < 1e-4, "{p:?}");
        assert!((p.roll - (-0.05f64).atan()).abs() < 1e-4, "{p:?}");
        // heading north: the front climbs 0.05, the right (east) side is 0.10 higher
        let p = g.pose(offset(O, 20.0, 20.0), 0.0, 5.0, 1.8, &mut plane).unwrap();
        assert!((p.pitch - 0.05f64.atan()).abs() < 1e-4 && (p.roll - 0.10f64.atan()).abs() < 1e-4, "{p:?}");
    }

    #[test]
    fn unknown_ground_is_asked_again_and_not_kept() {
        let mut g = GroundGrid::new(O, 5.0);
        let mut asked = 0;
        assert!(g.at(O, &mut |_, _| { asked += 1; None }).is_none());
        assert_eq!(g.len(), 0, "an unknown height is not kept");
        assert!(g.at(O, &mut |_, _| Some(f64::NAN)).is_none(), "NaN is unknown");
        let mut n = 0;
        assert_eq!(g.at(offset(O, 1.0, 1.0), &mut |_, _| { n += 1; Some(7.0) }), Some(7.0));
        assert_eq!(n, 4);
        assert_eq!(g.at(offset(O, 2.0, 2.0), &mut |_, _| { n += 1; Some(9.0) }), Some(7.0), "the same cell: no new question");
        assert_eq!(n, 4);
        g.clear();
        assert!(g.is_empty());
        let _ = M_PER_DEG;
    }
}
