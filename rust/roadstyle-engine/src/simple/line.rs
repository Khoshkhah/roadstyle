//! A line in metres around its first point (numpy's flat projection and rounding).

use super::*;

/// np.round(x, d) for d > 0: rint(x * 10^d) / 10^d.
pub(crate) fn np_round(x: f64, scale: f64) -> f64 {
    (x * scale).round_ties_even() / scale
}

/// A line in metres from its first point (as _casing_parts and _halves project it), with its cumulative lengths.
pub(crate) struct Line {
    pub(crate) xy: Vec<Pt>,
    pub(crate) cum: Vec<f64>,
    pub(crate) lon0: f64,
    pub(crate) lat0: f64,
    pub(crate) kx: f64,
}

pub(crate) const KY: f64 = 111320.0;

impl Line {
    pub(crate) fn new(c: &[Pt]) -> Line {
        let (lon0, lat0) = (c[0][0], c[0][1]);
        let kx = 111320.0 * lat0.to_radians().cos();
        let xy: Vec<Pt> = c.iter().map(|p| [(p[0] - lon0) * kx, (p[1] - lat0) * KY]).collect();
        let mut cum = Vec::with_capacity(xy.len());
        let mut s = 0.0;
        cum.push(0.0);
        for w in xy.windows(2) {
            s += (w[1][0] - w[0][0]).hypot(w[1][1] - w[0][1]);
            cum.push(s);
        }
        Line { xy, cum, lon0, lat0, kx }
    }

    pub(crate) fn len(&self) -> f64 {
        self.cum[self.cum.len() - 1]
    }

    // np.searchsorted(cum, d, side="right") / side="left"
    pub(crate) fn right(&self, d: f64) -> usize {
        self.cum.partition_point(|&x| x <= d)
    }
    pub(crate) fn left(&self, d: f64) -> usize {
        self.cum.partition_point(|&x| x < d)
    }

    /// _at: the point at the distance d.
    pub(crate) fn at(&self, d: f64) -> Pt {
        let j = (self.right(d) as isize - 1).clamp(0, self.cum.len() as isize - 2) as usize;
        let w = self.cum[j + 1] - self.cum[j];
        let t = if w > 0.0 { (d - self.cum[j]) / w } else { 0.0 };
        let (p, q) = (self.xy[j], self.xy[j + 1]);
        [p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])]
    }

    /// _part: the cut points at a and b and the vertices between them.
    pub(crate) fn part(&self, a: f64, b: f64) -> Vec<Pt> {
        let mut out = vec![self.at(a)];
        let (i, j) = (self.right(a), self.left(b));
        if i < j {
            out.extend_from_slice(&self.xy[i..j]);
        }
        out.push(self.at(b));
        out
    }

    /// Back to lon / lat, rounded as numpy rounds (scale 1e7 or 1e8).
    pub(crate) fn lonlat(&self, pts: &[Pt], scale: f64) -> Vec<Pt> {
        pts.iter().map(|p| [np_round(p[0] / self.kx + self.lon0, scale), np_round(p[1] / KY + self.lat0, scale)]).collect()
    }
}

/// `__rs_s`: the key in KEY_UNITs and the edge's tie-breaker.
pub(crate) fn sort_key(key: f64, edge: i64) -> i64 {
    (key * KEY_UNIT).round() as i64 + edge
}

pub(crate) fn int(p: &Props, k: &str) -> i64 {
    p.get(k).and_then(Value::as_i64).unwrap_or(0)
}
