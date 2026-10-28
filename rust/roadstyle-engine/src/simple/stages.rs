//! The stages that make pieces from the roads: the casing parts, the halves and the end stubs.

use super::*;

/// _casing_parts: the casing of every edge as pieces. An edge whose three casing numbers differ (or with two different ends) is cut into
/// its start head, its main part and its end head, with a seam (and a lap, not on a dashed or tunnel casing) at each cut inside it.
pub(crate) fn casing_parts(roads: &Roads, head_m: f64) -> Vec<Piece> {
    let mut out = Vec::new();
    for p in roads.iter() {
        let d = p.draw();
        if d.dup {
            continue; // one line for a reverse pair: its twin draws it
        }
        let edge = p.i as u32;
        if d.twin.is_some_and(|tw| tw.get() < edge as usize) {
            continue; // a two-way pair's one casing: the first edge's pieces
        }
        let piece = |part: Part, coords: PieceLine| Piece { edge, part, end: End::AsIs, draw: None, coords };
        let [cm, _, cs, ce] = d.levels64().unwrap_or_default();
        let split = d.split.is_some();
        let c = match p.line() {
            Some(c) if c.len() >= 2 && !(cs == cm && cm == ce && !split) => c,
            _ => {
                out.push(piece(Part::Casing, if p.line().is_some() { PieceLine::Road } else { PieceLine::None }));
                continue;
            }
        };
        let line = Line::new(c);
        let n = line.len();
        let (h0, h1) = (d.head(&roads.values, 0).unwrap_or(head_m), d.head(&roads.values, 1).unwrap_or(head_m));
        // k: 0 the start head, 1 the main part, 2 the end head. A short road is cut once, in the heads' ratio (roadstyle after 0.24.2,
        // short_road_heads.md "One cut"): two cuts at h0 and n - h1 are one point only in exact arithmetic
        let cuts: Vec<(f64, f64, i64, u8)> = if h0 + h1 >= n - 0.05 {
            let h0 = n * h0 / (h0 + h1);
            vec![(0.0, h0, cs, 0), (h0, n, ce, 2)]
        } else {
            vec![(0.0, h0, cs, 0), (h0, n - h1, cm, 1), (n - h1, n, ce, 2)]
        };
        for &(a, b, num, k) in &cuts {
            let pts = line.part(a, b);
            if pts.len() < 2 || !pts.windows(2).any(|w| w[0] != w[1]) {
                continue;
            }
            out.push(piece(Part::Cut(k, num), PieceLine::own(line.lonlat(&pts, 1e7))));
        }
        // a seam at each cut inside the edge, at the lower of the two pieces' numbers; below zoom 17 a flat lap instead
        let mut cut_at: Vec<f64> = cuts[1..].iter().map(|c| c.0).collect();
        cut_at.retain(|&x| x != 0.0 && x != n);
        cut_at.sort_by(f64::total_cmp);
        cut_at.dedup_by(|a, b| a == b);
        let solid = !is_yes(p.get(Mark::Dash.name())) && !is_yes(p.get(Mark::Tunnel.name()));
        for &cut in &cut_at {
            let near: Vec<&(f64, f64, i64, u8)> = cuts.iter().filter(|(a, b, _, _)| b - a > 1e-9 && ((b - cut).abs() < 1e-9 || (a - cut).abs() < 1e-9)).collect();
            let half = near.iter().map(|(a, b, _, _)| (b - a) / 4.0).fold(SEAM_M, f64::min);
            let pts = line.part((cut - half).max(0.0), (cut + half).min(n));
            if near.len() < 2 || pts.len() < 2 {
                continue;
            }
            let num = near.iter().map(|x| x.2).min().unwrap();
            out.push(piece(Part::Seam(num), PieceLine::own(line.lonlat(&pts, 1e8))));
            if !solid {
                continue; // a solid lap would fill a dashed casing's gaps
            }
            let half = near.iter().map(|(a, b, _, _)| (b - a) / 2.0).fold(LAP_M, f64::min);
            let pts = line.part((cut - half).max(0.0), (cut + half).min(n));
            out.push(piece(Part::Lap(num), PieceLine::own(line.lonlat(&pts, 1e7))));
        }
    }
    out
}

/// _halves: the fill of every edge with two different ends (__rs_split) as two halves cut at the middle, each with its end's cap.
pub(crate) fn halves(roads: &Roads) -> HashMap<i64, Vec<Piece>> {
    let mut out: HashMap<i64, Vec<Piece>> = HashMap::new();
    for p in roads.iter() {
        let Some(c) = p.line().filter(|c| c.len() >= 2) else { continue };
        if p.draw().split.is_none() || p.draw().dup {
            continue;
        }
        let line = Line::new(c);
        let n = line.len();
        for (k, (a, b)) in [(0.0, n / 2.0), (n / 2.0, n)].into_iter().enumerate() {
            out.entry(p.i as i64).or_default().push(Piece { edge: p.i as u32, part: Part::Half(k as u8), end: End::AsIs, draw: None,
                                                             coords: PieceLine::own(line.lonlat(&line.part(a, b), 1e7)) });
        }
    }
    out
}

/// _end_stub: a piece with one road end and one cut whose road end is not flat is drawn flat, plus a short stub at the road end that
/// carries the end's shape (0.5 m for a square end, 5 cm for a round one). Any other piece as it is.
pub(crate) fn end_stub(q: Piece, roads: &Roads) -> Vec<Piece> {
    let at = |a: &Pt, b: &Pt| (a[0] - b[0]).abs() < 1e-6 && (a[1] - b[1]).abs() < 1e-6;
    let (Some(c), Some(e)) = (q.points(roads), roads.line(q.edge as usize)) else { return vec![q] };
    if c.len() < 2 || e.len() < 2 || at(&c[0], &e[0]) == at(&c[c.len() - 1], &e[e.len() - 1]) {
        return vec![q];
    }
    let first = at(&c[0], &e[0]);
    let (end, prev) = if first { (c[0], c[1]) } else { (c[c.len() - 1], c[c.len() - 2]) };
    let m = if q.cap(roads) == Some(Cap::Square) { 0.5 } else { 0.05 };
    let d = ((prev[0] - end[0]) * 111320.0 * end[1].to_radians().cos()).hypot((prev[1] - end[1]) * 111320.0);
    let k = (m / d.max(1e-6)).min(1.0);
    let inner = [end[0] + (prev[0] - end[0]) * k, end[1] + (prev[1] - end[1]) * k];
    let stub = if first { vec![end, inner] } else { vec![inner, end] };
    vec![Piece { end: End::Flat, ..q.clone() }, Piece { end: End::Stub, coords: PieceLine::own(stub), ..q }]
}
