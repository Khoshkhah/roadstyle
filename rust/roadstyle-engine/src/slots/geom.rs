//! The slots' geometry (in lon / lat, or in metres for the chain).

use crate::simple::Pt;

/// The floor quotient and the modulo of two floats (the sign of the divisor), as `length // slot_m` and `length % slot_m` give them.
pub(super) fn floor_divmod(vx: f64, wx: f64) -> (f64, f64) {
    let mut m = vx % wx;
    let mut div = (vx - m) / wx;
    if m != 0.0 {
        if (wx < 0.0) != (m < 0.0) {
            m += wx;
            div -= 1.0;
        }
    } else {
        m = 0f64.copysign(wx);
    }
    let floordiv = if div != 0.0 {
        let f = div.floor();
        if div - f > 0.5 { f + 1.0 } else { f }
    } else {
        0f64.copysign(vx / wx)
    };
    (floordiv, m)
}

// --- geometry (in lon / lat, or in metres for the chain) ---

fn cross(o: Pt, a: Pt, b: Pt) -> f64 {
    (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
}

fn sign(v: f64) -> i8 {
    if v > 0.0 { 1 } else if v < 0.0 { -1 } else { 0 }
}

fn in_box(p: Pt, a: Pt, b: Pt) -> bool {
    p[0] >= a[0].min(b[0]) && p[0] <= a[0].max(b[0]) && p[1] >= a[1].min(b[1]) && p[1] <= a[1].max(b[1])
}

/// The points where two segments meet: none, one (a crossing or a touch) or the two ends of their common part (collinear).
pub(super) fn seg_meet(p1: Pt, p2: Pt, q1: Pt, q2: Pt) -> Vec<Pt> {
    if !(p1[0].min(p2[0]) <= q1[0].max(q2[0]) && q1[0].min(q2[0]) <= p1[0].max(p2[0])
        && p1[1].min(p2[1]) <= q1[1].max(q2[1]) && q1[1].min(q2[1]) <= p1[1].max(p2[1])) {
        return vec![];
    }
    let (o1, o2) = (sign(cross(p1, p2, q1)), sign(cross(p1, p2, q2)));
    let (o3, o4) = (sign(cross(q1, q2, p1)), sign(cross(q1, q2, p2)));
    if o1 == 0 && o2 == 0 && o3 == 0 && o4 == 0 {
        // collinear: the common part, along the longer axis of p
        let ax = if (p2[0] - p1[0]).abs() >= (p2[1] - p1[1]).abs() { 0 } else { 1 };
        let mut pts: Vec<Pt> = [p1, p2, q1, q2].into_iter()
            .filter(|&r| in_box(r, p1, p2) && in_box(r, q1, q2)).collect();
        pts.sort_by(|a, b| a[ax].total_cmp(&b[ax]));
        pts.dedup();
        return match pts.len() {
            0 => vec![],
            1 => pts,
            _ => vec![pts[0], pts[pts.len() - 1]],
        };
    }
    if o1 * o2 > 0 || o3 * o4 > 0 {
        return vec![];
    }
    // a touch at an end point: that point exactly
    for (o, r, a, b) in [(o1, q1, p1, p2), (o2, q2, p1, p2), (o3, p1, q1, q2), (o4, p2, q1, q2)] {
        if o == 0 && in_box(r, a, b) {
            return vec![r];
        }
    }
    let d = cross([0.0, 0.0], [p2[0] - p1[0], p2[1] - p1[1]], [q2[0] - q1[0], q2[1] - q1[1]]);
    if d == 0.0 {
        return vec![];
    }
    let t = cross([0.0, 0.0], [q1[0] - p1[0], q1[1] - p1[1]], [q2[0] - q1[0], q2[1] - q1[1]]) / d;
    vec![[p1[0] + t * (p2[0] - p1[0]), p1[1] + t * (p2[1] - p1[1])]]
}

fn dist(a: Pt, b: Pt) -> f64 {
    let (dx, dy) = (a[0] - b[0], a[1] - b[1]);
    (dx * dx + dy * dy).sqrt()
}

/// GEOS Distance::pointToSegment.
fn point_seg_dist(p: Pt, a: Pt, b: Pt) -> f64 {
    if a == b {
        return dist(p, a);
    }
    let len2 = (b[0] - a[0]) * (b[0] - a[0]) + (b[1] - a[1]) * (b[1] - a[1]);
    let r = ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / len2;
    if r <= 0.0 {
        return dist(p, a);
    }
    if r >= 1.0 {
        return dist(p, b);
    }
    let s = ((a[1] - p[1]) * (b[0] - a[0]) - (a[0] - p[0]) * (b[1] - a[1])) / len2;
    s.abs() * len2.sqrt()
}

pub(crate) fn point_line_dist(p: Pt, c: &[Pt]) -> f64 {
    c.windows(2).map(|w| point_seg_dist(p, w[0], w[1])).fold(f64::INFINITY, f64::min)
}

/// GEOS LengthIndexedLine::project (LengthIndexOfPoint): the length along `c` to the point of it nearest `p`; the first nearest segment
/// wins a tie; lengths are sums of segment lengths.
pub(super) fn project(c: &[Pt], p: Pt) -> f64 {
    let (mut best, mut at, mut start) = (f64::INFINITY, 0.0, 0.0);
    for w in c.windows(2) {
        let len = dist(w[0], w[1]);
        let d = point_seg_dist(p, w[0], w[1]);
        if d < best {
            best = d;
            let r = if w[0] == w[1] { 0.0 } else {    // LineSegment::projectionFactor
                ((p[0] - w[0][0]) * (w[1][0] - w[0][0]) + (p[1] - w[0][1]) * (w[1][1] - w[0][1]))
                    / ((w[1][0] - w[0][0]) * (w[1][0] - w[0][0]) + (w[1][1] - w[0][1]) * (w[1][1] - w[0][1]))
            };
            at = if r <= 0.0 { start } else if r <= 1.0 { start + r * len } else { start + len };
        }
        start += len;
    }
    at
}

pub(super) fn bbox(c: &[Pt]) -> ([f64; 2], [f64; 2]) {
    let mut lo = [f64::INFINITY; 2];
    let mut hi = [f64::NEG_INFINITY; 2];
    for p in c {
        for k in 0..2 {
            lo[k] = lo[k].min(p[k]);
            hi[k] = hi[k].max(p[k]);
        }
    }
    (lo, hi)
}