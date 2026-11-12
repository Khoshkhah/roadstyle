//! The first part of the 3D bridge engine, the filler (docs/guides/bridge-profile.md, docs/design/bridge_profile_edit.md): it reads an input profile that can be incomplete (every value is
//! optional, down to `{}`), keeps every value that the person gave, and fills every value that is missing from the profile that the rules give for these roads (`decks::today_profile`).
//! It writes a complete profile, which the maker (`decks::make_pieces`) reads. It makes no piece.
//!
//! The rules are two. The default is today's rule: the height of a junction from the length of its group and its distance to the free end, the top of a chain, the parameters of today. With
//! `parameters.height_rule: "design"` the heights follow the design rules (`design_heights`, docs/design/bridge_height_design.md): the highest junction that the design grade allows from the
//! ground and from every height the person gave, and not above the top that the clearance needs; the chain between two nodes rises at the design grade to its top and comes down at the same grade,
//! and the curve is `design`. With the curve `design` the filler also writes the length of the vertical curve at every interior point (`bridge_curve::curve_length`) and the top of every chain. A value that the engine adds is marked `source: "rule"`, `method: "derived"` (a junction) or `source: "data"`, `method: "mapped"` (a node on the ground), as in the profile of today.
//! A value that the person gave is never changed; one that cannot be true for these roads is an error that says which, and the filler changes nothing to make it true.
//!
//! Two properties are tested: an empty input gives the profile of today, and a complete profile gives itself (the filler twice is the filler once).

use crate::bridge_curve::{self, Pvi};
use crate::bridge_profile::{metres_between, BridgeProfile, Curve, Ground, Kind, Point, Rule, ZReference, FORMAT, MATCH_M};
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
    ground: Option<Ground>,
    groups: Option<Vec<InGroup>>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Params {
    design_speed_kmh: Option<f64>,
    design_grade: Option<f64>,
    curve: Option<Curve>,
    height_rule: Option<Rule>,
    z_reference: Option<ZReference>,
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
    portal: Option<bool>,
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

/// The error for a free end of a bridge (a node where one chain ends) with a height above 0: the end is on the ground, so the height is wrong.
pub fn ground_end(id: &str, z: f64) -> String {
    format!("the node {id} is a free end of its bridge, so it is on the ground, and its z_m is {z}: a deck that ends in the air is a wrong height. Give 0, or leave z_m out")
}

/// The error for a profile with `z_reference: "elevation"` that does not name its ground: an elevation means nothing without the vertical datum of the ground that it is measured in.
pub fn elevation_needs_ground() -> String {
    "z_reference is \"elevation\", so the profile must name its ground (ground.id, the SHA-256 of the elevation file; ground.vertical_datum): an elevation means nothing without the datum that it is in".into()
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
    if input.ground.is_some() {
        found.ground = input.ground.clone();
    }
    let given_params = input.parameters.as_ref();
    let elev = given_params.and_then(|p| p.z_reference) == Some(ZReference::Elevation);
    if let Some(r) = given_params.and_then(|p| p.z_reference) {
        found.parameters.z_reference = Some(r);
    }
    if elev {
        // the heights are elevations: no rule can find one (the rules measure from the ground), and the curve is `design` (the ramps of `smooth` start on the ground)
        if given_params.and_then(|p| p.height_rule) == Some(Rule::Design) {
            return bad("z_reference is \"elevation\", so every node needs its own elevation: the rule height_rule \"design\" finds heights above the ground, and cannot be used".into());
        }
        if given_params.and_then(|p| p.curve) == Some(Curve::Smooth) {
            return bad("z_reference is \"elevation\", which needs the curve \"design\": the curve \"smooth\" makes ramps from the ground".into());
        }
        found.parameters.curve = Some(Curve::Design);
        if input.ground.as_ref().and_then(|g| g.id.as_ref()).is_none() {
            return bad(elevation_needs_ground());
        }
    }
    if given_params.and_then(|p| p.height_rule) == Some(Rule::Design) {
        // the design rules: 5 % unless the person gives a grade, and the curve `design` unless the person gives the curve
        found.parameters.height_rule = Some(Rule::Design);
        found.parameters.design_grade = DESIGN_GRADE;
        found.parameters.curve = Some(Curve::Design);
    } else if let Some(r) = given_params.and_then(|p| p.height_rule) {
        found.parameters.height_rule = Some(r);
    }
    if let Some(p) = given_params {
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
    let mut fixed_z = std::collections::HashSet::new();                                // the ids of the nodes that have a height in the input, whoever made it: the rules keep it
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
            if n.z_m.is_some() {
                fixed_z.insert(id.clone());
            }
            // a height of the person: not one that the engine wrote in an earlier profile (`rule`, `data`)
            if n.z_m.is_some() && !matches!(n.source.as_deref(), Some("rule" | "data")) {
                given_z.insert(id.clone());
            }
            let node = &mut found.groups[g].nodes[i];
            if n.kind.is_some_and(|k| k != node.kind) {
                return bad(format!("the node {id} is a {:?} in these roads, and the input says {:?}: the input is not for these roads", node.kind, n.kind.unwrap()));
            }
            if n.portal.is_some_and(|p| p != node.portal) {
                return bad(format!("the node {id} is {} portal in these roads (a free end of a bridge where a road of level below 0 starts), and the input says portal {}: the input is not for these roads", if node.portal { "a" } else { "not a" }, n.portal.unwrap()));
            }
            if n.chains.as_ref().is_some_and(|c| c.iter().collect::<std::collections::BTreeSet<_>>() != node.chains.iter().collect()) {
                return bad(format!("the node {id} has the chains {:?} in these roads, and the input says {:?}: the input is not for these roads", node.chains, n.chains.as_ref().unwrap()));
            }
            if let Some(ll) = n.lonlat {
                node.lonlat = ll;
            }
            match n.z_m {
                Some(z) if !(z.is_finite() && (elev || z >= 0.0)) => return bad(format!("the node {id} has z_m {z}; a height is a number of metres, 0 or more")),
                Some(z) if !elev && node.kind == Kind::Ground && z != 0.0 => return bad(ground_end(&id, z)),
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
    let mut given_points = std::collections::HashSet::new();                           // the ids of the chains that have `points` in the input (an empty list is a list)
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
            if v.is_some_and(|v| !(v.is_finite() && (v > 0.0 || (elev && what == "top_m")))) {
                return bad(format!("the chain {id} has {what} {}; it is a number of metres above 0", v.unwrap()));
            }
        }
        if let Some(w) = &c.osm_ways {
            chain.osm_ways = w.clone();
        }
        if let Some(p) = &c.points {
            chain.points = p.clone();
            given_points.insert(id.clone());
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
    if elev {
        let missing: Vec<&str> = found.groups.iter().flat_map(|g| g.nodes.iter()).filter(|n| !fixed_z.contains(&n.id)).map(|n| n.id.as_str()).collect();
        if !missing.is_empty() {
            let shown = missing.iter().take(8).copied().collect::<Vec<_>>().join(", ");
            return bad(format!("z_reference is \"elevation\", so every node needs its elevation in z_m, and {} nodes have none: {shown}{}", missing.len(), if missing.len() > 8 { ", ..." } else { "" }));
        }
    }
    if found.parameters.height_rule == Some(Rule::Design) {
        design_heights(&mut found, &fixed_z, warnings);
        if found.parameters.curve == Some(Curve::Design) {
            design_points(&mut found, &given_points, warnings);
        }
    }
    // the top of a chain that the person did not give: the top of the rule, or the higher node if a given height is above it. A given top below its nodes is an error.
    for grp in &mut found.groups {
        let z: HashMap<&str, f64> = grp.nodes.iter().map(|n| (n.id.as_str(), n.z_m)).collect();
        for c in &mut grp.chains {
            let high = z[c.from.as_str()].max(z[c.to.as_str()]);
            if found.parameters.curve == Some(Curve::Design) {
                // the curve `design` draws the lift as the height over the top: the top is the highest point of the chain (a curve is never above its points)
                let top = c.points.iter().map(|p| p.z_m).fold(high, f64::max);
                match given_top.get(&c.id) {
                    Some(&t) if top > t + 1e-9 => return bad(format!("the chain {} has top_m {t}, and its highest point is {top} m high: a point cannot be above the top of its chain", c.id)),
                    Some(&t) => c.top_m = Some(t),
                    None => c.top_m = Some(if elev { top } else { top.max(MIN_TOP_M) }),
                }
                continue;
            }
            match given_top.get(&c.id) {
                Some(&t) if high > t + 1e-9 => return bad(format!("the chain {} has top_m {t}, and one of its nodes is {high} m high: a node cannot be above the top of its chain", c.id)),
                Some(&t) => c.top_m = Some(t),
                None => c.top_m = Some(c.top_m.unwrap_or(0.0).max(high)),
            }
        }
    }
    if found.parameters.curve == Some(Curve::Design) {
        design_curves(&mut found, warnings)?;
    }
    // the average grade of a chain above the design grade, where an end has a height of the person
    for grp in &found.groups {
        let z: HashMap<&str, f64> = grp.nodes.iter().map(|n| (n.id.as_str(), n.z_m)).collect();
        for c in &grp.chains {
            if !(given_z.contains(&c.from) || given_z.contains(&c.to)) || found.parameters.curve == Some(Curve::Design) {
                continue;                          // (with the curve `design` every straight grade is checked: `design_curves`)
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

/// The design grade of the rule `design`, as a fraction (5 %).
const DESIGN_GRADE: f64 = 0.05;
/// The clearance under a bridge over a road (rule 1 of the design note: 4.9 m for a freeway or an arterial, and 0.15 m for a new surface), the least depth of the structure, and the span
/// that the filler assumes when it knows no obstacle: the length of the chain, and at most this.
const CLEARANCE_M: f64 = 5.0;
const DEPTH_MIN_M: f64 = 0.8;
const ASSUMED_SPAN_MAX_M: f64 = 100.0;
/// The top of a chain that stays on the ground: a chain needs a top above 0.
const MIN_TOP_M: f64 = 0.1;
/// A level top longer than this has no drainage; the rule gives it a crest with this grade on each side (rule 6 of the design note: at least 0.5 %).
const DRAIN_FROM_M: f64 = 76.0;
const DRAIN_GRADE: f64 = 0.005;
/// A point that the rule makes is not nearer than this to an end or to the point before it (the shape would change by less than 5 % of this).
const MIN_GAP_M: f64 = 0.5;

/// The top `P` of a chain with no known obstacle: the clearance and the depth of the structure for a span of the chain's length, at most `ASSUMED_SPAN_MAX_M` (the design note, "The data that the engine needs").
fn top_of(length: f64) -> f64 {
    CLEARANCE_M + (length.min(ASSUMED_SPAN_MAX_M) / 25.0).max(DEPTH_MIN_M)
}

/// The heights of the junctions by the design rules. A node on the ground, and a node that has a height in the input, is a fixed point. The height of any other node is the highest height that the
/// design grade allows from every fixed point along the chains (`z_fixed + grade × distance`, the smallest), and not above the top `P` of the chains that meet there. A group with no fixed point
/// has the top. Written with `source: "rule"` and `method: "derived"`, as the rule of the length writes them.
fn design_heights(found: &mut BridgeProfile, fixed: &std::collections::HashSet<String>, _warnings: &mut Vec<String>) {
    let g = found.parameters.design_grade;
    for grp in &mut found.groups {
        let at: HashMap<&str, usize> = grp.nodes.iter().enumerate().map(|(i, n)| (n.id.as_str(), i)).collect();
        // the equivalent distance of a node: the distance along the chains to a fixed point, plus the distance that its height takes at the grade
        let mut eq: Vec<f64> = grp.nodes.iter().map(|n| if n.kind == Kind::Ground || fixed.contains(&n.id) { n.z_m / g } else { f64::INFINITY }).collect();
        loop {
            let mut changed = false;
            for c in &grp.chains {
                let (a, b) = (at[c.from.as_str()], at[c.to.as_str()]);
                for (x, y) in [(a, b), (b, a)] {
                    if eq[x] + c.length_m < eq[y] - 1e-9 {
                        eq[y] = eq[x] + c.length_m;
                        changed = true;
                    }
                }
            }
            if !changed {
                break;
            }
        }
        let top: Vec<f64> = grp.nodes.iter().map(|n| grp.chains.iter().filter(|c| c.from == n.id || c.to == n.id).map(|c| top_of(c.length_m)).fold(0.0, f64::max)).collect();
        for (i, n) in grp.nodes.iter_mut().enumerate() {
            if n.kind == Kind::Junction && !fixed.contains(&n.id) {
                n.z_m = (g * eq[i]).min(top[i]);
                n.source = "rule".into();
                n.method = "derived".into();
            }
        }
    }
}

/// The interior points of the chains that have none in the input (a chain whose input has `points`, even an empty list, keeps them): from each end the deck rises at the design grade until it
/// is at the top of the chain (the larger of its `P` and its two nodes), and comes down at the same grade to the other end. A chain too short to reach the top has one crest. Two nodes that are
/// further apart in height than the grade allows give a straight chain (the warning of the grade is the one of `fill`).
fn design_points(found: &mut BridgeProfile, given: &std::collections::HashSet<String>, warnings: &mut Vec<String>) {
    let g = found.parameters.design_grade;
    for grp in &mut found.groups {
        let kind_z: HashMap<String, (Kind, f64)> = grp.nodes.iter().map(|n| (n.id.clone(), (n.kind, n.z_m))).collect();
        for c in grp.chains.iter_mut().filter(|c| !given.contains(&c.id)) {
            let ((k0, z0), (k1, z1)) = (kind_z[&c.from], kind_z[&c.to]);
            let (l, p) = (c.length_m, top_of(c.length_m));
            let t = p.max(z0).max(z1);
            c.points.clear();
            if (z0 - z1).abs() > g * l + 1e-9 {
                continue;
            }
            let (a, b) = ((t - z0) / g, (t - z1) / g);
            let at: Vec<(f64, f64)> = if a + b <= l {
                let run = l - a - b;
                if run > DRAIN_FROM_M {
                    // a flat top has no drainage (rule 6): the top has a grade of at least 0.5 %. The ramps from the two nodes reach the sides of the top, a little under `t` (or at the node, if the
                    // node is higher), and from the sides the top rises at 0.5 % to a crest in between. Two sides that differ by more than the crest allows are joined by one straight grade
                    let t_low = t - DRAIN_GRADE * run / 2.0;
                    let (tl, tr) = (t_low.max(z0), t_low.max(z1));
                    let (sl, sr) = ((tl - z0) / g, l - (tr - z1) / g);
                    let crest = (sl + sr) / 2.0 + (tr - tl) / (2.0 * DRAIN_GRADE);
                    let mut v = vec![(sl, tl)];
                    if crest > sl && crest < sr {
                        v.push((crest, tl + DRAIN_GRADE * (crest - sl)));
                    }
                    v.push((sr, tr));
                    v
                } else {
                    vec![(a, t), (l - b, t)]
                }
            } else {
                let d = (l + (z1 - z0) / g) / 2.0;
                if k0 == Kind::Ground && k1 == Kind::Ground && z0 + g * d < p - 0.05 {
                    warnings.push(format!("bridge_profile: the chain {} is {l:.0} m long and reaches {:.1} m at the design grade {g}; its top is {p:.1} m and it needs {:.0} m", c.id, z0 + g * d, 2.0 * p / g));
                }
                vec![(d, z0 + g * d)]
            };
            let mut last = 0.0;
            for (s, z) in at {
                if s > last + MIN_GAP_M && s < l - MIN_GAP_M {
                    c.points.push(Point { s, z_m: z, curve_m: None, source: Some("rule".into()), method: Some("derived".into()) });
                    last = s;
                }
            }
        }
    }
}

/// The length of the vertical curve at every interior point that has none, from the grades on its two sides and the design speed, and shortened where two curves would overlap (the filler
/// says so). A length that the person gave is not changed.
fn design_curves(found: &mut BridgeProfile, warnings: &mut Vec<String>) -> Result<(), Error> {
    let v = found.parameters.design_speed_kmh;
    for grp in &mut found.groups {
        let z: HashMap<String, f64> = grp.nodes.iter().map(|n| (n.id.clone(), n.z_m)).collect();
        for c in &mut grp.chains {
            let mut p: Vec<Pvi> = vec![Pvi { s: 0.0, z: z[&c.from], curve_m: 0.0 }];
            p.extend(c.points.iter().map(|q| Pvi { s: q.s, z: q.z_m, curve_m: q.curve_m.unwrap_or(0.0) }));
            p.push(Pvi { s: c.length_m, z: z[&c.to], curve_m: 0.0 });
            if let Err(e) = bridge_curve::check(&p.iter().map(|q| Pvi { curve_m: 0.0, ..*q }).collect::<Vec<_>>(), c.length_m, if found.parameters.is_elevation() { f64::NEG_INFINITY } else { 0.0 }) {
                return bad(format!("the chain {}: {e}", c.id));
            }
            // a straight grade steeper than the design grade (a height of the person next to a point or a node that is too far in height): a warning, and the number is not changed
            let worst = p.windows(2).map(|w| ((w[1].z - w[0].z).abs() / (w[1].s - w[0].s), w)).max_by(|a, b| a.0.total_cmp(&b.0));
            if let Some((grade, w)) = worst.filter(|(g, _)| *g > found.parameters.design_grade + 1e-9) {
                warnings.push(format!("bridge_profile: the chain {} goes from {:.1} m to {:.1} m between {:.0} m and {:.0} m (a grade of {:.3}); the design grade is {}", c.id, w[0].z, w[1].z, w[0].s, w[1].s, grade, found.parameters.design_grade));
            }
            let mut want: Vec<f64> = (0..p.len()).map(|i| {
                if i == 0 || i == p.len() - 1 || c.points[i - 1].curve_m.is_some() { p[i].curve_m } else {
                    let (g1, g2) = ((p[i].z - p[i - 1].z) / (p[i].s - p[i - 1].s), (p[i + 1].z - p[i].z) / (p[i + 1].s - p[i].s));
                    bridge_curve::curve_length(v, g1, g2)
                }
            }).collect();
            let filled: Vec<bool> = (0..p.len()).map(|i| i > 0 && i < p.len() - 1 && c.points[i - 1].curve_m.is_none()).collect();
            for i in 0..p.len() - 1 {
                let (need, gap) = ((want[i] + want[i + 1]) / 2.0, p[i + 1].s - p[i].s);
                if need <= gap + 1e-9 {
                    continue;
                }
                // a curve that the person gave stays; the curves that the rule made share what is left of the gap
                let kept: f64 = [i, i + 1].iter().filter(|&&j| !filled[j]).map(|&j| want[j] / 2.0).sum();
                let free: f64 = [i, i + 1].iter().filter(|&&j| filled[j]).map(|&j| want[j] / 2.0).sum();
                if free <= 0.0 {
                    continue;                      // two curves of the person overlap: the check of the maker says so
                }
                let f = ((gap - kept) / free).clamp(0.0, 1.0);
                for j in [i, i + 1].into_iter().filter(|&j| filled[j]) {
                    warnings.push(format!("bridge_profile: the chain {}: the curve at {:.0} m is shortened from {:.0} m to {:.0} m to fit between its neighbours; the design speed {v} km/h is high for this length", c.id, p[j].s, want[j], want[j] * f));
                    want[j] *= f;
                }
            }
            for (i, q) in c.points.iter_mut().enumerate() {
                if q.curve_m.is_none() {
                    q.curve_m = Some(round_down(want[i + 1]));
                }
            }
        }
    }
    Ok(())
}

/// Down to 0.01 m: a curve that is rounded up could overlap its neighbour by a hair.
fn round_down(x: f64) -> f64 {
    (x * 100.0).floor() / 100.0
}
