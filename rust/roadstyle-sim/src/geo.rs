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

    /// The metres from the start to the point of the line nearest to `p`.
    pub fn project(&self, p: [f64; 2]) -> f64 {
        let mut best = (f64::INFINITY, 0.0);
        for i in 0..self.pts.len().saturating_sub(1) {
            let (a, b) = (delta_m(p, self.pts[i]), delta_m(p, self.pts[i + 1]));
            let (dx, dy) = (b[0] - a[0], b[1] - a[1]);
            let l2 = dx * dx + dy * dy;
            let u = if l2 > 0.0 { (-(a[0] * dx + a[1] * dy) / l2).clamp(0.0, 1.0) } else { 0.0 };
            let d = (a[0] + u * dx).hypot(a[1] + u * dy);
            if d < best.0 {
                best = (d, self.cum[i] + u * (self.cum[i + 1] - self.cum[i]));
            }
        }
        best.1
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
