//! A level area as the level editor has it (roadstyle's level_area and level_editor, docs/guides/levels.md): its roads (both directions
//! of a segment are one road), the pairs that the input found (pairs.csv) and your edits (edits.csv). The edits go on top of the pairs,
//! the solver solves them with fixed roads when asked, and a rule to add is checked for loops first. Typed: the files' text and the
//! answers' JSON are the adapter's (roadstyle::level_editor).

use crate::Error;
use super::solve::{self, Rules};
use std::collections::{HashMap, HashSet, VecDeque};

/// A road: its id (the id of its first edge), the edges that run its way and the edges that run the other way.
#[derive(Clone, Debug)]
pub struct AreaRoad {
    pub id: i64,
    pub edges: Vec<i64>,
    pub reversed: Vec<i64>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum Relation {
    /// The ends `a_end` of `a` and `b_end` of `b` are one node: each head is under the other road's fill.
    Meet,
    /// The part `a_end` of `a`'s casing is over `b`'s fill (a crossing).
    Stack,
    /// The same, for a part that only comes near `b` (the last wish).
    Near,
    /// `a`'s fill is over `b`'s fill where they meet (a wish).
    Order,
    /// `b` is a path at the end `a_end` of `a`, where the car road `a` goes on (a crossing at grade): `a`'s head there is over `b`'s
    /// fill, so the path is drawn under the road's outline (a wish after the stack rules).
    Crossing,
}

/// An end of a road (`Start`, `End`) or a part of its casing (`Start` head, `Main` part, `End` head).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum Side {
    Start,
    Main,
    End,
}

impl Side {
    /// The index of a casing part: 0 start, 1 main, 2 end.
    pub fn index(self) -> usize {
        self as usize
    }

    pub fn from_index(i: usize) -> Side {
        [Side::Start, Side::Main, Side::End][i]
    }

    /// The other end of the road (an edge that runs against its road names it so); the main part stays.
    fn turned(self) -> Side {
        match self {
            Side::Start => Side::End,
            Side::End => Side::Start,
            Side::Main => Side::Main,
        }
    }
}

/// A row of pairs.csv or edits.csv; `a` and `b` are any edges of their roads. `enabled` false switches the same rule off.
#[derive(Clone, Debug, PartialEq)]
pub struct PairRow {
    pub relation: Relation,
    pub a: i64,
    pub b: i64,
    pub a_end: Option<Side>,
    pub b_end: Option<Side>,
    pub enabled: bool,
}

/// The answer of a solve, per road (in the road's own way) and per rule. A road is its index in `Area::roads`.
#[derive(Clone, Debug, Default)]
pub struct AreaSolved {
    /// `[casing_start, casing_level, casing_end, fill_level]` of each road: the main casing number of most edges is 0, the numbers are
    /// small and consecutive.
    pub levels: Vec<[i64; 4]>,
    /// The stack pairs (upper, lower) with a part that is not over the lower fill, and those parts.
    pub given_up: Vec<(usize, usize)>,
    pub given_up_parts: Vec<(usize, usize, Side)>,
    /// The near parts that are not over the lower fill (warnings), and the order wishes not kept (higher, lower).
    pub near_parts: Vec<(usize, usize, Side)>,
    /// The crossings (road, path, the road's end) whose path is not under the road's head.
    pub crossings_not_kept: Vec<(usize, usize, Side)>,
    pub orders_not_kept: Vec<(usize, usize)>,
    /// The number of stack pairs (near rules included), meets, order wishes and crossings.
    pub pairs: usize,
    pub crossings: usize,
    pub meets: usize,
    pub order_pairs: usize,
}

/// What the local re-solve needs of the answer before it: the numbers, the given-up parts, and the counts of the order wishes not kept
/// and of the near warnings (roadstyle's _worse compares them).
#[derive(Clone, Debug, Default)]
pub struct Previous {
    pub levels: Vec<[i64; 4]>,
    pub given_up_parts: HashSet<(usize, usize, Side)>,
    pub orders_not_kept: usize,
    pub near: usize,
    pub crossings: usize,
}

impl From<&AreaSolved> for Previous {
    fn from(s: &AreaSolved) -> Previous {
        Previous {
            levels: s.levels.clone(),
            given_up_parts: s.given_up_parts.iter().copied().collect(),
            orders_not_kept: s.orders_not_kept.len(),
            near: s.near_parts.len(),
            crossings: s.crossings_not_kept.len(),
        }
    }
}

/// Why a rule to add conflicts: the same rule is there and holds, it is there but in a loop, or it makes a loop.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Why {
    Duplicate,
    NotKept,
    Loop,
}

/// A rule to add that conflicts (`Area::conflicts`): its index in the rows, why, and the rows of the rules it conflicts with.
#[derive(Clone, Debug)]
pub struct Conflict {
    pub row: usize,
    pub why: Why,
    pub with: Vec<PairRow>,
}

/// A rule's identity (roadstyle's merged_relations): a meet is the same pair whichever road is named first; a stack or near rule is
/// one part of the upper road.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
enum Key {
    Meet((i64, Side), (i64, Side)),
    Part(Relation, i64, i64, Side),
    Order(i64, i64),
}

fn key(r: &PairRow) -> Key {
    match r.relation {
        Relation::Meet => {
            let (x, y) = (
                (r.a, r.a_end.unwrap_or(Side::Start)),
                (r.b, r.b_end.unwrap_or(Side::Start)),
            );
            Key::Meet(x.min(y), x.max(y))
        }
        Relation::Stack | Relation::Near | Relation::Crossing => {
            Key::Part(r.relation, r.a, r.b, r.a_end.unwrap_or(Side::Main))
        }
        Relation::Order => Key::Order(r.a, r.b),
    }
}

/// A level area: its roads and the pairs that the input found.
pub struct Area {
    pub roads: Vec<AreaRoad>,
    pub pairs: Vec<PairRow>,
    /// any edge id (or road id) -> (its road, whether the edge runs against the road)
    of: HashMap<i64, (usize, bool)>,
}

impl Area {
    /// The area of `roads` and `pairs` (on road ids). A meet names the ends start or end of both roads; a stack or near rule names a part
    /// of the upper road.
    pub fn new(roads: Vec<AreaRoad>, pairs: Vec<PairRow>) -> Result<Area, Error> {
        let mut of = HashMap::new();
        for (i, r) in roads.iter().enumerate() {
            of.insert(r.id, (i, false));
            of.extend(r.edges.iter().map(|&e| (e, (i, false))));
            of.extend(r.reversed.iter().map(|&e| (e, (i, true))));
        }
        for p in &pairs {
            check(p, "pairs")?;
        }
        Ok(Area { roads, pairs, of })
    }

    /// The road of any edge id (or road id).
    pub fn road_of(&self, id: i64) -> Option<usize> {
        self.of.get(&id).map(|&(r, _)| r)
    }

    /// The pairs with the edits on top (roadstyle's merged_relations), in their order: the row (on road ids, the ends in the road's own
    /// way) and whether it is an edit. A row with `enabled` false removes the same rule (an error when there is none), any other row adds it.
    pub fn merged(&self, edits: &[PairRow]) -> Result<Vec<(PairRow, bool)>, Error> {
        let mut out: Vec<(Key, PairRow, bool)> = self
            .pairs
            .iter()
            .map(|p| (key(p), p.clone(), false))
            .collect();
        let mut at: HashMap<Key, usize> = HashMap::new();
        for (i, (k, _, _)) in out.iter().enumerate() {
            at.insert(*k, i); // a pair named twice: the last one
        }
        for e in edits {
            check(e, "edits")?;
            let mut row = e.clone();
            let &(ra, ba) = self
                .of
                .get(&row.a)
                .ok_or(Error::Edits(format!("edits: '{}' is not an edge of the roads", row.a)))?;
            let &(rb, bb) = self
                .of
                .get(&row.b)
                .ok_or(Error::Edits(format!("edits: '{}' is not an edge of the roads", row.b)))?;
            // an edge that runs against its road names the road's other end (a meet: both ends; a stack: a's part)
            if ba {
                row.a_end = row.a_end.map(Side::turned);
            }
            if bb && row.relation == Relation::Meet {
                row.b_end = row.b_end.map(Side::turned);
            }
            (row.a, row.b) = (self.roads[ra].id, self.roads[rb].id);
            let k = key(&row);
            if !row.enabled {
                let i = at.remove(&k).ok_or(
                    Error::Edits(format!(
                        "edits: no {:?} pair {} {} to switch off",
                        row.relation, row.a, row.b
                    )
                    .to_lowercase()),
                )?;
                out.remove(i);
                at.values_mut().filter(|v| **v > i).for_each(|v| *v -= 1);
            } else if let Some(&i) = at.get(&k) {
                out[i] = (k, row, true);
            } else {
                at.insert(k, out.len());
                out.push((k, row, true));
            }
        }
        Ok(out.into_iter().map(|(_, r, own)| (r, own)).collect())
    }

    /// The merged rows as the solver's rules (on road indexes), and the rows in the order of `difference_rules`: the meets, the stacks,
    /// the near rules, the orders.
    fn rules(&self, merged: &[(PairRow, bool)]) -> Result<(Rules, Vec<PairRow>), Error> {
        let idx = |id: i64| {
            self.road_of(id)
                .ok_or(Error::Edits(format!("pairs: '{id}' is not a road")))
        };
        let mut r = Rules {
            roads: self.roads.len(),
            ..Default::default()
        };
        let mut rows: [Vec<PairRow>; 5] = Default::default();
        for (row, _) in merged {
            let (a, b) = (idx(row.a)?, idx(row.b)?);
            let part = row.a_end.unwrap_or(Side::Main).index();
            match row.relation {
                Relation::Meet => r.meets.push((
                    a,
                    row.a_end.unwrap_or(Side::Start).index(),
                    b,
                    row.b_end.unwrap_or(Side::Start).index(),
                )),
                Relation::Stack => r.lifts.push((a, b, part)),
                Relation::Near => r.near.push((a, b, part)),
                Relation::Crossing => r.crossings.push((a, b, part)),
                Relation::Order => r.orders.push((a, b)),
            }
            rows[row.relation as usize].push(row.clone());
        }
        Ok((r, rows.concat()))
    }

    /// Solves the area with `edits` (roadstyle's solve_levels): `fixed` roads keep their numbers (around the ground 0, in the road's way).
    pub fn solve(
        &self,
        edits: &[PairRow],
        fixed: &HashMap<usize, [i64; 4]>,
        max_level: i64,
        margin: f64,
    ) -> Result<AreaSolved, Error> {
        let (mut rules, _) = self.rules(&self.merged(edits)?)?;
        for (&r, v) in fixed {
            if v.iter().any(|x| x.abs() > max_level) {
                return Err(Error::Options(format!(
                    "solve_levels: a fixed number is outside [-max_level, max_level] ({max_level})"
                )));
            }
            rules.fixed.push((r, v.map(|x| x + max_level)));
        }
        let steps = (2.0 * max_level as f64 / margin + 1e-9).floor() as i64;
        let s = solve::solve(&rules, steps, true)?;
        let weight: Vec<usize> = self.roads.iter().map(|road| road.edges.len() + road.reversed.len()).collect();
        let levels = crate::to_ground(&s.parts, &weight, max_level)?;
        let both: HashSet<(usize, usize)> = rules
            .lifts
            .iter()
            .chain(&rules.near)
            .map(|&(u, l, _)| (u, l))
            .collect();
        let side = |v: &[(usize, usize, usize)]| {
            v.iter()
                .map(|&(u, l, h)| (u, l, Side::from_index(h)))
                .collect()
        };
        Ok(AreaSolved {
            levels,
            given_up: s.given_up.clone(),
            given_up_parts: side(&s.given_up_parts),
            near_parts: side(&s.near_not_kept),
            crossings_not_kept: side(&s.crossings_not_kept),
            orders_not_kept: s.orders_not_kept.clone(),
            pairs: both.len(),
            meets: rules.meets.len(),
            crossings: rules.crossings.len(),
            order_pairs: rules.orders.iter().collect::<HashSet<_>>().len(),
        })
    }

    /// The roads within `hops` relations (the pairs and the edits, any relation) of the roads of `changed` (any edge ids).
    pub fn around(&self, edits: &[PairRow], changed: &[i64], hops: usize) -> HashSet<usize> {
        let mut nb: HashMap<usize, HashSet<usize>> = HashMap::new();
        for row in self.pairs.iter().chain(edits) {
            if let (Some(a), Some(b)) = (self.road_of(row.a), self.road_of(row.b)) {
                nb.entry(a).or_default().insert(b);
                nb.entry(b).or_default().insert(a);
            }
        }
        let mut seen: HashSet<usize> = changed.iter().filter_map(|&x| self.road_of(x)).collect();
        let mut ring = seen.clone();
        for _ in 0..hops {
            ring = ring
                .iter()
                .flat_map(|x| nb.get(x).into_iter().flatten().copied())
                .filter(|y| !seen.contains(y))
                .collect();
            seen.extend(&ring);
        }
        seen
    }

    /// The editor's solve after a change (roadstyle's solve_local): the roads within `hops` relations of the `changed` ones are solved
    /// again, every other road keeps its numbers of `previous`. When the local answer gives up a crossing part that `previous` kept, has
    /// more order wishes not kept or more near warnings, or fails, the whole area is solved. Returns the answer and how: None (local) or
    /// why the whole area was solved.
    pub fn solve_local(
        &self,
        edits: &[PairRow],
        previous: &Previous,
        changed: &[i64],
        hops: usize,
        max_level: i64,
        margin: f64,
    ) -> Result<(AreaSolved, Option<String>), Error> {
        let free = self.around(edits, changed, hops);
        if free.len() == self.roads.len() {
            return Ok((
                self.solve(edits, &HashMap::new(), max_level, margin)?,
                Some("every road is around the change".into()),
            ));
        }
        let fixed: HashMap<usize, [i64; 4]> = (0..self.roads.len())
            .filter(|r| !free.contains(r))
            .map(|r| (r, previous.levels[r]))
            .collect();
        let why = match self.solve(edits, &fixed, max_level, margin) {
            Ok(mut local) => {
                match worse(&local, previous) {
                    None => {
                        // the solver puts its ground at 0: shift the answer as a whole so that the fixed roads keep their numbers
                        let shifts: HashSet<i64> = fixed
                            .iter()
                            .map(|(&r, v)| v[0] - local.levels[r][0])
                            .collect();
                        if shifts.len() > 1 {
                            return Err(Error::Check(format!("solve_local: the fixed roads moved by different amounts ({shifts:?})")));
                        }
                        if let Some(&k) = shifts.iter().next() {
                            local.levels.iter_mut().for_each(|v| *v = v.map(|x| x + k));
                        }
                        return Ok((local, None));
                    }
                    Some(why) => why,
                }
            }
            Err(e) => format!("the local solve failed ({e})"),
        };
        Ok((
            self.solve(edits, &HashMap::new(), max_level, margin)?,
            Some(why),
        ))
    }

    /// The check before rules are added (roadstyle's rule_conflicts): each of `rows` that conflicts with the enabled rules (the pairs,
    /// `edits` and the rows before it). A loop is a cycle of the solver's rules through the new one that no numbers can keep.
    pub fn conflicts(&self, edits: &[PairRow], rows: &[PairRow]) -> Result<Vec<Conflict>, Error> {
        let mut rel = self.merged(edits)?;
        let mut out = Vec::new();
        let none = Area {
            roads: self.roads.clone(),
            pairs: Vec::new(),
            of: self.of.clone(),
        };
        for (i, row) in rows.iter().enumerate() {
            if !row.enabled {
                continue;
            }
            let (new, _) = none.merged(std::slice::from_ref(row))?.remove(0);
            let k = key(&new);
            if let Some(at) = rel.iter().position(|(r, _)| key(r) == k) {
                let others: Vec<_> = rel
                    .iter()
                    .enumerate()
                    .filter(|(j, _)| *j != at)
                    .map(|(_, x)| x.clone())
                    .collect();
                out.push(match self.cycle(&others, &new)? {
                    None => Conflict {
                        row: i,
                        why: Why::Duplicate,
                        with: vec![rel[at].0.clone()],
                    },
                    Some(path) => Conflict {
                        row: i,
                        why: Why::NotKept,
                        with: path,
                    },
                });
                continue;
            }
            if let Some(path) = self.cycle(&rel, &new)? {
                out.push(Conflict {
                    row: i,
                    why: Why::Loop,
                    with: path,
                });
            }
            rel.push((new, true));
        }
        Ok(out)
    }

    /// The rows of a cycle of the rules of `rel` through the rule `new`, or None (roadstyle's _loop): a path in the graph of the rules
    /// `x_i - x_j <= w` (an arc j -> i) from the new rule's i back to its j with a strict step on it (a breadth-first search on (number,
    /// strict yet)).
    fn cycle(
        &self,
        rel: &[(PairRow, bool)],
        new: &PairRow,
    ) -> Result<Option<Vec<PairRow>>, Error> {
        let (rules, rows) = self.rules(rel)?;
        let mut adj: HashMap<usize, Vec<(usize, bool, Option<usize>)>> = HashMap::new();
        for (i, j, w, src) in difference_rules(&rules) {
            adj.entry(j).or_default().push((i, w < 0, src));
        }
        let (mine, _) = self.rules(&[(new.clone(), true)])?;
        for (i, j, w, _) in difference_rules(&mine)
            .into_iter()
            .filter(|r| r.3.is_some())
        {
            let start = (i, w < 0);
            let mut prev: HashMap<(usize, bool), Option<((usize, bool), Option<usize>)>> =
                HashMap::from([(start, None)]);
            let mut q = VecDeque::from([start]);
            let mut end = None;
            'search: while let Some(s @ (v, f)) = q.pop_front() {
                for &(u, strict, src) in adj.get(&v).into_iter().flatten() {
                    let t = (u, f || strict);
                    if let std::collections::hash_map::Entry::Vacant(e) = prev.entry(t) {
                        e.insert(Some((s, src)));
                        if t == (j, true) {
                            end = Some(t);
                            break 'search;
                        }
                        q.push_back(t);
                    }
                }
            }
            if let Some(mut e) = end {
                let mut path: Vec<usize> = Vec::new();
                while let Some(Some((p, src))) = prev.get(&e).cloned() {
                    if let Some(s) = src.filter(|s| !path.contains(s)) {
                        path.push(s);
                    }
                    e = p;
                }
                path.reverse();
                return Ok(Some(path.into_iter().map(|s| rows[s].clone()).collect()));
            }
        }
        Ok(None)
    }
}

/// A row's ends as its relation needs them: a meet the ends start or end of both roads; a stack or near rule a part of the upper road.
fn check(r: &PairRow, file: &str) -> Result<(), Error> {
    match r.relation {
        Relation::Meet
            if !matches!(r.a_end, Some(Side::Start | Side::End))
                || !matches!(r.b_end, Some(Side::Start | Side::End)) =>
        {
            Err(Error::Edits(format!(
                "{file}: a meet needs an end of each road (start / end): {} {}",
                r.a, r.b
            )))
        }
        Relation::Stack | Relation::Near if r.a_end.is_none() => Err(Error::Edits(format!(
            "{file}: a stack names one part of the upper road (start, main or end): {} over {}{}",
            r.a,
            r.b,
            if file == "pairs" {
                " (a pairs.csv made before 2026-10-08: make the area again)"
            } else {
                ""
            }
        ))),
        _ => Ok(()),
    }
}

/// The solver's rules as `(i, j, w, row)`: `x_i - x_j <= w` on the columns of roadstyle's _difference_rules (a road's fill is column r,
/// its casing parts n + 3 r + 0 / 1 / 2); `row` is the index of the rule's row in the order of `Area::rules`, None for a casing part under
/// its own fill.
fn difference_rules(r: &Rules) -> Vec<(usize, usize, i64, Option<usize>)> {
    let n = r.roads;
    let col = |road: usize, h: usize| n + 3 * road + h;
    let mut out: Vec<_> = (0..n)
        .flat_map(|road| (0..3).map(move |h| (col(road, h), road, 0, None)))
        .collect();
    let mut k = 0;
    for &(x, ex, y, ey) in &r.meets {
        out.push((col(x, ex), y, 0, Some(k)));
        out.push((col(y, ey), x, 0, Some(k)));
        k += 1;
    }
    for &(u, l, h) in r.lifts.iter().chain(&r.near) {
        out.push((l, col(u, h), -1, Some(k)));
        k += 1;
    }
    for &(x, y) in &r.orders {
        out.push((y, x, -1, Some(k)));
        k += 1;
    }
    out
}

/// Why a local answer cannot stand for the whole solve (roadstyle's _worse), or None.
fn worse(local: &AreaSolved, previous: &Previous) -> Option<String> {
    let new = local
        .given_up_parts
        .iter()
        .filter(|p| !previous.given_up_parts.contains(p))
        .count();
    if new > 0 {
        return Some(format!("{new} crossing part(s) given up that were kept"));
    }
    if local.orders_not_kept.len() > previous.orders_not_kept {
        return Some(format!(
            "{} order wishes not kept, {} before",
            local.orders_not_kept.len(),
            previous.orders_not_kept
        ));
    }
    if local.crossings_not_kept.len() > previous.crossings {
        return Some(format!(
            "{} crossings not kept, {} before",
            local.crossings_not_kept.len(),
            previous.crossings
        ));
    }
    if local.near_parts.len() > previous.near {
        return Some(format!(
            "{} near warnings, {} before",
            local.near_parts.len(),
            previous.near
        ));
    }
    None
}

/// The local re-solve frees the changed roads and their neighbours this many relations away (roadstyle's level_area.HOPS).
pub const HOPS: usize = 3;
