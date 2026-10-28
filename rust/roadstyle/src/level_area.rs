//! A level area's input in Rust (roadstyle's level_area.make_area and level_input, `roadstyle-levels make`): from the edges, the folder's
//! roads.parquet (one row for each road: its edges both ways, its band and priority, the fields the editor shows, each edge's own oneway,
//! driving, directed, edge_ref, lanes and modes, the first edge's line), pairs.csv (the rules between the roads) and an empty edits.csv
//! the first time. The rules come from roadstyle-levels' `make`.

use roadstyle_engine::{level_edges, Cell, RoadTable};
use roadstyle_io::columns::{write_columns, Column};
use roadstyle_levels::{make, Options, Order};
use serde_json::Value;
use std::collections::HashSet;
use std::path::Path;

/// The keywords of roadstyle's make_area / level_input.
#[derive(Clone, Debug)]
pub struct MakeOptions {
    /// The edges' id column (`id_col`, default edge_id; the row number when the edges have none).
    pub id_col: String,
    pub highway_col: String,
    pub layer_col: String,
    pub bridge_col: String,
    pub tunnel_col: String,
    pub junction_col: String,
    /// The caller's bands (integers), else the level from the tags.
    pub band_col: Option<String>,
    /// "priority" (default), "class", a column of numbers, or None.
    pub order: Option<String>,
    pub band_dist: f64,
    pub head_m: f64,
    pub near_rules: bool,
}

impl Default for MakeOptions {
    fn default() -> MakeOptions {
        MakeOptions { id_col: "edge_id".into(), highway_col: "highway".into(), layer_col: "layer".into(), bridge_col: "bridge".into(),
                      tunnel_col: "tunnel".into(), junction_col: "junction".into(), band_col: None, order: Some("priority".into()), band_dist: 10.0,
                      head_m: 5.0, near_rules: false }
    }
}

/// What make_area did: the number of roads and of pairs, and its warnings.
pub struct Made {
    pub roads: usize,
    pub pairs: usize,
    pub warnings: Vec<String>,
}

/// A level area's files in memory: roads.parquet (bytes), pairs.csv and an empty edits.csv (text).
pub struct AreaFiles {
    pub roads: Vec<u8>,
    pub pairs: String,
    pub edits: String,
    pub made: Made,
}

/// The header of an empty edits.csv.
pub const EDITS_HEADER: &str = "relation,a,b,a_end,b_end,enabled\n";

/// The solver's input of the edges `table` in `folder`: roads.parquet and pairs.csv (written again each time) and an empty edits.csv the
/// first time. The folder's heads.csv, when there is one, gives a road's own head lengths.
pub fn make_area(table: &RoadTable, folder: &Path, o: &MakeOptions) -> Result<AreaFiles, crate::Error> {
    let heads = std::fs::read_to_string(folder.join("heads.csv")).unwrap_or_default();
    let f = make_files(table, o, &heads)?;
    std::fs::create_dir_all(folder).map_err(|e| crate::error::file(folder.display(), e))?;
    let write = |name: &str, bytes: &[u8]| std::fs::write(folder.join(name), bytes).map_err(|e| crate::error::file(folder.join(name).display(), e));
    write("roads.parquet", &f.roads)?;
    write("pairs.csv", f.pairs.as_bytes())?;
    if !folder.join("edits.csv").exists() {
        write("edits.csv", f.edits.as_bytes())?;
    }
    Ok(f)
}

/// The solver's input of the edges `table` in memory (a page with no server makes its area so): `heads` is heads.csv's text ("" for none),
/// which gives a road's own head lengths.
pub fn make_files(table: &RoadTable, o: &MakeOptions, heads: &str) -> Result<AreaFiles, crate::Error> {
    let mut warnings = Vec::new();
    let has = |c: &str| table.names().iter().any(|n| n == c);
    let (order, order_col) = match o.order.as_deref() {
        None => (Order::None, ""),
        Some("priority") => (Order::Priority, ""),
        Some("class") => (Order::Class, ""),
        Some(c) => (Order::Column, c),
    };
    if order == Order::Priority && !has(&o.junction_col) {
        warnings.push(format!("the edges have no {:?} column: no road is known as a roundabout, so none is put on top where roads meet (add the \
                               OSM junction tag as {:?}, or pass junction_col=...)", o.junction_col, o.junction_col));
    }
    let band = o.band_col.as_deref().unwrap_or("");
    let cols = [o.highway_col.as_str(), &o.layer_col, &o.bridge_col, &o.tunnel_col, &o.junction_col, band, order_col];
    let mut edges = level_edges(table, cols).into_edges();
    // the ids: the id column's values (whole numbers, duckOSM's BIGINT), else the row numbers
    let ids: Vec<i64> = (0..table.len()).map(|i| match has(&o.id_col) {
        false => Ok(i as i64),
        true => table.get(i, &o.id_col).and_then(|c| cell_text(c)).and_then(|t| t.parse().ok())
            .ok_or_else(|| crate::Error::Model(roadstyle_model::Error::Column { column: o.id_col.clone(), message: format!("make: row {i} is not a whole number") })),
    }).collect::<Result<_, _>>()?;
    for (e, &id) in edges.iter_mut().zip(&ids) {
        e.edge_id = id;
    }
    let heads = read_heads(heads)?;
    let lo = Options { band_col: o.band_col.is_some(), order, band_dist: o.band_dist, head_m: o.head_m, near_rules: o.near_rules, ..Default::default() };
    let input = make(&edges, &lo, &heads)?;
    let id = |i: usize| ids[i];
    let n = input.roads.len();
    let mut out: Vec<(String, Column)> = vec![
        // the ids as Int64 (duckOSM's BIGINT edge ids; roadstyle.level_area.write_roads does the same)
        ("road".into(), Column::Int(input.roads.iter().map(|r| Some(id(r.first))).collect())),
        ("edges".into(), Column::IntList(input.roads.iter().map(|r| r.edges.iter().map(|&e| Some(id(e))).collect()).collect())),
        ("reversed".into(), Column::IntList(input.roads.iter().map(|r| r.reversed.iter().map(|&e| Some(id(e))).collect()).collect())),
        ("band".into(), Column::Int(input.band.iter().map(|&b| Some(b)).collect())),
        ("priority".into(), Column::Float(input.priority.clone())),
    ];
    // the fields the editor shows: the first edge's, modes and bus lines of all the road's edges
    let mut shown: Vec<&str> = Vec::new();
    for c in [o.highway_col.as_str(), "name", "edge_ref", "lanes", "modes", &o.tunnel_col, &o.bridge_col, &o.layer_col] {
        if has(c) && !shown.contains(&c) {
            shown.push(c);
        }
    }
    let all = |r: &roadstyle_levels::InputRoad| r.edges.iter().chain(&r.reversed).copied().collect::<Vec<usize>>();
    for c in shown {
        let col = if c == "modes" {
            Column::Text(input.roads.iter().map(|r| {
                let mut seen: Vec<String> = Vec::new();
                for i in all(r) {
                    for m in table.get(i, "modes").and_then(cell_text).into_iter().flat_map(|t| t.split(" + ").map(String::from).collect::<Vec<_>>()) {
                        if !seen.contains(&m) {
                            seen.push(m);
                        }
                    }
                }
                (!seen.is_empty()).then(|| seen.join(" + "))
            }).collect())
        } else {
            column(input.roads.iter().map(|r| value(table.get(r.first, c))).collect())
        };
        out.push((c.into(), col));
    }
    if has("bus_lines") {
        out.push(("bus_lines".into(), Column::Text(input.roads.iter().map(|r| {
            let mut lines: Vec<String> = Vec::new();
            for i in all(r) {
                for t in table.get(i, "bus_lines").and_then(cell_text).unwrap_or_default().split(',').map(str::trim).filter(|t| !t.is_empty()) {
                    if !lines.iter().any(|l| l == t) {
                        lines.push(t.to_string());
                    }
                }
            }
            lines.sort_by_key(|t| natural(t));
            (!lines.is_empty()).then(|| lines.join(", "))
        }).collect())));
    }
    // each edge's own values, its way and the other way
    let ways = |f: &dyn Fn(usize) -> Value| -> [Vec<Vec<Value>>; 2] {
        [input.roads.iter().map(|r| r.edges.iter().map(|&i| f(i)).collect()).collect(),
         input.roads.iter().map(|r| r.reversed.iter().map(|&i| f(i)).collect()).collect()]
    };
    for (c, names) in [("lanes", ["edges_lanes", "reversed_lanes"]), ("modes", ["edges_modes", "reversed_modes"])] {
        if has(c) {
            for (name, v) in names.into_iter().zip(ways(&|i| value(table.get(i, c)))) {
                out.push((name.into(), list_column(v)));
            }
        }
    }
    if has("edge_ref") {
        for (name, v) in ["edge_refs", "reversed_refs"].into_iter().zip(ways(&|i| table.get(i, "edge_ref").and_then(cell_text).map_or(Value::Null, Value::from))) {
            out.push((name.into(), list_column(v)));
        }
    }
    let flag = |c: &str, i: usize| table.get(i, c).filter(|v| !v.is_null()).map(|v| roadstyle_model::flags::yes(&v.to_value()));
    let single: HashSet<String> = roadstyle_engine::look::Look::resolve(&Default::default())?.sections.roads.flagged("single_line").into_iter().collect();
    // directed (roadstyle's is_directed): open to cars or bikes and not a path; null when the edges have no driving or cycling column
    let directed = |i: usize| -> Option<bool> {
        if !(has("driving") && has("cycling")) {
            return None;
        }
        let path = table.get(i, &o.highway_col).and_then(cell_text).is_some_and(|h| single.contains(&h));
        if path {
            return Some(false);
        }
        match (flag("driving", i), flag("cycling", i)) {
            (Some(true), _) | (_, Some(true)) => Some(true),
            (Some(false), Some(false)) => Some(false),
            _ => None,
        }
    };
    for (c, names) in [("oneway", ["edges_oneway", "reversed_oneway"]), ("driving", ["edges_driving", "reversed_driving"]),
                       ("directed", ["edges_directed", "reversed_directed"])] {
        let f = |i: usize| -> Value { if c == "directed" { directed(i) } else { flag(c, i) }.map_or(Value::Null, Value::from) };
        for (name, v) in names.into_iter().zip(ways(&f)) {
            out.push((name.into(), Column::BoolList(v.into_iter().map(|r| r.iter().map(Value::as_bool).collect()).collect())));
        }
    }
    let wkb = |i: usize| table.line(i).map(roadstyle_io::columns::line_wkb);
    out.push(("geometry".into(), Column::Wkb(input.roads.iter().map(|r| wkb(r.first)).collect())));
    // pairs.csv: the meets, the stacks (one row for each part), the near rules (near_rules), the order wishes, the crossings (a path at a
    // node where a car road goes on: the road's end in a_end)
    let road = |r: usize| id(input.roads[r].first);
    let (end, part) = (["start", "", "end"], ["start", "main", "end"]);
    let mut pairs = String::from("relation,a,b,a_end,b_end\n");
    let r = &input.rules;
    for &(x, ex, y, ey) in &r.meets {
        pairs += &format!("meet,{},{},{},{}\n", road(x), road(y), end[ex], end[ey]);
    }
    for (rel, list) in [("stack", &r.lifts), ("near", &r.near)] {
        for &(u, l, h) in list.iter() {
            pairs += &format!("{rel},{},{},{},\n", road(u), road(l), part[h]);
        }
    }
    for &(x, y) in &r.orders {
        pairs += &format!("order,{},{},,\n", road(x), road(y));
    }
    for &(c, p, h) in &r.crossings {
        pairs += &format!("crossing,{},{},{},\n", road(c), road(p), end[h]);
    }
    let count = r.meets.len() + r.lifts.len() + r.near.len() + r.orders.len() + r.crossings.len();
    Ok(AreaFiles { roads: write_columns(out)?, pairs, edits: EDITS_HEADER.into(), made: Made { roads: n, pairs: count, warnings } })
}

/// A road's own head lengths: an edge id and `[start_m, end_m]` in that edge's way (None: the default).
type Heads = Vec<(i64, [Option<f64>; 2])>;

/// heads.csv's text (`road`, `start_m`, `end_m`; empty: the default), by any edge id of a road.
fn read_heads(text: &str) -> Result<Heads, crate::Error> {
    let mut lines = text.lines().filter(|l| !l.trim().is_empty());
    let head: Vec<&str> = lines.next().unwrap_or("").split(',').map(str::trim).collect();
    let at = |n: &str| head.iter().position(|h| *h == n);
    let (Some(r), s, e) = (at("road"), at("start_m"), at("end_m")) else { return Ok(Vec::new()) };
    lines.map(|l| {
        let f: Vec<&str> = l.split(',').map(str::trim).collect();
        let num = |i: Option<usize>| -> Result<Option<f64>, crate::Error> {
            match i.and_then(|i| f.get(i)).copied().unwrap_or("") {
                "" => Ok(None),
                v => v.parse().map(Some).map_err(|_| crate::error::edits(format!("heads.csv: '{v}' is not a number of metres"))),
            }
        };
        let id = f.get(r).copied().unwrap_or("");
        Ok((id.parse().map_err(|_| crate::error::edits(format!("heads.csv: '{id}' is not an edge id")))?, [num(s)?, num(e)?]))
    }).collect()
}

/// A cell as text (a whole number without ".0"); None when it is null.
fn cell_text(c: Cell) -> Option<String> {
    match c.to_value() {
        Value::Null => None,
        Value::String(s) => Some(s),
        Value::Number(n) => Some(n.as_f64().filter(|f| f.fract() == 0.0 && f.abs() < 1e15).map_or(n.to_string(), |f| format!("{}", f as i64))),
        v => Some(v.to_string()),
    }
}

fn value(c: Option<Cell>) -> Value {
    c.map_or(Value::Null, |c| c.to_value())
}


/// A column of the values' own type, as pandas makes it: booleans, whole numbers (numbers when one is null), numbers or text.
fn column(v: Vec<Value>) -> Column {
    let set: Vec<&Value> = v.iter().filter(|x| !x.is_null()).collect();
    if !set.is_empty() && set.iter().all(|x| x.is_boolean()) {
        Column::Bool(v.iter().map(Value::as_bool).collect())
    } else if !set.is_empty() && set.len() == v.len() && set.iter().all(|x| x.is_i64()) {
        Column::Int(v.iter().map(Value::as_i64).collect())
    } else if !set.is_empty() && set.iter().all(|x| x.is_number()) {
        Column::Float(v.iter().map(Value::as_f64).collect())
    } else {
        Column::Text(v.iter().map(|x| if x.is_null() { None } else { Some(x.as_str().map_or(x.to_string(), String::from)) }).collect())
    }
}

/// A list column of the values' own type.
fn list_column(v: Vec<Vec<Value>>) -> Column {
    let set: Vec<&Value> = v.iter().flatten().filter(|x| !x.is_null()).collect();
    if !set.is_empty() && set.iter().all(|x| x.is_i64()) {
        Column::IntList(v.iter().map(|r| r.iter().map(Value::as_i64).collect()).collect())
    } else if !set.is_empty() && set.iter().all(|x| x.is_number()) {
        Column::FloatList(v.iter().map(|r| r.iter().map(Value::as_f64).collect()).collect())
    } else {
        Column::TextList(v.iter().map(|r| r.iter().map(|x| if x.is_null() { None } else { Some(x.as_str().map_or(x.to_string(), String::from)) }).collect()).collect())
    }
}

/// The natural order of bus line names ("3", "12", "X1"): the digits as numbers.
fn natural(t: &str) -> Vec<(u8, u64, String)> {
    let mut out = Vec::new();
    let mut digits = String::new();
    let mut text = String::new();
    for c in t.chars().chain(std::iter::once('\u{0}')) {
        if c.is_ascii_digit() {
            if !text.is_empty() {
                out.push((1, 0, std::mem::take(&mut text)));
            }
            digits.push(c);
        } else {
            if !digits.is_empty() {
                out.push((0, digits.parse().unwrap_or(u64::MAX), String::new()));
                digits.clear();
            }
            if c != '\u{0}' {
                text.push(c);
            }
        }
    }
    if !text.is_empty() {
        out.push((1, 0, text));
    }
    out
}
