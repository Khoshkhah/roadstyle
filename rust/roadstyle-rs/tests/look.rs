//! The look (src/look.rs) must be the one roadstyle makes (Python): the fixture's look.json byte for byte (its mapstyle part, "features",
//! given), and the looks of tests/make_looks.py: each built-in profile x palette, and settings sources in the older and the newer layout.

mod common;

use common::diff;
use serde_json::{json, Value};

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
                                                   "features": want["features"]})).unwrap();
    same(&got, &want, "look.json");
    assert_eq!(got.to_string(), want.to_string(), "look.json: the same text");
}

#[test]
fn the_looks_of_roadstyle() {
    for case in common::gz_json("looks.json.gz").as_array().unwrap() {
        let mut o = case["options"].clone();
        o["args"] = json!({});
        let got = roadstyle_rs::look::make_look(&o).unwrap_or_else(|e| panic!("{}: {e}", case["options"]));
        same(&got, &case["look"], &case["options"].to_string());
    }
}
