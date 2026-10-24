//! The roadstyle program on Monaco: stage 1 (sources), stage 2 (tiles) as PMTiles and as XYZ, a level area (levels make: the pairs of
//! roadstyle's make_area; levels solve) and its errors.

use std::path::PathBuf;
use std::process::Command;

fn data(p: &str) -> String {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../roadstyle-rs/tests/data").join(p).to_string_lossy().into_owned()
}

/// Runs `roadstyle args`: its stdout, or a panic with its stderr.
fn roadstyle(args: &[&str]) -> String {
    let out = Command::new(env!("CARGO_BIN_EXE_roadstyle")).args(args).output().unwrap();
    assert!(out.status.success(), "roadstyle {args:?}: {}", String::from_utf8_lossy(&out.stderr));
    String::from_utf8_lossy(&out.stdout).into_owned()
}

fn tmp(tag: &str) -> PathBuf {
    let d = std::env::temp_dir().join(format!("roadstyle-cli-{tag}-{}", std::process::id()));
    std::fs::remove_dir_all(&d).ok();
    d
}

#[test]
fn sources_then_tiles() {
    let dir = tmp("stages");
    let s1 = dir.join("stage1");
    let said = roadstyle(&["sources", &data("monaco/roads.parquet"), &s1.to_string_lossy(), "--format", "geoparquet", "--color-by", "lanes",
                           "--no-labels", "--name", "Monaco"]);
    assert!(said.contains("style.json") && said.contains("road_table.parquet"), "{said}");
    let style: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(s1.join("style.json")).unwrap()).unwrap();
    assert_eq!(style["name"], "Monaco");
    let pm = dir.join("monaco.pmtiles");
    roadstyle(&["tiles", &s1.to_string_lossy(), &pm.to_string_lossy()]);
    assert!(std::fs::read(&pm).unwrap().starts_with(b"PMTiles"));
    let xyz = dir.join("xyz");
    let said = roadstyle(&["tiles", &s1.to_string_lossy(), &xyz.to_string_lossy(), "--format", "xyz", "--base-url", "https://example.org/t"]);
    assert!(said.contains("tiles and style.json"), "{said}");
    let st = std::fs::read_to_string(xyz.join("style.json")).unwrap();
    assert!(st.contains("https://example.org/t/roads/{z}/{x}/{y}"));
    assert!(std::fs::read_dir(xyz.join("roads")).unwrap().count() > 0);
    std::fs::remove_dir_all(&dir).ok();
}

#[test]
fn levels_make_and_solve() {
    let dir = tmp("levels");
    let said = roadstyle(&["levels", "make", &data("level_area/edges.parquet"), &dir.to_string_lossy()]);
    assert!(said.contains("694 roads"), "{said}");
    let lines = |p: String| {
        let mut l: Vec<String> = std::fs::read_to_string(p).unwrap().lines().map(String::from).collect();
        l.sort();
        l
    };
    assert_eq!(lines(dir.join("pairs.csv").to_string_lossy().into_owned()), lines(data("level_area/pairs.csv")));
    let said = roadstyle(&["levels", "solve", &dir.to_string_lossy()]);
    assert!(said.contains("694 roads"), "{said}");
    let rows = std::fs::read_to_string(dir.join("levels.csv")).unwrap().lines().count();
    assert_eq!(rows, 1 + 1373, "a header and a row for each edge");
    assert!(std::fs::read_to_string(dir.join("levels_info.json")).unwrap().contains("\"order_violations\""));
    std::fs::remove_dir_all(&dir).ok();
}

#[test]
fn an_unknown_option_or_command_is_an_error() {
    let run = |args: &[&str]| Command::new(env!("CARGO_BIN_EXE_roadstyle")).args(args).output().unwrap();
    let out = run(&["levels", "solve", "/nowhere", "--fast"]);
    assert!(!out.status.success() && String::from_utf8_lossy(&out.stderr).contains("unknown option --fast"));
    assert!(!run(&["draw"]).status.success());
    assert!(String::from_utf8_lossy(&run(&["help"]).stdout).contains("roadstyle sources"));
}
