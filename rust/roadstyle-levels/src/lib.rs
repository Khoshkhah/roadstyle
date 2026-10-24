//! The drawing order of the roads, `visualization.edge_levels` and `edge_levels_meta` (docs/levels.md): roadstyle's
//! `compute_levels`, with `method="tags"` (a rule on the tags, the default) or `method="solve"` (its optimization,
//! with the defaults of duckOSM's `duckosm levels` and no edits).

// Ported numeric code: index loops over parallel arrays and tuple types of the Python stages read as they are in Python.
#![allow(clippy::needless_range_loop, clippy::type_complexity)]

pub mod area;
mod error;
pub mod flow;
mod input;
pub mod solve;

pub use error::Error;

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

/// One edge as the levels read it: its id, the tags that the rules read, and its line. `band` and `order`: the values of
/// `band_col` and of an `order` column, for `Options::band_col` and `Order::Column`.
#[derive(Default)]
pub struct LevelEdge {
    pub edge_id: i64,
    pub highway: String,
    pub tunnel: Option<String>,
    pub bridge: Option<String>,
    pub layer: Option<String>,
    pub junction: Option<String>,
    pub band: Option<String>,
    pub order: Option<f64>,
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

    /// The edges in the order they were added (all ranks).
    pub fn into_edges(self) -> Vec<LevelEdge> {
        self.0.into_iter().map(|(_, _, e)| e).collect()
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
    /// Solve only: the number of stack pairs (upper road, lower road), near rules included, and of order wishes.
    pub pairs: usize,
    pub order_pairs: usize,
    /// Solve only: the stack pairs that could not be kept, and the order wishes that were not kept.
    pub given_up: usize,
    pub orders_not_kept: usize,
    /// Solve only: the pairs themselves, as (upper road, lower road) and (higher road, lower road). A road is the id of its first edge, as
    /// Python's road ids.
    pub given_up_pairs: Vec<(i64, i64)>,
    pub orders_not_kept_pairs: Vec<(i64, i64)>,
    /// Solve only: the near parts (upper road, lower road, part 0, 1 or 2) that are not over the lower road.
    pub near_not_kept: Vec<(i64, i64, usize)>,
    /// Solve only: the best value of each stage (see `solve::Solved::stages`).
    pub stages: [i64; 4],
}

/// The wishes of `order`: the priority (roundabouts, tunnels, bridges, then the class), the class only, the edges'
/// `order` value, or none.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum Order {
    #[default]
    Priority,
    Class,
    Column,
    None,
}

/// One row of `visualization.level_edits` (roadstyle's `solve_levels(edits=...)`): `relation` is meet, stack, near or
/// order; `a` and `b` are any edges of their roads. `enabled` false removes the same rule of the roads, all other rows
/// add a rule. A meet has the ends `start` or `end`; a stack or a near rule has the part of `a` (`start`, `main` or
/// `end`) in `a_end`.
#[derive(Clone, Debug)]
pub struct Edit {
    pub relation: String,
    pub a: i64,
    pub b: i64,
    pub a_end: Option<String>,
    pub b_end: Option<String>,
    pub enabled: bool,
}

/// The options of roadstyle's `compute_levels` and `solve_levels`, with their defaults. `margin` changes only the scale
/// of the numbers, so the rows do not change with it. `fixed`: numbers of an earlier result (around the ground 0) that
/// stay as they are, by the id of an edge of the road, in that edge's direction.
#[derive(Clone, Debug)]
pub struct Options {
    pub method: Method,
    /// The edges' `band` is the band (else the level from the tags).
    pub band_col: bool,
    pub order: Order,
    pub band_dist: f64,
    pub head_m: f64,
    pub max_level: i64,
    pub margin: f64,
    pub min_positions: bool,
    pub near_rules: bool,
    pub fixed: Vec<(i64, [i64; 4])>,
    pub edits: Vec<Edit>,
}

impl Default for Options {
    fn default() -> Options {
        Options {
            method: Method::Solve,
            band_col: false,
            order: Order::Priority,
            band_dist: 10.0,
            head_m: 5.0,
            max_level: 20,
            margin: 1.0,
            min_positions: true,
            near_rules: false,
            fixed: Vec::new(),
            edits: Vec::new(),
        }
    }
}

/// The drawing levels of the edges (`compute_levels`). A caller that needs them two times keeps the value.
pub fn levels(edges: &LevelEdges, o: &Options) -> Result<Option<Levels>, Error> {
    if o.method == Method::None {
        return Ok(None);
    }
    compute(&edges.edges(), o).map(Some)
}

fn compute(edges: &[&LevelEdge], o: &Options) -> Result<Levels, Error> {
    if o.method == Method::Tags && (o.band_col || !matches!(o.order, Order::Priority | Order::None))
    {
        return Err(Error::Options("compute_levels: band_col and order are part of the optimization problem; use method='solve'".into()));
    }
    if o.method == Method::Solve && !(o.margin > 0.0 && o.max_level > 0) {
        return Err(Error::Options(format!(
            "compute_levels: margin and max_level must be greater than 0, not {} and {}",
            o.margin, o.max_level
        )));
    }
    let roads = input::road_split(edges)?;
    let (mut given_up, mut orders_not_kept, mut stages, mut pairs, mut order_pairs) =
        (0, 0, [0; 4], 0, 0);
    let (mut given_up_pairs, mut orders_not_kept_pairs, mut near_not_kept) =
        (Vec::new(), Vec::new(), Vec::new());
    let rows = match o.method {
        Method::Tags => tags(edges, &roads.ends),
        _ => {
            let (mut rules, _, _) = input::relations(edges, &roads, o, &HashMap::new());
            // each edge's road, and whether the edge runs against it
            let at: HashMap<i64, (usize, bool)> = edges
                .iter()
                .enumerate()
                .map(|(i, e)| (e.edge_id, (roads.road[i], !roads.same[i])))
                .collect();
            edit(&mut rules, &o.edits, &at)?;
            for &(id, v) in &o.fixed {
                let &(r, back) = at
                    .get(&id)
                    .ok_or(Error::Options(format!("fixed: {id} is not an edge of the roads")))?;
                let v = if back { [v[2], v[1], v[0], v[3]] } else { v };
                if v.iter().any(|x| x.abs() > o.max_level) {
                    return Err(Error::Options(format!(
                        "solve_levels: a fixed number is outside [-max_level, max_level] ({})",
                        o.max_level
                    )));
                }
                rules.fixed.push((r, v.map(|x| x + o.max_level)));
            }
            // in steps of the margin, as roadstyle's: the box [-max_level, max_level] holds 2 max_level / margin + 1 numbers
            let steps = (2.0 * o.max_level as f64 / o.margin + 1e-9).floor() as i64;
            let s = solve::solve(&rules, steps, o.min_positions)?;
            let both: std::collections::BTreeSet<(usize, usize)> = rules
                .lifts
                .iter()
                .chain(&rules.near)
                .map(|&(u, l, _)| (u, l))
                .collect();
            pairs = both.len();
            order_pairs = rules.orders.iter().collect::<HashSet<_>>().len();
            given_up = s.given_up.len();
            orders_not_kept = s.orders_not_kept.len();
            let id = |r: usize| edges[roads.first[r]].edge_id; // a road by the id of its first edge, as Python's road ids
            given_up_pairs = s.given_up.iter().map(|&(u, l)| (id(u), id(l))).collect();
            orders_not_kept_pairs = s
                .orders_not_kept
                .iter()
                .map(|&(x, y)| (id(x), id(y)))
                .collect();
            near_not_kept = s
                .near_not_kept
                .iter()
                .map(|&(u, l, h)| (id(u), id(l), h))
                .collect();
            stages = s.stages;
            solved_rows(edges, &roads, &rules, &s, o.head_m)
        }
    };
    let ids: Vec<i64> = rows.iter().map(|r| r.edge_id).collect();
    Ok(Levels {
        rows,
        method: o.method,
        edge_hash: edge_hash(&ids),
        roads: roads.first.len(),
        pairs,
        order_pairs,
        given_up,
        orders_not_kept,
        given_up_pairs,
        orders_not_kept_pairs,
        near_not_kept,
        stages,
    })
}

/// A road of a level area's input: its first edge (its id is the road's id) and its edges its way and the other way, by their index in
/// the edges.
#[derive(Clone, Debug)]
pub struct InputRoad {
    pub first: usize,
    pub edges: Vec<usize>,
    pub reversed: Vec<usize>,
}

/// The solver's input of a level area (`make`): the roads, the band and the priority of each (None: no order wish), and the rules
/// between them, on road indexes.
pub struct AreaInput {
    pub roads: Vec<InputRoad>,
    pub band: Vec<i64>,
    pub priority: Vec<Option<f64>>,
    pub rules: solve::Rules,
}

/// The solver's input of a level area (roadstyle's `level_input`, `roadstyle-levels make`), from the edges in their order: two edges on
/// one line (either way) of one kind are one road, named by its first edge. `heads`: heads.csv, `[start, end]` metres by any edge of a
/// road, in that edge's way (None: `o.head_m`); they decide once which parts of a stack's upper road cross the road under it.
pub fn make(
    edges: &[LevelEdge],
    o: &Options,
    heads: &[(i64, [Option<f64>; 2])],
) -> Result<AreaInput, Error> {
    let edges: Vec<&LevelEdge> = edges.iter().collect();
    let roads = input::road_split(&edges)?;
    let mut out: Vec<InputRoad> = roads
        .first
        .iter()
        .map(|&first| InputRoad {
            first,
            edges: Vec::new(),
            reversed: Vec::new(),
        })
        .collect();
    for (i, &r) in roads.road.iter().enumerate() {
        if roads.same[i] {
            out[r].edges.push(i)
        } else {
            out[r].reversed.push(i)
        }
    }
    let at: HashMap<i64, (usize, bool)> = edges
        .iter()
        .enumerate()
        .map(|(i, e)| (e.edge_id, (roads.road[i], !roads.same[i])))
        .collect();
    let mut own: HashMap<usize, [f64; 2]> = HashMap::new();
    for &(id, v) in heads {
        let &(r, back) = at
            .get(&id)
            .ok_or(Error::Edits(format!("heads: '{id}' is not an edge of the roads")))?;
        if v.iter().flatten().any(|m| m.is_nan() || *m <= 0.0) {
            return Err(Error::Edits(format!(
                "heads: the head lengths of {id} must be positive numbers of metres"
            )));
        }
        let v = v.map(|m| m.unwrap_or(o.head_m));
        own.insert(r, if back { [v[1], v[0]] } else { v });
    }
    let (rules, band, priority) = input::relations(&edges, &roads, o, &own);
    Ok(AreaInput {
        roads: out,
        band,
        priority,
        rules,
    })
}

/// The edits on the rules (roadstyle's `merged_relations`): a row with `enabled` false removes its rule (an error when
/// there is none), any other row adds it. An edge that runs against its road names the other end of the road.
fn edit(
    rules: &mut solve::Rules,
    edits: &[Edit],
    at: &HashMap<i64, (usize, bool)>,
) -> Result<(), Error> {
    let road = |id: i64| {
        at.get(&id)
            .copied()
            .ok_or(Error::Edits(format!("edits: '{id}' is not an edge of the roads")))
    };
    for e in edits {
        let ((a, ab), (b, bb)) = (road(e.a)?, road(e.b)?);
        let side = |v: &Option<String>, back: bool, parts: &[&str]| -> Result<usize, Error> {
            let p = match v.as_deref() {
                Some(s) if parts.contains(&s) => s,
                other => {
                    return Err(Error::Edits(format!(
                        "edits: a {} names {} in its end, not {:?} ({} and {})",
                        e.relation,
                        parts.join(", "),
                        other.unwrap_or(""),
                        e.a,
                        e.b
                    )))
                }
            };
            let h = ["start", "main", "end"]
                .iter()
                .position(|x| *x == p)
                .unwrap();
            Ok(if back { 2 - h } else { h })
        };
        let found = match e.relation.as_str() {
            "meet" => {
                let (x, y) = (
                    (a, side(&e.a_end, ab, &["start", "end"])?),
                    (b, side(&e.b_end, bb, &["start", "end"])?),
                );
                let (x, y) = (x.min(y), x.max(y));
                toggle(&mut rules.meets, (x.0, x.1, y.0, y.1), e.enabled)
            }
            "stack" => toggle(
                &mut rules.lifts,
                (a, b, side(&e.a_end, ab, &["start", "main", "end"])?),
                e.enabled,
            ),
            "near" => toggle(
                &mut rules.near,
                (a, b, side(&e.a_end, ab, &["start", "main", "end"])?),
                e.enabled,
            ),
            "order" => toggle(&mut rules.orders, (a, b), e.enabled),
            r => {
                return Err(Error::Edits(format!(
                    "pairs: the relation '{r}' is not meet, stack, near or order"
                )))
            }
        };
        if !found {
            return Err(Error::Edits(format!(
                "edits: no {} pair {} {} to switch off",
                e.relation, e.a, e.b
            )));
        }
    }
    Ok(())
}

/// Adds `rule` (when `on`), or removes it; false when there is no rule to remove.
fn toggle<T: PartialEq>(rules: &mut Vec<T>, rule: T, on: bool) -> bool {
    match rules.iter().position(|r| *r == rule) {
        Some(i) if !on => {
            rules.remove(i);
        }
        None if !on => return false,
        None => rules.push(rule),
        Some(_) => {}
    }
    true
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
    head_m: f64,
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
                head_start_m: Some(head_m),
                head_end_m: Some(head_m),
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
    fn the_tags_rule_on_two_edges() {
        let mut edges = LevelEdges::default();
        for (id, bridge) in [(7, None), (3, Some("yes".to_string()))] {
            let geometry = vec![(0.0, id as f64 * 1e-4), (1e-3, 0.0)];
            edges.add(
                0,
                LevelEdge {
                    edge_id: id,
                    highway: "residential".into(),
                    bridge,
                    geometry,
                    ..Default::default()
                },
            );
        }
        let o = Options {
            method: Method::Tags,
            ..Default::default()
        };
        let a = levels(&edges, &o).unwrap().unwrap();
        assert_eq!(a.edge_hash, edge_hash(&[7, 3]));
        assert_eq!(
            a.rows.iter().map(|r| r.fill_level).collect::<Vec<_>>(),
            [1, 0]
        );
    }
}
