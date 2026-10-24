//! A level area as the level editor has it (roadstyle's level_area and level_editor, docs/guides/levels.md): its roads (both directions
//! of a segment are one road), the pairs that the input found (pairs.csv) and your edits (edits.csv). The edits go on top of the pairs,
//! the solver solves them with fixed roads when asked, and a rule to add is checked for loops first. The roads and pairs are text, as in
//! the files.

use super::solve::{self, Rules};
use std::collections::{HashMap, HashSet, VecDeque};

/// A road: its id (the id of its first edge), the edges that run its way and the edges that run the other way.
#[derive(Clone, Debug)]
pub struct AreaRoad {
    pub id: String,
    pub edges: Vec<String>,
    pub reversed: Vec<String>,
}

/// A row of pairs.csv or edits.csv. An empty `a_end` or `b_end` is none; `enabled` "false", "0" or "no" switches the same found row off.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct PairRow {
    pub relation: String,
    pub a: String,
    pub b: String,
    pub a_end: String,
    pub b_end: String,
    pub enabled: String,
}

impl PairRow {
    fn off(&self) -> bool {
        matches!(
            self.enabled.trim().to_lowercase().as_str(),
            "false" | "0" | "no"
        )
    }
}

/// The rows of a CSV text with a header (pairs.csv, edits.csv): the columns relation, a, b, a_end, b_end and enabled, by name.
pub fn read_rows(csv: &str) -> Result<Vec<PairRow>, String> {
    let mut lines = csv.lines().filter(|l| !l.trim().is_empty());
    let Some(head) = lines.next() else {
        return Ok(Vec::new());
    };
    let head = fields(head);
    let at = |name: &str| head.iter().position(|h| h == name);
    let col = |row: &[String], name: &str| {
        at(name)
            .and_then(|i| row.get(i).cloned())
            .unwrap_or_default()
    };
    if at("relation").is_none() || at("a").is_none() || at("b").is_none() {
        return Err("pairs: the columns relation, a and b are missing".into());
    }
    Ok(lines
        .map(|l| {
            let f = fields(l);
            PairRow {
                relation: col(&f, "relation"),
                a: col(&f, "a"),
                b: col(&f, "b"),
                a_end: col(&f, "a_end"),
                b_end: col(&f, "b_end"),
                enabled: col(&f, "enabled"),
            }
        })
        .collect())
}

/// The fields of a CSV line, with quotes as pandas writes them.
fn fields(line: &str) -> Vec<String> {
    let (mut out, mut cur, mut quoted, mut chars) =
        (Vec::new(), String::new(), false, line.chars().peekable());
    while let Some(c) = chars.next() {
        match c {
            '"' if quoted && chars.peek() == Some(&'"') => {
                cur.push('"');
                chars.next();
            }
            '"' => quoted = !quoted,
            ',' if !quoted => out.push(std::mem::take(&mut cur)),
            _ => cur.push(c),
        }
    }
    out.push(cur);
    out
}

/// The answer of a solve, per road (in the road's own way) and per rule. A road is its index in `Area::roads`.
#[derive(Clone, Debug, Default)]
pub struct AreaSolved {
    /// `[casing_start, casing_level, casing_end, fill_level]` of each road: the main casing number of most edges is 0, the numbers are
    /// small and consecutive.
    pub levels: Vec<[i64; 4]>,
    /// The stack pairs (upper, lower) with a part that is not over the lower fill, and those parts (upper, lower, 0 start / 1 main / 2 end).
    pub given_up: Vec<(usize, usize)>,
    pub given_up_parts: Vec<(usize, usize, usize)>,
    /// The near parts that are not over the lower fill (warnings), and the order wishes not kept (higher, lower).
    pub near_parts: Vec<(usize, usize, usize)>,
    pub orders_not_kept: Vec<(usize, usize)>,
    /// The number of stack pairs (near rules included), meets and order wishes.
    pub pairs: usize,
    pub meets: usize,
    pub order_pairs: usize,
}

/// A level area: its roads and the pairs that the input found.
pub struct Area {
    pub roads: Vec<AreaRoad>,
    pub pairs: Vec<PairRow>,
    /// any edge id (or road id) -> (its road, whether the edge runs against the road)
    of: HashMap<String, (usize, bool)>,
}

const PARTS: [&str; 3] = ["start", "main", "end"];

impl Area {
    pub fn new(roads: Vec<AreaRoad>, pairs: Vec<PairRow>) -> Area {
        let mut of = HashMap::new();
        for (i, r) in roads.iter().enumerate() {
            of.insert(r.id.clone(), (i, false));
            for e in &r.edges {
                of.insert(e.clone(), (i, false));
            }
            for e in &r.reversed {
                of.insert(e.clone(), (i, true));
            }
        }
        Area { roads, pairs, of }
    }

    /// The road of any edge id (or road id).
    pub fn road_of(&self, id: &str) -> Option<usize> {
        self.of.get(id).map(|&(r, _)| r)
    }

    /// The pairs with the edits on top (roadstyle's merged_relations), in their order: the rule's key, the row (on road ids, the ends in
    /// the road's own way), and whether it is an edit. A row with `enabled` false removes the same rule (an error when there is none),
    /// any other row adds it; a stack or near row names one part of A.
    pub fn merged(&self, edits: &[PairRow]) -> Result<Vec<(String, PairRow, bool)>, String> {
        let mut out: Vec<(String, PairRow, bool)> = Vec::new();
        let mut at: HashMap<String, usize> = HashMap::new();
        type Merged = Vec<(String, PairRow, bool)>;
        fn put(
            out: &mut Merged,
            at: &mut HashMap<String, usize>,
            k: String,
            row: PairRow,
            own: bool,
        ) {
            match at.get(&k) {
                Some(&i) => out[i] = (k, row, own),
                None => {
                    at.insert(k.clone(), out.len());
                    out.push((k, row, own));
                }
            }
        }
        for row in &self.pairs {
            if matches!(row.relation.as_str(), "stack" | "near")
                && !PARTS.contains(&row.a_end.as_str())
            {
                return Err(format!(
                    "pairs: a stack row names no part of the upper road ({} over {}): a pairs.csv made before 2026-10-08. Make the area again",
                    row.a, row.b
                ));
            }
            put(&mut out, &mut at, key(row), row.clone(), false);
        }
        for e in edits {
            let mut row = e.clone();
            if matches!(row.relation.as_str(), "stack" | "near")
                && !PARTS.contains(&row.a_end.as_str())
            {
                return Err(format!(
                    "edits: a stack names one part of the upper road in a_end (start, main or end), not '{}' ({} over {})",
                    row.a_end, row.a, row.b
                ));
            }
            for side in [0, 1] {
                let id = if side == 0 { &row.a } else { &row.b };
                let &(r, back) = self
                    .of
                    .get(id)
                    .ok_or(format!("edits: '{id}' is not an edge of the roads"))?;
                let turn = |v: &str| match v {
                    "start" => "end".to_string(),
                    "end" => "start".to_string(),
                    v => v.to_string(),
                };
                let flips = row.relation == "meet"
                    || (matches!(row.relation.as_str(), "stack" | "near") && side == 0);
                if back && flips {
                    if side == 0 {
                        row.a_end = turn(&row.a_end);
                    } else {
                        row.b_end = turn(&row.b_end);
                    }
                }
                let road = self.roads[r].id.clone();
                if side == 0 {
                    row.a = road;
                } else {
                    row.b = road;
                }
            }
            let k = key(&row);
            if row.off() {
                let Some(&i) = at.get(&k) else {
                    return Err(format!(
                        "edits: no {} pair {} {} to switch off",
                        row.relation, row.a, row.b
                    ));
                };
                at.remove(&k);
                out.remove(i);
                for v in at.values_mut() {
                    if *v > i {
                        *v -= 1;
                    }
                }
            } else {
                put(&mut out, &mut at, k, row, true);
            }
        }
        Ok(out)
    }

    /// The merged rows as the solver's rules (on road indexes), and the rows in the order of `difference_rules`: the meets, the stacks,
    /// the near rules, the orders.
    fn rules(&self, merged: &[(String, PairRow, bool)]) -> Result<(Rules, Vec<PairRow>), String> {
        let idx = |id: &str| {
            self.of
                .get(id)
                .map(|&(r, _)| r)
                .ok_or(format!("pairs: '{id}' is not a road"))
        };
        let end = |v: &str| match v {
            "start" => Ok(0),
            "end" => Ok(2),
            v => Err(format!(
                "pairs: a meet needs the ends start or end, not '{v}'"
            )),
        };
        let part = |v: &str| {
            PARTS
                .iter()
                .position(|p| *p == v)
                .ok_or(format!("pairs: the part '{v}' is not start, main or end"))
        };
        let mut r = Rules {
            roads: self.roads.len(),
            ..Default::default()
        };
        let mut rows: [Vec<PairRow>; 4] = Default::default();
        for (_, row, _) in merged {
            let (a, b) = (idx(&row.a)?, idx(&row.b)?);
            let kind = match row.relation.as_str() {
                "meet" => {
                    r.meets.push((a, end(&row.a_end)?, b, end(&row.b_end)?));
                    0
                }
                "stack" => {
                    r.lifts.push((a, b, part(&row.a_end)?));
                    1
                }
                "near" => {
                    r.near.push((a, b, part(&row.a_end)?));
                    2
                }
                "order" => {
                    r.orders.push((a, b));
                    3
                }
                x => {
                    return Err(format!(
                        "pairs: the relation '{x}' is not meet, stack, near or order"
                    ))
                }
            };
            rows[kind].push(row.clone());
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
    ) -> Result<AreaSolved, String> {
        let (mut rules, _) = self.rules(&self.merged(edits)?)?;
        for (&r, v) in fixed {
            if v.iter().any(|x| x.abs() > max_level) {
                return Err(format!(
                    "solve_levels: a fixed number is outside [-max_level, max_level] ({max_level})"
                ));
            }
            rules.fixed.push((r, v.map(|x| x + max_level)));
        }
        let steps = (2.0 * max_level as f64 / margin + 1e-9).floor() as i64;
        let s = solve::solve(&rules, steps, true)?;
        // the main casing number that most edges have is the ground; then small consecutive numbers (roadstyle's _compress)
        let mut count: HashMap<i64, usize> = HashMap::new();
        for (r, road) in self.roads.iter().enumerate() {
            *count.entry(s.parts[r][1]).or_default() += road.edges.len() + road.reversed.len();
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
        let both: HashSet<(usize, usize)> = rules
            .lifts
            .iter()
            .chain(&rules.near)
            .map(|&(u, l, _)| (u, l))
            .collect();
        Ok(AreaSolved {
            levels: s.parts.iter().map(|p| p.map(small)).collect(),
            given_up: s.given_up.clone(),
            given_up_parts: s.given_up_parts.clone(),
            near_parts: s.near_not_kept.clone(),
            orders_not_kept: s.orders_not_kept.clone(),
            pairs: both.len(),
            meets: rules.meets.len(),
            order_pairs: rules.orders.iter().collect::<HashSet<_>>().len(),
        })
    }

    /// The roads within `hops` relations (the pairs and the edits, any relation) of the roads of `changed` (any edge ids).
    pub fn around(&self, edits: &[PairRow], changed: &[String], hops: usize) -> HashSet<usize> {
        let mut nb: HashMap<usize, HashSet<usize>> = HashMap::new();
        for row in self.pairs.iter().chain(edits) {
            if let (Some(a), Some(b)) = (self.road_of(&row.a), self.road_of(&row.b)) {
                nb.entry(a).or_default().insert(b);
                nb.entry(b).or_default().insert(a);
            }
        }
        let mut seen: HashSet<usize> = changed.iter().filter_map(|x| self.road_of(x)).collect();
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
        previous: &AreaSolved,
        changed: &[String],
        hops: usize,
        max_level: i64,
        margin: f64,
    ) -> Result<(AreaSolved, Option<String>), String> {
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
                            return Err(format!("solve_local: the fixed roads moved by different amounts ({shifts:?})"));
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

    /// The check before rules are added (roadstyle's rule_conflicts): for each of `rows` that conflicts with the enabled rules (the
    /// pairs, `edits` and the rows before it), its index, "duplicate", "not kept" or "loop", and the rows of the rules it conflicts with.
    /// A loop is a cycle of the solver's rules through the new one that no numbers can keep.
    pub fn conflicts(
        &self,
        edits: &[PairRow],
        rows: &[PairRow],
    ) -> Result<Vec<(usize, &'static str, Vec<PairRow>)>, String> {
        let mut rel = self.merged(edits)?;
        let mut out = Vec::new();
        let none = Area {
            roads: self.roads.clone(),
            pairs: Vec::new(),
            of: self.of.clone(),
        };
        for (i, row) in rows.iter().enumerate() {
            if row.off() {
                continue;
            }
            let mut one = none.merged(std::slice::from_ref(row))?;
            let (k, new, _) = one.remove(0);
            if let Some(at) = rel.iter().position(|(kk, _, _)| *kk == k) {
                let others: Vec<_> = rel
                    .iter()
                    .enumerate()
                    .filter(|(j, _)| *j != at)
                    .map(|(_, x)| x.clone())
                    .collect();
                match self.cycle(&others, &new)? {
                    None => out.push((i, "duplicate", vec![rel[at].1.clone()])),
                    Some(path) => out.push((i, "not kept", path)),
                }
                continue;
            }
            if let Some(path) = self.cycle(&rel, &new)? {
                out.push((i, "loop", path));
            }
            rel.push((k, new, true));
        }
        Ok(out)
    }

    /// The rows of a cycle of the rules of `rel` through the rule `new`, or None (roadstyle's _loop): a path in the graph of the rules
    /// `x_i - x_j <= w` (an arc j -> i) from the new rule's i back to its j with a strict step on it (a breadth-first search on (number,
    /// strict yet)).
    fn cycle(
        &self,
        rel: &[(String, PairRow, bool)],
        new: &PairRow,
    ) -> Result<Option<Vec<PairRow>>, String> {
        let (rules, rows) = self.rules(rel)?;
        let mut adj: HashMap<usize, Vec<(usize, bool, Option<usize>)>> = HashMap::new();
        for (i, j, w, src) in difference_rules(&rules) {
            adj.entry(j).or_default().push((i, w < 0, src));
        }
        let (mine, _) = self.rules(&[(String::new(), new.clone(), true)])?;
        let mine: Vec<_> = difference_rules(&mine)
            .into_iter()
            .filter(|r| r.3.is_some())
            .collect();
        for (i, j, w, _) in mine {
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
                    if let Some(s) = src {
                        if !path.contains(&s) {
                            path.push(s);
                        }
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

/// A rule's key (roadstyle's merged_relations): a meet is the same pair whichever road is named first; a stack or near rule is one part.
fn key(r: &PairRow) -> String {
    match r.relation.as_str() {
        "meet" => {
            let mut e = [
                (r.a.as_str(), r.a_end.as_str()),
                (r.b.as_str(), r.b_end.as_str()),
            ];
            e.sort();
            format!("meet|{}|{}|{}|{}", e[0].0, e[0].1, e[1].0, e[1].1)
        }
        "stack" | "near" => format!("{}|{}|{}|{}", r.relation, r.a, r.b, r.a_end),
        _ => format!("{}|{}|{}", r.relation, r.a, r.b),
    }
}

/// The solver's rules as `(i, j, w, row)`: `x_i - x_j <= w` on the columns of roadstyle's _difference_rules (a road's fill is column r,
/// its casing parts n + 3 r + 0 / 1 / 2); `row` is the index of the rule's row (meets, then stacks and near rules, then orders, in the order
/// of `Area::rules`), None for a casing part under its own fill.
fn difference_rules(r: &Rules) -> Vec<(usize, usize, i64, Option<usize>)> {
    let n = r.roads;
    let col = |road: usize, h: usize| n + 3 * road + h;
    let mut out: Vec<_> = (0..n)
        .flat_map(|road| (0..3).map(move |h| (col(road, h), road, 0, None)))
        .collect();
    let mut k = 0;
    let mut by_kind: Vec<(usize, usize, i64, Option<usize>)> = Vec::new();
    for &(x, ex, y, ey) in &r.meets {
        by_kind.push((col(x, ex), y, 0, Some(k)));
        by_kind.push((col(y, ey), x, 0, Some(k)));
        k += 1;
    }
    for &(u, l, h) in r.lifts.iter().chain(&r.near) {
        by_kind.push((l, col(u, h), -1, Some(k)));
        k += 1;
    }
    for &(x, y) in &r.orders {
        by_kind.push((y, x, -1, Some(k)));
        k += 1;
    }
    out.extend(by_kind);
    out
}

/// Why a local answer cannot stand for the whole solve (roadstyle's _worse), or None.
fn worse(local: &AreaSolved, previous: &AreaSolved) -> Option<String> {
    let before: HashSet<_> = previous.given_up_parts.iter().collect();
    let new: Vec<_> = local
        .given_up_parts
        .iter()
        .filter(|p| !before.contains(p))
        .collect();
    if !new.is_empty() {
        return Some(format!(
            "{} crossing part(s) given up that were kept",
            new.len()
        ));
    }
    if local.orders_not_kept.len() > previous.orders_not_kept.len() {
        return Some(format!(
            "{} order wishes not kept, {} before",
            local.orders_not_kept.len(),
            previous.orders_not_kept.len()
        ));
    }
    if local.near_parts.len() > previous.near_parts.len() {
        return Some(format!(
            "{} near warnings, {} before",
            local.near_parts.len(),
            previous.near_parts.len()
        ));
    }
    None
}
