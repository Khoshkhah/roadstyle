//! The page's declaration static/dashboard/reads.json is made from the marks (roadstyle-model mark.rs, target_architecture.md (c) item
//! 2): this test fails when the file differs, and ROADSTYLE_BLESS=1 writes it again (its `_doc` stays).

use roadstyle_rs::mark::{page_reads, Kind};
use serde_json::{Map, Value};
use std::path::PathBuf;

#[test]
fn reads_json_is_made_from_the_marks() {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../roadstyle-assets/files/static/dashboard/reads.json");
    let file: Map<String, Value> = serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
    let mut want = Map::new();
    want.insert("_doc".into(), file["_doc"].clone());
    for k in Kind::ALL {
        want.insert(k.name().into(), page_reads(k).into());
    }
    let sorted = |m: &Map<String, Value>, k: Kind| {
        let mut v: Vec<String> = m[k.name()].as_array().unwrap().iter().map(|x| x.to_string()).collect();
        v.sort();
        v
    };
    let same = Kind::ALL.iter().all(|&k| sorted(&file, k) == sorted(&want, k));
    // written only when a list differs (the order and the layout of the file are free)
    if !same && std::env::var("ROADSTYLE_BLESS").is_ok_and(|v| v == "1") {
        let text = serde_json::to_string_pretty(&Value::Object(want.clone())).unwrap();
        std::fs::write(&path, text + "\n").unwrap();
        return;
    }
    for k in Kind::ALL {
        assert_eq!(sorted(&file, k), sorted(&want, k), "reads.json's {}: run ROADSTYLE_BLESS=1 cargo test --test marks", k.name());
    }
}
