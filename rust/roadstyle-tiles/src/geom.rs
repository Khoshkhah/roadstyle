//! The geometry of a feature: Web Mercator points, lines and rings; their clip to a tile and their simplification.

use super::*;

pub(crate) type P = [f64; 2];

pub(crate) enum Geom {
    Points(Vec<P>),
    Lines(Vec<Vec<P>>),
    Polygons(Vec<Vec<Vec<P>>>),
}

/// Web Mercator in [0, 1] (x to the east, y to the south), as the tiles count.
pub(crate) fn merc(c: &Value) -> Option<P> {
    merc_ll(c.get(0)?.as_f64()?, c.get(1)?.as_f64()?)
}

pub(crate) fn merc_ll(lon: f64, lat: f64) -> Option<P> {
    if !lon.is_finite() || !lat.is_finite() {
        return None; // as JSON: a number that is not finite is null
    }
    let lat = lat.clamp(-85.051_128_78, 85.051_128_78);
    let y = (std::f64::consts::FRAC_PI_4 + lat.to_radians() / 2.0).tan().ln();
    Some([(lon + 180.0) / 360.0, 0.5 - y / (2.0 * std::f64::consts::PI)])
}

/// A line of longitude and latitude in Web Mercator (a point that is not finite is left out).
pub(crate) fn line_geom(c: &[[f64; 2]]) -> Geom {
    Geom::Lines(vec![c.iter().filter_map(|p| merc_ll(p[0], p[1])).collect()])
}

pub(crate) fn line(c: &Value) -> Vec<P> {
    c.as_array().map_or(Vec::new(), |a| a.iter().filter_map(merc).collect())
}

pub(crate) fn rings(c: &Value) -> Vec<Vec<P>> {
    c.as_array().map_or(Vec::new(), |a| a.iter().map(line).collect())
}

pub(crate) fn geom(g: &Value) -> Option<Geom> {
    let c = &g["coordinates"];
    let list = |f: &dyn Fn(&Value) -> Vec<Vec<P>>| c.as_array().map_or(Vec::new(), |a| a.iter().map(f).collect());
    Some(match g["type"].as_str()? {
        "Point" => Geom::Points(vec![merc(c)?]),
        "MultiPoint" => Geom::Points(c.as_array()?.iter().filter_map(merc).collect()),
        "LineString" => Geom::Lines(vec![line(c)]),
        "MultiLineString" => Geom::Lines(rings(c)),
        "Polygon" => Geom::Polygons(vec![rings(c)]),
        "MultiPolygon" => Geom::Polygons(list(&rings)),
        _ => return None,
    })
}

pub(crate) fn bounds(g: &Geom) -> Option<(P, P)> {
    let mut lo = [f64::INFINITY; 2];
    let mut hi = [f64::NEG_INFINITY; 2];
    let mut add = |p: &P| {
        for k in 0..2 {
            lo[k] = lo[k].min(p[k]);
            hi[k] = hi[k].max(p[k]);
        }
    };
    match g {
        Geom::Points(ps) => ps.iter().for_each(&mut add),
        Geom::Lines(ls) => ls.iter().flatten().for_each(&mut add),
        Geom::Polygons(ps) => ps.iter().flatten().flatten().for_each(&mut add),
    }
    (lo[0] <= hi[0]).then_some((lo, hi))
}

/// The parts of a line (in the tile's units, simplified: `Tiles::kept`) in a tile: none when shorter than half a unit, then
/// clipped to the square [lo, hi]^2 when `clip` is given.
pub(crate) fn line_parts(ls: Vec<Vec<P>>, clip: Option<(f64, f64)>) -> Vec<Vec<[i32; 2]>> {
    // a line shorter than half a tile unit is left out at every zoom (a whole layer's lines are not checked)
    if clip.is_some() && ls.iter().map(|l| length(l)).sum::<f64>() < 0.5 {
        return Vec::new();
    }
    ls.into_iter()
        .flat_map(|l| match clip {
            Some((lo, hi)) => clip_line(&l, lo, hi),
            None => vec![l],
        })
        .map(|l| dedup(l.into_iter().map(round)))
        .filter(|l| l.len() >= 2)
        .collect()
}

pub(crate) fn length(l: &[P]) -> f64 {
    l.windows(2).map(|w| (w[1][0] - w[0][0]).hypot(w[1][1] - w[0][1])).sum()
}

/// The distance from p to the segment ab.
pub(crate) fn seg_dist(p: P, a: P, b: P) -> f64 {
    let d = [b[0] - a[0], b[1] - a[1]];
    let l2 = d[0] * d[0] + d[1] * d[1];
    let t = if l2 == 0.0 { 0.0 } else { (((p[0] - a[0]) * d[0] + (p[1] - a[1]) * d[1]) / l2).clamp(0.0, 1.0) };
    (p[0] - a[0] - t * d[0]).hypot(p[1] - a[1] - t * d[1])
}

/// Douglas-Peucker: the points of the line that keep it within `tol` of the original (shapely's simplify).
/// ponytail: no topology check (GEOS's preserve_topology also keeps a line from crossing itself); add it if a simplified road
/// crosses itself at a low zoom.
/// The places of the points that Douglas-Peucker keeps (to `tol`), in their order.
pub(crate) fn douglas_peucker_kept(ps: &[P], tol: f64) -> Vec<u32> {
    if ps.len() < 3 {
        return (0..ps.len() as u32).collect();
    }
    let mut keep = vec![false; ps.len()];
    (keep[0], keep[ps.len() - 1]) = (true, true);
    let mut todo = vec![(0, ps.len() - 1)];
    while let Some((a, b)) = todo.pop() {
        let (mut far, mut at) = (0.0, a);
        for i in a + 1..b {
            let d = seg_dist(ps[i], ps[a], ps[b]);
            if d > far {
                (far, at) = (d, i);
            }
        }
        if far > tol {
            keep[at] = true;
            todo.push((a, at));
            todo.push((at, b));
        }
    }
    keep.iter().enumerate().filter(|(_, k)| **k).map(|(i, _)| i as u32).collect()
}

pub(crate) fn round(p: P) -> [i32; 2] {
    [p[0].round() as i32, p[1].round() as i32]
}

pub(crate) fn dedup(ps: impl Iterator<Item = [i32; 2]>) -> Vec<[i32; 2]> {
    let mut out: Vec<[i32; 2]> = Vec::new();
    for p in ps {
        if out.last() != Some(&p) {
            out.push(p);
        }
    }
    out
}

/// Twice the signed area by the surveyor's formula.
pub(crate) fn area(r: &[[i32; 2]]) -> i64 {
    (0..r.len()).map(|i| {
        let (a, b) = (r[i], r[(i + 1) % r.len()]);
        a[0] as i64 * b[1] as i64 - b[0] as i64 * a[1] as i64
    }).sum()
}

/// The parts of a line inside the square [lo, hi]^2 (Liang-Barsky on each segment).
pub(crate) fn clip_line(ps: &[P], lo: f64, hi: f64) -> Vec<Vec<P>> {
    let mut out = Vec::new();
    let mut cur: Vec<P> = Vec::new();
    for w in ps.windows(2) {
        match clip_seg(w[0], w[1], lo, hi) {
            Some((a, b)) => {
                if cur.last() != Some(&a) {
                    if cur.len() >= 2 {
                        out.push(std::mem::take(&mut cur));
                    }
                    cur.clear();
                    cur.push(a);
                }
                cur.push(b);
                if b != w[1] {
                    out.push(std::mem::take(&mut cur)); // the line leaves the square here
                }
            }
            None => {
                if cur.len() >= 2 {
                    out.push(std::mem::take(&mut cur));
                }
                cur.clear();
            }
        }
    }
    if cur.len() >= 2 {
        out.push(cur);
    }
    out
}

pub(crate) fn clip_seg(a: P, b: P, lo: f64, hi: f64) -> Option<(P, P)> {
    let d = [b[0] - a[0], b[1] - a[1]];
    let (mut t0, mut t1) = (0.0f64, 1.0f64);
    for k in 0..2 {
        for (p, q) in [(-d[k], a[k] - lo), (d[k], hi - a[k])] {
            if p == 0.0 {
                if q < 0.0 {
                    return None;
                }
            } else {
                let t = q / p;
                if p < 0.0 {
                    t0 = t0.max(t);
                } else {
                    t1 = t1.min(t);
                }
            }
        }
    }
    if t0 > t1 {
        return None;
    }
    let at = |t: f64| if t == 0.0 { a } else if t == 1.0 { b } else { [a[0] + t * d[0], a[1] + t * d[1]] };
    Some((at(t0), at(t1)))
}

/// A ring cut to the square [lo, hi]^2 (Sutherland-Hodgman); the parts outside become the square's edge, which the map does not draw.
pub(crate) fn clip_ring(r: &[P], lo: f64, hi: f64) -> Vec<P> {
    let mut pts = r.to_vec();
    for (k, edge, keep_above) in [(0, lo, true), (0, hi, false), (1, lo, true), (1, hi, false)] {
        if pts.is_empty() {
            break;
        }
        let inside = |p: &P| if keep_above { p[k] >= edge } else { p[k] <= edge };
        let mut out = Vec::with_capacity(pts.len());
        for i in 0..pts.len() {
            let (a, b) = (pts[(i + pts.len() - 1) % pts.len()], pts[i]);
            if inside(&b) {
                if !inside(&a) {
                    out.push(cut(a, b, k, edge));
                }
                out.push(b);
            } else if inside(&a) {
                out.push(cut(a, b, k, edge));
            }
        }
        pts = out;
    }
    pts
}

pub(crate) fn cut(a: P, b: P, k: usize, edge: f64) -> P {
    let t = (edge - a[k]) / (b[k] - a[k]);
    let mut p = [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])];
    p[k] = edge;
    p
}
