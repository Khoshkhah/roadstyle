//! The plane geometry of the levels (metres): the UTM projection, distances, the clip of a line by circles, the crossing test and the
//! casing parts of a road. The geometry follows shapely and GEOS (a circle is a polygon of 32 sides) so the relations are the same.

use super::Pt;
use rstar::{RTreeObject, AABB};

/// The UTM zone of a point and the projection to it: the transverse Mercator series of Krüger (6th order, as PROJ).
struct Utm {
    lon0: f64,
    north: f64,
    a: f64,
    alpha: [f64; 6],
    c: f64,
}

impl Utm {
    fn new(lon: f64, lat: f64) -> Utm {
        let zone = (((lon + 180.0) / 6.0).floor() as i32).clamp(0, 59) + 1;
        let f = 1.0 / 298.257_223_563;
        let n = f / (2.0 - f);
        let (n2, n3) = (n * n, n * n * n);
        let (n4, n5, n6) = (n2 * n2, n2 * n3, n3 * n3);
        Utm {
            lon0: (zone as f64 * 6.0 - 183.0).to_radians(),
            north: if lat >= 0.0 { 0.0 } else { 10_000_000.0 },
            a: 6_378_137.0 / (1.0 + n) * (1.0 + n2 / 4.0 + n4 / 64.0 + n6 / 256.0),
            alpha: [
                n / 2.0 - 2.0 * n2 / 3.0 + 5.0 * n3 / 16.0 + 41.0 * n4 / 180.0 - 127.0 * n5 / 288.0
                    + 7891.0 * n6 / 37800.0,
                13.0 * n2 / 48.0 - 3.0 * n3 / 5.0 + 557.0 * n4 / 1440.0 + 281.0 * n5 / 630.0
                    - 1983433.0 * n6 / 1935360.0,
                61.0 * n3 / 240.0 - 103.0 * n4 / 140.0
                    + 15061.0 * n5 / 26880.0
                    + 167603.0 * n6 / 181440.0,
                49561.0 * n4 / 161280.0 - 179.0 * n5 / 168.0 + 6601661.0 * n6 / 7257600.0,
                34729.0 * n5 / 80640.0 - 3418889.0 * n6 / 1995840.0,
                212378941.0 * n6 / 319334400.0,
            ],
            c: 2.0 * n.sqrt() / (1.0 + n),
        }
    }

    fn project(&self, p: Pt) -> Pt {
        let (phi, lam) = (p.1.to_radians(), p.0.to_radians() - self.lon0);
        let s = phi.sin();
        let t = (s.atanh() - self.c * (self.c * s).atanh()).sinh();
        let xi = t.atan2(lam.cos());
        let eta = (lam.sin() / (1.0 + t * t).sqrt()).atanh();
        let (mut x, mut y) = (eta, xi);
        for (j, al) in self.alpha.iter().enumerate() {
            let k = 2.0 * (j + 1) as f64;
            x += al * (k * xi).cos() * (k * eta).sinh();
            y += al * (k * xi).sin() * (k * eta).cosh();
        }
        let k0 = 0.9996;
        (500_000.0 + k0 * self.a * x, self.north + k0 * self.a * y)
    }
}

/// The lines in metres, in the UTM zone of the center of their box (geopandas' `estimate_utm_crs`).
pub(crate) fn metres(lines: &[&[Pt]]) -> Vec<Vec<Pt>> {
    let (mut x0, mut y0, mut x1, mut y1) = (f64::MAX, f64::MAX, f64::MIN, f64::MIN);
    for p in lines.iter().flat_map(|l| l.iter()) {
        (x0, y0, x1, y1) = (x0.min(p.0), y0.min(p.1), x1.max(p.0), y1.max(p.1));
    }
    let utm = Utm::new((x0 + x1) / 2.0, (y0 + y1) / 2.0);
    lines
        .iter()
        .map(|l| l.iter().map(|&p| utm.project(p)).collect())
        .collect()
}

// ---- plane geometry (metres) ----

fn sub(a: Pt, b: Pt) -> Pt {
    (a.0 - b.0, a.1 - b.1)
}
fn cross(a: Pt, b: Pt) -> f64 {
    a.0 * b.1 - a.1 * b.0
}
fn dot(a: Pt, b: Pt) -> f64 {
    a.0 * b.0 + a.1 * b.1
}

fn point_seg(p: Pt, a: Pt, b: Pt) -> f64 {
    let ab = sub(b, a);
    let l = dot(ab, ab);
    let t = if l == 0.0 {
        0.0
    } else {
        (dot(sub(p, a), ab) / l).clamp(0.0, 1.0)
    };
    let q = (a.0 + t * ab.0, a.1 + t * ab.1);
    dot(sub(p, q), sub(p, q)).sqrt()
}

fn orient(a: Pt, b: Pt, c: Pt) -> f64 {
    cross(sub(b, a), sub(c, a))
}

fn on_seg(p: Pt, a: Pt, b: Pt) -> bool {
    p.0 >= a.0.min(b.0) && p.0 <= a.0.max(b.0) && p.1 >= a.1.min(b.1) && p.1 <= a.1.max(b.1)
}

fn segs_meet(a: Pt, b: Pt, c: Pt, d: Pt) -> bool {
    let (d1, d2, d3, d4) = (
        orient(c, d, a),
        orient(c, d, b),
        orient(a, b, c),
        orient(a, b, d),
    );
    if ((d1 > 0.0 && d2 < 0.0) || (d1 < 0.0 && d2 > 0.0))
        && ((d3 > 0.0 && d4 < 0.0) || (d3 < 0.0 && d4 > 0.0))
    {
        return true;
    }
    (d1 == 0.0 && on_seg(a, c, d))
        || (d2 == 0.0 && on_seg(b, c, d))
        || (d3 == 0.0 && on_seg(c, a, b))
        || (d4 == 0.0 && on_seg(d, a, b))
}

fn seg_seg(a: Pt, b: Pt, c: Pt, d: Pt) -> f64 {
    if segs_meet(a, b, c, d) {
        return 0.0;
    }
    point_seg(a, c, d)
        .min(point_seg(b, c, d))
        .min(point_seg(c, a, b))
        .min(point_seg(d, a, b))
}

/// The distance between two sets of lines.
pub(crate) fn distance(a: &[Vec<Pt>], b: &[Vec<Pt>]) -> f64 {
    let mut best = f64::INFINITY;
    for la in a {
        for lb in b {
            for sa in la.windows(2) {
                for sb in lb.windows(2) {
                    best = best.min(seg_seg(sa[0], sa[1], sb[0], sb[1]));
                }
            }
        }
    }
    best
}

/// GEOS's buffer of a point (8 segments for a quarter circle): a polygon of 32 sides, counterclockwise.
pub(crate) fn circle(p: Pt, r: f64) -> Vec<Pt> {
    let inc = 2.0 * std::f64::consts::PI / 32.0;
    (0..32)
        .map(|i| {
            let a = i as f64 * inc;
            (p.0 + r * a.cos(), p.1 + r * a.sin())
        })
        .collect()
}

/// The part `[t0, t1]` of the segment a-b inside a convex polygon (counterclockwise), or None (Cyrus-Beck).
fn clip(a: Pt, b: Pt, poly: &[Pt]) -> Option<(f64, f64)> {
    let (mut t0, mut t1) = (0.0f64, 1.0f64);
    let d = sub(b, a);
    for k in 0..poly.len() {
        let (p, q) = (poly[k], poly[(k + 1) % poly.len()]);
        let e = sub(q, p);
        // inside: cross(e, x - p) >= 0
        let num = cross(e, sub(a, p));
        let den = cross(e, d);
        if den == 0.0 {
            if num < 0.0 {
                return None;
            }
        } else {
            let t = -num / den;
            if den > 0.0 {
                t0 = t0.max(t);
            } else {
                t1 = t1.min(t);
            }
            if t0 > t1 {
                return None;
            }
        }
    }
    Some((t0, t1))
}

/// The parts of a line out of a set of convex polygons (a line's `difference` with their union), one segment each,
/// without parts of length 0. Only their distance and whether there is one are used.
pub(crate) fn outside(line: &[Pt], polys: &[Vec<Pt>]) -> Vec<Vec<Pt>> {
    let mut out = Vec::new();
    for s in line.windows(2) {
        let (a, b) = (s[0], s[1]);
        let mut inside: Vec<(f64, f64)> = polys.iter().filter_map(|p| clip(a, b, p)).collect();
        inside.sort_by(|x, y| x.0.total_cmp(&y.0));
        let at = |t: f64| (a.0 + t * (b.0 - a.0), a.1 + t * (b.1 - a.1));
        let mut t = 0.0;
        for (u, v) in inside.into_iter().chain([(1.0, 1.0)]) {
            if u > t && at(u) != at(t) {
                out.push(vec![at(t), at(u)]);
            }
            t = t.max(v);
        }
    }
    out
}

/// Whether a part of the upper road crosses the lower road (`_crosses`): they meet at a point (or along a piece) out
/// of the circles of 0.5 m around the ends of both roads.
pub(crate) fn crosses(part: &[Pt], upper: &[Pt], lower: &[Pt]) -> bool {
    let ends: Vec<Vec<Pt>> = [
        upper[0],
        *upper.last().unwrap(),
        lower[0],
        *lower.last().unwrap(),
    ]
    .iter()
    .map(|&p| circle(p, 0.5))
    .collect();
    let free = |p: Pt| ends.iter().all(|c| clip(p, p, c).is_none());
    for s in part.windows(2) {
        for l in lower.windows(2) {
            let (a, b, c, d) = (s[0], s[1], l[0], l[1]);
            let (d1, d2) = (orient(c, d, a), orient(c, d, b));
            if d1 == 0.0 && d2 == 0.0 {
                // on one line: the common piece
                let ab = sub(b, a);
                let len2 = dot(ab, ab);
                if len2 == 0.0 {
                    if on_seg(a, c, d) && free(a) {
                        return true;
                    }
                    continue;
                }
                let (tc, td) = (dot(sub(c, a), ab) / len2, dot(sub(d, a), ab) / len2);
                let (u, v) = (tc.min(td).max(0.0), tc.max(td).min(1.0));
                if u > v {
                    continue;
                }
                let at = |t: f64| (a.0 + t * ab.0, a.1 + t * ab.1);
                if u == v {
                    if free(at(u)) {
                        return true;
                    }
                } else if !outside(&[at(u), at(v)], &ends).is_empty() {
                    return true;
                }
            } else if segs_meet(a, b, c, d) {
                // one point: where the lines cross, or an end on the other segment
                let p = if d1 == 0.0 {
                    a
                } else if d2 == 0.0 {
                    b
                } else if orient(a, b, c) == 0.0 {
                    c
                } else if orient(a, b, d) == 0.0 {
                    d
                } else {
                    let t = d1 / (d1 - d2);
                    (a.0 + t * (b.0 - a.0), a.1 + t * (b.1 - a.1))
                };
                if free(p) {
                    return true;
                }
            }
        }
    }
    false
}

fn length(l: &[Pt]) -> f64 {
    l.windows(2)
        .map(|s| dot(sub(s[1], s[0]), sub(s[1], s[0])).sqrt())
        .sum()
}

/// The point at `d` metres along the line.
fn interpolate(l: &[Pt], d: f64) -> Pt {
    let mut cum = 0.0;
    for s in l.windows(2) {
        let len = dot(sub(s[1], s[0]), sub(s[1], s[0])).sqrt();
        if d <= cum + len {
            let t = if len == 0.0 { 0.0 } else { (d - cum) / len };
            return (
                s[0].0 + t * (s[1].0 - s[0].0),
                s[0].1 + t * (s[1].1 - s[0].1),
            );
        }
        cum += len;
    }
    *l.last().unwrap()
}

/// The piece of the line from `a` to `b` metres (shapely's `substring`, `a` < `b`).
fn substring(l: &[Pt], a: f64, b: f64) -> Vec<Pt> {
    let mut out = vec![interpolate(l, a)];
    let mut cum = 0.0;
    for s in l.windows(2) {
        if a < cum && cum < b {
            out.push(s[0]);
        } else if cum >= b {
            break;
        }
        cum += dot(sub(s[1], s[0]), sub(s[1], s[0])).sqrt();
    }
    out.push(interpolate(l, b));
    out
}

/// The three casing parts of a road (`casing_parts`): the heads `[start, end]` metres long (cut in their ratio on a
/// short road), and the main part, None when it is shorter than 5 cm.
pub(crate) fn casing_parts(l: &[Pt], heads: [f64; 2]) -> [Option<Vec<Pt>>; 3] {
    let n = length(l);
    let [mut h0, mut h1] = heads;
    if h0 + h1 >= n {
        (h0, h1) = (n * h0 / (h0 + h1), n * h1 / (h0 + h1));
    }
    [
        Some(substring(l, 0.0, h0)),
        (n - h1 - h0 > 0.05).then(|| substring(l, h0, n - h1)),
        Some(substring(l, n - h1, n)),
    ]
}
pub(crate) struct Indexed(pub usize, pub AABB<[f64; 2]>);

impl RTreeObject for Indexed {
    type Envelope = AABB<[f64; 2]>;
    fn envelope(&self) -> Self::Envelope {
        self.1
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn utm_as_pyproj() {
        // pyproj (always_xy): EPSG:32632 (7.42, 43.73) and EPSG:32735 (26.7, -20.1)
        for (lon, lat, x, y) in [
            (7.42, 43.73, 372751.1228, 4843098.2362),
            (26.7, -20.1, 468638.1863, 7777424.4129),
        ] {
            let (px, py) = Utm::new(lon, lat).project((lon, lat));
            assert!((px - x).abs() < 1e-3 && (py - y).abs() < 1e-3, "{px} {py}");
        }
    }

    #[test]
    fn a_line_out_of_a_circle() {
        let c = vec![circle((0.0, 0.0), 1.0)];
        let parts = outside(&[(-3.0, 0.0), (3.0, 0.0)], &c);
        assert_eq!(parts.len(), 2);
        assert!(
            (parts[0][1].0 + 1.0).abs() < 1e-12 && parts[0][0] == (-3.0, 0.0),
            "{parts:?}"
        );
        assert!(outside(&[(-0.5, 0.0), (0.5, 0.0)], &c).is_empty());
    }

    #[test]
    fn a_crossing_and_a_join() {
        let upper = [(-10.0, 0.0), (10.0, 0.0)];
        assert!(crosses(&upper, &upper, &[(0.0, -10.0), (0.0, 10.0)]));
        // the lower road starts at the end of the upper road: a join, not a crossing
        assert!(!crosses(&upper, &upper, &[(10.0, 0.0), (10.0, 10.0)]));
    }
}
