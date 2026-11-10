//! A run, and the place of each vehicle at a clock time (docs/design/vehicles_spec.md, sections 4.3 and 4.4).
//!
//! Between two samples a, b of a vehicle:
//! - lane placement: the vehicle moves along the chain of lanes from a's lane to b's lane (the network's connections,
//!   also the internal lanes of junctions). Its distance along the chain is a cubic Hermite curve with the simulated
//!   speeds at both ends. Its middle is half its length behind the front bumper (SUMO's `pos`), along the lanes, so a
//!   curve is correct. A lane change moves it sideways with a smoothstep over `lane_change_s`, centred on the sample
//!   where SUMO changed the lane.
//! - lon/lat placement: a straight line between the two middles, the heading on the shortest turn.
//! - a jump longer than `teleport_m` (a SUMO teleport) is not interpolated: the vehicle is hidden between the samples.

use crate::fcd::{Samples, NONE};
use crate::geo::{dist_m, heading_deg, offset, turn_deg};

/// The lanes kept behind a chain: enough for half the length of a long vehicle over short lanes.
const BACK_LANES: usize = 8;
/// The most lanes in a chain between two samples. A vehicle crosses few lanes in one step, but a cluster of short edges has many: on
/// Monaco, chains of 7 lanes span only 3 to 8 m.
const MAX_CHAIN: usize = 16;
use crate::net::{Net, VTypeRow};
use crate::Error;
use std::collections::{HashMap, VecDeque};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Placement {
    Lane,
    LonLat,
}

#[derive(Debug, Clone)]
pub struct RunOptions {
    pub placement: Placement,
    pub teleport_m: f64,
    pub lane_change_s: f64,
    pub heading_lookahead_m: f64,
    /// the default length, width and height of each vehicle class (the profile's `vehicles.sizes`); a class that a
    /// vehicle type needs and that is not here is an error
    pub class_sizes: HashMap<String, [f32; 3]>,
}

/// One vehicle at one clock time.
#[derive(Debug, Clone, PartialEq)]
pub struct VehicleState {
    /// index into the run's vehicle ids
    pub vehicle: u32,
    /// the middle of the vehicle
    pub lon: f64,
    pub lat: f64,
    /// degrees, 0 = north, clockwise
    pub heading: f64,
    pub speed: f64,
    /// index into the run's lane ids (the lane of the sample before the clock time); NONE when the file has none
    pub lane: u32,
    pub vtype: u16,
    /// the vehicle's middle is on a tunnel lane (Run::set_tunnel_edges)
    pub tunnel: bool,
    /// the roads under the vehicle's middle: (net lane, drawn metres along its line, weight). One entry on a lane, two or three during a
    /// lane change, with the weights of the position's blend (their sum is 1). Empty with lon/lat placement. The vehicle's height comes
    /// from these roads (docs/design/road_heights.md), never from the ground at its lon/lat
    pub roads: Vec<(u32, f64, f64)>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Report {
    pub samples: usize,
    pub vehicles: usize,
    pub t0: f64,
    pub t1: f64,
    /// rows of the file with no vehicle (a time step with no vehicle)
    pub empty_rows: usize,
    /// samples whose lane is not in the network: placed by their lon/lat
    pub lanes_unknown: usize,
    /// pairs of samples with no chain of lanes between them: placed by their lon/lat
    pub path_gaps: usize,
    /// pairs of samples farther apart than `teleport_m`: the vehicle is hidden between them
    pub teleports: usize,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Kind {
    Lane,
    LonLat,
    Teleport,
}

/// The way from one sample of a vehicle to its next.
#[derive(Debug, Clone)]
struct Pair {
    kind: Kind,
    /// net lanes from a's lane to the lane of b's edge that the connections reach
    chain: Vec<u32>,
    /// the net lanes the vehicle drove before the chain, the nearest first (for a middle behind the chain's start)
    back: Vec<u32>,
    /// b's lane when it is not the chain's last lane (a lane change at b); NONE when there is none
    to: u32,
}

pub struct Run {
    pub samples: Samples,
    pub net: Option<Net>,
    pub opts: RunOptions,
    /// the sizes of each vehicle type (index = `samples.vtype`)
    pub sizes: Vec<[f32; 3]>,
    rows: Vec<Vec<u32>>,
    pairs: Vec<Vec<Pair>>,
    /// samples' lane index -> net lane index (NONE: not in the network)
    lane_net: Vec<u32>,
    /// net lane -> tunnel (set_tunnel_edges); empty: no lane is a tunnel
    tunnel: Vec<bool>,
    report: Report,
}

fn smoothstep(x: f64) -> f64 {
    let x = x.clamp(0.0, 1.0);
    x * x * (3.0 - 2.0 * x)
}

/// Cubic Hermite from 0 to `l` over the unit interval, with end slopes m0, m1 (metres per interval). The slopes are
/// limited to 3 l, so the curve does not go backward.
fn hermite(u: f64, l: f64, m0: f64, m1: f64) -> f64 {
    if l <= 0.0 {
        return 0.0;
    }
    let (m0, m1) = (m0.clamp(0.0, 3.0 * l), m1.clamp(0.0, 3.0 * l));
    let (u2, u3) = (u * u, u * u * u);
    (u3 - 2.0 * u2 + u) * m0 + (-2.0 * u3 + 3.0 * u2) * l + (u3 - u2) * m1
}

impl Run {
    /// Builds a run. `net` is required for lane placement; `vtypes` are the `<vType>` elements of the run's files.
    pub fn new(samples: Samples, net: Option<Net>, vtypes: &[VTypeRow], opts: RunOptions) -> Result<Run, Error> {
        if opts.placement == Placement::Lane && net.is_none() {
            return Err(Error::Options("lane placement needs the run's net.xml".into()));
        }
        let by_name: HashMap<&str, &VTypeRow> = vtypes.iter().map(|v| (v.name.as_str(), v)).collect();
        let mut sizes = Vec::with_capacity(samples.types.len());
        for name in &samples.types {
            let row = by_name.get(name.as_str());
            let class = row.map_or("passenger", |r| r.class.as_str());
            let d = opts.class_sizes.get(class).ok_or_else(|| {
                Error::Options(format!("vehicle type {name} is of class {class}, and the profile has no size for that class (vehicles.sizes.{class})"))
            })?;
            sizes.push([
                row.and_then(|r| r.length).unwrap_or(d[0]),
                row.and_then(|r| r.width).unwrap_or(d[1]),
                row.and_then(|r| r.height).unwrap_or(d[2]),
            ]);
        }
        let lane_net: Vec<u32> = match &net {
            Some(n) => samples.lanes.iter().map(|l| n.by_id.get(l).copied().unwrap_or(NONE)).collect(),
            None => vec![NONE; samples.lanes.len()],
        };
        let mut rows = vec![Vec::new(); samples.ids.len()];
        for (i, &v) in samples.id.iter().enumerate() {
            rows[v as usize].push(i as u32);
        }
        for r in rows.iter_mut() {
            r.sort_by(|&a, &b| samples.t[a as usize].total_cmp(&samples.t[b as usize]));
        }
        let lanes_unknown = samples.lane.iter().filter(|&&l| l != NONE && lane_net[l as usize] == NONE).count();
        let mut run = Run {
            report: Report {
                samples: samples.len(),
                vehicles: samples.ids.len(),
                t0: samples.t.iter().copied().fold(f64::INFINITY, f64::min),
                t1: samples.t.iter().copied().fold(f64::NEG_INFINITY, f64::max),
                empty_rows: samples.empty_rows,
                lanes_unknown,
                path_gaps: 0,
                teleports: 0,
            },
            samples,
            net,
            opts,
            sizes,
            rows,
            pairs: Vec::new(),
            lane_net,
            tunnel: Vec::new(),
        };
        run.pairs = (0..run.rows.len()).map(|v| run.build_pairs(v)).collect();
        Ok(run)
    }

    /// The tunnels: the edges (SUMO edge ids, which are the page's edge ids) whose roads are below the ground. A lane of such an edge is
    /// a tunnel lane, and so is an internal lane of a junction whose lanes in and out are tunnel lanes. The page decides which roads are
    /// tunnels (its roads' level below 0), so a vehicle follows the tunnel's look (fade, hide) with no second rule.
    pub fn set_tunnel_edges(&mut self, edges: &std::collections::HashSet<String>) {
        let Some(net) = &self.net else { return };
        let mut t: Vec<bool> = net.lanes.iter().map(|l| !l.internal && edges.contains(&l.edge)).collect();
        let mut prev: Vec<Vec<u32>> = vec![Vec::new(); net.lanes.len()];
        for (i, next) in net.next.iter().enumerate() {
            for &n in next {
                prev[n as usize].push(i as u32);
            }
        }
        // an internal lane: a tunnel lane before it and after it (through other internal lanes of the junction, a few at most)
        let reach = |start: u32, step: &dyn Fn(u32) -> Vec<u32>| {
            let mut seen = vec![start];
            let mut i = 0;
            while i < seen.len() && i < 32 {
                let l = seen[i];
                i += 1;
                for n in step(l) {
                    if net.lanes[n as usize].internal {
                        if !seen.contains(&n) { seen.push(n); }
                    } else if t[n as usize] {
                        return true;
                    }
                }
            }
            false
        };
        let inner: Vec<bool> = (0..net.lanes.len() as u32).map(|l| {
            net.lanes[l as usize].internal && reach(l, &|x| prev[x as usize].clone()) && reach(l, &|x| net.next[x as usize].clone())
        }).collect();
        for (i, v) in inner.into_iter().enumerate() {
            if v { t[i] = true; }
        }
        self.tunnel = t;
    }

    pub fn report(&self) -> &Report {
        &self.report
    }

    fn net_lane(&self, row: usize) -> u32 {
        let l = self.samples.lane[row];
        if l == NONE || self.samples.pos[row].is_nan() {
            NONE
        } else {
            self.lane_net[l as usize]
        }
    }

    /// The chain of net lanes from lane `a` to a lane of the edge of lane `b`, through the connections (at most MAX_CHAIN lanes).
    fn path(&self, a: u32, b: u32) -> Option<Vec<u32>> {
        let net = self.net.as_ref()?;
        let target = &net.lanes[b as usize].edge;
        if &net.lanes[a as usize].edge == target {
            return Some(vec![a]);
        }
        // b's own lane when a connection reaches it; else the first lane of b's edge (then a lane change at b)
        let mut seen: HashMap<u32, u32> = HashMap::from([(a, NONE)]);
        let mut q = VecDeque::from([(a, 1usize)]);
        let mut other = None;
        while let Some((l, depth)) = q.pop_front() {
            if depth >= MAX_CHAIN {
                continue;
            }
            for &n in &net.next[l as usize] {
                if seen.contains_key(&n) {
                    continue;
                }
                seen.insert(n, l);
                if n == b {
                    return Some(Self::trace(&seen, n));
                }
                if &net.lanes[n as usize].edge == target {
                    other.get_or_insert(n);
                    continue;
                }
                q.push_back((n, depth + 1));
            }
        }
        other.map(|n| Self::trace(&seen, n))
    }

    /// The chain from the search's start to lane `n`, through the lanes the search came from.
    fn trace(seen: &HashMap<u32, u32>, n: u32) -> Vec<u32> {
        let mut chain = vec![n];
        let mut c = seen[&n];
        while c != NONE {
            chain.push(c);
            c = seen[&c];
        }
        chain.reverse();
        chain
    }

    fn build_pairs(&mut self, v: usize) -> Vec<Pair> {
        let rows = self.rows[v].clone();
        let mut out = Vec::with_capacity(rows.len().saturating_sub(1));
        // the lanes driven so far, the latest last (for the lanes behind a chain)
        let mut driven: Vec<u32> = Vec::new();
        for w in rows.windows(2) {
            let (a, b) = (w[0] as usize, w[1] as usize);
            let s = &self.samples;
            let jump = dist_m([s.x[a], s.y[a]], [s.x[b], s.y[b]]);
            let mut pair = Pair { kind: Kind::LonLat, chain: Vec::new(), back: Vec::new(), to: NONE };
            if jump > self.opts.teleport_m {
                pair.kind = Kind::Teleport;
                self.report.teleports += 1;
                driven.clear();
            } else if self.opts.placement == Placement::Lane {
                let (la, lb) = (self.net_lane(a), self.net_lane(b));
                if la != NONE && lb != NONE {
                    match self.path(la, lb) {
                        Some(chain) => {
                            while driven.last() == Some(&la) {
                                driven.pop();
                            }
                            pair.back = driven.iter().rev().take(BACK_LANES).copied().collect();
                            for &l in &chain {
                                if driven.last() != Some(&l) {
                                    driven.push(l);
                                }
                            }
                            let reached = *chain.last().unwrap();
                            if reached != lb {
                                // the reached lane is beside b's lane, not behind it: it leaves the lanes driven
                                pair.to = lb;
                                driven.pop();
                                driven.push(lb);
                            }
                            pair.chain = chain;
                            pair.kind = Kind::Lane;
                        }
                        None => {
                            self.report.path_gaps += 1;
                            driven.clear();
                        }
                    }
                } else {
                    driven.clear();
                }
            }
            out.push(pair);
        }
        out
    }

    /// The point and the heading `off` drawn metres from station `s` (SUMO metres from the start of `fwd[0]`).
    /// Stations use SUMO's lane lengths (a vehicle's `pos` is measured on them) and each lane maps them onto its drawn
    /// line, as SUMO does; `off` (half a vehicle's length back, a look ahead) is in drawn metres, so a vehicle keeps its
    /// size on a lane whose drawn line is shorter than its SUMO length. Before the first lane the walk goes back through
    /// `back` (the nearest first); past the ends it stays at the end. The third value is the net lane under that point, the fourth the
    /// drawn metres along that lane's line.
    fn walk(&self, fwd: &[u32], back: &[u32], s: f64, off: f64) -> ([f64; 2], f64, u32, f64) {
        let lanes = &self.net.as_ref().unwrap().lanes;
        // the lanes in driving order: back (farthest first), then fwd; `zero`: the index of fwd[0]
        let order: Vec<u32> = back.iter().rev().chain(fwd.iter()).copied().collect();
        let zero = back.len();
        let sumo = |l: u32| lanes[l as usize].length.max(1e-9);
        let drawn = |l: u32| lanes[l as usize].line.len();
        // 1. station s to a drawn distance g from the start of fwd[0]
        let mut g = 0.0;
        if s >= 0.0 {
            let mut x = s;
            for &l in &order[zero..] {
                if x <= sumo(l) || l == *order.last().unwrap() {
                    g += x.min(sumo(l)) / sumo(l) * drawn(l);
                    break;
                }
                x -= sumo(l);
                g += drawn(l);
            }
        } else {
            let mut x = -s;
            for &l in order[..zero].iter().rev() {
                if x <= sumo(l) {
                    g -= x / sumo(l) * drawn(l);
                    x = 0.0;
                    break;
                }
                x -= sumo(l);
                g -= drawn(l);
            }
            let _ = x;
        }
        // 2. the drawn distance g + off to a lane and a point on it
        let mut target = g + off;
        if target >= 0.0 {
            for &l in &order[zero..] {
                if target <= drawn(l) || l == *order.last().unwrap() {
                    let x = target.min(drawn(l));
                    let (p, h) = lanes[l as usize].line.at(x);
                    return (p, h, l, x);
                }
                target -= drawn(l);
            }
        } else {
            for &l in order[..zero].iter().rev() {
                if -target <= drawn(l) {
                    let x = drawn(l) + target;
                    let (p, h) = lanes[l as usize].line.at(x);
                    return (p, h, l, x);
                }
                target += drawn(l);
            }
        }
        let first = order[0];
        let (p, h) = lanes[first as usize].line.at(0.0);
        (p, h, first, 0.0)
    }

    /// The lanes behind the end of a pair's chain (and behind its lane change), the nearest first.
    fn back_of_end(pair: &Pair) -> Vec<u32> {
        let mut back: Vec<u32> = pair.chain[..pair.chain.len() - 1].iter().rev().copied().collect();
        back.extend(&pair.back);
        back
    }

    /// Every vehicle that is on the network at clock time `t`.
    pub fn at(&self, t: f64) -> Vec<VehicleState> {
        (0..self.rows.len()).filter_map(|v| self.vehicle_at(v, t)).collect()
    }

    /// Vehicle `v` at clock time `t`, or None when it is not on the network then.
    pub fn vehicle_at(&self, v: usize, t: f64) -> Option<VehicleState> {
        let rows = &self.rows[v];
        let s = &self.samples;
        let (first, last) = (*rows.first()? as usize, *rows.last()? as usize);
        if t < s.t[first] || t > s.t[last] {
            return None;
        }
        // k: the last sample at or before t
        let k = rows.partition_point(|&r| s.t[r as usize] <= t) - 1;
        let a = rows[k] as usize;
        let len = self.sizes[s.vtype[a] as usize][0] as f64;
        let look = self.opts.heading_lookahead_m;
        let tunnel_of = |l: u32| l != NONE && self.tunnel.get(l as usize).copied().unwrap_or(false);
        let state = |p: [f64; 2], heading: f64, speed: f64, roads: Vec<(u32, f64, f64)>| VehicleState {
            vehicle: v as u32, lon: p[0], lat: p[1], heading, speed, lane: s.lane[a], vtype: s.vtype[a],
            tunnel: roads.first().is_some_and(|r| tunnel_of(r.0)), roads,
        };
        if k + 1 == rows.len() {
            // t is the last sample's time: the pair before it gives the lanes behind, else lon/lat
            return Some(match self.pairs[v].last() {
                Some(pair) if pair.kind == Kind::Lane => {
                    let la = self.net_lane(a);
                    let back = Self::back_of_end(pair);
                    let (p, _, under, along) = self.walk(&[la], &back, s.pos[a] as f64, -len * 0.5);
                    let (_, h, _, _) = self.walk(&[la], &back, s.pos[a] as f64, look - len * 0.5);
                    state(p, h, s.speed[a] as f64, vec![(under, along, 1.0)])
                }
                _ => {
                    let (p, h) = self.middle_lonlat(a);
                    state(p, h, s.speed[a] as f64, Vec::new())
                }
            });
        }
        let b = rows[k + 1] as usize;
        let pair = &self.pairs[v][k];
        let (ta, tb) = (s.t[a], s.t[b]);
        let h_t = tb - ta;
        let u = if h_t > 0.0 { (t - ta) / h_t } else { 0.0 };
        let speed = s.speed[a] as f64 + (s.speed[b] - s.speed[a]) as f64 * u;
        match pair.kind {
            Kind::Teleport => None,
            Kind::LonLat => {
                let (pa, ha) = self.middle_lonlat(a);
                let (pb, hb) = self.middle_lonlat(b);
                let p = [pa[0] + (pb[0] - pa[0]) * u, pa[1] + (pb[1] - pa[1]) * u];
                Some(state(p, (ha + turn_deg(ha, hb) * u).rem_euclid(360.0), speed, Vec::new()))
            }
            Kind::Lane => {
                let net = self.net.as_ref().unwrap();
                let chain = &pair.chain;
                let sa = s.pos[a] as f64;
                let before_end: f64 = chain[..chain.len() - 1].iter().map(|&l| net.lanes[l as usize].length).sum();
                let sb = before_end + s.pos[b] as f64;
                let d = sa + hermite(u, (sb - sa).max(0.0), s.speed[a] as f64 * h_t, s.speed[b] as f64 * h_t);
                let (mut p, _, under, along) = self.walk(chain, &pair.back, d, -len * 0.5);
                let (_, mut h, _, _) = self.walk(chain, &pair.back, d, look - len * 0.5);
                // a lane change: a blend of the places on the two lanes, centred on the sample where SUMO changed the lane
                let half = self.opts.lane_change_s * 0.5;
                // the roads under the vehicle, blended with the same weights as its place
                let mut roads = vec![(under, along, 1.0)];
                let mut blend = |q: [f64; 2], hq: f64, w: f64, lane: u32, at: f64| {
                    p = [p[0] + (q[0] - p[0]) * w, p[1] + (q[1] - p[1]) * w];
                    h = (h + turn_deg(h, hq) * w).rem_euclid(360.0);
                    for r in roads.iter_mut() {
                        r.2 *= 1.0 - w;
                    }
                    roads.push((lane, at, w));
                };
                if pair.to != NONE && t > tb - half {
                    // before b, toward b's lane: the same distance before b, on b's lane
                    let back = Self::back_of_end(pair);
                    let x = s.pos[b] as f64 - (sb - d);
                    let (q, _, lq, aq) = self.walk(&[pair.to], &back, x, -len * 0.5);
                    let (_, hq, _, _) = self.walk(&[pair.to], &back, x, look - len * 0.5);
                    blend(q, hq, smoothstep((t - (tb - half)) / self.opts.lane_change_s), lq, aq);
                }
                if k > 0 && t < ta + half {
                    let before = &self.pairs[v][k - 1];
                    if before.kind == Kind::Lane && before.to != NONE {
                        // after a, from a's former lane: the same distance after a, on that lane
                        let old = *before.chain.last().unwrap();
                        let back = Self::back_of_end(before);
                        let (q, _, lq, aq) = self.walk(&[old], &back, d, -len * 0.5);
                        let (_, hq, _, _) = self.walk(&[old], &back, d, look - len * 0.5);
                        blend(q, hq, 1.0 - smoothstep((t - (ta - half)) / self.opts.lane_change_s), lq, aq);
                    }
                }
                roads.retain(|r| r.2 > 1e-9);
                Some(state(p, h, speed, roads))
            }
        }
    }

    /// The middle of the vehicle of sample `r` from its lon/lat: half its length behind the front bumper, along its angle.
    fn middle_lonlat(&self, r: usize) -> ([f64; 2], f64) {
        let s = &self.samples;
        let h = s.angle[r] as f64;
        let half = self.sizes[s.vtype[r] as usize][0] as f64 * 0.5;
        let hr = h.to_radians();
        (offset([s.x[r], s.y[r]], -hr.sin() * half, -hr.cos() * half), h)
    }

    /// The heading from the middle of sample `r` toward its front bumper (for tests and checks).
    pub fn sample_heading(&self, r: usize) -> f64 {
        let (m, _) = self.middle_lonlat(r);
        heading_deg(m, [self.samples.x[r], self.samples.y[r]])
    }

    /// The pairs of samples with no chain of lanes between them (`Report::path_gaps`): the vehicle's id, the time of the first sample,
    /// and the two lanes' ids. A report can name them; they are placed by their lon/lat.
    pub fn gaps(&self) -> Vec<(String, f64, String, String)> {
        let s = &self.samples;
        let mut out = Vec::new();
        for (v, pairs) in self.pairs.iter().enumerate() {
            for (k, p) in pairs.iter().enumerate() {
                let (a, b) = (self.rows[v][k] as usize, self.rows[v][k + 1] as usize);
                if p.kind == Kind::LonLat && self.net_lane(a) != NONE && self.net_lane(b) != NONE && self.opts.placement == Placement::Lane {
                    out.push((s.ids[v].clone(), s.t[a], s.lanes[s.lane[a] as usize].clone(), s.lanes[s.lane[b] as usize].clone()));
                }
            }
        }
        out
    }

    /// The rows of vehicle `v`, in time order.
    pub fn rows(&self, v: usize) -> &[u32] {
        &self.rows[v]
    }
}
