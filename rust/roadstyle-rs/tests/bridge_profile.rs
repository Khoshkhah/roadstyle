//! The 3D bridge decks in two parts (docs/guides/bridge-profile.md): today's rule writes a complete bridge profile, and the maker makes the decks from a profile.
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
    let s = style(&[("bridge_profile_export", true.into())]).unwrap();
    s["metadata"]["roadstyle:bridge_profile"].clone()
}

fn error_of(profile: Value) -> String {
    style(&[("bridge_profile", profile)]).unwrap_err().to_string()
}

#[test]
fn the_maker_makes_the_decks_of_today_from_the_profile_of_today() {
    let today = style(&[]).unwrap();
    let wrote = style(&[("bridge_profile_export", true.into())]).unwrap();
    let profile = wrote["metadata"]["roadstyle:bridge_profile"].clone();
    assert!(!decks(&today).is_empty(), "Monaco has 3D bridges");
    assert!(today["metadata"]["roadstyle:bridge_profile"].is_null(), "the profile is in the style only when it is asked for");
    assert_eq!(decks(&today), decks(&wrote), "asking for the profile does not change the decks");
    // the profile as JSON text and back (a file), and the maker: the same decks
    let text = serde_json::to_string(&profile).unwrap();
    let from_text: Value = serde_json::from_str(&text).unwrap();
    assert_eq!(from_text, profile, "the profile is the same after JSON text");
    let made = style(&[("bridge_profile", from_text)]).unwrap();
    assert_eq!(decks(&today), decks(&made), "the maker makes the decks of today from the profile of today");
    // a page that is given a profile can write it again: the same profile
    let again = style(&[("bridge_profile", profile.clone()), ("bridge_profile_export", true.into())]).unwrap();
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
    // a node on the ground that stands 3 m above the ground (a landing on fill) changes the ramp that starts at it
    let mut p = profile_of_today();
    let (g, i) = first_node(&p, "ground");
    p["groups"][g]["nodes"][i]["z_m"] = 3.0.into();
    p["groups"][g]["nodes"][i]["source"] = "given".into();
    let changed = decks(&style(&[("bridge_profile", p)]).unwrap());
    assert_ne!(today, changed, "a node 3 m high changes the pieces of its chain");
    // a width for a chain: the deck of that chain is drawn that wide
    let mut p = profile_of_today();
    p["groups"][0]["chains"][0]["width_m"] = 9.0.into();
    let wide = decks(&style(&[("bridge_profile", p)]).unwrap());
    assert_ne!(today, wide, "a width changes the polygons");
    assert_eq!(today.len(), wide.len(), "the pieces are the same pieces");
}

#[test]
fn a_profile_that_is_not_complete_or_not_for_these_roads_says_so() {
    let p = profile_of_today();
    let with = |f: &dyn Fn(&mut Value)| { let mut q = p.clone(); f(&mut q); q };
    // not complete: the maker has no defaults
    let e = error_of(with(&|q| { q["groups"][0]["nodes"][0].as_object_mut().unwrap().remove("z_m"); }));
    assert!(e.contains("missing field `z_m`") && e.contains("fill it first"), "{e}");
    let e = error_of(with(&|q| { q["groups"][0]["chains"][0].as_object_mut().unwrap().remove("points"); }));
    assert!(e.contains("missing field `points`"), "{e}");
    let e = error_of(with(&|q| { q["groups"][0]["chains"][0].as_object_mut().unwrap().remove("top_m"); }));
    assert!(e.contains("no top_m") && e.contains("smooth"), "{e}");
    // the format, and what is not built
    assert!(error_of(with(&|q| q["format"] = "other".into())).contains("this engine reads"));
    assert!(error_of(with(&|q| q["parameters"]["curve"] = "design".into())).contains("not built yet"));
    let e = error_of(with(&|q| q["groups"][0]["chains"][0]["points"] = serde_json::json!([{"s": 5.0, "z_m": 2.0}])));
    assert!(e.contains("interior control points") && e.contains("curve `design`"), "{e}");
    // a node above the top of its chain
    let e = error_of(with(&|q| {
        let top = q["groups"][0]["chains"][0]["top_m"].as_f64().unwrap();
        let from = q["groups"][0]["chains"][0]["from"].as_str().unwrap().to_string();
        for n in q["groups"][0]["nodes"].as_array_mut().unwrap() {
            if n["id"] == from.as_str() { n["z_m"] = (top + 1.0).into(); }
        }
    }));
    assert!(e.contains("above the top of the chain"), "{e}");
    // not for these roads: a chain less, a length, a node that is not where the chain ends
    let e = error_of(with(&|q| { q["groups"][0]["chains"].as_array_mut().unwrap().pop(); }));
    assert!(e.contains("not for these roads"), "{e}");
    let e = error_of(with(&|q| q["groups"][0]["chains"][0]["length_m"] = 999.0.into()));
    assert!(e.contains("m long in the profile") && e.contains("not for these roads"), "{e}");
    let e = error_of(with(&|q| {
        let from = q["groups"][0]["chains"][0]["from"].as_str().unwrap().to_string();
        for n in q["groups"][0]["nodes"].as_array_mut().unwrap() {
            if n["id"] == from.as_str() { n["lonlat"][0] = (n["lonlat"][0].as_f64().unwrap() + 0.01).into(); }
        }
    }));
    assert!(e.contains("is not where the chain") && e.contains("not for these roads"), "{e}");
    let e = error_of(with(&|q| { q["groups"][0]["chains"][0]["from"] = "n999".into(); }));
    assert!(e.contains("n999") && e.contains("does not have"), "{e}");
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
