//! The look (roadstyle-look): the look of the fixture's options (tests/data/look.json's palette, settings, args and mapstyle part) and
//! the looks of each built-in profile x palette and of settings sources in the older and the newer layout, against goldens that the
//! Rust engine makes (tests/data/rust_looks.json, a summary of each look: a hash of each part; `ROADSTYLE_BLESS=1 cargo test --test
//! look` writes it). The last check of these looks against Python's (make_goldens.py's looks) was 2026-10-24. And a saved look of each
//! version, and export_look's colours.

mod common;

use serde_json::{json, Value};

/// A look as a golden sees it: the hash of each part, and of the whole look.
fn summary(look: &Value) -> Value {
    let parts: serde_json::Map<String, Value> = look.as_object().unwrap().iter().map(|(k, v)| (k.clone(), json!(common::hash16(v)))).collect();
    json!({"parts": parts, "hash": common::hash16(look)})
}

/// The cases of the looks (make_goldens.py's write_looks until 2026-10-24): each built-in profile x palette, the older settings layout
/// (as mapstyle writes it: a palette of its own under "palettes", config and selection keys, a roads table) and the newer one (a profile
/// and a palette by name, and a style value).
fn cases() -> Vec<Value> {
    let mut out: Vec<Value> = ["default", "highsat"].iter().flat_map(|pr| ["amber", "carto", "highsat", "mono"].map(|pa| json!({"palette": pa, "profile": pr})))
        .collect();
    out.push(json!({"palette": "mine", "settings": {"palettes": {"mine": {
        "residential": {"fill": "#123456", "width": 2.5, "casing_width": 3.0, "casing": "#654321"},
        "unclassified": {"fill": "#abcdef", "width": 2, "casing_width": 3, "dash": [4, 2]}}},
        "config": {"fill_opacity": 0.8, "minor_no_casing": ["footway"], "minzoom": {"service": 14}, "basemap": "osm"},
        "selection": {"core": "#ff0000"}, "roads": {"z_order": {"service": 3}}}}));
    out.push(json!({"settings": {"profile": "highsat", "palette": "carto", "labels": {"color": "#112233"}}, "palette": "carto"}));
    out
}

#[test]
fn the_looks_are_their_goldens() {
    let p = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data/look.json");
    let fixture: Value = serde_json::from_str(&std::fs::read_to_string(p).unwrap()).unwrap();
    let mut got = vec![json!({"options": "the fixture (look.json)", "look": summary(&roadstyle_rs::look::make_look(&json!({
        "palette": fixture["palette"], "settings": fixture["settings"], "args": fixture["args"], "features": fixture["features"]})).unwrap())})];
    for c in cases() {
        let mut o = c.clone();
        o["args"] = json!({});
        let look = roadstyle_rs::look::make_look(&o).unwrap_or_else(|e| panic!("{c}: {e}"));
        got.push(json!({"options": c, "look": summary(&look)}));
    }
    common::golden("rust_looks.json", &Value::Array(got));
}

/// The look of version 1 as version 0: without its `schema_version`.
fn v0(mut look: Value) -> Value {
    assert_eq!(look["schema_version"], 1, "a look of version 1");
    look.as_object_mut().unwrap().shift_remove("schema_version");
    look
}

#[test]
fn a_saved_look_of_version_0_and_1() {
    let p = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data/look.json");
    let text = std::fs::read_to_string(p).unwrap();
    let old = roadstyle_rs::Look::from_json(&text).unwrap();           // version 0: today's look.json
    let new = roadstyle_rs::Look::from_json(&old.to_json()).unwrap();  // version 1, written and read again
    assert_eq!(old.schema_version, 1);
    assert_eq!(new.to_json(), old.to_json());
    assert_eq!(v0(new.to_value()).to_string(), serde_json::from_str::<Value>(&text).unwrap().to_string());
    let later = text.replacen('{', r#"{"schema_version": 2, "#, 1);
    let e = roadstyle_rs::Look::from_json(&later).unwrap_err();
    assert_eq!(e, roadstyle_rs::look::Error::Version { found: 2 });
    assert_eq!(e.to_string(), "look version 2: this engine reads versions 0 and 1", "the text that Python and JavaScript show");
    let unknown = text.replacen('{', r#"{"pallete": "x", "#, 1);
    assert!(matches!(roadstyle_rs::Look::from_json(&unknown).unwrap_err(), roadstyle_rs::look::Error::Look(m) if m.contains("pallete")));
}

/// Review D4: a palette colour in export_look ("#fff" panicked there before): the short form, the long form and a colour name are colours
/// (moved toward the tunnel colour), "#zzz" is an error that names it, and "" (a palette's "no casing") stays as it is.
#[test]
fn export_look_reads_every_form_of_a_colour() {
    let text = std::fs::read_to_string(std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data/look.json")).unwrap();
    let base: Value = serde_json::from_str(&text).unwrap();
    let pal = base["theme"]["active"]["palette"].as_str().unwrap().to_string();
    let cols = roadstyle_rs::export_look::LookCols { highway: "highway", oneway: "oneway", tunnel: "tunnel", bridge: "bridge", id: "edge_id" };
    let with = |fill: &str| {
        let mut v = base.clone();
        v["theme"]["palettes"][&pal]["residential"]["fill"] = fill.into();
        roadstyle_rs::export_look::export_look(&roadstyle_rs::Look::from_value(v).unwrap(), &cols, &[0, 1])
    };
    for ok in ["#fff", "#ffffff", "red", ""] {
        assert!(with(ok).is_ok(), "{ok:?}: {:?}", with(ok).err());
    }
    // the tunnel's mixed colour is the same; outside a tunnel the palette's text stays as it is
    assert_eq!(serde_json::to_string(&with("#fff").unwrap()).unwrap().replace("\"#fff\"", "\"#ffffff\""),
               serde_json::to_string(&with("#ffffff").unwrap()).unwrap(), "the short form is the long form");
    let e = with("#zzz").unwrap_err();
    assert!(matches!(e, roadstyle_rs::EngineError::Look(_)) && e.to_string().contains("\"#zzz\" is not a colour"), "{e}");
}
