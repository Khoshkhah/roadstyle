//! The look (roadstyle-look) must be the one roadstyle makes (Python): the fixture's look.json byte for byte (its mapstyle part,
//! "features", given), and the looks of tests/make_looks.py: each built-in profile x palette, and settings sources in the older and the
//! newer layout. The goldens are version 0 (no `schema_version`); the look of version 1 is the same with `schema_version` first.

mod common;

use common::diff;
use serde_json::{json, Value};

/// The look of version 1 as version 0: without its `schema_version`.
fn v0(mut look: Value) -> Value {
    assert_eq!(look["schema_version"], 1, "a look of version 1");
    look.as_object_mut().unwrap().shift_remove("schema_version");
    look
}

fn same(got: &Value, want: &Value, what: &str) {
    let mut out = Vec::new();
    diff(got, want, "look", &mut out);
    assert!(out.is_empty(), "{what}: the first differences:\n{}", out.join("\n"));
}

#[test]
fn the_fixture_look() {
    let p = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data/look.json");
    let text = std::fs::read_to_string(p).unwrap();
    let want: Value = serde_json::from_str(&text).unwrap();
    let got = roadstyle_rs::look::make_look(&json!({"palette": want["palette"], "settings": want["settings"], "args": want["args"],
                                                   "features": want["features"]})).map(v0).unwrap();
    same(&got, &want, "look.json");
    assert_eq!(got.to_string(), want.to_string(), "look.json: the same text");
}

#[test]
fn the_looks_of_roadstyle() {
    for case in common::gz_json("looks.json.gz").as_array().unwrap() {
        let mut o = case["options"].clone();
        o["args"] = json!({});
        let got = roadstyle_rs::look::make_look(&o).map(v0).unwrap_or_else(|e| panic!("{}: {e}", case["options"]));
        same(&got, &case["look"], &case["options"].to_string());
    }
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
