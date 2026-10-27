//! The level editor in a page (docs/guides/levels.md, "Fix it by hand"): an area folder's roads (roads.parquet, one row for each road
//! with its edges both ways) and pairs, the solver of roadstyle-levels' `area`, and what the page draws and shows. The map is one row for
//! each edge (roadstyle's level_editor._edge_rows): an edge of the other direction runs the road's line backwards, with its heads, casing
//! numbers and caps swapped.

use roadstyle_io::read::{read_table, wkb_line};
use roadstyle_io::write;
use roadstyle_levels::area::{Area, AreaRoad, AreaSolved, Conflict, PairRow, Previous, Relation, Side, Why, HOPS};
use serde_json::{json, Map, Value};
use std::collections::{HashMap, HashSet};

/// The columns of roads.parquet that hold one value for each edge of a road: (the edge's column, its road's columns its way and the other way).
const PER_EDGE: [(&str, &str, &str); 6] = [
    ("edge_ref", "edge_refs", "reversed_refs"),
    ("oneway", "edges_oneway", "reversed_oneway"),
    ("driving", "edges_driving", "reversed_driving"),
    ("directed", "edges_directed", "reversed_directed"),
    ("lanes", "edges_lanes", "reversed_lanes"),
    ("modes", "edges_modes", "reversed_modes"),
];

/// The head length of an end that you did not set, in metres (level_area.defaults).
const HEAD_M: f64 = 5.0;

/// A road's ends as drawn: the head lengths, the caps, and yours (heads, caps; "" = not set), each [start, end] in the road's way.
pub type Ends = ([f64; 2], [String; 2], [String; 2], [String; 2]);

/// Your heads or caps (heads.csv, caps.csv) of each road that has one, by its place: [start, end] in its own way ("" = not set).
type OwnEnds = HashMap<usize, [String; 2]>;

pub struct Editor {
    pub area: Area,
    /// the last answer, for the local re-solve
    last: Option<Previous>,
    /// each road's columns (no list of its edges), its line, and its edges' own values (PER_EDGE) both ways
    cols: Vec<Map<String, Value>>,
    lines: Vec<Vec<[f64; 2]>>,
    own: Vec<[Map<String, Value>; 2]>,
    /// a two-way road's end that meets no other road (pairs.csv): a square cap, else round (level_area.defaults, dead_end_cap)
    dead_square: HashSet<(usize, usize)>,
}

impl Editor {
    /// The area of roads.parquet (bytes) and pairs.csv (text).
    pub fn new(roads: Vec<u8>, pairs: &str) -> Result<Editor, crate::Error> {
        let rows = read_table(roads, "geometry")?;
        let pairs = read_pairs(pairs)?;
        let ids = |v: &Value| -> Result<Vec<i64>, crate::Error> { v.as_array().into_iter().flatten().map(|x| id(&text(x))).collect() };
        let (mut cols, mut lines, mut own, mut roads) =
            (Vec::new(), Vec::new(), Vec::new(), Vec::new());
        for r in rows {
            let line = r
                .blob
                .as_deref()
                .and_then(wkb_line)
                .ok_or_else(|| crate::error::file("roads.parquet", "a road with no line"))?;
            let road = AreaRoad {
                id: id(&text(&r.cols["road"]))?,
                edges: ids(&r.cols["edges"])?,
                reversed: ids(&r.cols["reversed"])?,
            };
            let mut ways: [Map<String, Value>; 2] = Default::default();
            for (name, fw, bw) in PER_EDGE {
                for (k, src) in [fw, bw].into_iter().enumerate() {
                    if let Some(v) = r.cols.get(src) {
                        ways[k].insert(name.into(), v.clone());
                    }
                }
            }
            let mut c = r.cols;
            c.retain(|k, _| {
                k != "edges"
                    && k != "reversed"
                    && !PER_EDGE.iter().any(|(_, a, b)| k == a || k == b)
            });
            cols.push(c);
            lines.push(line);
            own.push(ways);
            roads.push(road);
        }
        for (name, fw, _) in &PER_EDGE[1..4] {
            if !own.iter().any(|w| w[0].contains_key(*name)) {
                return Err(crate::error::file("roads.parquet", format!("this area's file has no per-edge {name} ({fw}): make the area again from edges with that column")));
            }
        }
        let area = Area::new(roads, pairs)?;
        let mut met = HashSet::new();
        for p in area.pairs.iter().filter(|p| p.relation == Relation::Meet) {
            if let (Some(a), Some(b)) = (area.road_of(p.a), area.road_of(p.b)) {
                met.insert((a, usize::from(p.a_end == Some(Side::End))));
                met.insert((b, usize::from(p.b_end == Some(Side::End))));
            }
        }
        let dead_square = area
            .roads
            .iter()
            .enumerate()
            .filter(|(_, r)| !r.edges.is_empty() && !r.reversed.is_empty())
            .flat_map(|(i, _)| [(i, 0), (i, 1)])
            .filter(|e| !met.contains(e))
            .collect();
        Ok(Editor {
            area,
            last: None,
            cols,
            lines,
            own,
            dead_square,
        })
    }

    fn roads(&self) -> &[AreaRoad] {
        &self.area.roads
    }

    /// What the panel shows of each road, a list in the roads' order (level_editor.Area.facts): its names and class, its look, its length in metres, its
    /// directions with their own edge_ref, lanes and modes, and how many of its edges cars may drive.
    pub fn facts(&self) -> String {
        Value::Array((0..self.roads().len()).map(|i| self.fact(i)).collect()).to_string()
    }

    /// What the panel shows of the road `i` (`facts`).
    fn fact(&self, i: usize) -> Value {
        let r = &self.roads()[i];
        let c = &self.cols[i];
        let get = |k: &str| {
            c.get(k)
                .filter(|v| !v.is_null())
                .map(text)
                .unwrap_or_default()
        };
        let opt = |s: String| {
            if s.is_empty() {
                Value::Null
            } else {
                Value::String(s)
            }
        }; // a missing value is null, as Python's _txt
        let mut directions = Vec::new();
        for (k, (way, ids)) in [("along", &r.edges), ("against", &r.reversed)]
            .into_iter()
            .enumerate()
        {
            for (j, e) in ids.iter().enumerate() {
                let at = |name: &str| {
                    self.own[i][k]
                        .get(name)
                        .and_then(|v| v.get(j))
                        .filter(|v| !v.is_null())
                        .map(text)
                        .unwrap_or_default()
                };
                let edge_ref = match self.own[i][k].get("edge_ref") {
                    Some(_) => at("edge_ref"),
                    None if *e == r.id => get("edge_ref"),
                    None => String::new(),
                };
                directions.push(json!({"edge": e.to_string(), "edge_ref": opt(edge_ref), "way": way, "lanes": opt(at("lanes")), "modes": opt(at("modes"))}));
            }
        }
        let flag = |name: &str| {
            (0..2)
                .flat_map(|k| {
                    self.own[i][k]
                        .get(name)
                        .and_then(Value::as_array)
                        .cloned()
                        .unwrap_or_default()
                })
                .collect::<Vec<_>>()
        };
        let yes = |v: &Value| v.is_null() || v.as_bool().unwrap_or(true);
        let driving = flag("driving").iter().filter(|v| yes(v)).count();
        let two_way = !r.reversed.is_empty() && flag("directed").iter().all(yes);
        let truthy = |k: &str| !matches!(get(k).as_str(), "" | "no" | "false" | "0");
        json!({
            "road": r.id.to_string(), "name": opt(get("name")), "highway": opt(get("highway")), "edge_ref": opt(get("edge_ref")), "lanes": opt(get("lanes")),
            "modes": opt(get("modes")), "bus_lines": opt(get("bus_lines")), "band": c.get("band").cloned().unwrap_or(Value::Null),
            "priority": c.get("priority").cloned().unwrap_or(Value::Null), "edges": driving, "two_way": two_way,
            "length_m": (metres(&self.lines[i]) * 10.0).round() / 10.0, "directions": directions,
            "look": if truthy("tunnel") { "tunnel" } else if truthy("bridge") { "bridge" } else { "ground" },
            "width_px": Value::Null,
        })
    }

    /// The road ids, in the roads' order.
    pub fn road_ids(&self) -> Vec<String> {
        self.roads().iter().map(|r| r.id.to_string()).collect()
    }

    /// The road of each id (any edge id or road id; "" when it names none).
    pub fn road_of(&self, ids: &[String]) -> Vec<String> {
        ids.iter().map(|x| id(x).ok().and_then(|e| self.area.road_of(e)).map_or(String::new(), |i| self.roads()[i].id.to_string())).collect()
    }

    /// What the panel shows of the roads of `ids` (any edge id or road id; one that names none is left out), as `facts` gives each, with
    /// its place in the roads' order (`i`) and its ends (`ends` with your heads.csv and caps.csv): `heads` as drawn, `heads_own` (true:
    /// yours), `caps` (yours, "" = not set), and the defaults `heads_auto`, `caps_auto`. JSON text, a list in the order of `ids`.
    pub fn facts_of(&self, ids: &[String], heads: &str, caps: &str) -> Result<String, crate::Error> {
        let own = (self.own_ends(heads, ("start_m", "end_m"))?, self.own_ends(caps, ("start", "end"))?);
        let none = (HashMap::new(), HashMap::new());
        let mut seen = HashSet::new();
        let out: Vec<Value> = ids.iter().filter_map(|x| id(x).ok().and_then(|e| self.area.road_of(e))).filter(|i| seen.insert(*i)).map(|i| {
            let ((h, _, oh, oc), (ha, ca, _, _)) = (self.end_of(i, &own), self.end_of(i, &none));
            let mut f = self.fact(i);
            for (k, v) in [("i", json!(i)), ("heads", json!(h)), ("heads_own", json!(oh.map(|x| !x.is_empty()))), ("caps", json!(oc)),
                           ("heads_auto", json!(ha)), ("caps_auto", json!(ca))] {
                f[k] = v;
            }
            f
        }).collect();
        Ok(Value::Array(out).to_string())
    }

    /// Your heads and caps (heads.csv, caps.csv) of each road that has one: {road id: [[head start, head end], [cap start, cap end]]}
    /// ("" = not set), in the road's own way. JSON text.
    pub fn own_ends_json(&self, heads: &str, caps: &str) -> Result<String, crate::Error> {
        let (h, c) = (self.own_ends(heads, ("start_m", "end_m"))?, self.own_ends(caps, ("start", "end"))?);
        let none = [String::new(), String::new()];
        let out: Map<String, Value> = h.keys().chain(c.keys()).map(|&i| {
            (self.roads()[i].id.to_string(), json!([h.get(&i).unwrap_or(&none), c.get(&i).unwrap_or(&none)]))
        }).collect();
        Ok(Value::Object(out).to_string())
    }

    /// The roads whose edge_ref, or an edge's, has `q` in it (case not counted): [[road id, its edge_ref (null: none), one of them is
    /// `q`]], in the roads' order (the page sorts them). JSON text.
    pub fn find(&self, q: &str) -> String {
        let low = q.trim().to_lowercase();
        let out: Vec<Value> = (0..self.roads().len()).filter_map(|i| {
            let f = self.fact(i);
            let refs: Vec<String> = std::iter::once(&f["edge_ref"]).chain(f["directions"].as_array().into_iter().flatten().map(|d| &d["edge_ref"]))
                .filter_map(Value::as_str).filter(|x| !x.is_empty()).map(str::to_lowercase).collect();
            refs.iter().any(|x| x.contains(&low)).then(|| json!([f["road"], f["edge_ref"], refs.contains(&low)]))
        }).collect();
        Value::Array(out).to_string()
    }

    /// The 4 numbers of each road (its own way) from a levels.csv text (one row for each edge, levels_csv's columns): of its first edge,
    /// else of its first edge the other way (the start and end numbers swapped). None when a road has neither.
    pub fn levels_of(&self, csv: &str) -> Option<Vec<i32>> {
        let mut lines = csv.lines().filter(|l| !l.trim().is_empty());
        let head: Vec<&str> = lines.next()?.split(',').map(str::trim).collect();
        let cols: Vec<usize> = ["edge", "casing_start", "casing_level", "casing_end", "fill_level"].iter()
            .map(|n| head.iter().position(|h| h == n)).collect::<Option<_>>()?;
        // a number as the page reads it (JavaScript's +text, then a 32-bit integer: "" is 0, not a number 0)
        let num = |t: &str| { let t = t.trim(); if t.is_empty() { 0 } else { t.parse::<f64>().map_or(0, |v| v as i32) } };
        let mut at: HashMap<&str, [i32; 4]> = HashMap::new();
        for l in lines {
            let f: Vec<&str> = l.split(',').collect();
            let get = |k: usize| f.get(cols[k]).copied().unwrap_or("");
            at.insert(get(0).trim(), [1, 2, 3, 4].map(|k| num(get(k))));
        }
        let mut out = Vec::with_capacity(4 * self.roads().len());
        for r in self.roads() {
            let edge = |ids: &[i64]| ids.first().and_then(|e| at.get(e.to_string().as_str()));
            out.extend(match (edge(&r.edges), edge(&r.reversed)) {
                (Some(l), _) => *l,
                (None, Some(&[s, m, e, f])) => [e, m, s, f],
                _ => return None,
            });
        }
        Some(out)
    }

    /// The area's edge_hash (roadstyle_levels::edge_hash of every edge both ways), as the host's levels name it.
    pub fn edge_hash(&self) -> String {
        roadstyle_levels::edge_hash(&self.roads().iter().flat_map(|r| r.edges.iter().chain(&r.reversed).copied()).collect::<Vec<_>>())
    }

    /// Each road end as drawn (level_area.ends): your heads.csv and caps.csv (a row may name any edge of a road) over the defaults (5 m
    /// heads; round caps, square at a two-way road's dead end). Per road: `[head_start_m, head_end_m]`, `[cap_start, cap_end]`, and
    /// yours (`""`: not set), in the road's own way.
    pub fn ends(&self, heads: &str, caps: &str) -> Result<Vec<Ends>, crate::Error> {
        let own = (self.own_ends(heads, ("start_m", "end_m"))?, self.own_ends(caps, ("start", "end"))?);
        Ok((0..self.roads().len()).map(|i| self.end_of(i, &own)).collect())
    }

    /// The ends of the road `i` (`ends`) with your heads and caps `own` (`own_ends` of heads.csv and caps.csv).
    fn end_of(&self, i: usize, (own_h, own_c): &(OwnEnds, OwnEnds)) -> Ends {
        let auto_cap = |end: usize| {
            if self.dead_square.contains(&(i, end)) {
                "square"
            } else {
                "round"
            }
            .to_string()
        };
        let h = own_h.get(&i).cloned().unwrap_or_default();
        let c = own_c.get(&i).cloned().unwrap_or_default();
        let len = metres(&self.lines[i]);
        let (mut hs, mut he) = (
            h[0].parse().unwrap_or(HEAD_M),
            h[1].parse().unwrap_or(HEAD_M),
        );
        if hs + he > len && len > 0.0 {
            (hs, he) = (len * hs / (hs + he), len * he / (hs + he));
        }
        let drawn = [0, 1].map(|e| {
            if c[e].is_empty() {
                auto_cap(e)
            } else {
                c[e].clone()
            }
        });
        ([hs, he], drawn, h, c)
    }

    /// `ends` as JSON text, a list in the roads' order: `{"heads", "caps", "heads_own", "caps_own"}`.
    pub fn ends_json(&self, heads: &str, caps: &str) -> Result<String, crate::Error> {
        let ends = self.ends(heads, caps)?;
        let out: Vec<Value> = ends
            .into_iter()
            .map(|(h, c, oh, oc)| json!({"heads": h, "caps": c, "heads_own": oh, "caps_own": oc}))
            .collect();
        Ok(Value::Array(out).to_string())
    }

    /// levels.csv (level_area.write): one row for each edge, its four numbers and its ends as drawn, in its own way.
    pub fn levels_csv(&self, levels: &[i64], heads: &str, caps: &str) -> Result<String, crate::Error> {
        if levels.len() != 4 * self.roads().len() {
            return Err(crate::error::edits(format!("levels: {} numbers for {} roads", levels.len(), self.roads().len())));
        }
        let ends = self.ends(heads, caps)?;
        let mut out = String::from("edge,casing_start,casing_level,casing_end,fill_level,head_start_m,head_end_m,cap_start,cap_end\n");
        let num = |v: f64| {
            if v.fract() == 0.0 {
                format!("{v:.1}")
            } else {
                format!("{v}")
            }
        };
        for (i, r) in self.roads().iter().enumerate() {
            let (l, (h, c, _, _)) = (&levels[4 * i..4 * i + 4], &ends[i]);
            for e in &r.edges {
                out += &format!(
                    "{e},{},{},{},{},{},{},{},{}\n",
                    l[0],
                    l[1],
                    l[2],
                    l[3],
                    num(h[0]),
                    num(h[1]),
                    c[0],
                    c[1]
                );
            }
            for e in &r.reversed {
                out += &format!(
                    "{e},{},{},{},{},{},{},{},{}\n",
                    l[2],
                    l[1],
                    l[0],
                    l[3],
                    num(h[1]),
                    num(h[0]),
                    c[1],
                    c[0]
                );
            }
        }
        Ok(out)
    }

    /// heads.csv or caps.csv as {road: [start, end]} ("" = not set), each row by any edge of its road (an edge against its road: the two
    /// ends swapped).
    fn own_ends(
        &self,
        csv: &str,
        names: (&str, &str),
    ) -> Result<HashMap<usize, [String; 2]>, crate::Error> {
        let mut lines = csv.lines().filter(|l| !l.trim().is_empty());
        let Some(head) = lines.next() else {
            return Ok(HashMap::new());
        };
        let head: Vec<&str> = head.split(',').map(str::trim).collect();
        let at = |n: &str| head.iter().position(|h| *h == n);
        let (Some(r), s, e) = (at("road"), at(names.0), at(names.1)) else {
            return Ok(HashMap::new());
        };
        let mut out = HashMap::new();
        for l in lines {
            let f: Vec<&str> = l.split(',').collect();
            let get = |i: Option<usize>| {
                i.and_then(|i| f.get(i))
                    .map(|v| v.trim().to_string())
                    .unwrap_or_default()
            };
            let text = get(Some(r));
            let road = id(&text).ok().and_then(|i| self.area.road_of(i))
                .ok_or_else(|| crate::error::edits(format!("{}: '{text}' names no road of this area", names.0)))?;
            let back = id(&text).is_ok_and(|i| self.roads()[road].reversed.contains(&i));
            let v = if back {
                [get(e), get(s)]
            } else {
                [get(s), get(e)]
            };
            out.insert(road, v);
        }
        Ok(out)
    }

    /// The map's table: one row for each edge with its road's columns, its own values, `edge`, `road`, the four numbers, the ends as drawn
    /// and its road's two end points (`s_lon`, `s_lat`, `e_lon`, `e_lat`), as GeoParquet. `levels`: 4 numbers for each road, its own way.
    pub fn draw(&self, levels: &[i64], heads: &str, caps: &str) -> Result<Vec<u8>, crate::Error> {
        let n = self.roads().len();
        if levels.len() != 4 * n {
            return Err(crate::error::edits(format!("draw: {} numbers for {n} roads", levels.len())));
        }
        let ends = self.ends(heads, caps)?;
        let mut rows = Vec::new();
        for (i, r) in self.roads().iter().enumerate() {
            let lv = &levels[4 * i..4 * i + 4];
            let line = &self.lines[i];
            let (s, e) = (line[0], line[line.len() - 1]);
            for (k, ids) in [&r.edges, &r.reversed].into_iter().enumerate() {
                for (j, id) in ids.iter().enumerate() {
                    let back = k == 1;
                    let mut props: Vec<(String, Value)> = self.cols[i]
                        .iter()
                        .filter(|(c, _)| *c != "road")
                        .map(|(c, v)| (c.clone(), v.clone()))
                        .collect();
                    for (name, _, _) in PER_EDGE {
                        if let Some(v) = self.own[i][k].get(name) {
                            props.retain(|(c, _)| c != name);
                            props.push((name.into(), v.get(j).cloned().unwrap_or(Value::Null)));
                        }
                    }
                    let (hd, cp) = (&ends[i].0, &ends[i].1);
                    let (a, b) = if back { (1, 0) } else { (0, 1) };
                    props.extend([
                        ("edge".into(), json!(id.to_string())), // text: JavaScript holds no 64-bit integer exactly
                        ("road".into(), json!(r.id.to_string())),
                        (
                            "casing_start".into(),
                            json!(if back { lv[2] } else { lv[0] }),
                        ),
                        ("casing_level".into(), json!(lv[1])),
                        ("casing_end".into(), json!(if back { lv[0] } else { lv[2] })),
                        ("fill_level".into(), json!(lv[3])),
                        ("head_start_m".into(), json!(hd[a])),
                        ("head_end_m".into(), json!(hd[b])),
                        ("cap_start".into(), json!(cp[a])),
                        ("cap_end".into(), json!(cp[b])),
                        ("s_lon".into(), json!(s[0])),
                        ("s_lat".into(), json!(s[1])),
                        ("e_lon".into(), json!(e[0])),
                        ("e_lat".into(), json!(e[1])),
                    ]);
                    let coords: Vec<Value> = if back {
                        line.iter().rev().map(|p| json!(p)).collect()
                    } else {
                        line.iter().map(|p| json!(p)).collect()
                    };
                    rows.push(write::Row {
                        id: None,
                        props: props.into_iter().map(|(k, v)| (k.into(), v.into())).collect(),
                        geometry: Some(json!({"type": "LineString", "coordinates": coords}).into()),
                    });
                }
            }
        }
        write::parquet(
            || {
                rows.iter().map(|r| write::Row {
                    id: r.id,
                    props: r.props.clone(),
                    geometry: r.geometry.clone(),
                })
            },
            true,
        )
        .map_err(crate::Error::from)
    }
}

/// How an answer was solved: the whole area, or only the roads around a change.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum How {
    Full,
    Local,
}

/// A solve's answer (`Editor::solve`, `solve_local`): the numbers of each road (the roads' order), the rules not kept by road id, the
/// counts, and how it was solved (`why`: the reason for a whole solve after a change).
#[derive(Clone, Debug)]
pub struct Answer {
    pub levels: Vec<[i64; 4]>,
    pub given_up: Vec<(i64, i64)>,
    pub given_up_parts: Vec<(i64, i64, Side)>,
    pub near: Vec<(i64, i64, Side)>,
    pub orders_not_kept: Vec<(i64, i64)>,
    /// The crossings (road, path, the road's end) whose path is not under the road's head, and the number of crossings.
    pub crossings_not_kept: Vec<(i64, i64, Side)>,
    pub crossings: usize,
    pub roads: usize,
    pub pairs: usize,
    pub meets: usize,
    pub order_pairs: usize,
    /// The road pairs with a near warning.
    pub near_warnings: usize,
    pub how: How,
    pub why: Option<String>,
}

impl Answer {
    /// The answer as the page reads it, the road ids as text (JavaScript holds no 64-bit integer exactly).
    pub fn to_json(&self) -> Value {
        let pairs = |v: &[(i64, i64)]| v.iter().map(|&(a, b)| json!([a.to_string(), b.to_string()])).collect::<Vec<_>>();
        let parts = |v: &[(i64, i64, Side)]| v.iter().map(|&(a, b, h)| json!([a.to_string(), b.to_string(), side_name(h)])).collect::<Vec<_>>();
        json!({"levels": self.levels, "given_up": pairs(&self.given_up), "given_up_parts": parts(&self.given_up_parts),
               "near": parts(&self.near), "orders_not_kept": pairs(&self.orders_not_kept), "crossings_not_kept": parts(&self.crossings_not_kept),
               "info": {"roads": self.roads, "pairs": self.pairs, "meets": self.meets, "order_pairs": self.order_pairs,
                        "order_violations": self.orders_not_kept.len(), "near_warnings": self.near_warnings, "crossings": self.crossings,
                        "crossing_violations": self.crossings_not_kept.len(), "solver": "rust"},
               "resolve": {"how": match self.how { How::Full => "full", How::Local => "local" }, "why": self.why}})
    }
}

/// The check's conflicts as the page reads them: `[[index, why, [rule rows]]]`, why "duplicate", "not kept" or "loop".
pub fn conflicts_json(found: &[Conflict]) -> Value {
    let why = |w: Why| match w {
        Why::Duplicate => "duplicate",
        Why::NotKept => "not kept",
        Why::Loop => "loop",
    };
    Value::Array(found.iter().map(|c| json!([c.row, why(c.why), c.with.iter().map(row_json).collect::<Vec<_>>()])).collect())
}

impl Editor {
    /// The whole solve with the edits (edits.csv text).
    pub fn solve(&mut self, edits: &str) -> Result<Answer, crate::Error> {
        let s = self.area.solve(&read_pairs(edits)?, &HashMap::new(), 20, 1.0)?;
        self.last = Some(Previous::from(&s));
        Ok(self.answer(&s, How::Full, None))
    }

    /// The solve after a change that names the roads of `changed` (edge ids): the roads around it (local), else the whole area.
    pub fn solve_local(&mut self, edits: &str, changed: &[String]) -> Result<Answer, crate::Error> {
        let Some(prev) = &self.last else { return self.solve(edits) };
        let changed = changed.iter().map(|c| id(c)).collect::<Result<Vec<_>, _>>()?;
        let (s, why) = self.area.solve_local(&read_pairs(edits)?, prev, &changed, HOPS, 20, 1.0)?;
        self.last = Some(Previous::from(&s));
        Ok(self.answer(&s, if why.is_some() { How::Full } else { How::Local }, why))
    }

    /// The answer that the page starts from (levels.csv and levels_info.json, not solved again): 4 numbers for each road in its own way,
    /// the given-up parts (upper, lower, part) as levels_info.json has them, and the numbers of order wishes not kept, near warnings and
    /// crossings not kept.
    pub fn start_from(&mut self, levels: &[i64], given_up_parts: &[(String, String, String)], orders_not_kept: usize, near: usize,
                      crossings: usize) -> Result<(), crate::Error> {
        let n = self.roads().len();
        if levels.len() != 4 * n {
            return Err(crate::error::edits(format!("levels: {} numbers for {n} roads", levels.len())));
        }
        let road = |t: &str| id(t).ok().and_then(|i| self.area.road_of(i)).ok_or_else(|| crate::error::edits(format!("levels_info: '{t}' is not a road")));
        let parts = given_up_parts.iter().map(|(u, l, h)| Ok((road(u)?, road(l)?, side(h)?.ok_or_else(|| crate::error::edits("levels_info: a part with no name"))?)))
            .collect::<Result<_, crate::Error>>()?;
        self.last = Some(Previous { levels: levels.chunks(4).map(|c| [c[0], c[1], c[2], c[3]]).collect(), given_up_parts: parts, orders_not_kept, near, crossings });
        Ok(())
    }

    /// The check before rules are added (rows: CSV text with a header): the rows that conflict (`conflicts_json` for the page).
    pub fn check(&self, edits: &str, rows: &str) -> Result<Vec<Conflict>, crate::Error> {
        Ok(self.area.conflicts(&read_pairs(edits)?, &read_pairs(rows)?)?)
    }

    /// The typed answer of a solve: the area's road numbers as road ids.
    fn answer(&self, s: &AreaSolved, how: How, why: Option<String>) -> Answer {
        let id = |r: usize| self.roads()[r].id;
        let pairs = |v: &[(usize, usize)]| v.iter().map(|&(a, b)| (id(a), id(b))).collect();
        let parts = |v: &[(usize, usize, Side)]| v.iter().map(|&(a, b, h)| (id(a), id(b), h)).collect();
        let near: HashSet<(usize, usize)> = s.near_parts.iter().map(|&(u, l, _)| (u, l)).collect();
        Answer { levels: s.levels.clone(), given_up: pairs(&s.given_up), given_up_parts: parts(&s.given_up_parts), near: parts(&s.near_parts),
                 orders_not_kept: pairs(&s.orders_not_kept), crossings_not_kept: parts(&s.crossings_not_kept), crossings: s.crossings,
                 roads: self.roads().len(), pairs: s.pairs, meets: s.meets, order_pairs: s.order_pairs,
                 near_warnings: near.len(), how, why }
    }
}

/// The rows of pairs.csv or edits.csv (a header, then relation, a, b, a_end, b_end and enabled by name; pandas' quotes).
pub fn read_pairs(csv: &str) -> Result<Vec<PairRow>, crate::Error> {
    let mut lines = csv.lines().filter(|l| !l.trim().is_empty());
    let Some(head) = lines.next() else { return Ok(Vec::new()) };
    let head = fields(head);
    let at = |name: &str| head.iter().position(|h| h == name);
    if at("relation").is_none() || at("a").is_none() || at("b").is_none() {
        return Err(crate::error::edits("pairs: the columns relation, a and b are missing"));
    }
    lines.map(|l| {
        let f = fields(l);
        let col = |name: &str| at(name).and_then(|i| f.get(i)).map_or("", |s| s.as_str()).trim().to_string();
        let relation = match col("relation").as_str() {
            "meet" => Relation::Meet,
            "stack" => Relation::Stack,
            "near" => Relation::Near,
            "order" => Relation::Order,
            "crossing" => Relation::Crossing,
            r => return Err(crate::error::edits(format!("pairs: the relation '{r}' is not meet, stack, crossing, near or order"))),
        };
        Ok(PairRow { relation, a: id(&col("a"))?, b: id(&col("b"))?, a_end: side(&col("a_end"))?, b_end: side(&col("b_end"))?,
                     enabled: !matches!(col("enabled").to_lowercase().as_str(), "false" | "0" | "no") })
    }).collect()
}

/// A row as JSON, as the panel shows a rule.
fn row_json(r: &PairRow) -> Value {
    let rel = match r.relation {
        Relation::Meet => "meet",
        Relation::Stack => "stack",
        Relation::Near => "near",
        Relation::Order => "order",
        Relation::Crossing => "crossing",
    };
    json!({"relation": rel, "a": r.a.to_string(), "b": r.b.to_string(), "a_end": r.a_end.map_or("", side_name), "b_end": r.b_end.map_or("", side_name)})
}

fn side(s: &str) -> Result<Option<Side>, crate::Error> {
    match s {
        "" => Ok(None),
        "start" => Ok(Some(Side::Start)),
        "main" => Ok(Some(Side::Main)),
        "end" => Ok(Some(Side::End)),
        s => Err(crate::error::edits(format!("pairs: the end '{s}' is not start, main or end"))),
    }
}

fn side_name(s: Side) -> &'static str {
    ["start", "main", "end"][s.index()]
}

/// An edge or road id: a whole number (duckOSM's edge ids are BIGINT).
fn id(s: &str) -> Result<i64, crate::Error> {
    s.trim().parse().map_err(|_| crate::error::edits(format!("'{s}' is not an edge id (a whole number)")))
}

/// The fields of a CSV line, with quotes as pandas writes them.
fn fields(line: &str) -> Vec<String> {
    let (mut out, mut cur, mut quoted, mut chars) = (Vec::new(), String::new(), false, line.chars().peekable());
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

/// A value as the text of the files (a number without ".0" when it is whole).
fn text(v: &Value) -> String {
    match v {
        Value::String(s) => s.clone(),
        Value::Null => String::new(),
        Value::Number(n) => n
            .as_f64()
            .filter(|f| f.fract() == 0.0 && f.abs() < 1e15)
            .map_or(n.to_string(), |f| format!("{}", f as i64)),
        v => v.to_string(),
    }
}

/// The length of a line of (lon, lat) points in metres (a sphere of the WGS84 mean radius; the editor shows it to 0.1 m).
fn metres(line: &[[f64; 2]]) -> f64 {
    line.windows(2)
        .map(|w| {
            let (p, q) = (w[0], w[1]);
            let (la1, la2) = (p[1].to_radians(), q[1].to_radians());
            let (dla, dlo) = (la2 - la1, (q[0] - p[0]).to_radians());
            let h = (dla / 2.0).sin().powi(2) + la1.cos() * la2.cos() * (dlo / 2.0).sin().powi(2);
            2.0 * 6_371_008.8 * h.sqrt().asin()
        })
        .sum()
}
