//! The 3D bridge decks in two parts (docs/guides/bridge-profile.md): the filler completes an input profile (today's rule fills what is missing), and the maker makes the decks from the complete profile.
//! The one that matters: the maker, given the profile that today's rule wrote, makes the same decks as today (so a page that has no profile of its own does not change).
//! The roads are Monaco's bridges (tests/data/monaco_decks).

use serde_json::Value;
use std::path::PathBuf;

fn data(p: &str) -> Vec<u8> {
    let p = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data").join(p);
    std::fs::read(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()))
}

/// The style of the Monaco bridges with view_3d, and the keywords of `args` that the test adds.
fn style(args: &[(&str, Value)]) -> Result<Value, roadstyle_rs::Error> {
    let mut look: Value = serde_json::from_slice(&data("look.json")).unwrap();
    look["args"]["view_3d"] = true.into();
    for (k, v) in args {
        look["args"][*k] = v.clone();
    }
    let look = roadstyle_rs::Look::from_value(look)?;
    Ok(serde_json::from_str(&roadstyle_rs::inline_style(data("monaco_decks/roads.parquet"), &look, None, None, None)?).unwrap())
}

fn decks(style: &Value) -> Vec<Value> {
    style["sources"]["decks"]["data"]["features"].as_array().expect("the source decks").clone()
}

/// The complete profile that today's rule wrote.
fn profile_of_today() -> Value {
    let s = style(&[]).unwrap();
    s["metadata"]["roadstyle:bridge_profile"].clone()
}

fn error_of(profile: Value) -> String {
    style(&[("bridge_profile", profile)]).unwrap_err().to_string()
}

#[test]
fn the_maker_makes_the_decks_of_today_from_the_profile_of_today() {
    let today = style(&[]).unwrap();
    let profile = today["metadata"]["roadstyle:bridge_profile"].clone();
    assert!(!decks(&today).is_empty(), "Monaco has 3D bridges");
    assert!(profile.is_object(), "the style of a page with 3D bridges has the profile");
    // the profile as JSON text and back (a file), and the maker: the same decks
    let text = serde_json::to_string(&profile).unwrap();
    let from_text: Value = serde_json::from_str(&text).unwrap();
    assert_eq!(from_text, profile, "the profile is the same after JSON text");
    let made = style(&[("bridge_profile", from_text)]).unwrap();
    assert_eq!(decks(&today), decks(&made), "the maker makes the decks of today from the profile of today");
    // a page that is given a profile can write it again: the same profile
    let again = style(&[("bridge_profile", profile.clone())]).unwrap();
    assert_eq!(again["metadata"]["roadstyle:bridge_profile"], profile);
}

#[test]
fn the_profile_of_today_is_complete_and_says_what_it_is() {
    let p = profile_of_today();
    assert_eq!(p["format"], "roadstyle.bridge_profile/1");
    assert_eq!(p["parameters"]["curve"], "smooth");
    let groups = p["groups"].as_array().unwrap();
    assert!(!groups.is_empty());
    let (mut nodes, mut chains, mut ground, mut junction) = (0, 0, 0, 0);
    for g in groups {
        for n in g["nodes"].as_array().unwrap() {
            nodes += 1;
            match n["kind"].as_str().unwrap() {
                "ground" => {
                    ground += 1;
                    assert_eq!((n["z_m"].as_f64().unwrap(), n["source"].as_str().unwrap(), n["method"].as_str().unwrap()), (0.0, "data", "mapped"));
                    assert_eq!(n["chains"].as_array().unwrap().len(), 1, "a node on the ground has one chain");
                }
                _ => {
                    junction += 1;
                    assert!(n["chains"].as_array().unwrap().len() >= 2, "a junction has two chains or more");
                    assert_eq!((n["source"].as_str().unwrap(), n["method"].as_str().unwrap()), ("rule", "derived"));
                }
            }
        }
        for c in g["chains"].as_array().unwrap() {
            chains += 1;
            assert!(c["top_m"].as_f64().unwrap() >= 5.0 && c["points"].as_array().unwrap().is_empty() && c.get("width_m").is_none());
        }
    }
    assert_eq!((nodes, ground + junction), (nodes, nodes));
    assert!(chains >= 2 && ground >= 2, "{chains} chains, {ground} nodes on the ground, {junction} junctions");
    // the chains are c1, c2... in the order of the engine over the whole page (a group has its own, in order), and the nodes n1, n2... from the north to the south
    let number = |c: &Value| c["id"].as_str().unwrap()[1..].parse::<usize>().unwrap();
    for g in groups {
        let ns: Vec<usize> = g["chains"].as_array().unwrap().iter().map(number).collect();
        assert!(ns.windows(2).all(|w| w[0] < w[1]), "the chains of a group are in order: {ns:?}");
    }
    let mut all: Vec<usize> = groups.iter().flat_map(|g| g["chains"].as_array().unwrap().iter().map(number)).collect();
    all.sort();
    assert_eq!(all, (1..=chains).collect::<Vec<_>>(), "every chain number from 1 to the number of chains");
    let lats: Vec<f64> = (1..=nodes).map(|k| {
        let id = format!("n{k}");
        groups.iter().flat_map(|g| g["nodes"].as_array().unwrap()).find(|n| n["id"] == id.as_str()).unwrap()["lonlat"][1].as_f64().unwrap()
    }).collect();
    assert!(lats.windows(2).all(|w| w[0] >= w[1]), "the nodes are from the north to the south");
}

/// The group and the place in it of the first node of a kind.
fn first_node(p: &Value, kind: &str) -> (usize, usize) {
    for (g, group) in p["groups"].as_array().unwrap().iter().enumerate() {
        if let Some(i) = group["nodes"].as_array().unwrap().iter().position(|n| n["kind"] == kind) {
            return (g, i);
        }
    }
    panic!("no node of the kind {kind}");
}

#[test]
fn a_person_changes_a_number_and_the_maker_uses_it() {
    let today = decks(&style(&[]).unwrap());
    // a junction that is 0.1 m higher changes the ramps of its chains
    let mut p = profile_of_today();
    let (g, i) = first_node(&p, "junction");
    p["groups"][g]["nodes"][i]["z_m"] = (p["groups"][g]["nodes"][i]["z_m"].as_f64().unwrap() * 0.5).into();
    p["groups"][g]["nodes"][i]["source"] = "given".into();
    let changed = decks(&style(&[("bridge_profile", p)]).unwrap());
    assert_ne!(today, changed, "a junction at half its height changes the pieces of its chains");
    // a width for a chain: the deck of that chain is drawn that wide
    let mut p = profile_of_today();
    p["groups"][0]["chains"][0]["width_m"] = 9.0.into();
    let wide = decks(&style(&[("bridge_profile", p)]).unwrap());
    assert_ne!(today, wide, "a width changes the polygons");
    assert_eq!(today.len(), wide.len(), "the pieces are the same pieces");
}

/// An input profile with one entry: the node of the first node of `kind` in the profile `p`, with a height. The entry names the node by its position when no other node is within 5 m
/// of it (Monaco has nodes that are 2 m apart: for those the id is the only name), and returns the id.
fn input_with_height(p: &Value, kind: &str, z: f64) -> (Value, String) {
    let (g, i) = first_node(p, kind);
    let n = &p["groups"][g]["nodes"][i];
    let near = p["groups"].as_array().unwrap().iter().flat_map(|g| g["nodes"].as_array().unwrap()).filter(|o| {
        let d = |k: usize| (o["lonlat"][k].as_f64().unwrap() - n["lonlat"][k].as_f64().unwrap()).abs();
        d(0) < 1e-4 && d(1) < 1e-4
    }).count();
    let entry = if near == 1 { serde_json::json!({"lonlat": n["lonlat"], "z_m": z}) } else { serde_json::json!({"id": n["id"], "z_m": z}) };
    (serde_json::json!({"groups": [{"nodes": [entry]}]}), n["id"].as_str().unwrap().to_string())
}

fn node<'a>(p: &'a Value, id: &str) -> &'a Value {
    p["groups"].as_array().unwrap().iter().flat_map(|g| g["nodes"].as_array().unwrap()).find(|n| n["id"] == id).unwrap()
}

fn export(input: Value) -> Result<(Value, Value), roadstyle_rs::Error> {
    let s = style(&[("bridge_profile", input)])?;
    Ok((s["metadata"]["roadstyle:bridge_profile"].clone(), s))
}

#[test]
fn the_filler_makes_the_profile_of_today_from_an_empty_input_and_changes_nothing_in_a_complete_one() {
    let today = style(&[]).unwrap();
    let profile = today["metadata"]["roadstyle:bridge_profile"].clone();
    for empty in [serde_json::json!({}), serde_json::json!({"groups": []}), serde_json::json!({"parameters": {}, "groups": [{"nodes": [], "chains": []}]})] {
        let (p, s) = export(empty).unwrap();
        assert_eq!(p, profile, "an empty input fills everything with the rules of today");
        assert_eq!(decks(&s), decks(&today));
    }
    // a complete profile is its own fill (the filler twice is the filler once), and so is a filled one
    assert_eq!(export(profile.clone()).unwrap().0, profile);
    let (partial, _) = input_with_height(&profile, "junction", 2.0);
    let once = export(partial).unwrap().0;
    assert_eq!(export(once.clone()).unwrap().0, once);
}

#[test]
fn a_given_height_is_kept_and_everything_else_is_filled() {
    let today = profile_of_today();
    let kind = if today["groups"].as_array().unwrap().iter().any(|g| g["nodes"].as_array().unwrap().iter().any(|n| n["kind"] == "junction")) { "junction" } else { "ground" };
    let (input, id) = input_with_height(&today, kind, 3.0);
    let (p, s) = export(input).unwrap();
    let n = node(&p, &id);
    assert_eq!((n["z_m"].as_f64().unwrap(), n["source"].as_str().unwrap(), n["method"].as_str().unwrap()), (3.0, "given", "chosen"));
    // the rest of the profile is the profile of today, except the chains of that node (their top is at least as high as the node)
    for other in today["groups"].as_array().unwrap().iter().flat_map(|g| g["nodes"].as_array().unwrap()).filter(|o| o["id"] != id.as_str()) {
        assert_eq!(node(&p, other["id"].as_str().unwrap()), other);
    }
    assert_ne!(decks(&s), decks(&style(&[]).unwrap()), "a height of 3 m changes the pieces of its chains");
    // the source and the method of the person are kept
    let (g, i) = first_node(&today, kind);
    let input = serde_json::json!({"groups": [{"nodes": [{"id": today["groups"][g]["nodes"][i]["id"], "z_m": 3.0, "source": "survey", "method": "measured"}]}]});
    let n = node(&export(input).unwrap().0, &id).clone();
    assert_eq!((n["source"].as_str().unwrap(), n["method"].as_str().unwrap()), ("survey", "measured"));
    // a given width and top are kept
    let p = export(serde_json::json!({"groups": [{"chains": [{"id": "c1", "width_m": 9.0, "top_m": 40.0}]}]})).unwrap().0;
    let c = &p["groups"][0]["chains"][0];
    assert_eq!((c["top_m"].as_f64().unwrap(), c["width_m"].as_f64().unwrap(), c["width_source"].as_str().unwrap()), (40.0, 9.0, "given"));
    // a node above the top of the rule raises the top of its chains
    let (input, id) = input_with_height(&today, "junction", 50.0);
    let p = export(input).unwrap().0;
    for c in p["groups"].as_array().unwrap().iter().flat_map(|g| g["chains"].as_array().unwrap()).filter(|c| c["from"] == id.as_str() || c["to"] == id.as_str()) {
        assert!(c["top_m"].as_f64().unwrap() >= 50.0);
    }
}

#[test]
fn a_profile_with_a_value_missing_is_filled_and_one_that_is_not_for_these_roads_says_so() {
    let p = profile_of_today();
    let today = decks(&style(&[]).unwrap());
    let with = |f: &dyn Fn(&mut Value)| { let mut q = p.clone(); f(&mut q); q };
    // every value is optional: the filler adds what is missing (a height, a top, a chain, a node, the parameters)
    for q in [
        with(&|q| { q["groups"][0]["nodes"][0].as_object_mut().unwrap().remove("z_m"); }),
        with(&|q| { q["groups"][0]["chains"][0].as_object_mut().unwrap().remove("top_m"); }),
        with(&|q| { q["groups"][0]["chains"].as_array_mut().unwrap().pop(); }),
        with(&|q| { q.as_object_mut().unwrap().remove("parameters"); }),
    ] {
        let (filled, s) = export(q).unwrap();
        assert_eq!(filled, p);
        assert_eq!(decks(&s), today);
    }
    // the format, and what is not built
    assert!(error_of(with(&|q| q["format"] = "other".into())).contains("this engine reads"));
    assert!(error_of(with(&|q| q["extra"] = 1.into())).contains("unknown field `extra`"));
    let e = error_of(with(&|q| q["groups"][0]["chains"][0]["points"] = serde_json::json!([{"s": 5.0, "z_m": 2.0}])));
    assert!(e.contains("interior control points") && e.contains("curve `design`"), "{e}");
    // a node above the top of its chain
    let e = error_of(with(&|q| {
        // a junction (the end of a bridge is on the ground and cannot be raised) and the first chain that ends there
        let (g, i) = first_node(q, "junction");
        let id = q["groups"][g]["nodes"][i]["id"].as_str().unwrap().to_string();
        let top = q["groups"][g]["chains"].as_array().unwrap().iter().find(|c| c["from"] == id.as_str() || c["to"] == id.as_str()).unwrap()["top_m"].as_f64().unwrap();
        q["groups"][g]["nodes"][i]["z_m"] = (top + 1.0).into();
    }));
    assert!(e.contains("cannot be above the top"), "{e}");
    // not for these roads
    let e = error_of(with(&|q| q["groups"][0]["chains"][0]["length_m"] = 999.0.into()));
    assert!(e.contains("m long in these roads") && e.contains("not for these roads"), "{e}");
    let e = error_of(with(&|q| {
        let from = q["groups"][0]["chains"][0]["from"].as_str().unwrap().to_string();
        for n in q["groups"][0]["nodes"].as_array_mut().unwrap() {
            if n["id"] == from.as_str() { n["lonlat"][0] = (n["lonlat"][0].as_f64().unwrap() + 0.01).into(); }
        }
    }));
    assert!(e.contains("m from the position") && e.contains("not for these roads"), "{e}");
    let e = error_of(with(&|q| { q["groups"][0]["chains"][0]["from"] = "n999".into(); }));
    assert!(e.contains("n999") && e.contains("not for these roads"), "{e}");
    let e = error_of(with(&|q| { q["groups"][0]["chains"][0]["id"] = "c999".into(); }));
    assert!(e.contains("c999") && e.contains("not for these roads"), "{e}");
}

#[test]
fn an_input_that_cannot_be_true_for_these_roads_is_an_error_that_says_what() {
    let today = profile_of_today();
    let (g, i) = first_node(&today, "ground");
    let n = &today["groups"][g]["nodes"][i];
    let (ll, id) = (n["lonlat"].clone(), n["id"].clone());
    let nodes = |v: Value| serde_json::json!({"groups": [{"nodes": v}]});
    let e = error_of(nodes(serde_json::json!([{"lonlat": ll, "z_m": 0.0}, {"id": id, "z_m": 0.0}])));
    assert!(e.contains("two entries of the input are for the node"), "{e}");
    assert!(error_of(nodes(serde_json::json!([{"lonlat": [0.0, 0.0], "z_m": 0.0}]))).contains("no node of these roads is within 5 m"));
    assert!(error_of(nodes(serde_json::json!([{"z_m": 1.0}]))).contains("no id and no lonlat"));
    assert!(error_of(nodes(serde_json::json!([{"lonlat": ll, "z_m": -1.0}]))).contains("0 or more"));
    assert!(error_of(nodes(serde_json::json!([{"id": "n999", "z_m": 0.0}]))).contains("n999"));
    assert!(error_of(nodes(serde_json::json!([{"lonlat": ll, "kind": "junction", "z_m": 1.0}]))).contains("is a Ground in these roads"));
    assert!(error_of(serde_json::json!({"groups": [{"chains": [{"width_m": 4.0}]}]})).contains("has no id"));
    assert!(error_of(serde_json::json!({"groups": [{"chains": [{"id": "c1", "width_m": 0.0}]}]})).contains("above 0"));
    assert!(error_of(serde_json::json!({"groups": [{"chains": [{"id": "c1"}, {"id": "c1"}]}]})).contains("two entries of the input are for the chain c1"));
    // a given top below a given height
    let (g, i) = first_node(&today, "junction");
    let (jid, chain) = (today["groups"][g]["nodes"][i]["id"].clone(), today["groups"][g]["nodes"][i]["chains"][0].clone());
    let input = serde_json::json!({"groups": [{"nodes": [{"id": jid, "z_m": 3.0}], "chains": [{"id": chain, "top_m": 1.0}]}]});
    assert!(error_of(input).contains("cannot be above the top"));
    assert!(error_of(serde_json::json!({"groups": [{"name": "x"}]})).contains("has a name and no node"));
}

#[test]
fn a_profile_on_a_page_with_no_3d_bridges_makes_no_decks_and_heights_give_way_to_it() {
    let p = profile_of_today();
    let flat = style(&[("view_3d", false.into()), ("bridge_profile", p.clone())]).unwrap();
    assert!(flat["sources"]["decks"].is_null() || decks(&flat).is_empty(), "view_3d=False: no decks");
    // bridge_heights names ids that Monaco's roads do not have; with a profile they are not read, and the page is made from the profile
    let both = style(&[("bridge_profile", p), ("bridge_heights", serde_json::json!({"no such road": 14.0}))]).unwrap();
    assert_eq!(decks(&both), decks(&style(&[]).unwrap()));
}

// ---- the curve `design` and the design rules (docs/design/bridge_height_design.md) ----

fn design_input(extra: Value) -> Value {
    let mut v = serde_json::json!({"parameters": {"height_rule": "design"}});
    if let Some(o) = extra.as_object() {
        for (k, x) in o {
            v[k] = x.clone();
        }
    }
    v
}

/// The deck pieces (not the casing slabs) of each chain: `(s0, s1, z0, z1)` in metres along the chain and above the ground, from the lifts that the page draws.
fn pieces_of(s: &Value, p: &Value) -> std::collections::BTreeMap<u64, Vec<(f64, f64, f64, f64)>> {
    let length: std::collections::HashMap<String, f64> = p["groups"].as_array().unwrap().iter().flat_map(|g| g["chains"].as_array().unwrap()).map(|c| (c["id"].as_str().unwrap().to_string(), c["length_m"].as_f64().unwrap())).collect();
    let mut out: std::collections::BTreeMap<u64, Vec<(f64, f64, f64, f64)>> = Default::default();
    for f in decks(s) {
        let q = &f["properties"];
        if q.get("__rs_casing_slab").is_some() {
            continue;
        }
        let (n, full, l) = (q["__rs_chain"].as_u64().unwrap(), q["__rs_full"].as_f64().unwrap(), length[&format!("c{}", q["__rs_chain"])]);
        out.entry(n).or_default().push((q["__rs_s0"].as_f64().unwrap() * l, q["__rs_s1"].as_f64().unwrap() * l, q["__rs_lift0"].as_f64().unwrap() * full, q["__rs_lift1"].as_f64().unwrap() * full));
    }
    out
}

#[test]
fn the_design_rules_make_a_profile_that_never_rises_faster_than_the_design_grade() {
    let (p, s) = export(design_input(serde_json::json!({}))).unwrap();
    assert_eq!((p["parameters"]["curve"].as_str(), p["parameters"]["height_rule"].as_str(), p["parameters"]["design_grade"].as_f64()), (Some("design"), Some("design"), Some(0.05)));
    let g = 0.05;
    let mut points = 0;
    for grp in p["groups"].as_array().unwrap() {
        let z: std::collections::HashMap<&str, f64> = grp["nodes"].as_array().unwrap().iter().map(|n| (n["id"].as_str().unwrap(), n["z_m"].as_f64().unwrap())).collect();
        for c in grp["chains"].as_array().unwrap() {
            let (l, top) = (c["length_m"].as_f64().unwrap(), c["top_m"].as_f64().unwrap());
            let (z0, z1) = (z[c["from"].as_str().unwrap()], z[c["to"].as_str().unwrap()]);
            assert!((z0 - z1).abs() <= g * l + 1e-6, "{}: the two nodes differ by more than the grade allows", c["id"]);
            let pts = c["points"].as_array().unwrap();
            points += pts.len();
            for q in pts {
                assert!(q["curve_m"].as_f64().unwrap() >= 0.0 && q["z_m"].as_f64().unwrap() <= top + 1e-9, "every point has the length of its curve, and none is above the top");
            }
            assert!(pts.windows(2).all(|w| w[0]["s"].as_f64() < w[1]["s"].as_f64()));
        }
    }
    assert!(points > 0, "Monaco has a chain that is long enough for a top");
    // the pieces: no piece is steeper than the grade (the lifts are rounded to 4 decimals: 0.002 of slack)
    for (n, v) in pieces_of(&s, &p) {
        for (s0, s1, z0, z1) in v {
            assert!(s1 > s0 && (z1 - z0).abs() / (s1 - s0) <= g + 0.002, "chain {n}: the piece from {s0} m to {s1} m rises {} m", z1 - z0);
        }
    }
}

#[test]
fn the_design_profile_is_its_own_fill_and_a_given_height_is_a_fixed_point_of_the_rule() {
    let (p, s) = export(design_input(serde_json::json!({}))).unwrap();
    let (again, s2) = export(p.clone()).unwrap();
    assert_eq!(again, p, "the filler twice is the filler once");
    assert_eq!(decks(&s2), decks(&s), "and the maker makes the same decks");
    // a height of the person (a junction at 5 cm, where the rule gave more) is kept, and the nodes next to it follow the grade from it
    let (g, i) = first_node(&p, "junction");
    let id = p["groups"][g]["nodes"][i]["id"].as_str().unwrap().to_string();
    let rule_z = p["groups"][g]["nodes"][i]["z_m"].as_f64().unwrap();
    let (input, _) = input_with_height(&p, "junction", 0.05);
    let q = export(design_input(input)).unwrap().0;
    let n = node(&q, &id);
    assert_eq!((n["z_m"].as_f64().unwrap(), n["source"].as_str().unwrap()), (0.05, "given"));
    assert!(rule_z > 0.05, "the rule gave a higher junction ({rule_z} m)");
    for c in q["groups"].as_array().unwrap().iter().flat_map(|g| g["chains"].as_array().unwrap()).filter(|c| c["from"] == id.as_str() || c["to"] == id.as_str()) {
        let other = if c["from"] == id.as_str() { c["to"].as_str().unwrap() } else { c["from"].as_str().unwrap() };
        assert!((node(&q, other)["z_m"].as_f64().unwrap() - 0.05).abs() <= 0.05 * c["length_m"].as_f64().unwrap() + 1e-6);
    }
}

#[test]
fn points_and_curves_given_by_a_person_are_kept_and_the_wrong_ones_say_what() {
    let (p, _) = export(design_input(serde_json::json!({}))).unwrap();
    // a chain with points: the first chain that has two
    let (c_id, pts) = p["groups"].as_array().unwrap().iter().flat_map(|g| g["chains"].as_array().unwrap()).find(|c| !c["points"].as_array().unwrap().is_empty()).map(|c| (c["id"].as_str().unwrap().to_string(), c["points"].clone())).expect("a chain with points");
    let l = p["groups"].as_array().unwrap().iter().flat_map(|g| g["chains"].as_array().unwrap()).find(|c| c["id"] == c_id.as_str()).unwrap()["length_m"].as_f64().unwrap();
    let entry = |points: Value| serde_json::json!({"groups": [{"chains": [{"id": c_id, "points": points}]}]});
    // one point of the person, with its own curve, and no top: the rule gives the length of the curves of the points that have none
    let one = serde_json::json!([{"s": l * 0.4, "z_m": 3.0, "curve_m": 4.0}, {"s": l * 0.7, "z_m": 4.0}]);
    let q = export(design_input(entry(one))).unwrap().0;
    let c = q["groups"].as_array().unwrap().iter().flat_map(|g| g["chains"].as_array().unwrap()).find(|c| c["id"] == c_id.as_str()).unwrap().clone();
    assert_eq!(c["points"][0]["curve_m"].as_f64(), Some(4.0), "a curve that the person gave is kept");
    assert!(c["points"][1]["curve_m"].as_f64().unwrap() >= 30.0 - 1e-9 || c["points"][1]["curve_m"].as_f64().unwrap() > 0.0, "a curve that is missing is written");
    assert!(c["top_m"].as_f64().unwrap() >= 4.0);
    // a chain with points of the person keeps them when the filler goes over the profile again
    assert_eq!(export(q.clone()).unwrap().0, q);
    // errors
    let e = export(design_input(entry(serde_json::json!([{"s": 50.0, "z_m": 3.0}, {"s": 40.0, "z_m": 3.0}])))).unwrap_err().to_string();
    assert!(e.contains("not in order of s"), "{e}");
    let e = export(design_input(entry(serde_json::json!([{"s": l + 5.0, "z_m": 3.0}])))).unwrap_err().to_string();
    assert!(e.contains("not in order of s") || e.contains("end at the length"), "{e}");
    let e = export(design_input(entry(serde_json::json!([{"s": l / 2.0, "z_m": 3.0, "curve_m": l * 2.0}])))).unwrap_err().to_string();
    assert!(e.contains("overlap"), "{e}");
    // the maker has no rule: a profile whose point has no curve_m is an error that says to fill it
    let mut raw = p.clone();
    for g in raw["groups"].as_array_mut().unwrap() {
        for c in g["chains"].as_array_mut().unwrap() {
            for q in c["points"].as_array_mut().unwrap() {
                q.as_object_mut().unwrap().remove("curve_m");
            }
        }
    }
    // (the filler goes first, so the profile is complete again: the same fill)
    assert_eq!(export(raw).unwrap().0["groups"], p["groups"], "the filler writes the missing curves back");
    // points with the curve smooth
    let e = export(serde_json::json!({"parameters": {"curve": "smooth"}, "groups": [{"chains": [{"id": c_id, "points": pts}]}]})).unwrap_err().to_string();
    assert!(e.contains("curve `design`"), "{e}");
}

#[test]
fn the_end_of_a_bridge_is_on_the_ground_and_a_height_above_0_there_is_an_error_that_says_so() {
    let p = profile_of_today();
    // in an input
    let (input, id) = input_with_height(&p, "ground", 3.0);
    let e = export(input).unwrap_err().to_string();
    assert!(e.contains(&id) && e.contains("free end of its bridge") && e.contains("on the ground") && e.contains("wrong height"), "{e}");
    // 0 is allowed (it is the height already)
    let (input, id) = input_with_height(&p, "ground", 0.0);
    assert_eq!(node(&export(input).unwrap().0, &id)["z_m"].as_f64(), Some(0.0));
    // in a complete profile that the maker reads
    let mut q = p.clone();
    let (g, i) = first_node(&q, "ground");
    q["groups"][g]["nodes"][i]["z_m"] = 3.0.into();
    let e = error_of(q);
    assert!(e.contains("free end of its bridge"), "{e}");
}

/// An input profile with `z_reference: "elevation"`: every node of the profile `p` at `base` metres plus its height in `p`, and the ground named.
fn elevation_input(p: &Value, base: f64) -> Value {
    let nodes: Vec<Value> = p["groups"].as_array().unwrap().iter().flat_map(|g| g["nodes"].as_array().unwrap())
        .map(|n| serde_json::json!({"id": n["id"], "z_m": base + n["z_m"].as_f64().unwrap(), "source": "test", "method": "measured"})).collect();
    serde_json::json!({"parameters": {"z_reference": "elevation"},
                       "ground": {"id": "3e79bae171d8f22d9e2a0cfd64408b4ac961ba533db492f00c36cca9ff7582b5", "source": "test ground", "product": "DTM", "vertical_datum": "EGM2008"},
                       "groups": [{"nodes": nodes}]})
}

#[test]
fn an_elevation_profile_keeps_every_elevation_and_the_free_ends_are_not_forced_to_0() {
    let p = profile_of_today();
    let (out, s) = export(elevation_input(&p, 120.0)).unwrap();
    assert_eq!(out["parameters"]["z_reference"], "elevation");
    assert_eq!(out["parameters"]["curve"], "design", "elevation needs the curve design");
    assert_eq!(out["ground"]["vertical_datum"], "EGM2008");
    let mut ground_ends = 0;
    for g in out["groups"].as_array().unwrap() {
        for n in g["nodes"].as_array().unwrap() {
            let before = node(&p, n["id"].as_str().unwrap())["z_m"].as_f64().unwrap();
            assert_eq!(n["z_m"].as_f64().unwrap(), 120.0 + before, "the elevation is the one that was given");
            assert_eq!((n["source"].as_str().unwrap(), n["method"].as_str().unwrap()), ("test", "measured"));
            ground_ends += (n["kind"] == "ground") as usize;
        }
        for c in g["chains"].as_array().unwrap() {
            assert!(c["top_m"].as_f64().unwrap() >= 120.0, "the top of a chain is its highest elevation");
        }
    }
    assert!(ground_ends > 0, "the roads have free ends, and they are at 120 m or more: not an error");
    assert!(!decks(&s).is_empty());
    // the filler twice is the filler once
    let (again, _) = export(serde_json::from_value(out.clone()).unwrap()).unwrap();
    assert_eq!(again, out);
}

#[test]
fn an_elevation_below_the_sea_still_gives_decks_with_finite_marks() {
    let p = profile_of_today();
    let (_, s) = export(elevation_input(&p, -8.0)).unwrap();
    let d = decks(&s);
    assert!(!d.is_empty());
    for f in &d {
        for k in ["__rs_base", "__rs_height", "__rs_lift0", "__rs_lift1", "__rs_full"] {
            if let Some(v) = f["properties"].get(k) {
                assert!(v.as_f64().is_some_and(|x| x.is_finite() && x >= -1e-9), "{k} = {v}");
            }
        }
    }
}

#[test]
fn an_elevation_profile_says_what_is_missing_or_cannot_be_used() {
    let p = profile_of_today();
    // a node with no elevation: every node needs one, the error names them
    let mut input = elevation_input(&p, 50.0);
    let removed = input["groups"][0]["nodes"].as_array_mut().unwrap().remove(0)["id"].as_str().unwrap().to_string();
    let e = export(input).unwrap_err().to_string();
    assert!(e.contains("every node needs its elevation") && e.contains(&removed), "{e}");
    // no ground
    let mut input = elevation_input(&p, 50.0);
    input.as_object_mut().unwrap().remove("ground");
    let e = export(input).unwrap_err().to_string();
    assert!(e.contains("must name its ground") && e.contains("ground.id"), "{e}");
    // the rule of the design finds heights above the ground
    let mut input = elevation_input(&p, 50.0);
    input["parameters"]["height_rule"] = "design".into();
    let e = export(input).unwrap_err().to_string();
    assert!(e.contains("height_rule") && e.contains("elevation"), "{e}");
    // the curve smooth makes ramps from the ground
    let mut input = elevation_input(&p, 50.0);
    input["parameters"]["curve"] = "smooth".into();
    let e = export(input).unwrap_err().to_string();
    assert!(e.contains("needs the curve"), "{e}");
}

#[test]
fn a_profile_that_is_above_the_ground_has_no_z_reference_and_is_not_changed() {
    let p = profile_of_today();
    assert!(p["parameters"].get("z_reference").is_none(), "the profile of today does not say it: its heights are above the ground");
}
