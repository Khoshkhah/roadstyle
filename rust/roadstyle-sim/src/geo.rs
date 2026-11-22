//! Lon/lat helpers for short distances: a local flat earth at the latitude of each segment. Over one lane (metres to a
//! few hundred metres) the error is far under a centimetre.

/// Metres per degree of latitude (mean earth radius 6371008.8 m).
pub const M_PER_DEG: f64 = 6371008.8 * std::f64::consts::PI / 180.0;

/// The vector from a to b in metres (east, north).
pub fn delta_m(a: [f64; 2], b: [f64; 2]) -> [f64; 2] {
    let k = ((a[1] + b[1]) * 0.5).to_radians().cos();
    [(b[0] - a[0]) * M_PER_DEG * k, (b[1] - a[1]) * M_PER_DEG]
}

pub fn dist_m(a: [f64; 2], b: [f64; 2]) -> f64 {
    let d = delta_m(a, b);
    d[0].hypot(d[1])
}

/// The point that is (east, north) metres from p.
pub fn offset(p: [f64; 2], east: f64, north: f64) -> [f64; 2] {
    [p[0] + east / (M_PER_DEG * p[1].to_radians().cos()), p[1] + north / M_PER_DEG]
}

/// The heading from a to b in degrees: 0 = north, clockwise (SUMO's `angle`).
pub fn heading_deg(a: [f64; 2], b: [f64; 2]) -> f64 {
    let d = delta_m(a, b);
    d[0].atan2(d[1]).to_degrees().rem_euclid(360.0)
}

/// The signed shortest turn from heading a to heading b, in degrees (-180..180).
pub fn turn_deg(a: f64, b: f64) -> f64 {
    (b - a + 540.0).rem_euclid(360.0) - 180.0
}

/// A polyline with the metres from its start at each point.
#[derive(Debug, Clone)]
pub struct Line {
    pub pts: Vec<[f64; 2]>,
    pub cum: Vec<f64>,
}

impl Line {
    pub fn new(pts: Vec<[f64; 2]>) -> Line {
        let mut cum = Vec::with_capacity(pts.len());
        let mut s = 0.0;
        for (i, p) in pts.iter().enumerate() {
            if i > 0 {
                s += dist_m(pts[i - 1], *p);
            }
            cum.push(s);
        }
        Line { pts, cum }
    }

    pub fn len(&self) -> f64 {
        *self.cum.last().unwrap_or(&0.0)
    }

    /// The point and the heading (degrees) at s metres; s is clamped to the line. A line of one point has heading 0.
    pub fn at(&self, s: f64) -> ([f64; 2], f64) {
        let n = self.pts.len();
        if n == 1 {
            return (self.pts[0], 0.0);
        }
        let s = s.clamp(0.0, self.len());
        let i = match self.cum.binary_search_by(|c| c.partial_cmp(&s).unwrap()) {
            Ok(i) => i.min(n - 2),
            Err(i) => (i.max(1) - 1).min(n - 2),
        };
        let (a, b) = (self.pts[i], self.pts[i + 1]);
        let seg = self.cum[i + 1] - self.cum[i];
        let u = if seg > 0.0 { (s - self.cum[i]) / seg } else { 0.0 };
        ([a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u], heading_deg(a, b))
    }
}

/// The line `pts` moved `d` metres to its right (left for a negative `d`): each point along the mean of the normals of its two
/// segments, by d / cos(half the turn), at most 2 d (a sharp corner).
pub fn offset_line(pts: &[[f64; 2]], d: f64) -> Vec<[f64; 2]> {
    let n = pts.len();
    if n < 2 {
        return pts.to_vec();
    }
    let unit_right = |a: [f64; 2], b: [f64; 2]| {
        let v = delta_m(a, b);
        let l = v[0].hypot(v[1]).max(1e-9);
        [v[1] / l, -v[0] / l]
    };
    (0..n)
        .map(|i| {
            let r0 = if i > 0 { Some(unit_right(pts[i - 1], pts[i])) } else { None };
            let r1 = if i + 1 < n { Some(unit_right(pts[i], pts[i + 1])) } else { None };
            let r = match (r0, r1) {
                (Some(a), Some(b)) => {
                    let m = [a[0] + b[0], a[1] + b[1]];
                    let l = m[0].hypot(m[1]).max(1e-9);
                    let cos_half = (l / 2.0).max(0.5);
                    [m[0] / l / cos_half, m[1] / l / cos_half]
                }
                (Some(a), None) | (None, Some(a)) => a,
                (None, None) => [0.0, 0.0],
            };
            offset(pts[i], r[0] * d, r[1] * d)
        })
        .collect()
}

#[cfg(test)]
mod offset_tests {
    use super::*;

    #[test]
    fn a_line_moved_right_keeps_its_distance() {
        // a line to the east, then to the north: 1.5 m to its right is south of the first segment and east of the second
        let a = [7.4, 43.7];
        let b = offset(a, 100.0, 0.0);
        let c = offset(b, 0.0, 100.0);
        let o = offset_line(&[a, b, c], 1.5);
        assert!((delta_m(a, o[0])[1] + 1.5).abs() < 1e-6);
        assert!((delta_m(c, o[2])[0] - 1.5).abs() < 1e-6);
        let corner = delta_m(b, o[1]);
        assert!((corner[0] - 1.5).abs() < 1e-6 && (corner[1] + 1.5).abs() < 1e-6, "{corner:?}");
    }
}
