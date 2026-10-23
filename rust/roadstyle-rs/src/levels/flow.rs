//! A minimum-cost flow with whole numbers: the primal-dual algorithm (Dijkstra on the reduced costs, then a maximum
//! flow on the arcs of reduced cost 0). The costs of the levels are small (0, -1 and the span), so there are few
//! rounds. docs/levels.md, "The finding".

use std::cmp::Reverse;
use std::collections::{BinaryHeap, VecDeque};

/// The capacity of an arc with no limit.
pub const INF: i64 = i64::MAX / 4;

/// Arcs `from -> to` with a cost and a capacity (lower bound 0).
#[derive(Clone, Debug, Default)]
pub struct Network {
    pub nodes: usize,
    pub from: Vec<u32>,
    pub to: Vec<u32>,
    pub cost: Vec<i64>,
    pub cap: Vec<i64>,
}

impl Network {
    pub fn add(&mut self, from: usize, to: usize, cost: i64, cap: i64) {
        self.from.push(from as u32);
        self.to.push(to as u32);
        self.cost.push(cost);
        self.cap.push(cap);
    }

    fn reduced(&self, k: usize, pi: &[i64]) -> i64 {
        self.cost[k] + pi[self.from[k] as usize] - pi[self.to[k] as usize]
    }

    /// The flow of least cost that sends `supply[v]` out of each node (a negative supply comes in). `pi` is the start
    /// potential: the reduced cost `cost + pi[from] - pi[to]` of each arc without a limit must not be negative. The
    /// arcs with a limit and a negative reduced cost start full. Returns the flow, and the potentials in `pi`. After
    /// the solve, the flow and `pi` are checked: they agree (complementary slackness), so the flow is the best one.
    pub fn solve(&self, supply: &[i64], pi: &mut [i64]) -> Result<Vec<i64>, String> {
        let (n, m) = (self.nodes, self.from.len());
        let mut flow = vec![0i64; m];
        let mut excess = supply.to_vec();
        for k in 0..m {
            if self.reduced(k, pi) < 0 {
                if self.cap[k] >= INF {
                    return Err("the hard rules have no solution (a loop of rules)".into());
                }
                flow[k] = self.cap[k];
                excess[self.from[k] as usize] -= flow[k];
                excess[self.to[k] as usize] += flow[k];
            }
        }
        // the residual arcs of each node: 2k is arc k forward, 2k + 1 is arc k backward
        let mut start = vec![0usize; n + 1];
        for k in 0..m {
            start[self.from[k] as usize + 1] += 1;
            start[self.to[k] as usize + 1] += 1;
        }
        for v in 0..n {
            start[v + 1] += start[v];
        }
        let mut adj = vec![0u32; 2 * m];
        let mut fill = start.clone();
        for k in 0..m {
            for (v, r) in [(self.from[k], 2 * k), (self.to[k], 2 * k + 1)] {
                adj[fill[v as usize]] = r as u32;
                fill[v as usize] += 1;
            }
        }
        let arc = |r: usize, flow: &[i64]| self.residual(r, flow);
        let mut dist = vec![i64::MAX; n];
        let mut level = vec![u32::MAX; n];
        let mut next = vec![0usize; n];
        loop {
            if excess.iter().all(|&e| e <= 0) {
                break;
            }
            // Dijkstra from all nodes with excess, up to the first node that takes flow
            dist.fill(i64::MAX);
            let mut heap = BinaryHeap::new();
            for v in 0..n {
                if excess[v] > 0 {
                    dist[v] = 0;
                    heap.push(Reverse((0i64, v)));
                }
            }
            let mut reach = None;
            while let Some(Reverse((d, u))) = heap.pop() {
                if d > dist[u] {
                    continue;
                }
                if excess[u] < 0 {
                    reach = Some(d);
                    break;
                }
                for &r in &adj[start[u]..start[u + 1]] {
                    let (v, res, c) = arc(r as usize, &flow);
                    if res > 0 {
                        let nd = d + c + pi[u] - pi[v];
                        if nd < dist[v] {
                            dist[v] = nd;
                            heap.push(Reverse((nd, v)));
                        }
                    }
                }
            }
            let reach =
                reach.ok_or("the supplies cannot be sent (no path to a node that takes them)")?;
            for v in 0..n {
                pi[v] += dist[v].min(reach);
            }
            // A push-relabel on the arcs of reduced cost 0 (FIFO, with a global relabel from time to time): it moves the
            // excess to the nodes that take flow until no such path is left. It has no phases: Dinic needed 274 phases,
            // each a search of the whole graph, in the last stage of Burnaby (17 s). A node at height n has no path left.
            let top = n as u32;
            let mut work = usize::MAX; // a global relabel first
            let mut active = VecDeque::new();
            let mut queued = vec![false; n];
            loop {
                if work > n + adj.len() {
                    // the heights: the distances to the nodes that take flow, by a backward search
                    self.heights(&start, &adj, &flow, pi, &excess, &mut level);
                    next.copy_from_slice(&start[..n]);
                    active.clear();
                    for v in 0..n {
                        queued[v] = excess[v] > 0 && level[v] < top;
                        if queued[v] {
                            active.push_back(v);
                        }
                    }
                    work = 0;
                }
                let Some(u) = active.pop_front() else { break };
                queued[u] = false;
                while excess[u] > 0 && level[u] < top {
                    if next[u] == start[u + 1] {
                        // relabel: one above the lowest node that u can push to
                        let mut h = top;
                        for &r in &adj[start[u]..start[u + 1]] {
                            let (v, res, c) = arc(r as usize, &flow);
                            if res > 0 && c + pi[u] - pi[v] == 0 {
                                h = h.min(level[v] + 1);
                            }
                        }
                        level[u] = h;
                        next[u] = start[u];
                        work += start[u + 1] - start[u] + 12;
                        continue;
                    }
                    let r = adj[next[u]] as usize;
                    let (v, res, c) = arc(r, &flow);
                    if res > 0 && c + pi[u] - pi[v] == 0 && level[u] == level[v] + 1 {
                        let amount = excess[u].min(res);
                        if r.is_multiple_of(2) {
                            flow[r / 2] += amount;
                        } else {
                            flow[r / 2] -= amount;
                        }
                        excess[u] -= amount;
                        excess[v] += amount;
                        if excess[v] > 0 && !queued[v] {
                            queued[v] = true;
                            active.push_back(v);
                        }
                        if amount < res {
                            break; // u has no excess left, and the arc has room for the next time
                        }
                    }
                    next[u] += 1;
                }
            }
        }
        if excess.iter().any(|&e| e != 0) {
            return Err("the supplies do not sum to 0".into());
        }
        self.check(supply, &flow, pi)?;
        Ok(flow)
    }

    /// A residual arc `r` (2k: arc k forward, 2k + 1: arc k backward): its head, its room and its cost.
    fn residual(&self, r: usize, flow: &[i64]) -> (usize, i64, i64) {
        let k = r / 2;
        if r.is_multiple_of(2) {
            (self.to[k] as usize, self.cap[k] - flow[k], self.cost[k])
        } else {
            (self.from[k] as usize, flow[k], -self.cost[k])
        }
    }

    /// The heights of the push-relabel: the number of arcs of reduced cost 0 with room from each node to a node that
    /// takes flow (negative excess), or n if there is no such path.
    fn heights(
        &self,
        start: &[usize],
        adj: &[u32],
        flow: &[i64],
        pi: &[i64],
        excess: &[i64],
        height: &mut [u32],
    ) {
        let n = height.len();
        height.fill(n as u32);
        let mut queue: Vec<usize> = (0..n).filter(|&v| excess[v] < 0).collect();
        for &v in &queue {
            height[v] = 0;
        }
        let mut i = 0;
        while i < queue.len() {
            let v = queue[i];
            i += 1;
            // the arcs into v: the partners of the residual arcs out of v
            for &r in &adj[start[v]..start[v + 1]] {
                let back = r as usize ^ 1;
                let (head, res, c) = self.residual(back, flow);
                debug_assert_eq!(head, v);
                let u = if r % 2 == 0 {
                    self.to[r as usize / 2] as usize
                } else {
                    self.from[r as usize / 2] as usize
                };
                if res > 0 && height[u] == n as u32 && c + pi[u] - pi[v] == 0 {
                    height[u] = height[v] + 1;
                    queue.push(u);
                }
            }
        }
    }

    /// The proof that `flow` is the best flow: it keeps the supplies and the capacities, and no arc has a reduced
    /// cost against it (negative with room, or positive with flow).
    fn check(&self, supply: &[i64], flow: &[i64], pi: &[i64]) -> Result<(), String> {
        let mut net = supply.to_vec();
        for k in 0..self.from.len() {
            let f = flow[k];
            if f < 0 || f > self.cap[k] || f >= INF {
                return Err(format!("flow check: arc {k} has the flow {f}"));
            }
            net[self.from[k] as usize] -= f;
            net[self.to[k] as usize] += f;
            let rc = self.reduced(k, pi);
            if (rc < 0 && f < self.cap[k]) || (rc > 0 && f > 0) {
                return Err(format!(
                    "flow check: arc {k} has the reduced cost {rc} and the flow {f}"
                ));
            }
        }
        if net.iter().any(|&e| e != 0) {
            return Err("flow check: a supply is not kept".into());
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn two_paths() {
        // 0 -> 3 through 1 (cost 1 + 1, limit 2) or through 2 (cost 5 + 0): 3 units, 2 on the cheap path
        let mut g = Network {
            nodes: 4,
            ..Default::default()
        };
        g.add(0, 1, 1, 2);
        g.add(1, 3, 1, INF);
        g.add(0, 2, 5, INF);
        g.add(2, 3, 0, INF);
        let mut pi = vec![0; 4];
        let f = g.solve(&[3, 0, 0, -3], &mut pi).unwrap();
        assert_eq!(f, vec![2, 2, 1, 1]);
    }

    #[test]
    fn negative_loop_with_limits() {
        // a loop of cost -1 + -1 + 1: each arc has a limit of 1, so one unit goes round
        let mut g = Network {
            nodes: 3,
            ..Default::default()
        };
        g.add(0, 1, -1, 1);
        g.add(1, 2, -1, 1);
        g.add(2, 0, 1, INF);
        let mut pi = vec![0; 3];
        let f = g.solve(&[0, 0, 0], &mut pi).unwrap();
        assert_eq!(f, vec![1, 1, 1]);
    }

    #[test]
    fn a_loop_of_hard_rules_is_an_error() {
        let mut g = Network {
            nodes: 2,
            ..Default::default()
        };
        g.add(0, 1, -1, INF);
        g.add(1, 0, 0, INF);
        assert!(g.solve(&[0, 0], &mut [0, 0]).is_err());
    }
}
