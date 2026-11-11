//! The first part of the 3D bridge engine, the filler (docs/guides/bridge-profile.md, docs/design/bridge_profile_edit.md): it reads an input profile that can be incomplete (every value is
//! optional, down to `{}`), keeps every value that the person gave, and fills every value that is missing from the profile that the rules give for these roads (`decks::today_profile`).
//! It writes a complete profile, which the maker (`decks::make_pieces`) reads. It makes no piece.
//!
//! The rules until the design rules are built are today's rule: the height of a junction from the length of its group and its distance to the free end, the top of a chain, the parameters of
//! today. A value that the engine adds is marked `source: "rule"`, `method: "derived"` (a junction) or `source: "data"`, `method: "mapped"` (a node on the ground), as in the profile of today.
//! A value that the person gave is never changed; one that cannot be true for these roads is an error that says which, and the filler changes nothing to make it true.
//!
//! Two properties are tested: an empty input gives the profile of today, and a complete profile gives itself (the filler twice is the filler once).

use crate::bridge_profile::{metres_between, BridgeProfile, Curve, Kind, Point, FORMAT, MATCH_M};
use crate::Error;
use serde::Deserialize;
use serde_json::Value;
use std::collections::HashMap;

/// An input profile: the same keys as a complete profile, all optional.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Input {
    format: Option<String>,
    parameters: Option<Params>,
    groups: Option<Vec<InGroup>>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Params {
    design_speed_kmh: Option<f64>,
    design_grade: Option<f64>,
    curve: Option<Curve>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct InGroup {
    name: Option<String>,
    nodes: Option<Vec<InNode>>,
    chains: Option<Vec<InChain>>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct InNode {
    id: Option<String>,
    lonlat: Option<[f64; 2]>,
    kind: Option<Kind>,
    chains: Option<Vec<String>>,
    z_m: Option<f64>,
    source: Option<String>,
    method: Option<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct InChain {
    id: Option<String>,
    osm_ways: Option<Vec<i64>>,
    length_m: Option<f64>,
    from: Option<String>,
    to: Option<String>,
    points: Option<Vec<Point>>,
    top_m: Option<f64>,
    width_m: Option<f64>,
    width_source: Option<String>,
}

fn bad<T>(m: String) -> Result<T, Error> {
    Err(Error::Data(format!("bridge_profile: {m}")))
}

/// The complete profile: `found` (the profile that the rules give for these roads) with the values of `input` in place of its own. `warnings` gets the cases that are allowed and
/// probably not wanted (a grade above the design grade between two heights).
pub fn fill(mut found: BridgeProfile, input: &Value, warnings: &mut Vec<String>) -> Result<BridgeProfile, Error> {
    let input: Input = serde_json::from_value(input.clone()).map_err(|e| Error::Data(format!("bridge_profile: {e}. (An input profile has the keys of a complete profile, and every key is optional: docs/reference/formats.md)")))?;
    if let Some(f) = &input.format {
        if f != FORMAT {
            return bad(format!("the format is {f:?}; this engine reads {FORMAT:?}"));
        }
    }
    if let Some(p) = &input.parameters {
        let q = &mut found.parameters;
        q.design_speed_kmh = p.design_speed_kmh.unwrap_or(q.design_speed_kmh);
        q.design_grade = p.design_grade.unwrap_or(q.design_grade);
        q.curve = p.curve.or(q.curve);
    }
    // where each id is: (group, place) in `found`
    let node_at: HashMap<String, (usize, usize)> = found.groups.iter().enumerate().flat_map(|(g, grp)| grp.nodes.iter().enumerate().map(move |(i, n)| (n.id.clone(), (g, i)))).collect();
    let chain_at: HashMap<String, (usize, usize)> = found.groups.iter().enumerate().flat_map(|(g, grp)| grp.chains.iter().enumerate().map(move |(i, c)| (c.id.clone(), (g, i)))).collect();

    let mut entered = std::collections::HashSet::new();                                // the ids of the nodes that the input has an entry for
    let mut given_z = std::collections::HashSet::new();                                // the ids of the nodes whose height the person gave (for the grade warning)
    let mut named: HashMap<usize, String> = HashMap::new();                              // the name a person gave a group, by the found group
    let mut seen_chain = std::collections::HashSet::new();
    for entry in input.groups.iter().flatten() {
        let mut group_of_entry: Option<usize> = None;
        for n in entry.nodes.iter().flatten() {
            let (g, i) = find_node(&found, &node_at, n)?;
            group_of_entry.get_or_insert(g);
            let id = found.groups[g].nodes[i].id.clone();
            if !entered.insert(id.clone()) {
                return bad(format!("two entries of the input are for the node {id}"));
            }
            // a height of the person: not one that the engine wrote in an earlier profile (`rule`, `data`)
            if n.z_m.is_some() && !matches!(n.source.as_deref(), Some("rule" | "data")) {
                given_z.insert(id.clone());
            }
            let node = &mut found.groups[g].nodes[i];
            if n.kind.is_some_and(|k| k != node.kind) {
                return bad(format!("the node {id} is a {:?} in these roads, and the input says {:?}: the input is not for these roads", node.kind, n.kind.unwrap()));
            }
            if n.chains.as_ref().is_some_and(|c| c.iter().collect::<std::collections::BTreeSet<_>>() != node.chains.iter().collect()) {
                return bad(format!("the node {id} has the chains {:?} in these roads, and the input says {:?}: the input is not for these roads", node.chains, n.chains.as_ref().unwrap()));
            }
            if let Some(ll) = n.lonlat {
                node.lonlat = ll;
            }
            match n.z_m {
                Some(z) if !(z.is_finite() && z >= 0.0) => return bad(format!("the node {id} has z_m {z}; a height is a number of metres, 0 or more")),
                Some(z) => {
                    node.z_m = z;
                    node.source = n.source.clone().unwrap_or_else(|| "given".into());
                    node.method = n.method.clone().unwrap_or_else(|| "chosen".into());
                }
                None => {}                      // no height: the rule fills it, and its source and method with it (they say where a height comes from)
            }
        }
        if let (Some(name), Some(g)) = (&entry.name, group_of_entry) {
            if named.insert(g, name.clone()).is_some_and(|old| old != *name) {
                return bad(format!("two entries of the input name the same group: {:?} and {name:?}", named[&g]));
            }
        } else if entry.name.is_some() {
            return bad("a group of the input has a name and no node: the engine finds a group by its nodes, so give one node".into());
        }
    }
    for (g, name) in named {
        found.groups[g].name = name;
    }
    seen_chain.clear();
    let mut given_top: HashMap<String, f64> = HashMap::new();
    for c in input.groups.iter().flatten().flat_map(|g| g.chains.iter().flatten()) {
        let Some(id) = &c.id else { return bad("a chain of the input has no id: name it c1, c2... (the ids are in the complete profile that the engine writes)".into()) };
        let Some(&(g, i)) = chain_at.get(id) else { return bad(format!("the input has the chain {id}, and these roads do not have it: the input is not for these roads")) };
        if !seen_chain.insert(id.clone()) {
            return bad(format!("two entries of the input are for the chain {id}"));
        }
        let chain = &mut found.groups[g].chains[i];
        for (what, got, have) in [("from", &c.from, &chain.from), ("to", &c.to, &chain.to)] {
            if got.as_ref().is_some_and(|x| x != have) {
                return bad(format!("the chain {id} has {what} {have} in these roads, and the input says {:?}: the input is not for these roads", got.as_ref().unwrap()));
            }
        }
        if c.length_m.is_some_and(|l| (l - chain.length_m).abs() > 0.5) {
            return bad(format!("the chain {id} is {:.1} m long in these roads, and the input says {} m: the input is not for these roads", chain.length_m, c.length_m.unwrap()));
        }
        for (what, v) in [("top_m", c.top_m), ("width_m", c.width_m)] {
            if v.is_some_and(|v| !(v.is_finite() && v > 0.0)) {
                return bad(format!("the chain {id} has {what} {}; it is a number of metres above 0", v.unwrap()));
            }
        }
        if let Some(w) = &c.osm_ways {
            chain.osm_ways = w.clone();
        }
        if let Some(p) = &c.points {
            chain.points = p.clone();
        }
        chain.width_m = c.width_m.or(chain.width_m);
        chain.width_source = c.width_source.clone().or(chain.width_source.take());
        if c.width_m.is_some() && chain.width_source.is_none() {
            chain.width_source = Some("given".into());
        }
        if let Some(t) = c.top_m {
            given_top.insert(id.clone(), t);
        }
    }
    // the top of a chain that the person did not give: the top of the rule, or the higher node if a given height is above it. A given top below its nodes is an error.
    for grp in &mut found.groups {
        let z: HashMap<&str, f64> = grp.nodes.iter().map(|n| (n.id.as_str(), n.z_m)).collect();
        for c in &mut grp.chains {
            let high = z[c.from.as_str()].max(z[c.to.as_str()]);
            match given_top.get(&c.id) {
                Some(&t) if high > t + 1e-9 => return bad(format!("the chain {} has top_m {t}, and one of its nodes is {high} m high: a node cannot be above the top of its chain", c.id)),
                Some(&t) => c.top_m = Some(t),
                None => c.top_m = Some(c.top_m.unwrap_or(0.0).max(high)),
            }
        }
    }
    // the average grade of a chain above the design grade, where an end has a height of the person
    for grp in &found.groups {
        let z: HashMap<&str, f64> = grp.nodes.iter().map(|n| (n.id.as_str(), n.z_m)).collect();
        for c in &grp.chains {
            if !(given_z.contains(&c.from) || given_z.contains(&c.to)) {
                continue;
            }
            let grade = (z[c.from.as_str()] - z[c.to.as_str()]).abs() / c.length_m;
            if grade > found.parameters.design_grade + 1e-9 {
                warnings.push(format!("bridge_profile: the chain {} rises {:.1} m in {:.0} m between {} and {} (a grade of {:.3}); the design grade is {}",
                    c.id, (z[c.from.as_str()] - z[c.to.as_str()]).abs(), c.length_m, c.from, c.to, grade, found.parameters.design_grade));
            }
        }
    }
    Ok(found)
}

/// The node of `found` that an entry of the input is for: by its id, or by its position (the one node within `MATCH_M` metres). Both, if the entry has both.
fn find_node(found: &BridgeProfile, node_at: &HashMap<String, (usize, usize)>, n: &InNode) -> Result<(usize, usize), Error> {
    let at = |g: usize, i: usize| &found.groups[g].nodes[i];
    match (&n.id, n.lonlat) {
        (Some(id), ll) => {
            let Some(&(g, i)) = node_at.get(id) else { return bad(format!("the input has the node {id}, and these roads do not have it: the input is not for these roads")) };
            if let Some(ll) = ll {
                let d = metres_between(ll, at(g, i).lonlat);
                if d > MATCH_M {
                    return bad(format!("the node {id} is {d:.0} m from the position that the input gives: the input is not for these roads"));
                }
            }
            Ok((g, i))
        }
        (None, Some(ll)) => {
            let near: Vec<(usize, usize)> = found.groups.iter().enumerate().flat_map(|(g, grp)| (0..grp.nodes.len()).map(move |i| (g, i))).filter(|&(g, i)| metres_between(ll, at(g, i).lonlat) <= MATCH_M).collect();
            match near.as_slice() {
                [one] => Ok(*one),
                [] => bad(format!("no node of these roads is within {MATCH_M} m of {ll:?}: the input is not for these roads")),
                _ => bad(format!("{} nodes of these roads are within {MATCH_M} m of {ll:?}: give the id of the node", near.len())),
            }
        }
        (None, None) => bad("a node of the input has no id and no lonlat: one of them says which node it is".into()),
    }
}
