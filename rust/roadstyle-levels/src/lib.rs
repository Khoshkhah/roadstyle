//! The drawing order of the roads, `visualization.edge_levels` and `edge_levels_meta` (docs/levels.md): roadstyle's
//! `compute_levels`, with `method="tags"` (a rule on the tags, the default) or `method="solve"` (its optimization,
//! with the defaults of duckOSM's `duckosm levels` and no edits).

// Ported numeric code: index loops over parallel arrays and tuple types of the Python stages read as they are in Python.
#![allow(clippy::needless_range_loop, clippy::type_complexity)]

pub mod flow;
mod input;
mod solve;

use std::collections::{HashMap, HashSet};

/// A point (lon, lat).
pub type Pt = (f64, f64);

/// The roadstyle version whose rules and defaults this port follows (`edge_levels_meta.roadstyle_version`).
pub const ROADSTYLE_VERSION: &str = "0.24.2";

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum Method {
    None,
    #[default]
    Tags,
    Solve,
}

impl Method {
    pub fn parse(s: &str) -> Option<Method> {
        match s {
            "none" => Some(Method::None),
            "tags" => Some(Method::Tags),
            "solve" => Some(Method::Solve),
            _ => None,
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            Method::None => "none",
            Method::Tags => "tags",
            Method::Solve => "solve",
        }
    }
}

/// One edge as the levels read it: its id, the tags that the rules read, and its line.
pub struct LevelEdge {
    pub edge_id: i64,
    pub highway: String,
    pub tunnel: Option<String>,
    pub bridge: Option<String>,
    pub layer: Option<String>,
    pub junction: Option<String>,
    pub geometry: Vec<Pt>,
}

/// The edges of all modes, `edges` and `private_edges` (duckOSM's `load_roads`). An edge in several tables has the
/// attributes of the one with the lowest rank. duckOSM's ranks: driving 0, walking 1, cycling 2, then their private
/// edges 3, 4 and 5.
#[derive(Default)]
pub struct LevelEdges(Vec<(i64, u8, LevelEdge)>);

impl LevelEdges {
    pub fn add(&mut self, rank: u8, edge: LevelEdge) {
        self.0.push((edge.edge_id, rank, edge));
    }

    fn edges(&self) -> Vec<&LevelEdge> {
        let mut order: Vec<&(i64, u8, LevelEdge)> = self.0.iter().collect();
        order.sort_by_key(|(id, rank, _)| (*id, *rank));
        order.dedup_by_key(|(id, _, _)| *id);
        order.into_iter().map(|(_, _, e)| e).collect()
    }
}

/// One row of `edge_levels`. The heads and the caps are None with the tags rule.
#[derive(Clone, Debug, PartialEq)]
pub struct Row {
    pub edge_id: i64,
    pub casing_start: i64,
    pub casing_level: i64,
    pub casing_end: i64,
    pub fill_level: i64,
    pub head_start_m: Option<f64>,
    pub head_end_m: Option<f64>,
    pub cap_start: Option<&'static str>,
    pub cap_end: Option<&'static str>,
}

/// The result: the rows (in `edge_id` order) and what `edge_levels_meta` and a summary say.
pub struct Levels {
    pub rows: Vec<Row>,
    pub method: Method,
    /// roadstyle's hash of the edge ids: sha256 of the sorted ids (8 bytes each, little endian), 32 hex characters.
    pub edge_hash: String,
    pub roads: usize,
    /// Solve only: the stack pairs that could not be kept, and the order wishes that were not kept.
    pub given_up: usize,
    pub orders_not_kept: usize,
    /// Solve only: the pairs themselves, as (upper road, lower road) and (first road, second road), the road numbers of `input::road_split`.
    pub given_up_pairs: Vec<(usize, usize)>,
    pub orders_not_kept_pairs: Vec<(usize, usize)>,
    /// Solve only: the best value of each stage (see `solve::Solved::stages`).
    pub stages: [i64; 3],
}

/// The options of roadstyle's `compute_levels`, with its defaults.
#[derive(Clone, Debug)]
pub struct Options {
    pub method: Method,
}

impl Default for Options {
    fn default() -> Options {
        Options {
            method: Method::Solve,
        }
    }
}

/// The levels of the last networks, by a hash of the edges and the options: a style, its tiles and each palette of one network
/// solve one time.
/// ponytail: the last 2 networks only; keep more when a caller alternates between more networks.
static CACHE: std::sync::Mutex<Vec<(u64, std::sync::Arc<Levels>)>> =
    std::sync::Mutex::new(Vec::new());

/// The drawing levels of the edges (`compute_levels`), from the cache when the same edges and options were done before.
pub fn levels(edges: &LevelEdges, o: &Options) -> Result<Option<std::sync::Arc<Levels>>, String> {
    use std::hash::{Hash, Hasher};
    if o.method == Method::None {
        return Ok(None);
    }
    let edges = edges.edges();
    let mut h = std::collections::hash_map::DefaultHasher::new();
    format!("{o:?}").hash(&mut h);
    for e in &edges {
        (
            e.edge_id,
            &e.highway,
            &e.tunnel,
            &e.bridge,
            &e.layer,
            &e.junction,
        )
            .hash(&mut h);
        e.geometry
            .iter()
            .for_each(|p| (p.0.to_bits(), p.1.to_bits()).hash(&mut h));
    }
    let key = h.finish();
    let mut cache = CACHE.lock().map_err(|e| e.to_string())?;
    if let Some((_, lv)) = cache.iter().find(|(k, _)| *k == key) {
        return Ok(Some(lv.clone()));
    }
    let lv = std::sync::Arc::new(compute(&edges, o)?);
    if cache.len() == 2 {
        cache.remove(0);
    }
    cache.push((key, lv.clone()));
    Ok(Some(lv))
}

fn compute(edges: &[&LevelEdge], o: &Options) -> Result<Levels, String> {
    let roads = input::road_split(edges)?;
    let (mut given_up, mut orders_not_kept, mut stages) = (0, 0, [0; 3]);
    let (mut given_up_pairs, mut orders_not_kept_pairs) = (Vec::new(), Vec::new());
    let rows = match o.method {
        Method::Tags => tags(edges, &roads.ends),
        _ => {
            let (rules, _) = input::relations(edges, &roads);
            let s = solve::solve(&rules, 20)?;
            given_up = s.given_up.len();
            orders_not_kept = s.orders_not_kept.len();
            given_up_pairs = s.given_up.clone();
            orders_not_kept_pairs = s.orders_not_kept.clone();
            stages = s.stages;
            solved_rows(edges, &roads, &rules, &s)
        }
    };
    let ids: Vec<i64> = rows.iter().map(|r| r.edge_id).collect();
    Ok(Levels {
        rows,
        method: o.method,
        edge_hash: edge_hash(&ids),
        roads: roads.first.len(),
        given_up,
        orders_not_kept,
        given_up_pairs,
        orders_not_kept_pairs,
        stages,
    })
}

/// roadstyle's hash of the edge ids (`edge_levels_meta.edge_hash`): sha256 of the sorted ids, 8 bytes each, little endian; the first
/// 32 hex characters.
pub fn edge_hash(ids: &[i64]) -> String {
    use sha2::{Digest, Sha256};
    let mut sorted = ids.to_vec();
    sorted.sort_unstable();
    let mut h = Sha256::new();
    for id in sorted {
        h.update(id.to_le_bytes());
    }
    h.finalize()
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect::<String>()[..32]
        .to_string()
}

/// `method="tags"` (`_tag_intervals`): N(v) is the value of [min L, max L] of the edges at node v nearest 0; the
/// casing is min(N(s), N(t), L) and the fill max(N(s), N(t), L).
fn tags(edges: &[&LevelEdge], ends: &[(u32, u32)]) -> Vec<Row> {
    let lv: Vec<i64> = edges.iter().map(|e| input::level(e)).collect();
    let mut at: HashMap<u32, (i64, i64)> = HashMap::new();
    for (&(s, t), &l) in ends.iter().zip(&lv) {
        for v in [s, t] {
            let e = at.entry(v).or_insert((l, l));
            *e = (e.0.min(l), e.1.max(l));
        }
    }
    let nv = |v: u32| {
        let (lo, hi) = at[&v];
        lo.max(0).min(hi)
    };
    edges
        .iter()
        .zip(ends)
        .zip(&lv)
        .map(|((e, &(s, t)), &l)| {
            let c = nv(s).min(nv(t)).min(l);
            let f = nv(s).max(nv(t)).max(l);
            Row {
                edge_id: e.edge_id,
                casing_start: c,
                casing_level: c,
                casing_end: c,
                fill_level: f,
                head_start_m: None,
                head_end_m: None,
                cap_start: None,
                cap_end: None,
            }
        })
        .collect()
}

/// The rows of a solve (`solve_levels`, then duckOSM's level area with its defaults): the casing number of most
/// edges becomes 0 (the ground), the numbers become consecutive, an edge against its road gets the heads the other
/// way round; the heads are 5 m, a cap is round, square at the dead end of a two-way road (`dead_end_cap`).
fn solved_rows(
    edges: &[&LevelEdge],
    roads: &input::Roads,
    rules: &solve::Rules,
    s: &solve::Solved,
) -> Vec<Row> {
    let mut count: HashMap<i64, usize> = HashMap::new();
    for &r in &roads.road {
        *count.entry(s.parts[r][1]).or_default() += 1;
    }
    let ground = count
        .iter()
        .max_by_key(|(v, c)| (**c, -**v))
        .map_or(0, |(v, _)| *v);
    let mut values: Vec<i64> = s.parts.iter().flatten().map(|v| v - ground).collect();
    values.push(0);
    values.sort_unstable();
    values.dedup();
    let zero = values.binary_search(&0).unwrap() as i64;
    let small = |v: i64| values.binary_search(&(v - ground)).unwrap() as i64 - zero;
    let met: HashSet<(usize, usize)> = rules
        .meets
        .iter()
        .flat_map(|&(x, ex, y, ey)| [(x, ex), (y, ey)])
        .collect();
    let n = roads.first.len();
    let (mut fwd, mut back) = (vec![false; n], vec![false; n]);
    for (i, &r) in roads.road.iter().enumerate() {
        if roads.same[i] {
            fwd[r] = true;
        } else {
            back[r] = true;
        }
    }
    let cap = |r: usize, end: usize| {
        if !met.contains(&(r, end)) && fwd[r] && back[r] {
            "square"
        } else {
            "round"
        }
    };
    edges
        .iter()
        .enumerate()
        .map(|(i, e)| {
            let r = roads.road[i];
            let [a0, am, a2, b] = s.parts[r].map(small);
            let (cs, ce) = (cap(r, 0), cap(r, 2));
            let (casing_start, casing_end, cap_start, cap_end) = if roads.same[i] {
                (a0, a2, cs, ce)
            } else {
                (a2, a0, ce, cs)
            };
            Row {
                edge_id: e.edge_id,
                casing_start,
                casing_level: am,
                casing_end,
                fill_level: b,
                head_start_m: Some(input::HEAD_M),
                head_end_m: Some(input::HEAD_M),
                cap_start: Some(cap_start),
                cap_end: Some(cap_end),
            }
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_second_call_is_from_the_cache() {
        let mut edges = LevelEdges::default();
        for (id, bridge) in [(7, None), (3, Some("yes".to_string()))] {
            let geometry = vec![(0.0, id as f64 * 1e-4), (1e-3, 0.0)];
            edges.add(
                0,
                LevelEdge {
                    edge_id: id,
                    highway: "residential".into(),
                    tunnel: None,
                    bridge,
                    layer: None,
                    junction: None,
                    geometry,
                },
            );
        }
        let o = Options {
            method: Method::Tags,
        };
        let (a, b) = (
            levels(&edges, &o).unwrap().unwrap(),
            levels(&edges, &o).unwrap().unwrap(),
        );
        assert!(std::sync::Arc::ptr_eq(&a, &b));
        assert_eq!(a.edge_hash, edge_hash(&[7, 3]));
        assert_eq!(
            a.rows.iter().map(|r| r.fill_level).collect::<Vec<_>>(),
            [1, 0]
        );
    }
}
