//! The drawing order of the roads, `visualization.edge_levels` and `edge_levels_meta` (docs/levels.md): roadstyle's
//! `compute_levels`, with `method="tags"` (a rule on the tags, the default) or `method="solve"` (its optimization,
//! with the defaults of duckOSM's `duckosm levels` and no edits).

// Numeric code: index loops over parallel arrays and tuple types read as they are.
#![allow(clippy::needless_range_loop, clippy::type_complexity)]

pub mod area;
mod error;
pub mod flags;
pub mod flow;
mod input;
mod plane;
pub mod solve;

pub use error::Error;

use std::collections::{HashMap, HashSet};

/// A point (lon, lat).
pub type Pt = (f64, f64);

/// The roadstyle version of these rules and defaults (`edge_levels_meta.roadstyle_version`): this crate's version, which is roadstyle's.
pub const ROADSTYLE_VERSION: &str = env!("CARGO_PKG_VERSION");

/// The path classes (OSM's `highway`): the ways that a car does not use. The one list of every crate: the level input (a path at a node
/// where a car road goes on is a crossing, not a meet), the base map's edges (a crossing's street) and duckOSM's walking network.
pub const PATH_CLASSES: [&str; 7] = ["footway", "path", "cycleway", "steps", "pedestrian", "bridleway", "corridor"];

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

/// The tags of an edge that the rules read. `band`: the value of `band_col`, for `Options::band_col`. Many edges have the
/// same tags (all edges of a way, and most roads of one class): they can share one copy (Kentucky: 2.45 million edges).
#[derive(Clone, Debug, Default, PartialEq, Eq, Hash)]
pub struct LevelTags {
    pub highway: String,
    pub tunnel: Option<String>,
    pub bridge: Option<String>,
    pub layer: Option<String>,
    pub junction: Option<String>,
    pub band: Option<String>,
}

/// One edge as the levels read it: its id, its tags (shared, see [`LevelTags`]), and its line. `order`: the value of an
/// `order` column, for `Order::Column`.
#[derive(Default)]
pub struct LevelEdge {
    pub edge_id: i64,
    pub tags: std::sync::Arc<LevelTags>,
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

    /// Makes space for `additional` more edges, with no extra space. Call it before the edges of a table are added:
    /// without it the list doubles while it grows, and in WebAssembly, where the memory never shrinks, the peak stays
    /// up to three times the size of the edges.
    pub fn reserve(&mut self, additional: usize) {
        self.0.reserve_exact(additional);
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
    /// The road ids.
    pub given_up_pairs: Vec<(i64, i64)>,
    pub orders_not_kept_pairs: Vec<(i64, i64)>,
    /// Solve only: the near parts (upper road, lower road, part 0, 1 or 2) that are not over the lower road.
    pub near_not_kept: Vec<(i64, i64, usize)>,
    /// Solve only: the crossings (a path at a node where a car road goes on), and those whose path is not under the road's head (road,
    /// path, end 0 or 2).
    pub crossings: usize,
    pub crossings_not_kept: Vec<(i64, i64, usize)>,
    /// Solve only: the best value of each stage (see `solve::Solved::stages`).
    pub stages: [i64; 5],
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

/// One row of `visualization.level_edits` (roadstyle's `solve_levels(edits=...)`): `relation` is meet, stack, crossing, near or
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
    let mut rows = Vec::new();
    let mut lv = compute(&edges.edges(), o, &mut |mut part| {
        rows.append(&mut part);
        Ok(())
    })?;
    lv.rows = rows;
    Ok(Some(lv))
}

/// The edges of one part of the rows of [`levels_each`].
const ROWS_PER_PART: usize = 1 << 16;

/// [`levels`], with the rows given to `sink` in parts in the order of the result (`edge_id`), so that all rows are never in
/// memory at once (Kentucky: 2.45 million rows). The `Levels` has no rows.
pub fn levels_each(
    edges: &LevelEdges,
    o: &Options,
    sink: &mut dyn FnMut(Vec<Row>) -> Result<(), Error>,
) -> Result<Option<Levels>, Error> {
    if o.method == Method::None {
        return Ok(None);
    }
    compute(&edges.edges(), o, sink).map(Some)
}

fn compute(edges: &[&LevelEdge], o: &Options, sink: &mut dyn FnMut(Vec<Row>) -> Result<(), Error>) -> Result<Levels, Error> {
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
    let (mut given_up, mut orders_not_kept, mut stages, mut pairs, mut order_pairs, mut crossings) =
        (0, 0, [0; 5], 0, 0, 0);
    let (mut given_up_pairs, mut orders_not_kept_pairs, mut near_not_kept, mut crossings_not_kept) =
        (Vec::new(), Vec::new(), Vec::new(), Vec::new());
    match o.method {
        Method::Tags => sink(tags(edges, &roads.ends))?,
        _ => {
            let (mut rules, _, _) = input::relations(edges, &roads, o, &HashMap::new());
            // each edge's road, and whether the edge runs against it: only for the edges of the edits and the fixed numbers (for all
            // edges: Kentucky +0.1 GB)
            let wanted: HashSet<i64> = o.edits.iter().flat_map(|e| [e.a, e.b]).chain(o.fixed.iter().map(|f| f.0)).collect();
            let at: HashMap<i64, (usize, bool)> = edges
                .iter()
                .enumerate()
                .filter(|(_, e)| wanted.contains(&e.edge_id))
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
            // the tags rule first, then each group of roads whose rules it breaks alone (solve::solve_local): the memory of the largest
            // group, not of the area. The tags numbers of a road: its lowest casing and its highest fill, in the box [0, steps]
            let start = tags_start(edges, &roads, o, steps);
            let s = solve::solve_local(&rules, &start, steps, o.min_positions)?;
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
            let id = |r: usize| edges[roads.first[r]].edge_id; // a road by the id of its first edge ids
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
            crossings = rules.crossings.len();
            crossings_not_kept = s.crossings_not_kept.iter().map(|&(c, p, h)| (id(c), id(p), h)).collect();
            stages = s.stages;
            solved_rows(edges, &roads, &rules, &s, o.head_m, o.max_level, sink)?
        }
    };
    // the rows are in the order of the edges
    let ids: Vec<i64> = edges.iter().map(|e| e.edge_id).collect();
    Ok(Levels {
        rows: Vec::new(),
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
        crossings,
        crossings_not_kept,
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
            "crossing" => toggle(
                &mut rules.crossings,
                (a, b, side(&e.a_end, ab, &["start", "end"])?),
                e.enabled,
            ),
            "order" => toggle(&mut rules.orders, (a, b), e.enabled),
            r => {
                return Err(Error::Edits(format!(
                    "pairs: the relation '{r}' is not meet, stack, crossing, near or order"
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

/// The key of a level area's solve inputs, by their content: the SHA-256 (hex) of roads.parquet, pairs.csv and edits.csv, joined by ":".
/// levels_info.json keeps it (`inputs`), and the level editor starts from levels.csv only when its inputs have the same key; heads.csv
/// and caps.csv are drawing only, not inputs. The editor page (level_editor.js, inputsKey) makes the same key.
pub fn inputs_key(roads: &[u8], pairs: &[u8], edits: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    let hex = |b: &[u8]| Sha256::digest(b).iter().map(|x| format!("{x:02x}")).collect::<String>();
    format!("{}:{}:{}", hex(roads), hex(pairs), hex(edits))
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

/// What a tile knows of its edges (see [`levels_tile`]): the edges it owns (their numbers are its answer), and the numbers of
/// the edges that an earlier tile solved (raw numbers in the box `[0, steps]`, in the way of the edge). The other edges are
/// of a later tile: they are free in this tile, and their rules are counted in the later tile.
pub struct TileRoles<'a> {
    pub owned: &'a dyn Fn(i64) -> bool,
    pub earlier: &'a dyn Fn(i64) -> Option<[i64; 4]>,
}

/// The answer of one tile: the rows of its edges with raw numbers (in the box `[0, steps]`; [`Ground`] maps them for the whole
/// area), and its part of the summary. A rule is counted in the tile where none of its roads is of a later tile, so each rule
/// one time.
#[derive(Default)]
pub struct TileLevels {
    pub rows: Vec<Row>,
    /// the roads that the tile owns
    pub roads: usize,
    pub pairs: usize,
    pub order_pairs: usize,
    pub given_up: usize,
    pub orders_not_kept: usize,
    pub crossings: usize,
    /// the soft stages 0 to 3, and the sum of the casings of the owned roads (the stage 4 without the span; see
    /// [`tiled_stage4`])
    pub stages: [i64; 5],
}

/// `method="tags"` on one tile of a large area (duckOSM's levels by tiles): the rule reads only an edge's tags and the edges at
/// the two ends of its line, so a tile with its own edges and the edges around them gives the rows of its own edges (`owned`) as
/// [`levels`] gives them. Returns those rows (in `edge_id` order) and the number of the tile's own roads (for the summary).
pub fn tags_tile(edges: &LevelEdges, owned: &dyn Fn(i64) -> bool) -> Result<(Vec<Row>, usize), Error> {
    let edges = edges.edges();
    let roads = input::road_split(&edges)?;
    let own_roads = roads.first.iter().filter(|&&f| owned(edges[f].edge_id)).count();
    let rows = tags(&edges, &roads.ends).into_iter().filter(|r| owned(r.edge_id)).collect();
    Ok((rows, own_roads))
}

/// The levels of one tile of a large area (`method = "solve"`): the roads of `edges` (the tile's own edges and the edges
/// around it), with the roads that an earlier tile solved fixed at their numbers. The tags rule first, then the local repair,
/// as [`levels`]. An area in one tile gives the numbers of [`levels`] before the move to the ground.
pub fn levels_tile(edges: &LevelEdges, roles: &TileRoles, o: &Options) -> Result<TileLevels, Error> {
    if o.method != Method::Solve || !o.fixed.is_empty() || !o.edits.is_empty() {
        return Err(Error::Options("levels_tile: only method='solve', with no fixed numbers and no edits".into()));
    }
    let edges = edges.edges();
    let edges = &edges[..];
    let roads = input::road_split(edges)?;
    let (mut rules, _, _) = input::relations(edges, &roads, o, &HashMap::new());
    let n = roads.first.len();
    let owned: Vec<bool> = (0..n).map(|r| (roles.owned)(edges[roads.first[r]].edge_id)).collect();
    let mut counted = owned.clone(); // owned or of an earlier tile
    let mut fixed = vec![false; n];
    for (i, e) in edges.iter().enumerate() {
        if let Some(v) = (roles.earlier)(e.edge_id) {
            let r = roads.road[i];
            counted[r] = true;
            fixed[r] = true;
            rules.fixed.push((r, if roads.same[i] { v } else { [v[2], v[1], v[0], v[3]] }));
        }
    }
    // a meet of two roads of earlier tiles is theirs: this tile can miss a road at their node (a road with no part near the
    // tile), so it can see a meet where the tile of the roads saw a crossing (France). The solve does not move fixed roads, so
    // the rule only made the check fail.
    rules.meets.retain(|&(a, _, b, _)| !(fixed[a] && fixed[b]));
    let steps = (2.0 * o.max_level as f64 / o.margin + 1e-9).floor() as i64;
    let start = tags_start(edges, &roads, o, steps);
    let s = solve::solve_local(&rules, &start, steps, o.min_positions)?;
    let mut out = TileLevels { roads: owned.iter().filter(|&&x| x).count(), ..Default::default() };
    rows_of(edges, &roads, &rules, &s.parts, o.head_m, &|i| owned[roads.road[i]], &mut |mut r| {
        out.rows.append(&mut r);
        Ok(())
    })?;
    let both = |u: usize, l: usize| counted[u] && counted[l];
    out.pairs = rules.lifts.iter().chain(&rules.near).filter(|r| both(r.0, r.1)).map(|&(u, l, _)| (u, l)).collect::<HashSet<_>>().len();
    out.order_pairs = rules.orders.iter().filter(|r| both(r.0, r.1)).collect::<HashSet<_>>().len();
    out.given_up = s.given_up.iter().filter(|r| both(r.0, r.1)).count();
    out.orders_not_kept = s.orders_not_kept.iter().filter(|r| both(r.0, r.1)).count();
    out.crossings = rules.crossings.iter().filter(|r| both(r.0, r.1)).count();
    let st = solve::stage_sums(&rules, &s.parts, &|r| counted[r]);
    out.stages = [st[0], st[1], st[2], st[3], s.parts.iter().zip(&owned).filter(|(_, &o)| o).map(|(p, _)| 3 * p[3] - p[0] - p[1] - p[2]).sum()];
    Ok(out)
}

/// The stage 4 of the tiles of an area: the sum of the casings (`casings`, the sum of the tiles' stage 4) and, with
/// `min_positions`, the span of all numbers (`span`) with its weight, as the solve of the whole area gives it.
pub fn tiled_stage4(casings: i64, roads: usize, span: i64, o: &Options) -> i64 {
    let steps = (2.0 * o.max_level as f64 / o.margin + 1e-9).floor() as i64;
    casings + if o.min_positions { (3 * roads as i64 * steps + 1) * span } else { 0 }
}

/// The move to the ground of the raw numbers of all tiles (as [`to_ground`]): the main casing number that most edges have
/// becomes 0, and the numbers become consecutive.
pub struct Ground {
    values: Vec<i64>,
    zero: i64,
}

impl Ground {
    /// From the count of the edges of each main casing number (`casing`), and all numbers of all rows (`values`).
    pub fn new(casing: &HashMap<i64, usize>, values: &std::collections::BTreeSet<i64>, max_level: i64) -> Result<Ground, Error> {
        let ground = casing.iter().max_by_key(|(v, c)| (**c, -**v)).map_or(0, |(v, _)| *v);
        let mut values: Vec<i64> = values.iter().copied().chain([ground]).collect();
        values.sort_unstable();
        values.dedup();
        let top = values.len() as i64 - 1;
        if top > 2 * max_level {
            return Err(Error::Options(format!(
                "compute_levels: the answer has {} different numbers, more than the box [-max_level, max_level] holds ({}): \
                 make max_level larger or the margin 1 or more",
                top + 1,
                2 * max_level + 1
            )));
        }
        let zero = (values.binary_search(&ground).unwrap() as i64).clamp(top - max_level, max_level);
        Ok(Ground { values, zero })
    }

    /// The level of a raw number.
    pub fn level(&self, v: i64) -> i64 {
        self.values.binary_search(&v).expect("a number of the rows") as i64 - self.zero
    }
}

/// The tags numbers of each road: its lowest casing and its highest fill, in the box [0, steps].
fn tags_start(edges: &[&LevelEdge], roads: &input::Roads, o: &Options, steps: i64) -> Vec<[i64; 4]> {
    let level = tag_levels(edges, &roads.ends);
    let n = roads.first.len();
    let mut p = vec![[i64::MAX, i64::MAX, i64::MAX, i64::MIN]; n];
    for i in 0..edges.len() {
        let (r, (casing, fill)) = (roads.road[i], level(i));
        let c = p[r][0].min(casing);
        p[r] = [c, c, c, p[r][3].max(fill)];
    }
    let to_box = |v: i64| (((v + o.max_level) as f64 / o.margin).round() as i64).clamp(0, steps);
    p.iter().map(|q| [to_box(q[0]), to_box(q[1]), to_box(q[2]), to_box(q[3])]).collect()
}

/// `method="tags"` (`_tag_intervals`): N(v) is the value of [min L, max L] of the edges at node v nearest 0; the
/// casing is min(N(s), N(t), L) and the fill max(N(s), N(t), L).
fn tags(edges: &[&LevelEdge], ends: &[(u32, u32)]) -> Vec<Row> {
    let level = tag_levels(edges, ends);
    edges
        .iter()
        .enumerate()
        .map(|(i, e)| {
            let (c, f) = level(i);
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

/// The casing and the fill of edge `i` by the tags rule (see `tags`).
fn tag_levels<'a>(edges: &[&LevelEdge], ends: &'a [(u32, u32)]) -> impl Fn(usize) -> (i64, i64) + 'a {
    let lv: Vec<i64> = edges.iter().map(|e| input::level(e)).collect();
    let mut at: HashMap<u32, (i64, i64)> = HashMap::new();
    for (&(s, t), &l) in ends.iter().zip(&lv) {
        for v in [s, t] {
            let e = at.entry(v).or_insert((l, l));
            *e = (e.0.min(l), e.1.max(l));
        }
    }
    move |i| {
        let nv = |v: u32| {
            let (lo, hi) = at[&v];
            lo.max(0).min(hi)
        };
        let ((s, t), l) = (ends[i], lv[i]);
        (nv(s).min(nv(t)).min(l), nv(s).max(nv(t)).max(l))
    }
}

/// The solver's numbers (`parts`, in the box [0, 2 max_level]) around the ground: the main casing number that most edges have
/// (`weight`: the edges of each road) becomes 0 and the numbers become consecutive (roadstyle's _compress). Then, if a number is out of
/// the box [-max_level, max_level], the ground moves by the smallest step that puts all numbers in the box, so that the answer is a
/// correct `fixed` input again. An error when the answer has more than 2 max_level + 1 different numbers (a margin below 1).
pub(crate) fn to_ground(parts: &[[i64; 4]], weight: &[usize], max_level: i64) -> Result<Vec<[i64; 4]>, Error> {
    let mut count: HashMap<i64, usize> = HashMap::new();
    for (p, &w) in parts.iter().zip(weight) {
        *count.entry(p[1]).or_default() += w;
    }
    let ground = count
        .iter()
        .max_by_key(|(v, c)| (**c, -**v))
        .map_or(0, |(v, _)| *v);
    let mut values: Vec<i64> = parts.iter().flatten().copied().chain([ground]).collect();
    values.sort_unstable();
    values.dedup();
    let top = values.len() as i64 - 1;
    if top > 2 * max_level {
        return Err(Error::Options(format!(
            "compute_levels: the answer has {} different numbers, more than the box [-max_level, max_level] holds ({}): \
             make max_level larger or the margin 1 or more",
            top + 1,
            2 * max_level + 1
        )));
    }
    let zero = (values.binary_search(&ground).unwrap() as i64).clamp(top - max_level, max_level);
    Ok(parts
        .iter()
        .map(|p| p.map(|v| values.binary_search(&v).unwrap() as i64 - zero))
        .collect())
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
    max_level: i64,
    sink: &mut dyn FnMut(Vec<Row>) -> Result<(), Error>,
) -> Result<(), Error> {
    let mut weight = vec![0; roads.first.len()];
    for &r in &roads.road {
        weight[r] += 1;
    }
    let parts = to_ground(&s.parts, &weight, max_level)?;
    rows_of(edges, roads, rules, &parts, head_m, &|_| true, sink)
}

/// The rows of the edges `keep` (by their place in `edges`) from the numbers of the roads (`parts`), in the order of the edges:
/// an edge against its road gets the heads the other way round; a cap is round, square at the dead end of a two-way road.
fn rows_of(
    edges: &[&LevelEdge],
    roads: &input::Roads,
    rules: &solve::Rules,
    parts: &[[i64; 4]],
    head_m: f64,
    keep: &dyn Fn(usize) -> bool,
    sink: &mut dyn FnMut(Vec<Row>) -> Result<(), Error>,
) -> Result<(), Error> {
    let n = roads.first.len();
    // the ends of each road that meet another road: bit 1 the start, bit 4 the end (a set of pairs: Kentucky +0.1 GB)
    let mut met = vec![0u8; n];
    for &(x, ex, y, ey) in &rules.meets {
        met[x] |= 1 << ex;
        met[y] |= 1 << ey;
    }
    let (mut fwd, mut back) = (vec![false; n], vec![false; n]);
    for (i, &r) in roads.road.iter().enumerate() {
        if roads.same[i] {
            fwd[r] = true;
        } else {
            back[r] = true;
        }
    }
    let cap = |r: usize, end: usize| {
        if met[r] & (1 << end) == 0 && fwd[r] && back[r] {
            "square"
        } else {
            "round"
        }
    };
    let row = |(i, e): (usize, &&LevelEdge)| {
            let r = roads.road[i];
            let [a0, am, a2, b] = parts[r];
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
    };
    for start in (0..edges.len()).step_by(ROWS_PER_PART) {
        let end = (start + ROWS_PER_PART).min(edges.len());
        sink(edges[start..end].iter().enumerate().filter(|(k, _)| keep(start + k)).map(|(k, e)| row((start + k, e))).collect())?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    #[test]
    fn the_inputs_key_is_the_sha256_of_each_file() {
        let empty = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";
        let abc = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
        assert_eq!(super::inputs_key(b"abc", b"", b"abc"), format!("{abc}:{empty}:{abc}"));
    }

    use super::*;

    /// The ground of most edges is the lowest number, and the highest number is 4 above it: the ground moves up by 2, so that every
    /// number is in the box [-2, 2]. Six different numbers do not go in the box of max_level 2.
    #[test]
    fn the_ground_keeps_the_box() {
        let parts = [[0, 0, 0, 1], [0, 0, 0, 1], [3, 3, 3, 4]];
        assert_eq!(to_ground(&parts, &[1, 1, 1], 20).unwrap(), [[0, 0, 0, 1], [0, 0, 0, 1], [2, 2, 2, 3]]);
        let parts = [[0, 0, 0, 1], [0, 0, 0, 1], [2, 2, 3, 4]];
        assert_eq!(to_ground(&parts, &[1, 1, 1], 2).unwrap(), [[-2, -2, -2, -1], [-2, -2, -2, -1], [0, 0, 1, 2]]);
        assert!(to_ground(&[[0, 1, 2, 5], [3, 4, 4, 5]], &[1, 1], 2).is_err());
    }

    /// The tags rule by tiles: each tile has its own edges and the edges at their ends, and the rows of the tiles are the rows of
    /// the whole rule. Three edges in a line, the middle one a bridge: each end node sees the bridge.
    #[test]
    fn the_tags_rule_by_tiles_equals_the_whole() {
        let edge = |id: i64, x: f64, bridge: bool| LevelEdge {
            edge_id: id,
            tags: LevelTags { highway: "primary".into(), bridge: bridge.then(|| "yes".to_string()), layer: bridge.then(|| "1".to_string()), ..Default::default() }.into(),
            geometry: vec![(x, 0.0), (x + 1e-3, 0.0)],
            ..Default::default()
        };
        let all = [(1, 0.0, false), (2, 1e-3, true), (3, 2e-3, false)];
        let mut whole = LevelEdges::default();
        for &(id, x, b) in &all {
            whole.add(0, edge(id, x, b));
        }
        let o = Options { method: Method::Tags, ..Default::default() };
        let want = levels(&whole, &o).unwrap().unwrap().rows;
        // tile A owns edges 1 and 2 and sees edge 3 at the end of edge 2; tile B owns edge 3 and sees edge 2
        let mut got = Vec::new();
        for (own, see) in [(&[1, 2][..], &[3][..]), (&[3][..], &[2][..])] {
            let mut t = LevelEdges::default();
            for &(id, x, b) in all.iter().filter(|e| own.contains(&e.0) || see.contains(&e.0)) {
                t.add(0, edge(id, x, b));
            }
            let (rows, roads) = tags_tile(&t, &|id| own.contains(&id)).unwrap();
            assert_eq!(roads, own.len());
            got.extend(rows);
        }
        got.sort_by_key(|r| r.edge_id);
        assert_eq!(got, want);
    }

    #[test]
    fn the_tags_rule_on_two_edges() {
        let mut edges = LevelEdges::default();
        for (id, bridge) in [(7, None), (3, Some("yes".to_string()))] {
            let geometry = vec![(0.0, id as f64 * 1e-4), (1e-3, 0.0)];
            edges.add(
                0,
                LevelEdge {
                    edge_id: id,
                    tags: LevelTags { highway: "residential".into(), bridge, ..Default::default() }.into(),
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
