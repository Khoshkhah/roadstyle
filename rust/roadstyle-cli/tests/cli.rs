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

/// The page in one call (page_options::page_from): the options in RS_OPTIONS, MapLibre inline, a view's palette, and a tiled page.
#[test]
fn page_of_monaco() {
    let dir = tmp("page");
    std::fs::create_dir_all(&dir).unwrap();
    let page = |args: &[&str]| {
        let out = dir.join("monaco.html");
        let mut c = Command::new(env!("CARGO_BIN_EXE_roadstyle"));
        c.args(["page", &data("monaco/roads.parquet"), &out.to_string_lossy()]).args(args);
        let r = c.env_remove("ROADSTYLE_API_KEY").env_remove("GOOGLE_MAPS_KEY").output().unwrap();
        assert!(r.status.success(), "roadstyle page {args:?}: {}", String::from_utf8_lossy(&r.stderr));
        let html = std::fs::read_to_string(&out).unwrap();
        let at = html.find("const RS_OPTIONS = ").unwrap() + "const RS_OPTIONS = ".len();
        let opts = serde_json::Deserializer::from_str(&html[at..]).into_iter::<serde_json::Value>().next().unwrap().unwrap();
        (html, opts)
    };
    let (html, o) = page(&["--basemap", "osm", "--palette", "amber", "--views", r#"{"mono": {"palette": "mono"}}"#, "--tiles", "false", "--name", "Monaco"]);
    assert!(!html.contains("__MAPLIBRE_JS__") && html.contains("maplibregl") && html.contains("<title>Monaco</title>"));
    assert_eq!((o["basemaps"][0]["key"].as_str(), o["tiles"].as_bool(), o["views"][0]["name"].as_str()), (Some("osm"), Some(false), Some("mono")));
    assert!(o["filter"]["palettes"]["mono"].is_object() && o["camera"]["bounds"][0][0].as_f64().unwrap() > 7.0);
    // the default is tiles (one rule, MLT); GeoJSON roads only with --no-tiles
    let (html, o) = page(&["--basemap", "osm"]);
    assert!(o["tiles"] == true && html.contains("pmtiles://roads"));
    let (html, o) = page(&["--basemap", "osm", "--no-tiles"]);
    assert!(o["tiles"] == false && !html.contains("pmtiles://roads"));
    std::fs::remove_dir_all(&dir).ok();
}

#[test]
fn levels_make_and_solve() {
    let dir = tmp("levels");
    let said = roadstyle(&["levels", "make", &data("level_area/edges.parquet"), &dir.to_string_lossy()]);
    assert!(said.contains("694 roads"), "{said}");
    // the pairs of make's golden (roadstyle-rs tests/level_area.rs: rust_make.json)
    let golden: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(data("level_area/rust_make.json")).unwrap()).unwrap();
    let pairs = std::fs::read_to_string(dir.join("pairs.csv")).unwrap().lines().count() - 1;
    assert_eq!(pairs as u64, golden["pairs"].as_u64().unwrap());
    let said = roadstyle(&["levels", "solve", &dir.to_string_lossy()]);
    assert!(said.contains("694 roads"), "{said}");
    let rows = std::fs::read_to_string(dir.join("levels.csv")).unwrap().lines().count();
    assert_eq!(rows, 1 + 1373, "a header and a row for each edge");
    assert!(std::fs::read_to_string(dir.join("levels_info.json")).unwrap().contains("\"order_violations\""));
    // the key of the solve's inputs (roadstyle-levels' inputs_key), as the editor page makes it: the page starts from these levels
    let info: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(dir.join("levels_info.json")).unwrap()).unwrap();
    let file = |f: &str| std::fs::read(dir.join(f)).unwrap();
    assert_eq!(info["inputs"], roadstyle::levels::inputs_key(&file("roads.parquet"), &file("pairs.csv"), &file("edits.csv")));
    std::fs::remove_dir_all(&dir).ok();
}

/// The roads by the file's extension (audit N18): Södermalm's GeoPackage (EPSG:3006, reprojected), and an error for another file.
#[test]
fn levels_make_reads_a_geopackage() {
    let dir = tmp("gpkg");
    let gpkg = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../notebooks/data/sodermalm_edges.gpkg");
    let said = roadstyle(&["levels", "make", &gpkg.to_string_lossy(), &dir.to_string_lossy()]);
    assert!(said.starts_with("4563 edges"), "{said}");
    let out = Command::new(env!("CARGO_BIN_EXE_roadstyle")).args(["levels", "make", "roads.csv", &dir.to_string_lossy()]).output().unwrap();
    assert!(String::from_utf8_lossy(&out.stderr).contains("roads.csv: the roads must be a .parquet, .geojson, .shp or .gpkg file"));
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

#[test]
fn levels_edit_needs_a_made_area() {
    let dir = tmp("edit-empty");
    let out = Command::new(env!("CARGO_BIN_EXE_roadstyle")).args(["levels", "edit", &dir.to_string_lossy()]).output().unwrap();
    assert!(!out.status.success() && String::from_utf8_lossy(&out.stderr).contains("no roads.parquet: make the area first"));
    std::fs::remove_dir_all(&dir).ok();
}

#[test]
fn levels_make_keeps_the_boundary_of_the_area() {
    let dir = tmp("boundary");
    std::fs::create_dir_all(&dir).unwrap();
    let square = dir.join("square.geojson");
    std::fs::write(&square, r#"{"type":"Polygon","coordinates":[[[7.4,43.7],[7.5,43.7],[7.5,43.8],[7.4,43.7]]]}"#).unwrap();
    let area = dir.join("area");
    roadstyle(&["levels", "make", &data("level_area/edges.parquet"), &area.to_string_lossy(), "--boundary", &square.to_string_lossy()]);
    assert_eq!(std::fs::read_to_string(area.join("boundary.geojson")).unwrap(), std::fs::read_to_string(&square).unwrap());
    // a file that is not GeoJSON is an error, and the area has no boundary.geojson from it
    let text = dir.join("roads.txt");
    std::fs::write(&text, r#"{"type":"Point"}"#).unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_roadstyle"))
        .args(["levels", "make", &data("level_area/edges.parquet"), &dir.join("other").to_string_lossy(), "--boundary", &text.to_string_lossy()]).output().unwrap();
    assert!(!out.status.success() && String::from_utf8_lossy(&out.stderr).contains("not a GeoJSON polygon"));
    std::fs::remove_dir_all(&dir).ok();
}
