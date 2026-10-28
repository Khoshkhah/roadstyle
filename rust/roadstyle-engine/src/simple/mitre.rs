//! The mitre of the road ends: the pieces and items that meet at a node are cut back so their corners fit.

use super::*;

// _mitre_ends: a flat end where another road with metre widths goes on is pushed on to close the corner with the road that goes on most
// straight, turning _MITRE_MAX degrees at most; an item's end where an item of its colour and dash goes on (within _ITEM_JOIN_M) too.
pub(crate) const MITRE_MAX: f64 = 60.0;
pub(crate) const ITEM_JOIN_M: f64 = 2.0;

/// _unit: the unit vector from a to b in metres east and north, and its length.
pub(crate) fn unit(a: &Pt, b: &Pt, lat: f64) -> ((f64, f64), f64) {
    let (x, y) = ((b[0] - a[0]) * 111320.0 * lat.to_radians().cos(), (b[1] - a[1]) * 111320.0);
    let n = x.hypot(y);
    (if n > 0.0 { (x / n, y / n) } else { (0.0, 0.0) }, n)
}

/// _heading: the way a line runs at its first or last point, from a point at least 0.5 m away.
pub(crate) fn heading(c: &[Pt], first: bool) -> (f64, f64) {
    let pts: Vec<&Pt> = if first { c.iter().rev().collect() } else { c.iter().collect() };
    let last = pts[pts.len() - 1];
    let flip = |u: (f64, f64)| if first { (-u.0, -u.1) } else { u };
    for q in pts[..pts.len() - 1].iter().rev() {
        let (u, n) = unit(q, last, last[1]);
        if n >= 0.5 {
            return flip(u);
        }
    }
    flip(unit(pts[0], last, last[1]).0)
}

/// _reach: how far a flat end goes on to close the corner with the line that goes on (None: not a corner to close).
pub(crate) fn reach(own: ((f64, f64), (f64, f64), f64, f64), oth: ((f64, f64), (f64, f64), f64, f64)) -> Option<f64> {
    let ((p, u, h, o), (q, v, k, w)) = (own, oth);
    let cos = (u.0 * v.0 + u.1 * v.1).clamp(-1.0, 1.0);
    let turn = cos.acos().to_degrees();
    if !(0.5..=MITRE_MAX).contains(&turn) {
        return None;
    }
    let rn = |d: (f64, f64), x: f64| (d.1 * x, -d.0 * x);
    let (pa, pb) = ((p.0 + rn(u, o).0, p.1 + rn(u, o).1), (q.0 + rn(v, w).0, q.1 + rn(v, w).1));
    let det = u.0 * v.1 - u.1 * v.0;
    let (dx, dy) = (pb.0 - pa.0, pb.1 - pa.1);
    let (s, t) = ((dx * v.1 - dy * v.0) / det, (u.0 * dy - u.1 * dx) / det);
    if s.abs().max(t.abs()) > ITEM_JOIN_M {
        return None;
    }
    let sin = turn.to_radians().sin();
    Some(s.max(0.0) + ((k - h * cos) / sin).max(0.0).min(h * (turn.to_radians() / 2.0).tan()))
}

/// _push: the line with its first or last point pushed `m` metres straight on.
pub(crate) fn push(c: &mut Vec<Pt>, first: bool, m: f64) {
    let u = heading(c, first);
    let u = if first { (-u.0, -u.1) } else { u };
    let end = if first { c[0] } else { c[c.len() - 1] };
    let pt = [crate::layers::round_to(end[0] + u.0 * m / (111320.0 * end[1].to_radians().cos()), 7), crate::layers::round_to(end[1] + u.1 * m / 111320.0, 7)];
    if first { c.insert(0, pt) } else { c.push(pt) }
}

pub(crate) fn mitre_ends(out: &mut [Piece], line_of: &[Option<&[Pt]>], roads: &Roads, items: &mut [Item]) {
    let xy = flat_xy(items, line_of);
    mitre_roads(out, line_of, roads, &xy);
    mitre_items(items, &xy);
}

/// The projection to flat metres: one latitude for all of them (two points' own ones put them metres apart): the first item's, else the
/// first road's.
fn flat_xy(items: &[Item], line_of: &[Option<&[Pt]>]) -> impl Fn(&Pt) -> (f64, f64) {
    let lat0 = items.first().and_then(|f| f.coords.as_ref()).and_then(|c| c.first()).map(|p| p[1])
        .or_else(|| line_of.iter().flatten().find(|c| !c.is_empty()).map(|c| c[0][1])).unwrap_or(0.0);
    let k0 = 111320.0 * lat0.to_radians().cos();
    move |pt: &Pt| (pt[0] * k0, pt[1] * 111320.0)
}

/// The flat ends of the metre roads, pushed on at a node where another metre road goes on.
fn mitre_roads(out: &mut [Piece], line_of: &[Option<&[Pt]>], roads: &Roads, xy: &impl Fn(&Pt) -> (f64, f64)) {
    let topo = roads.topo();
    let mut wide: indexmap::IndexMap<i64, (f64, f64)> = indexmap::IndexMap::new();
    for p in roads.iter() {
        let (Some(wm), Some(c)) = (p.get(Mark::WidthM.name()).and_then(Cell::as_f64), p.line().filter(|c| c.len() >= 2)) else { continue };
        if is_yes(p.get(Mark::Dup.name())) {
            continue;
        }
        let k = c[0][1].to_radians().cos();
        let cm = p.get(Mark::CasingM.name()).and_then(Cell::as_f64).unwrap_or(0.0);
        wide.insert(p.get(Mark::Edge.name()).and_then(Cell::as_u64).and_then(crate::road::row_of).unwrap_or(p.i) as i64, (wm * k, (wm - 2.0 * cm) * k));
    }
    let line = |e: i64| line_of.get(e as usize).copied().flatten();
    // the ends of the metre roads at each node (a road end's node: Topology)
    let node_of = |e: i64, first: bool| topo.ends.get(e as usize).copied().flatten().map(|n| n[usize::from(!first)]);
    let mut ends: HashMap<u32, Vec<(i64, bool)>> = HashMap::new();
    for &e in wide.keys() {
        for first in [true, false] {
            if let Some(n) = node_of(e, first) {
                ends.entry(n).or_default().push((e, first));
            }
        }
    }
    let at = |a: &Pt, b: &Pt| (a[0] - b[0]).abs() < 1e-6 && (a[1] - b[1]).abs() < 1e-6;
    for f in out.iter_mut() {
        let edge = f.edge as i64;
        if !wide.contains_key(&edge) || f.cap(roads) != Some(Cap::Flat) || f.seam() {
            continue;
        }
        let j = if f.draw.map(|d| d.kind) == Some(1) { 1 } else { 0 };
        let (Some(c), Some(e)) = (f.points(roads).filter(|c| c.len() >= 2), line(edge)) else { continue };
        let mut pushes = Vec::new();        // the ends that reach further, put on the piece's own copy after (R11)
        for first in [true, false] {
            let (cp, ep) = if first { (&c[0], &e[0]) } else { (&c[c.len() - 1], &e[e.len() - 1]) };
            if !at(cp, ep) {
                continue;
            }
            let node = *ep;
            let u = heading(e, first);
            let u = if first { (-u.0, -u.1) } else { u };
            let mut best: Option<(f64, f64)> = None;
            for &(o, ofirst) in node_of(edge, first).and_then(|n| ends.get(&n)).into_iter().flatten() {
                if o == edge {
                    continue;
                }
                let Some(oc) = line(o) else { continue };
                let v = heading(oc, ofirst);
                let v = if ofirst { v } else { (-v.0, -v.1) };
                let pick = |x: (f64, f64)| if j == 1 { x.1 } else { x.0 };
                let m = reach((xy(&node), u, pick(wide[&edge]) / 2.0, 0.0), (xy(&node), v, pick(wide[&o]) / 2.0, 0.0));
                let dot = u.0 * v.0 + u.1 * v.1;
                if let Some(m) = m {
                    if best.is_none_or(|b| dot > b.0) {
                        best = Some((dot, m));
                    }
                }
            }
            if let Some((_, m)) = best.filter(|b| b.1 > 0.0) {
                pushes.push((first, m));
            }
        }
        if !pushes.is_empty() {
            let mut own = f.points(roads).unwrap_or_default().to_vec();
            for (first, m) in pushes {
                push(&mut own, first, m);
            }
            f.coords = PieceLine::own(own);
        }
    }
}

/// The ends of the items: an end that meets the items of its colour and dash is pushed on to close the corner.
fn mitre_items(items: &mut [Item], xy: &impl Fn(&Pt) -> (f64, f64)) {
    // the items: an end with the items of its colour and dash that start within ITEM_JOIN_M (and a start with those that end there)
    let lines: Vec<usize> = (0..items.len()).filter(|&k| items[k].coords.as_ref().is_some_and(|c| c.len() >= 2)).collect();
    let text = |f: &Item, k: &str| f.props.get(k).filter(|v| !v.is_null()).map(Value::to_string);     // missing or null
    let key = |f: &Item| (text(f, Mark::ItemColor.name()), text(f, Mark::Dash.name()));
    let cell = |p: &Pt| ((p[0] / 3e-5).floor() as i64, (p[1] / 3e-5).floor() as i64);
    let end_of = |c: &Vec<Pt>, first: bool| if first { c[0] } else { c[c.len() - 1] };
    let mut by: HashMap<_, Vec<usize>> = HashMap::new();
    for &k in &lines {
        let c = items[k].coords.as_ref().unwrap();
        for first in [true, false] {
            by.entry((key(&items[k]), first, cell(&end_of(c, first)))).or_default().push(k);
        }
    }
    let num = |p: &Props, k: &str| p.get(k).and_then(Value::as_f64).unwrap_or(0.0);
    let side = |f: &Item, first: bool| {
        let c = f.coords.as_ref().unwrap();
        let cl = c[0][1].to_radians().cos();
        let u = heading(c, first);
        let out_u = if first { (-u.0, -u.1) } else { u };
        let o = num(&f.props, Mark::ItemOffsetM.name()) * cl;
        (xy(&end_of(c, first)), out_u, num(&f.props, Mark::ItemWidthM.name()) * cl / 2.0, if first { -o } else { o })
    };
    let mut pushes = Vec::new();
    for &k in &lines {
        for first in [true, false] {
            let (p, u, h, o) = side(&items[k], first);
            let (x, y) = cell(&end_of(items[k].coords.as_ref().unwrap(), first));
            let mut best: Option<(f64, f64)> = None;
            for dx in [-1, 0, 1] {
                for dy in [-1, 0, 1] {
                    for &j in by.get(&(key(&items[k]), !first, (x + dx, y + dy))).into_iter().flatten() {
                        if j == k {
                            continue;
                        }
                        let (q, v, kk, w) = side(&items[j], !first);
                        let (v, w) = ((-v.0, -v.1), -w);
                        if (q.0 - p.0).hypot(q.1 - p.1) > ITEM_JOIN_M {
                            continue;
                        }
                        let dot = u.0 * v.0 + u.1 * v.1;
                        if let Some(m) = reach((p, u, h, o), (q, v, kk, w)) {
                            if best.is_none_or(|b| dot > b.0) {
                                best = Some((dot, m));
                            }
                        }
                    }
                }
            }
            if let Some((_, m)) = best.filter(|b| b.1 > 0.0) {
                pushes.push((k, first, m));
            }
        }
    }
    for (k, first, m) in pushes {
        push(items[k].coords.as_mut().unwrap(), first, m);
    }
}
