//! The map options of today's keywords (T3 step 1, docs/design/t3_map_options_and_look.md): the `args` of every golden look parse, and
//! each keyword of render_edges (docs/reference/parameters.md) is a map option or a keyword that the table below names as the page's, the
//! style writer's, the tiles' or the Python binding's.

use roadstyle_look::MapOptions;
use serde_json::Value;
use std::io::Read;
use std::path::PathBuf;

fn repo(p: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..").join(p)
}

fn json(p: &str) -> Value {
    let mut text = String::new();
    let f = std::fs::File::open(repo(p)).unwrap();
    if p.ends_with(".gz") { flate2::read::GzDecoder::new(f).read_to_string(&mut text) } else { std::io::BufReader::new(f).read_to_string(&mut text) }.unwrap();
    serde_json::from_str(&text).unwrap()
}

/// The keywords of render_edges that are not map options, and where they go (the design's table "What leaves MapOptions").
const NOT_MAP: &[(&str, &[&str])] = &[
    ("PageOptions", &["basemap", "basemaps", "basemap_switcher", "zoom_readout", "api_key", "legend", "legend_position", "filter_control",
                      "find_control", "overlay_control", "overlay_popup", "template", "views", "popup_mode", "side_panel_html",
                      "host_panel_width", "hover_delay_ms", "copy_field", "street_view", "street_view_key", "google_3d", "google_3d_layers", "layout", "boundary_dim", "boundary_limit", "dashboard", "page_script", "page_style", "pitch",
                      "max_pitch", "bearing", "compress", "box_layout"]),
    ("SourceMode", &["data_maxzoom", "data_tolerance"]),
    ("TileOptions", &["tiles", "tile_keep", "tile_layers"]),
    // the Python binding: it reads them before the engine (the look's sources, the filtering of the edges, a DataFrame's colour column)
    ("Python", &["palette", "profile", "settings", "backend", "engine", "include", "exclude", "match_links", "selected", "color_col"]),
];

/// The keywords of render_edges in parameters.md: the first cell of each row of its section, and the names after "/" in it.
fn keywords() -> Vec<String> {
    let text = std::fs::read_to_string(repo("docs/reference/parameters.md")).unwrap();
    let start = text.find("## `render_edges`").unwrap();
    let end = start + text[start..].find("\n## Pages").unwrap();
    let mut out = Vec::new();
    for row in text[start..end].lines().filter(|l| l.starts_with("| `")) {
        let cell = row.split('|').nth(1).unwrap();
        out.extend(cell.split('`').skip(1).step_by(2).map(String::from));
    }
    out
}

#[test]
fn every_keyword_of_render_edges_has_its_place() {
    let not_map: Vec<&str> = NOT_MAP.iter().flat_map(|(_, k)| k.iter().copied()).collect();
    let kws = keywords();
    assert!(kws.len() > 80, "{} keywords: the table of parameters.md was not read", kws.len());
    let mut bad = Vec::new();
    for k in &kws {
        // a value that is not the keyword's own kind is fine here: the test asks only whether the keyword is a map option
        let (_, rest) = MapOptions::from_args(&serde_json::json!({k: Value::Bool(true)}))
            .unwrap_or_else(|_| (MapOptions::default(), vec![]));
        if rest.contains(k) != not_map.contains(&k.as_str()) {
            bad.push(k.as_str());
        }
    }
    assert!(bad.is_empty(), "a map option and in NOT_MAP, or neither (give each its place): {bad:?}");
}

#[test]
fn the_args_of_every_golden_look_parse() {
    let not_map: Vec<&str> = NOT_MAP.iter().flat_map(|(_, k)| k.iter().copied()).collect();
    let mut args: Vec<Value> = vec![json("rust/roadstyle-rs/tests/data/look.json")["args"].clone()];
    for area in ["monaco", "tartu", "sodermalm"] {
        args.push(json(&format!("rust/roadstyle-rs/tests/data/{area}/golden_options.json.gz"))["args"].clone());
    }
    args.extend(json("rust/roadstyle-look/tests/data/mapstyle_looks.json.gz")["parts"]["args"].as_array().unwrap().iter().cloned());
    assert!(args.len() > 10);
    for a in &args {
        let (m, rest) = MapOptions::from_args(a).unwrap_or_else(|e| panic!("{e}: {a}"));
        assert!(rest.iter().all(|k| not_map.contains(&k.as_str())), "{rest:?}");
        // the stored level columns: the caller's columns
        if a.get("casing_level_col").is_some() {
            assert_eq!(m.columns.levels.unwrap().casing_level.as_deref(), a["casing_level_col"].as_str());
        }
    }
}
