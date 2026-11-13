//! The numbers of the roads from their rules (roadstyle's `_solve_intervals`, docs/levels.md): the stages as minimum-cost
//! flows. Each stage keeps the best value of the stage before it: a rule with flow holds as an equality, a soft rule
//! that the stage did not break becomes hard, and a broken rule holds in the other direction.

use crate::Error;
use super::flow::{Network, INF};
use std::cmp::Reverse;
use std::collections::BinaryHeap;

/// The relations of the roads, on road indexes. A casing part is 0 (start head), 1 (main part) or 2 (end head).
#[derive(Clone, Debug, Default)]
pub struct Rules {
    pub roads: usize,
    /// `(x, x_end, y, y_end)`: an end of `x` (0 start, 2 end) and an end of `y` are one node.
    pub meets: Vec<(usize, usize, usize, usize)>,
    /// `(upper, lower, part)`: that casing part of the upper road is over the fill of the lower road.
    pub lifts: Vec<(usize, usize, usize)>,
    /// `(road, path, end)`: a path at a node where the road goes on (a crossing at grade): the road's head there over the path's fill,
    /// so the path is drawn under the road's outline. A wish after the stack rules: a bridge over the road outranks it.
    pub crossings: Vec<(usize, usize, usize)>,
    /// `(higher, lower)`: the fill of the higher road is over the fill of the lower road where they meet (a wish).
    pub orders: Vec<(usize, usize)>,
    /// `(upper, lower, part)`: a casing part that only comes near the lower road (`near_rules`): the last wish.
    pub near: Vec<(usize, usize, usize)>,
    /// `(road, [casing_start, casing_level, casing_end, fill_level])`: numbers in the box `[0, steps]` that stay as they are.
    pub fixed: Vec<(usize, [i64; 4])>,
}

#[derive(Clone, Debug, Default)]
pub struct Solved {
    /// `[casing_start, casing_level, casing_end, fill_level]` of each road, not yet moved to the ground.
    pub parts: Vec<[i64; 4]>,
    /// The stack pairs `(upper, lower)` with a lifted part that is not over the lower fill.
    pub given_up: Vec<(usize, usize)>,
    /// The lifted parts `(upper, lower, part)` of those pairs that are not over the lower fill.
    pub given_up_parts: Vec<(usize, usize, usize)>,
    /// The crossings `(road, path, end)` whose path is not under the road's head.
    pub crossings_not_kept: Vec<(usize, usize, usize)>,
    /// The order wishes that are not kept.
    pub orders_not_kept: Vec<(usize, usize)>,
    /// The near parts `(upper, lower, part)` that are not over the lower fill.
    pub near_not_kept: Vec<(usize, usize, usize)>,
    /// The best value of each stage (roadstyle's objectives): the steps by which the stack rules are broken, the
    /// same for the crossings, the order wishes and the near rules, and the cost (the casings, and the span with its weight).
    pub stages: [i64; 5],
}

#[derive(Clone, Copy, PartialEq)]
enum Kind {
    Hard,
    Stack,
    Crossing,
    Order,
    Near,
    Gone,
}

/// An arc `from -> to` of cost `w`: 16 bytes (Kentucky: 19 million arcs). The costs are small (0, -1, the box, the span).
type Arc = (u32, u32, i32, Kind);

fn arc(i: usize, j: usize, w: i64, k: Kind) -> Arc {
    (i as u32, j as u32, w as i32, k)
}

/// Lists by node in one list, in the order they come (node `u` has `out[start[u]..start[u + 1]]`): a list for each of the
/// millions of nodes took its own allocation. `each` gives the entries; it runs two times (the count, then the fill).
fn by_node<T: Copy + Default>(nodes: usize, each: impl Fn(&mut dyn FnMut(usize, T))) -> (Vec<usize>, Vec<T>) {
    let mut start = vec![0usize; nodes + 1];
    each(&mut |u, _| start[u + 1] += 1);
    for v in 0..nodes {
        start[v + 1] += start[v];
    }
    let mut fill = start.clone();
    let mut out = vec![T::default(); start[nodes]];
    each(&mut |u, e| {
        out[fill[u]] = e;
        fill[u] += 1;
    });
    (start, out)
}

/// The column of the casing part `h` of road `r` (the road's fill is the column `r`).
fn col(n: usize, r: usize, h: usize) -> usize {
    n + 3 * r + h
}

/// The rules sorted and without doubles. A part that is a stack and a near rule is a stack.
struct Cleaned {
    lifts: Vec<(usize, usize, usize)>,
    crossings: Vec<(usize, usize, usize)>,
    orders: Vec<(usize, usize)>,
    near: Vec<(usize, usize, usize)>,
}

fn sorted<T: Ord + Copy>(v: impl Iterator<Item = T>) -> Vec<T> {
    let mut v: Vec<T> = v.collect();
    v.sort_unstable();
    v.dedup();
    v
}

impl Cleaned {
    fn new(rules: &Rules) -> Self {
        let lifts = sorted(rules.lifts.iter().copied());
        let near = sorted(rules.near.iter().copied().filter(|p| lifts.binary_search(p).is_err()));
        Cleaned { lifts, crossings: sorted(rules.crossings.iter().copied()), orders: sorted(rules.orders.iter().copied()), near }
    }
}

/// Every rule x_i - x_j <= w is an arc i -> j of cost w.
fn rule_arcs(rules: &Rules, c: &Cleaned, steps: i64) -> Vec<Arc> {
    let n = rules.roads;
    let col = |r, h| col(n, r, h);
    let (hi, lo, z) = (4 * n, 4 * n + 1, 4 * n + 2);
    let size = 3 * n + 2 * rules.meets.len() + 8 * n + 2 + 8 * rules.fixed.len() + c.lifts.len() + c.crossings.len()
        + c.near.len() + c.orders.len();
    let mut arcs: Vec<Arc> = Vec::with_capacity(size);
    for r in 0..n {
        for h in 0..3 {
            arcs.push(arc(col(r, h), r, 0, Kind::Hard)); // H1: a casing part not over its own fill
        }
    }
    for &(x, ex, y, ey) in &rules.meets {
        arcs.push(arc(col(x, ex), y, 0, Kind::Hard)); // H2: the heads of two roads that meet, under the other's fill
        arcs.push(arc(col(y, ey), x, 0, Kind::Hard));
    }
    for v in 0..4 * n {
        arcs.push(arc(v, hi, 0, Kind::Hard)); // the span: every number between L and H
        arcs.push(arc(lo, v, 0, Kind::Hard));
    }
    arcs.push(arc(hi, z, steps, Kind::Hard)); // the box [0, steps]; z is 0
    arcs.push(arc(z, lo, 0, Kind::Hard));
    for &(r, v) in &rules.fixed {
        for (c, x) in [col(r, 0), col(r, 1), col(r, 2), r].into_iter().zip(v) {
            arcs.push(arc(c, z, x, Kind::Hard)); // x_c = x: x_c - x_z <= x and x_z - x_c <= -x
            arcs.push(arc(z, c, -x, Kind::Hard));
        }
    }
    for &(u, l, h) in &c.lifts {
        arcs.push(arc(l, col(u, h), -1, Kind::Stack)); // H3: b_l + 1 <= a_(u, h)
    }
    for &(cr, p, h) in &c.crossings {
        arcs.push(arc(p, col(cr, h), -1, Kind::Crossing)); // b_p + 1 <= a_(c, h)
    }
    for &(u, l, h) in &c.near {
        arcs.push(arc(l, col(u, h), -1, Kind::Near));
    }
    for &(x, y) in &c.orders {
        arcs.push(arc(y, x, -1, Kind::Order)); // H4: b_y + 1 <= b_x
    }
    arcs
}

/// The four soft stages, one after the other: each finds the least steps by which its rules are broken (`stages[0..4]`), then holds
/// that answer for the next stage: a rule that is broken holds the other way, and one that is tight becomes an equality.
fn soft_stages(arcs: &mut Vec<Arc>, nodes: usize, pi: &mut [i64], stages: &mut [i64; 5]) -> Result<(), Error> {
    for (s, soft) in [Kind::Stack, Kind::Crossing, Kind::Order, Kind::Near].into_iter().enumerate() {
        if !arcs.iter().any(|a| a.3 == soft) {
            continue;
        }
        let (g, idx) = network(arcs, nodes, |k| match k {
            Kind::Hard => Some(INF),
            k if k == soft => Some(1),
            _ => None,
        });
        let flow = g.solve(&vec![0; nodes], pi)?;
        stages[s] = -(0..idx.len()).map(|e| flow[e] * g.cost[e]).sum::<i64>(); // the value of the LP (duality)
        let mut more = Vec::new();
        for (e, &a) in idx.iter().enumerate() {
            let a = a as usize;
            let (i, j, w, kind) = arcs[a];
            if kind == soft && flow[e] >= 1 {
                arcs[a].3 = Kind::Gone; // broken: it holds the other way, x_j - x_i <= -w
                more.push((j, i, -w, Kind::Hard));
            } else {
                arcs[a].3 = Kind::Hard;
                if flow[e] > 0 {
                    more.push((j, i, -w, Kind::Hard)); // tight: an equality
                }
            }
        }
        arcs.reserve_exact(more.len());   // the exact size: a list that doubles needs up to three times its size for a moment
        arcs.extend(more);
    }
    Ok(())
}

/// The numbers are in a box of `steps + 1` values (roadstyle's `2 * max_level / margin`); `min_positions`: the span of the numbers is
/// as small as possible.
pub fn solve(rules: &Rules, steps: i64, min_positions: bool) -> Result<Solved, Error> {
    if rules.roads == 0 {
        return Ok(Solved::default());
    }
    let (x, stages) = numbers(rules, steps, min_positions)?;
    feasible(rules, &x, steps)?;
    Ok(report(rules.roads, &Cleaned::new(rules), &x, stages))
}

/// The numbers of all nodes (the columns, then H, L and 0 as the last), and the best value of each stage.
fn numbers(rules: &Rules, steps: i64, min_positions: bool) -> Result<(Vec<i64>, [i64; 5]), Error> {
    let n = rules.roads;
    let (hi, lo) = (4 * n, 4 * n + 1);
    let c = Cleaned::new(rules);
    let mut arcs = rule_arcs(rules, &c, steps);
    let nodes = 4 * n + 3;
    let mut pi = vec![0i64; nodes];
    if !rules.fixed.is_empty() {
        pi = potentials(&arcs, nodes)?; // the arcs of the fixed numbers have negative costs
    }
    let mut stages = [0i64; 5];
    soft_stages(&mut arcs, nodes, &mut pi, &mut stages)?;
    // the cost: the sum of (b - a) over all casing parts, and a large weight w4 on the span H - L. The weight is larger
    // than any sum, so this is two steps: first the least span, then the least sum at that span. The least span is minus
    // the shortest distance from L to H in all the hard rules (also the rules through H, L and 0 that the stages made
    // equalities, and the fixed numbers); an arc H -> L of that cost keeps it, and the flow carries only the casing parts.
    // The best numbers are the same. (As a supply of w4 at H and L, the flow took 260 phases on Burnaby: 17 s.)
    let w4 = 3 * n as i64 * steps + 1;
    pi = from_node(&arcs, nodes, lo, &pi);
    let span = -pi[hi];
    if min_positions {
        arcs.reserve_exact(1);
        arcs.push(arc(hi, lo, span, Kind::Hard));
    }
    let mut supply = vec![0i64; nodes];
    for r in 0..n {
        for h in 0..3 {
            supply[r] -= 1;
            supply[col(n, r, h)] += 1;
        }
    }
    let (g, _) = network(&arcs, nodes, |k| (k == Kind::Hard).then_some(INF));
    drop(arcs); // the network has the rules now: the list goes before the largest flow
    let flow = g.solve(&supply, &mut pi)?;
    let w4 = if min_positions { w4 } else { 0 };
    stages[4] = w4 * span - (0..g.from.len()).map(|e| flow[e] * g.cost[e]).sum::<i64>();
    Ok((least_numbers(&g, &flow, &pi), stages))
}

/// The levels of a large area with little memory (Kaveh, 2026-11-13): `start` gives each road its numbers `[casing_start,
/// casing_level, casing_end, fill]` in the box `[0, steps]` (the tags rule), then each group of roads that the rules broken by those
/// numbers join is solved alone, with the roads around it fixed at their numbers of that moment. The memory is that of the largest
/// group, not of the area (Kentucky: 50,547 groups, the largest 4,854 of 1,266,648 roads). The groups go one after the other: a rule
/// between two groups is a rule of the later one, so every hard rule holds at the end. A group with no solution keeps its numbers.
/// `stages`: the sums over the groups.
pub fn solve_local(rules: &Rules, start: &[[i64; 4]], steps: i64, min_positions: bool) -> Result<Solved, Error> {
    let n = rules.roads;
    let mut x: Vec<[i64; 4]> = start.to_vec();
    let mut fixed = vec![false; n];
    for &(r, v) in &rules.fixed {
        x[r] = v;
        fixed[r] = true;
    }
    // the rules as (kind, index): 0 meet, 1 lift, 2 crossing, 3 order, 4 near
    let count = [rules.meets.len(), rules.lifts.len(), rules.crossings.len(), rules.orders.len(), rules.near.len()];
    let roads_of = |k: u8, i: usize| -> (usize, usize) {
        match k {
            0 => (rules.meets[i].0, rules.meets[i].2),
            1 => (rules.lifts[i].0, rules.lifts[i].1),
            2 => (rules.crossings[i].0, rules.crossings[i].1),
            3 => rules.orders[i],
            _ => (rules.near[i].0, rules.near[i].1),
        }
    };
    let broken = |x: &[[i64; 4]], k: u8, i: usize| -> bool {
        match k {
            0 => {
                let (a, ea, b, eb) = rules.meets[i];
                x[a][ea] > x[b][3] || x[b][eb] > x[a][3]
            }
            1 => x[rules.lifts[i].1][3] >= x[rules.lifts[i].0][rules.lifts[i].2],
            2 => x[rules.crossings[i].1][3] >= x[rules.crossings[i].0][rules.crossings[i].2],
            3 => x[rules.orders[i].1][3] >= x[rules.orders[i].0][3],
            _ => x[rules.near[i].1][3] >= x[rules.near[i].0][rules.near[i].2],
        }
    };
    // the groups: the roads that a broken rule joins
    let mut parent: Vec<u32> = (0..n as u32).collect();
    fn find(p: &mut [u32], mut v: usize) -> usize {
        while p[v] as usize != v {
            p[v] = p[p[v] as usize];
            v = p[v] as usize;
        }
        v
    }
    let mut bad = vec![false; n];
    for (k, &m) in count.iter().enumerate() {
        for i in 0..m {
            if broken(&x, k as u8, i) {
                let (a, b) = roads_of(k as u8, i);
                bad[a] = true;
                bad[b] = true;
                let (ra, rb) = (find(&mut parent, a), find(&mut parent, b));
                if ra != rb {
                    parent[ra.max(rb)] = ra.min(rb) as u32;
                }
            }
        }
    }
    let mut members: Vec<(u32, u32)> = (0..n).filter(|&r| bad[r]).map(|r| (find(&mut parent, r) as u32, r as u32)).collect();
    members.sort_unstable();
    drop((parent, bad));
    // the rules of each road
    let (at, of) = by_node::<(u8, u32)>(n, |put| {
        for (k, &m) in count.iter().enumerate() {
            for i in 0..m {
                let (a, b) = roads_of(k as u8, i);
                put(a, (k as u8, i as u32));
                if b != a {
                    put(b, (k as u8, i as u32));
                }
            }
        }
    });
    let mut stages = [0i64; 5];
    for group in members.chunk_by(|a, b| a.0 == b.0) {
        // the roads of the group first, then the roads around it; the rules that touch the group
        let mut roads: Vec<usize> = group.iter().map(|&(_, r)| r as usize).collect();
        let size = roads.len();
        let mut local: std::collections::HashMap<usize, usize> = roads.iter().enumerate().map(|(l, &r)| (r, l)).collect();
        let mut ids: Vec<(u8, u32)> = roads.iter().flat_map(|&r| of[at[r]..at[r + 1]].iter().copied()).collect();
        ids.sort_unstable();
        ids.dedup();
        for &(k, i) in &ids {
            let (a, b) = roads_of(k, i as usize);
            for v in [a, b] {
                if !local.contains_key(&v) {
                    local.insert(v, roads.len());
                    roads.push(v);
                }
            }
        }
        let m = |v: usize| local[&v];
        let mut sub = Rules { roads: roads.len(), ..Default::default() };
        for &(k, i) in &ids {
            let i = i as usize;
            match k {
                0 => {
                    let (a, ea, b, eb) = rules.meets[i];
                    sub.meets.push((m(a), ea, m(b), eb));
                }
                1 => {
                    let (u, l, h) = rules.lifts[i];
                    sub.lifts.push((m(u), m(l), h));
                }
                2 => {
                    let (c, p, h) = rules.crossings[i];
                    sub.crossings.push((m(c), m(p), h));
                }
                3 => sub.orders.push((m(rules.orders[i].0), m(rules.orders[i].1))),
                _ => {
                    let (u, l, h) = rules.near[i];
                    sub.near.push((m(u), m(l), h));
                }
            }
        }
        for (l, &r) in roads.iter().enumerate() {
            if l >= size || fixed[r] {
                sub.fixed.push((l, x[r]));
            }
        }
        let Ok((xs, st)) = numbers(&sub, steps, min_positions) else { continue };
        if feasible(&sub, &xs, steps).is_err() {
            continue;
        }
        let (nl, z) = (sub.roads, xs[xs.len() - 1]);
        for (l, &r) in roads[..size].iter().enumerate() {
            if !fixed[r] {
                x[r] = [xs[nl + 3 * l] - z, xs[nl + 3 * l + 1] - z, xs[nl + 3 * l + 2] - z, xs[l] - z];
            }
        }
        for (s, v) in stages.iter_mut().zip(st) {
            *s += v;
        }
    }
    // all numbers in the columns of the whole area (0 as the last node), the check of every hard rule, and the report
    let mut flat = vec![0i64; 4 * n + 3];
    for r in 0..n {
        flat[r] = x[r][3];
        for h in 0..3 {
            flat[col(n, r, h)] = x[r][h];
        }
    }
    feasible(rules, &flat, steps)?;
    Ok(report(n, &Cleaned::new(rules), &flat, stages))
}

/// The answer: the numbers of the parts and the rules that the numbers `x` do not keep.
fn report(n: usize, c: &Cleaned, x: &[i64], stages: [i64; 5]) -> Solved {
    let col = |r, h| col(n, r, h);
    let parts = (0..n).map(|r| [x[col(r, 0)], x[col(r, 1)], x[col(r, 2)], x[r]]).collect();
    let not_over = |&&(u, l, h): &&(usize, usize, usize)| x[l] - x[col(u, h)] > -1;
    let given_up_parts: Vec<(usize, usize, usize)> = c.lifts.iter().filter(not_over).copied().collect();
    let mut given_up: Vec<(usize, usize)> = given_up_parts.iter().map(|&(u, l, _)| (u, l)).collect();
    given_up.dedup();
    Solved {
        parts,
        given_up,
        given_up_parts,
        crossings_not_kept: c.crossings.iter().filter(|&&(cr, p, h)| x[p] - x[col(cr, h)] > -1).copied().collect(),
        orders_not_kept: c.orders.iter().filter(|&&(a, b)| x[b] - x[a] > -1).copied().collect(),
        near_not_kept: c.near.iter().filter(not_over).copied().collect(),
        stages,
    }
}


/// The check of an answer: every hard rule holds. Each casing part is not over its fill, the heads of two roads that meet are not
/// over the other road's fill, the fixed numbers are as given, and every number is in the box `[0, steps]` (all against node 0,
/// the last node). The stack rules, the order wishes and the near rules can break: the solve gives the broken ones.
fn feasible(rules: &Rules, x: &[i64], steps: i64) -> Result<(), Error> {
    let n = rules.roads;
    let (col, z) = (|r: usize, h: usize| n + 3 * r + h, x[x.len() - 1]);
    let bad = |what: String| Err(Error::Check(format!("levels: the answer breaks a hard rule ({what})")));
    for r in 0..n {
        for h in 0..3 {
            if x[col(r, h)] > x[r] {
                return bad(format!("road {r}: casing part {h} over its fill"));
            }
        }
    }
    for &(a, ea, b, eb) in &rules.meets {
        if x[col(a, ea)] > x[b] || x[col(b, eb)] > x[a] {
            return bad(format!(
                "roads {a} and {b} meet: a head over the other's fill"
            ));
        }
    }
    for &(r, v) in &rules.fixed {
        if [col(r, 0), col(r, 1), col(r, 2), r]
            .iter()
            .zip(v)
            .any(|(&c, v)| x[c] - z != v)
        {
            return bad(format!("road {r}: not at its fixed numbers"));
        }
    }
    if x[..4 * n].iter().any(|&v| v - z < 0 || v - z > steps) {
        return bad(format!("a number out of the box [0, {steps}]"));
    }
    Ok(())
}

/// The arcs whose kind has a capacity, as a network; and the index into `arcs` of each of its arcs.
fn network(arcs: &[Arc], nodes: usize, cap: impl Fn(Kind) -> Option<i64>) -> (Network, Vec<u32>) {
    let m = arcs.iter().filter(|a| cap(a.3).is_some()).count();
    let mut g = Network {
        nodes,
        ..Default::default()
    };
    g.reserve(m);
    let mut idx = Vec::with_capacity(m);
    for (a, &(i, j, w, kind)) in arcs.iter().enumerate() {
        if let Some(c) = cap(kind) {
            g.add(i as usize, j as usize, w as i64, c);
            idx.push(a as u32);
        }
    }
    (g, idx)
}

/// Potentials for the hard rules (the reduced cost of each arc is not negative): the shortest distances from an extra
/// node with an arc of cost 0 to each node, by a Bellman-Ford with a queue. An error when the rules have no solution.
fn potentials(arcs: &[Arc], nodes: usize) -> Result<Vec<i64>, Error> {
    let mut out: Vec<Vec<(usize, i64)>> = vec![Vec::new(); nodes];
    for &(i, j, w, kind) in arcs {
        if kind == Kind::Hard {
            out[i as usize].push((j as usize, w as i64));
        }
    }
    let mut dist = vec![0i64; nodes];
    let mut count = vec![0usize; nodes];
    let mut queued = vec![true; nodes];
    let mut queue: std::collections::VecDeque<usize> = (0..nodes).collect();
    while let Some(u) = queue.pop_front() {
        queued[u] = false;
        for &(v, w) in &out[u] {
            if dist[u] + w < dist[v] {
                dist[v] = dist[u] + w;
                if !queued[v] {
                    count[v] += 1;
                    if count[v] > nodes {
                        return Err(
                            Error::NoSolution("levels: the fixed numbers and the hard rules have no solution".into()),
                        );
                    }
                    queued[v] = true;
                    queue.push_back(v);
                }
            }
        }
    }
    Ok(dist)
}

/// The shortest distances from `from` in the hard rules, with a Dijkstra on the costs reduced by `pi`: potentials for
/// the last stage. Every node can be reached from L.
fn from_node(arcs: &[Arc], nodes: usize, from: usize, pi: &[i64]) -> Vec<i64> {
    let (start, out) = by_node(nodes, |put| {
        for &(i, j, w, kind) in arcs {
            if kind == Kind::Hard {
                let (i, j) = (i as usize, j as usize);
                put(i, (j as u32, w as i64 + pi[i] - pi[j]));
            }
        }
    });
    let mut dist = vec![i64::MAX; nodes];
    dist[from] = 0;
    let mut heap = BinaryHeap::from([Reverse((0i64, from))]);
    while let Some(Reverse((d, u))) = heap.pop() {
        if d > dist[u] {
            continue;
        }
        for &(v, c) in &out[start[u]..start[u + 1]] {
            debug_assert!(c >= 0);
            let v = v as usize;
            if d + c < dist[v] {
                dist[v] = d + c;
                heap.push(Reverse((d + c, v)));
            }
        }
    }
    (0..nodes).map(|v| dist[v] - pi[from] + pi[v]).collect()
}

/// roadstyle's numbers from the flow: the shortest distances from an extra node (an arc of cost 0 to each node) in
/// the graph of the rules that the flow leaves (`x_i <= x_j + w` while arc i -> j has room, `x_j <= x_i - w` while
/// it has flow), shifted to start at 0. There is one such answer for each set of rules. `-pi` already keeps the rules,
/// so Dijkstra runs on the costs reduced by it.
fn least_numbers(g: &Network, flow: &[i64], pi: &[i64]) -> Vec<i64> {
    let n = g.nodes;
    let p: Vec<i64> = pi.iter().map(|v| -v).collect();
    // each entry: the next node and the arc, 8 bytes; the high bit says that the arc is used backwards (it has flow). The cost
    // reduced by p comes from the arc when the entry is read: ±w + p[u] - p[v]
    const BACK: u32 = 1 << 31;
    assert!(g.from.len() < BACK as usize, "levels: more than 2^31 arcs");
    let (start, out) = by_node(n, |put| {
        for k in 0..g.from.len() {
            let (i, j) = (g.from[k] as usize, g.to[k] as usize);
            if flow[k] < g.cap[k] {
                put(j, (i as u32, k as u32));
            }
            if flow[k] > 0 {
                put(i, (j as u32, k as u32 | BACK));
            }
        }
    });
    let top = *p.iter().max().unwrap();
    let mut dist: Vec<i64> = p.iter().map(|&v| top - v).collect(); // the arcs from the extra node
    let mut heap: BinaryHeap<Reverse<(i64, usize)>> =
        (0..n).map(|v| Reverse((dist[v], v))).collect();
    while let Some(Reverse((d, u))) = heap.pop() {
        if d > dist[u] {
            continue;
        }
        for &(v, k) in &out[start[u]..start[u + 1]] {
            let v = v as usize;
            let w = g.cost[(k & !BACK) as usize];
            let c = if k & BACK == 0 { w } else { -w } + p[u] - p[v];
            debug_assert!(c >= 0);
            if d + c < dist[v] {
                dist[v] = d + c;
                heap.push(Reverse((d + c, v)));
            }
        }
    }
    let x: Vec<i64> = (0..n).map(|v| dist[v] - top + p[v]).collect();
    let low = *x[..n - 1].iter().min().unwrap();
    x.iter().map(|v| v - low).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_bridge_over_a_road() {
        // road 0 (the bridge) crosses road 1 with its main part
        let r = Rules {
            roads: 2,
            lifts: vec![(0, 1, 1)],
            ..Default::default()
        };
        let s = solve(&r, 20, true).unwrap();
        let [_, a0m, _, b0] = s.parts[0];
        let [_, _, _, b1] = s.parts[1];
        assert!(a0m > b1 && b0 >= a0m, "{:?}", s.parts);
        assert!(s.given_up.is_empty() && s.stages[0] == 0);
    }

    #[test]
    fn four_bands_in_three_numbers() {
        // four roads that cross at one point, each over the ones below it, in a box of 3 numbers: one stack pair gives way
        let mut lifts = Vec::new();
        for u in 0..4 {
            for l in 0..u {
                lifts.push((u, l, 1));
            }
        }
        let r = Rules {
            roads: 4,
            lifts,
            ..Default::default()
        };
        let s = solve(&r, 2, true).unwrap();
        assert_eq!((s.given_up.len(), s.stages[0]), (1, 1), "{:?}", s.parts);
        assert!(s.parts.iter().flatten().all(|&x| (0..=2).contains(&x)));
    }

    #[test]
    fn a_ring_of_wishes_cannot_all_hold() {
        // three roads that meet in a ring, each one wants to be over the next one: one wish is broken
        let r = Rules {
            roads: 3,
            meets: vec![(0, 2, 1, 0), (1, 2, 2, 0), (2, 2, 0, 0)],
            orders: vec![(0, 1), (1, 2), (2, 0)],
            ..Default::default()
        };
        let s = solve(&r, 20, true).unwrap();
        assert!(!s.orders_not_kept.is_empty(), "{:?}", s.parts);
        assert_eq!(s.stages[2], 3); // around the ring the misses add up to 3 steps, however they are shared
    }
}
