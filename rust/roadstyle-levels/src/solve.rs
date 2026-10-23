//! The numbers of the roads from their rules (roadstyle's `_solve_intervals`, docs/levels.md): the stages as minimum-cost
//! flows. Each stage keeps the best value of the stage before it: a rule with flow holds as an equality, a soft rule
//! that the stage did not break becomes hard, and a broken rule holds in the other direction.

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
    /// `(higher, lower)`: the fill of the higher road is over the fill of the lower road where they meet (a wish).
    pub orders: Vec<(usize, usize)>,
}

#[derive(Clone, Debug, Default)]
pub struct Solved {
    /// `[casing_start, casing_level, casing_end, fill_level]` of each road, not yet moved to the ground.
    pub parts: Vec<[i64; 4]>,
    /// The stack pairs `(upper, lower)` with a lifted part that is not over the lower fill.
    pub given_up: Vec<(usize, usize)>,
    /// The order wishes that are not kept.
    pub orders_not_kept: Vec<(usize, usize)>,
    /// The best value of each stage (roadstyle's objectives): the steps by which the stack rules are broken, the
    /// same for the order wishes, and the cost (the casings, and the span with its weight).
    pub stages: [i64; 3],
}

#[derive(Clone, Copy, PartialEq)]
enum Kind {
    Hard,
    Stack,
    Order,
    Gone,
}

/// roadstyle's defaults: `max_level` 20 (the numbers are in a box of 2 * 20 + 1 values), `margin` 1, `min_positions`.
pub fn solve(rules: &Rules, max_level: i64) -> Result<Solved, String> {
    let n = rules.roads;
    if n == 0 {
        return Ok(Solved::default());
    }
    let col = |r: usize, h: usize| n + 3 * r + h;
    let (hi, lo, z) = (4 * n, 4 * n + 1, 4 * n + 2);
    // every rule x_i - x_j <= w is an arc i -> j of cost w
    let mut arcs: Vec<(usize, usize, i64, Kind)> = Vec::new();
    for r in 0..n {
        for h in 0..3 {
            arcs.push((col(r, h), r, 0, Kind::Hard)); // H1: a casing part not over its own fill
        }
    }
    for &(x, ex, y, ey) in &rules.meets {
        arcs.push((col(x, ex), y, 0, Kind::Hard)); // H2: the heads of two roads that meet, under the other's fill
        arcs.push((col(y, ey), x, 0, Kind::Hard));
    }
    for v in 0..4 * n {
        arcs.push((v, hi, 0, Kind::Hard)); // the span: every number between L and H
        arcs.push((lo, v, 0, Kind::Hard));
    }
    arcs.push((hi, z, 2 * max_level, Kind::Hard)); // the box [0, 2 max_level]; z is 0
    arcs.push((z, lo, 0, Kind::Hard));
    let mut lifts = rules.lifts.clone();
    lifts.sort_unstable();
    lifts.dedup();
    let mut orders = rules.orders.clone();
    orders.sort_unstable();
    orders.dedup();
    for &(u, l, h) in &lifts {
        arcs.push((l, col(u, h), -1, Kind::Stack)); // H3: b_l + 1 <= a_(u, h)
    }
    for &(x, y) in &orders {
        arcs.push((y, x, -1, Kind::Order)); // H4: b_y + 1 <= b_x
    }
    let nodes = 4 * n + 3;
    let mut pi = vec![0i64; nodes];
    let mut stages = [0i64; 3];
    for (s, soft) in [Kind::Stack, Kind::Order].into_iter().enumerate() {
        if !arcs.iter().any(|a| a.3 == soft) {
            continue;
        }
        let (g, idx) = network(&arcs, nodes, |k| match k {
            Kind::Hard => Some(INF),
            k if k == soft => Some(1),
            _ => None,
        });
        let flow = g.solve(&vec![0; nodes], &mut pi)?;
        stages[s] = -(0..idx.len()).map(|e| flow[e] * g.cost[e]).sum::<i64>(); // the value of the LP (duality)
        let mut more = Vec::new();
        for (e, &a) in idx.iter().enumerate() {
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
        arcs.extend(more);
    }
    // the cost: the sum of (b - a) over all casing parts, and a large weight w4 on the span H - L. The weight is larger
    // than any sum, so this is two steps: first the least span, then the least sum at that span. The least span is the
    // longest chain of the rules (`least_span`); the box then has that size, and the flow carries only the casing
    // parts. The best numbers are the same. (As a supply of w4 at H and L, the flow took 260 phases on Burnaby: 17 s.)
    let w4 = 3 * n as i64 * 2 * max_level + 1;
    let (span, start) = least_span(&arcs, 4 * n, &pi);
    pi = start;
    for a in arcs.iter_mut().filter(|a| a.0 == hi && a.1 == z) {
        a.2 = span;
    }
    let mut supply = vec![0i64; nodes];
    for r in 0..n {
        for h in 0..3 {
            supply[r] -= 1;
            supply[col(r, h)] += 1;
        }
    }
    let (g, _) = network(&arcs, nodes, |k| (k == Kind::Hard).then_some(INF));
    let flow = g.solve(&supply, &mut pi)?;
    stages[2] = w4 * span - (0..g.from.len()).map(|e| flow[e] * g.cost[e]).sum::<i64>();
    let x = least_numbers(&g, &flow, &pi);
    let parts = (0..n)
        .map(|r| [x[col(r, 0)], x[col(r, 1)], x[col(r, 2)], x[r]])
        .collect();
    let mut given_up: Vec<(usize, usize)> = lifts
        .iter()
        .filter(|&&(u, l, h)| x[l] - x[col(u, h)] > -1)
        .map(|&(u, l, _)| (u, l))
        .collect();
    given_up.dedup();
    let orders_not_kept = orders
        .iter()
        .copied()
        .filter(|&(a, b)| x[b] - x[a] > -1)
        .collect();
    Ok(Solved {
        parts,
        given_up,
        orders_not_kept,
        stages,
    })
}

/// The arcs whose kind has a capacity, as a network; and the index into `arcs` of each of its arcs.
fn network(
    arcs: &[(usize, usize, i64, Kind)],
    nodes: usize,
    cap: impl Fn(Kind) -> Option<i64>,
) -> (Network, Vec<usize>) {
    let mut g = Network {
        nodes,
        ..Default::default()
    };
    let mut idx = Vec::new();
    for (a, &(i, j, w, kind)) in arcs.iter().enumerate() {
        if let Some(c) = cap(kind) {
            g.add(i, j, w, c);
            idx.push(a);
        }
    }
    (g, idx)
}

/// The least span of the numbers of the `roads` first nodes (all except H, L and 0) under the hard rules: minus the
/// shortest distance from a node to another one, with a Dijkstra on the costs reduced by `pi`. Also returns potentials
/// for the last stage: the distances from an extra node with an arc of cost 0 to each node (they are 0 or less), with H
/// at the least distance and L and 0 at 0 (the box of size `span`).
fn least_span(arcs: &[(usize, usize, i64, Kind)], roads: usize, pi: &[i64]) -> (i64, Vec<i64>) {
    let mut out: Vec<Vec<(u32, i64)>> = vec![Vec::new(); roads];
    for &(i, j, w, kind) in arcs {
        if kind == Kind::Hard && i < roads && j < roads {
            out[i].push((j as u32, w + pi[i] - pi[j]));
        }
    }
    // an extra node with an arc of cost 0 to each node; `top` keeps its reduced costs not negative
    let top = *pi[..roads].iter().max().unwrap();
    let mut dist: Vec<i64> = pi[..roads].iter().map(|&p| top - p).collect();
    let mut heap: BinaryHeap<Reverse<(i64, usize)>> =
        (0..roads).map(|v| Reverse((dist[v], v))).collect();
    while let Some(Reverse((d, u))) = heap.pop() {
        if d > dist[u] {
            continue;
        }
        for &(v, c) in &out[u] {
            debug_assert!(c >= 0);
            let v = v as usize;
            if d + c < dist[v] {
                dist[v] = d + c;
                heap.push(Reverse((d + c, v)));
            }
        }
    }
    let mut start: Vec<i64> = (0..roads).map(|v| dist[v] - top + pi[v]).collect();
    let span = -*start.iter().min().unwrap();
    start.extend([-span, 0, 0]); // H, L and 0
    (span, start)
}

/// roadstyle's numbers from the flow: the shortest distances from an extra node (an arc of cost 0 to each node) in
/// the graph of the rules that the flow leaves (`x_i <= x_j + w` while arc i -> j has room, `x_j <= x_i - w` while
/// it has flow), shifted to start at 0. There is one such answer for each set of rules. `-pi` already keeps the rules,
/// so Dijkstra runs on the costs reduced by it.
fn least_numbers(g: &Network, flow: &[i64], pi: &[i64]) -> Vec<i64> {
    let n = g.nodes;
    let p: Vec<i64> = pi.iter().map(|v| -v).collect();
    let mut out: Vec<Vec<(u32, i64)>> = vec![Vec::new(); n];
    for k in 0..g.from.len() {
        let (i, j, w) = (g.from[k] as usize, g.to[k] as usize, g.cost[k]);
        if flow[k] < g.cap[k] {
            out[j].push((i as u32, w + p[j] - p[i]));
        }
        if flow[k] > 0 {
            out[i].push((j as u32, -w + p[i] - p[j]));
        }
    }
    let top = *p.iter().max().unwrap();
    let mut dist: Vec<i64> = p.iter().map(|&v| top - v).collect(); // the arcs from the extra node
    let mut heap: BinaryHeap<Reverse<(i64, usize)>> =
        (0..n).map(|v| Reverse((dist[v], v))).collect();
    while let Some(Reverse((d, u))) = heap.pop() {
        if d > dist[u] {
            continue;
        }
        for &(v, c) in &out[u] {
            debug_assert!(c >= 0);
            let v = v as usize;
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
        let s = solve(&r, 20).unwrap();
        let [_, a0m, _, b0] = s.parts[0];
        let [_, _, _, b1] = s.parts[1];
        assert!(a0m > b1 && b0 >= a0m, "{:?}", s.parts);
        assert!(s.given_up.is_empty() && s.stages[0] == 0);
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
        let s = solve(&r, 20).unwrap();
        assert!(!s.orders_not_kept.is_empty(), "{:?}", s.parts);
        assert_eq!(s.stages[1], 3); // around the ring the misses add up to 3 steps, however they are shared
    }
}
