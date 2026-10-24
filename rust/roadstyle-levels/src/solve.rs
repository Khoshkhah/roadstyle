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
    /// The order wishes that are not kept.
    pub orders_not_kept: Vec<(usize, usize)>,
    /// The near parts `(upper, lower, part)` that are not over the lower fill.
    pub near_not_kept: Vec<(usize, usize, usize)>,
    /// The best value of each stage (roadstyle's objectives): the steps by which the stack rules are broken, the
    /// same for the order wishes and for the near rules, and the cost (the casings, and the span with its weight).
    pub stages: [i64; 4],
}

#[derive(Clone, Copy, PartialEq)]
enum Kind {
    Hard,
    Stack,
    Order,
    Near,
    Gone,
}

/// The numbers are in a box of `steps + 1` values (roadstyle's `2 * max_level / margin`); `min_positions`: the span of the numbers is
/// as small as possible.
pub fn solve(rules: &Rules, steps: i64, min_positions: bool) -> Result<Solved, String> {
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
    arcs.push((hi, z, steps, Kind::Hard)); // the box [0, steps]; z is 0
    arcs.push((z, lo, 0, Kind::Hard));
    let mut lifts = rules.lifts.clone();
    lifts.sort_unstable();
    lifts.dedup();
    let mut orders = rules.orders.clone();
    orders.sort_unstable();
    orders.dedup();
    // a part that is a stack and a near rule is a stack
    let mut near: Vec<(usize, usize, usize)> = rules
        .near
        .iter()
        .copied()
        .filter(|p| lifts.binary_search(p).is_err())
        .collect();
    near.sort_unstable();
    near.dedup();
    for &(r, v) in &rules.fixed {
        for (c, x) in [col(r, 0), col(r, 1), col(r, 2), r].into_iter().zip(v) {
            arcs.push((c, z, x, Kind::Hard)); // x_c = x: x_c - x_z <= x and x_z - x_c <= -x
            arcs.push((z, c, -x, Kind::Hard));
        }
    }
    for &(u, l, h) in &lifts {
        arcs.push((l, col(u, h), -1, Kind::Stack)); // H3: b_l + 1 <= a_(u, h)
    }
    for &(u, l, h) in &near {
        arcs.push((l, col(u, h), -1, Kind::Near));
    }
    for &(x, y) in &orders {
        arcs.push((y, x, -1, Kind::Order)); // H4: b_y + 1 <= b_x
    }
    let nodes = 4 * n + 3;
    let mut pi = vec![0i64; nodes];
    if !rules.fixed.is_empty() {
        pi = potentials(&arcs, nodes)?; // the arcs of the fixed numbers have negative costs
    }
    let mut stages = [0i64; 4];
    for (s, soft) in [Kind::Stack, Kind::Order, Kind::Near]
        .into_iter()
        .enumerate()
    {
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
    // than any sum, so this is two steps: first the least span, then the least sum at that span. The least span is minus
    // the shortest distance from L to H in all the hard rules (also the rules through H, L and 0 that the stages made
    // equalities, and the fixed numbers); an arc H -> L of that cost keeps it, and the flow carries only the casing parts.
    // The best numbers are the same. (As a supply of w4 at H and L, the flow took 260 phases on Burnaby: 17 s.)
    let w4 = 3 * n as i64 * steps + 1;
    pi = from_node(&arcs, nodes, lo, &pi);
    let span = -pi[hi];
    if min_positions {
        arcs.push((hi, lo, span, Kind::Hard));
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
    let w4 = if min_positions { w4 } else { 0 };
    stages[3] = w4 * span - (0..g.from.len()).map(|e| flow[e] * g.cost[e]).sum::<i64>();
    let x = least_numbers(&g, &flow, &pi);
    feasible(rules, &x, steps)?;
    let parts = (0..n)
        .map(|r| [x[col(r, 0)], x[col(r, 1)], x[col(r, 2)], x[r]])
        .collect();
    let given_up_parts: Vec<(usize, usize, usize)> = lifts
        .iter()
        .copied()
        .filter(|&(u, l, h)| x[l] - x[col(u, h)] > -1)
        .collect();
    let mut given_up: Vec<(usize, usize)> =
        given_up_parts.iter().map(|&(u, l, _)| (u, l)).collect();
    given_up.dedup();
    let orders_not_kept = orders
        .iter()
        .copied()
        .filter(|&(a, b)| x[b] - x[a] > -1)
        .collect();
    let near_not_kept = near
        .iter()
        .copied()
        .filter(|&(u, l, h)| x[l] - x[col(u, h)] > -1)
        .collect();
    Ok(Solved {
        parts,
        given_up,
        given_up_parts,
        orders_not_kept,
        near_not_kept,
        stages,
    })
}

/// The check of an answer: every hard rule holds. Each casing part is not over its fill, the heads of two roads that meet are not
/// over the other road's fill, the fixed numbers are as given, and every number is in the box `[0, steps]` (all against node 0,
/// the last node). The stack rules, the order wishes and the near rules can break: the solve gives the broken ones.
fn feasible(rules: &Rules, x: &[i64], steps: i64) -> Result<(), String> {
    let n = rules.roads;
    let (col, z) = (|r: usize, h: usize| n + 3 * r + h, x[x.len() - 1]);
    let bad = |what: String| Err(format!("levels: the answer breaks a hard rule ({what})"));
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

/// Potentials for the hard rules (the reduced cost of each arc is not negative): the shortest distances from an extra
/// node with an arc of cost 0 to each node, by a Bellman-Ford with a queue. An error when the rules have no solution.
fn potentials(arcs: &[(usize, usize, i64, Kind)], nodes: usize) -> Result<Vec<i64>, String> {
    let mut out: Vec<Vec<(usize, i64)>> = vec![Vec::new(); nodes];
    for &(i, j, w, kind) in arcs {
        if kind == Kind::Hard {
            out[i].push((j, w));
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
                            "levels: the fixed numbers and the hard rules have no solution".into(),
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
fn from_node(
    arcs: &[(usize, usize, i64, Kind)],
    nodes: usize,
    from: usize,
    pi: &[i64],
) -> Vec<i64> {
    let mut out: Vec<Vec<(u32, i64)>> = vec![Vec::new(); nodes];
    for &(i, j, w, kind) in arcs {
        if kind == Kind::Hard {
            out[i].push((j as u32, w + pi[i] - pi[j]));
        }
    }
    let mut dist = vec![i64::MAX; nodes];
    dist[from] = 0;
    let mut heap = BinaryHeap::from([Reverse((0i64, from))]);
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
    (0..nodes).map(|v| dist[v] - pi[from] + pi[v]).collect()
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
        assert_eq!(s.stages[1], 3); // around the ring the misses add up to 3 steps, however they are shared
    }
}
