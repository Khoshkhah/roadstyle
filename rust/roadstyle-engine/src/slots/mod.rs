//! The "slots" source: the names and the one-way arrows, from
//! the roads after their stages (roads::mark_roads). Spike S6 (docs/design/rust-spike.md).
//!
//! The graph half (representatives, groups, chains, chain numbers) is `mod.rs` and `chain.rs`. The geometry half (`geom.rs`, `place.rs`) is
//! an R-tree (rstar) for the nearest roads, and segment intersection, projection and point-to-line distance written as GEOS computes them
//! where it matters (the first nearest segment wins a tie; lengths along a line are sums of `sqrt(dx * dx + dy * dy)`). Intersection points
//! are not computed with GEOS's arithmetic, so a slot can differ from a GEOS-based result by a rounding step of its 6 decimals.

mod chain;
mod geom;
mod place;

use crate::road::Roads;
use crate::roads::is_yes;
use crate::simple::Pt;
use indexmap::IndexMap;
use roadstyle_model::mark::Mark;
use roadstyle_model::{Cell, Role};
use serde_json::{json, Value};
use std::collections::HashMap;

pub(crate) use geom::point_line_dist;

/// The look values of the slots (roadstyle-look: look.json "slots" and config.annotations).
pub use roadstyle_look::SlotLook;

type Node = u32; // a road end's node (roadstyle-model's Topology: the point rounded to 6 places)

/// One road of a group: its ends (rounded), its line, and the road it belongs to (owner: its position and its twin's).
struct Rep {
    a: (Node, (f64, f64)),
    z: (Node, (f64, f64)),
    c: Vec<Pt>,
    p: usize, // the road's position
    owner: (usize, Option<usize>),
}

/// The representatives that share a name, level, direction, class, fill number and tunnel (`reps`: their positions in the list).
struct Group {
    name: Option<String>,
    lvl: Value,
    oneway: bool,
    fl: Value,
    tun: bool,
    reps: Vec<usize>,
}

fn class_key(v: Option<Cell>) -> String {
    match v {
        None => String::new(),
        Some(c) if c.is_null() => String::new(),
        Some(c) => c.as_str().map_or_else(|| c.to_value().to_string(), String::from),
    }
}

/// The "slots" source.
pub fn slots_source(roads: &Roads, look: &SlotLook) -> Value {
    let reps = representatives(roads);
    let mut feats: Vec<Value> = groups(roads, &reps).iter().flat_map(|g| place::group_slots(roads, look, g, &reps)).collect();
    mark_roads(roads, &mut feats);
    number_arrows(&mut feats);
    crate::obj([("type", "geojson".into()), ("data", crate::obj([("type", "FeatureCollection".into()), ("features", Value::Array(feats))]))])
}

/// One representative per two-way pair; owner: the road and its twin (or its single-line partner).
fn representatives(roads: &Roads) -> Vec<Rep> {
    let hw_of = |i: usize| roads.role(i, Role::Class);
    // the nodes of the road ends (the Topology's)
    let topo = roads.topo();
    let node = |i: usize, k: usize| -> (Node, (f64, f64)) {
        let n = topo.ends[i].expect("a line of two points or more")[k];
        let p = topo.points[n as usize];
        (n, (p[0], p[1]))
    };
    let mut by_ends: HashMap<(Node, Node, String), usize> = HashMap::new();
    let mut lines = Vec::new();
    for i in (0..roads.len()).filter(|&i| topo.ends[i].is_some()) {
        let (a, z) = (node(i, 0), node(i, 1));
        by_ends.insert((a.0, z.0, class_key(hw_of(i))), i);
        lines.push((i, a, z));
    }
    let mut reps = Vec::new();
    for (i, a, z) in lines {
        let p = roads.road(i);
        if is_yes(p.get(Mark::Dup.name())) {
            continue;
        }
        let twin = by_ends.get(&(z.0, a.0, class_key(hw_of(i)))).copied();
        let two_way = is_yes(p.get(Mark::Twoway.name()));
        if two_way {
            let q_one = twin.is_some_and(|j| is_yes(roads.get(j, Mark::Oneway.name())));
            let mine = (!is_yes(p.get(Mark::Oneway.name())), a.1, z.1);
            let other = (!q_one, z.1, a.1);
            if other.partial_cmp(&mine) == Some(std::cmp::Ordering::Less) {
                continue;
            }
        }
        let partner = if two_way { twin } else { p.get(Mark::Edge2.name()).and_then(Cell::as_u64).and_then(crate::road::row_of) };
        reps.push(Rep { a, z, c: roads.line(i).unwrap().to_vec(), p: i, owner: (i, partner) });
    }
    reps
}

/// The groups, in the order of their first road.
fn groups(roads: &Roads, reps: &[Rep]) -> Vec<Group> {
    let mut groups: IndexMap<String, Group> = IndexMap::new();
    for (r, rep) in reps.iter().enumerate() {
        let p = roads.road(rep.p);
        let name = p.get("name").and_then(Cell::as_str).filter(|s| !s.is_empty()).map(String::from);
        let lvl = p.get("lvl").map_or(json!(0), Cell::to_value);
        let oneway = is_yes(p.get(Mark::Oneway.name()));
        let fl = p.get(Mark::FillLevel.name()).map_or(Value::Null, Cell::to_value);
        let tun = is_yes(p.get(Mark::Tunnel.name()));
        let key = json!([name, lvl, oneway as u8, class_key(roads.role(rep.p, Role::Class)), fl, tun]).to_string();
        groups.entry(key).or_insert_with(|| Group { name, lvl, oneway, fl, tun, reps: Vec::new() }).reps.push(r);
    }
    groups.into_values().collect()
}

/// _mark_cls: each slot has its road's class and access kind (access_col: the same for the names and arrows). The order of the keys:
/// the class before the arrow number.
fn mark_roads(roads: &Roads, feats: &mut [Value]) {
    for f in feats.iter_mut() {
        let e = f["properties"][Mark::Edge.name()].as_u64().and_then(crate::road::row_of).expect("a slot has its road's key");
        f["properties"][Mark::Class.name()] = roads.road(e).cls();
        if let Some(a) = roads.get(e, Mark::Access.name()).filter(|a| !a.is_null()) {
            f["properties"][Mark::Access.name()] = a.to_value();
        }
    }
}

/// The export: number the arrow slots (the odd ones, else the chain's only slot) of each one-way chain.
fn number_arrows(feats: &mut [Value]) {
    let mut by_chain: IndexMap<i64, Vec<usize>> = IndexMap::new();
    for (k, f) in feats.iter().enumerate() {
        if f["properties"]["oneway"] == 1 {
            by_chain.entry(f["properties"]["chain"].as_i64().unwrap()).or_default().push(k);
        }
    }
    let slot = |f: &Value| f["properties"]["slot"].as_i64().unwrap();
    for (_, mut ks) in by_chain {
        ks.sort_by_key(|&k| slot(&feats[k]));
        let odd: Vec<usize> = ks.iter().copied().filter(|&k| slot(&feats[k]) % 2 != 0).collect();
        let pick = if odd.is_empty() { ks[..1].to_vec() } else { odd };
        for (n, k) in pick.into_iter().enumerate() {
            feats[k]["properties"][Mark::SlotArrow.name()] = n.into();
        }
    }
}
