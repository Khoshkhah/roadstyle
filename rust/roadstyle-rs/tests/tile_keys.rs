//! The keys of a tile (docs/design/tiling.md, "The keys of a tile"): a road feature in a tile has the geometry, the feature id (the road's row) and
//! the keys that the style and the dashboard's filters read in MapLibre. No data column, and no text value outside `TILE_TEXT_KEYS`, on every path
//! that makes tiles: the page's look (the page archive and the map worker), the export look (`export_style`), and the files of stage 1 (the
//! program `roadstyle tiles`). Each path is checked on the tiles of Monaco at zooms 12, 14 and 15.

mod common;

use roadstyle_rs::tiles::Tiles;
use roadstyle_rs::Look;
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::path::PathBuf;

fn data(p: &str) -> Vec<u8> {
    let p = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data").join(p);
    std::fs::read(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()))
}

fn look(export: bool) -> Look {
    let mut look: Value = serde_json::from_slice(&data("look.json")).unwrap();
    look["args"]["arrows"] = true.into();
    look["args"]["labels"] = true.into();
    look["args"]["export"] = export.into();
    if !export {
        look["args"]["state"] = "live".into();          // a page's style: the interaction contract, with the filter panel's classes (`roadstyle:controls.filter`)
    }
    Look::from_value(look).unwrap()
}

/// Every tile of the roads' box at zooms 12, 14 and 15: (layer, key, is a text) with the number of features that have it.
fn keys_of(tiles: &Tiles, roads: &[u8]) -> BTreeMap<(String, String, bool), usize> {
    // the entry (layer, "#features", false) is the number of features of the layer
    let t = roadstyle_rs::read::read_roads(roads.to_vec(), "geometry").unwrap();
    let (mut x0, mut y0, mut x1, mut y1) = (f64::INFINITY, f64::INFINITY, f64::NEG_INFINITY, f64::NEG_INFINITY);
    for c in (0..t.len()).filter_map(|i| t.line(i)).flatten() {
        (x0, y0, x1, y1) = (x0.min(c[0]), y0.min(c[1]), x1.max(c[0]), y1.max(c[1]));
    }
    let mut out = BTreeMap::new();
    for z in [12u32, 14, 15] {
        let k = (1u64 << z) as f64;
        let tx = |lon: f64| ((lon + 180.0) / 360.0 * k) as u32;
        let ty = |lat: f64| ((1.0 - lat.to_radians().tan().asinh() / std::f64::consts::PI) / 2.0 * k) as u32;
        for x in tx(x0)..=tx(x1) {
            for y in ty(y1)..=ty(y0) {
                for (layer, feats) in common::decode_tile(&tiles.tile(z, x, y)) {
                    for (id, props, _, _) in feats {
                        *out.entry((layer.clone(), "#features".to_string(), false)).or_insert(0) += 1;
                        if layer == "simple" || layer == "slots" {
                            assert!(id.is_some(), "{layer}: a feature has no id (the id is the road's row)");
                        }
                        for (key, v) in props {
                            *out.entry((layer.clone(), key, v.is_string())).or_insert(0) += 1;
                        }
                    }
                }
            }
        }
    }
    out
}

/// The key table of a path, as the tests print it (and append to `ROADSTYLE_TILE_KEYS_OUT`, the CI's step summary): for each key of a road layer, its type, the number
/// of features that have it, the style layers that read it (`["get", key]`) and what the dashboard reads (reads.json: pieces, slots, table).
fn table(path: &str, style: &str, found: &BTreeMap<(String, String, bool), usize>) {
    use roadstyle_rs::mark::{page_reads, Kind};
    let style: Value = serde_json::from_str(style).unwrap();
    let layers = style["layers"].as_array().cloned().unwrap_or_default();
    let mut out = format!("\n### Tile keys: {path}\n\n| layer | key | value | features | read by the style | read by the page |\n|---|---|---|---|---|---|\n");
    for ((layer, key, is_text), n) in found.iter().filter(|((l, k, _), _)| (l == "simple" || l == "slots") && k != "#features") {
        let get = format!("[\"get\",\"{key}\"]");
        let style_layers: Vec<String> = layers.iter().filter(|l| l["source-layer"] == layer.as_str())
            .filter(|l| ["paint", "layout", "filter"].iter().any(|k| l[k].to_string().contains(&get))).map(|l| l["id"].as_str().unwrap_or("").to_string()).collect();
        let kind = if layer == "simple" { Kind::Pieces } else { Kind::Slots };
        let page = if page_reads(kind).iter().any(|k| k == key) { "yes" } else { "" };
        let listed = roadstyle_rs::mark::TILE_TEXT_KEYS.iter().any(|(l, k)| l == layer && k == key);
        let ty = match (*is_text, listed) { (true, _) => "TEXT", _ => "number or flag" };
        out.push_str(&format!("| {layer} | {key} | {ty} | {n} | {} | {page} |\n", style_layers.join(", ")));
    }
    println!("{out}");
    if let Some(f) = std::env::var_os("ROADSTYLE_TILE_KEYS_OUT") {
        use std::io::Write;
        std::fs::OpenOptions::new().create(true).append(true).open(f).and_then(|mut f| f.write_all(out.as_bytes())).ok();
    }
}

fn check(path: &str, style: &str, found: &BTreeMap<(String, String, bool), usize>) {
    table(path, style, found);
    let road = |l: &str| l == "simple" || l == "slots";
    let text: BTreeSet<(String, String)> = roadstyle_rs::mark::TILE_TEXT_KEYS.iter().map(|(l, k)| (l.to_string(), k.to_string())).collect();
    let mut errors = Vec::new();
    for layer in ["simple", "slots"] {
        let n = |k: &str| found.get(&(layer.to_string(), k.to_string(), false)).copied().unwrap_or(0);
        if n("#features") > 0 && n(roadstyle_rs::mark::Mark::ClassIndex.name()) != n("#features") {
            errors.push(format!("{layer}: {} features and {} with the class number __rs_ci (the style's class tests read it)", n("#features"), n(roadstyle_rs::mark::Mark::ClassIndex.name())));
        }
    }
    for (layer, key, is_text) in found.keys().filter(|(l, k, _)| road(l) && k != "#features") {
        if !roadstyle_rs::mark::tile_key_allowed(key) {
            errors.push(format!("{layer}.{key}: not on the list of tile keys (a data column goes to the road table, not to a tile)"));
        }
        if *is_text && !text.contains(&(layer.clone(), key.clone())) {
            errors.push(format!("{layer}.{key}: a text value on a road feature (a number or a flag in the tile, the text in the road table)"));
        }
    }
    // the keys of a feature only go down (mark.rs TILE_KEY_COUNT); `__rs_arw` is the export look's own
    for (layer, max) in roadstyle_rs::mark::TILE_KEY_COUNT {
        let keys = found.keys().filter(|(l, k, _)| l == layer && k != "#features" && k != roadstyle_rs::mark::Mark::SlotArrow.name()).count();
        if keys > max {
            errors.push(format!("{layer}: {keys} keys, at most {max} (TILE_KEY_COUNT only goes down)"));
        }
    }
    for (layer, key) in &text {
        if !found.keys().any(|(l, k, t)| l == layer && k == key && *t) {
            errors.push(format!("{layer}.{key}: no text value any more on the {path}: take it out of TILE_TEXT_KEYS"));
        }
    }
    assert!(errors.is_empty(), "{path}:\n{}", errors.join("\n"));
}

#[test]
fn the_page_look_tiles_have_only_the_listed_keys() {
    let roads = data("monaco/roads.parquet");
    let (style, tiles, _) = roadstyle_rs::tiled_from_parquet(roads.clone(), &look(false), Some(data("monaco/features.parquet")), None, "rs://", &[]).unwrap();
    check("page look (the page's archive and the map worker)", &style, &keys_of(&tiles, &roads));
}

#[test]
fn the_export_look_tiles_have_only_the_listed_keys() {
    let roads = data("monaco/roads.parquet");
    let (style, tiles, _) = roadstyle_rs::tiled_from_parquet(roads.clone(), &look(true), Some(data("monaco/features.parquet")), None, "rs://", &[]).unwrap();
    check("export look (export_style, a server)", &style, &keys_of(&tiles, &roads));
}

#[test]
fn the_tiles_of_the_stage_1_files_have_only_the_listed_keys() {
    let roads = data("monaco/roads.parquet");
    let look = look(true);
    let s = roadstyle_rs::style_sources(roads.clone(), &look, Some(data("monaco/features.parquet")), None, None).unwrap();
    let dir = std::env::temp_dir().join(format!("roadstyle-tile-keys-{}", std::process::id()));
    roadstyle_rs::write_sources(&s, &dir, roadstyle_rs::Format::GeoParquet, &[]).unwrap();
    let (style, tiles) = roadstyle_rs::tiles_of_files(&dir, &[], None, &roadstyle_rs::xyz_at("")).unwrap();
    std::fs::remove_dir_all(&dir).ok();
    check("stage 1 files (the program roadstyle tiles)", &style.to_string(), &keys_of(&tiles, &roads));
}

/// One rule means one key set. The paths differ only where the style differs, and this list says where: `__rs_arw` marks the slots that carry an arrow,
/// which the export look's arrow layer reads and the page look has not (the page's `arrows.js` places its own arrows).
#[test]
fn the_paths_differ_only_in_the_documented_keys() {
    let roads = data("monaco/roads.parquet");
    let features = Some(data("monaco/features.parquet"));
    let keys = |look: &Look| -> BTreeSet<(String, String)> {
        let (_, tiles, _) = roadstyle_rs::tiled_from_parquet(roads.clone(), look, features.clone(), None, "rs://", &[]).unwrap();
        keys_of(&tiles, &roads).into_keys().filter(|(l, k, _)| (l == "simple" || l == "slots") && k != "#features").map(|(l, k, _)| (l, k)).collect()
    };
    let (page, export) = (keys(&look(false)), keys(&look(true)));
    let only_page: Vec<String> = page.difference(&export).map(|(l, k)| format!("{l}.{k}")).collect();
    let only_export: Vec<String> = export.difference(&page).map(|(l, k)| format!("{l}.{k}")).collect();
    assert!(only_page.is_empty(), "keys of the page look only: {only_page:?}");
    assert_eq!(only_export, ["slots.__rs_arw"], "keys of the export look only");
}
