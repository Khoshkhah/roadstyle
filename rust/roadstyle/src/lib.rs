//! roadstyle as a Rust library (docs/design/rust_library.md): the facade. It re-exports the crates of the core with the module paths
//! of the old single crate (`roadstyle::props`, `roadstyle::read`, `roadstyle::levels`, `roadstyle::tiles`, `roadstyle::make_style`,
//! ...), and it has `make_tiled`, which needs both the engine and the tiles. A Rust user adds only this crate.

pub use roadstyle_engine::*;
pub use roadstyle_levels as levels;
pub use roadstyle_tiles as tiles;

use serde_json::{json, Value};

/// The style with one vector-tile source, `roads` (`<prefix>roads/{z}/{x}/{y}`), and the tiles to answer it with (tiles.rs: the rules of
/// roadstyle's tiles.py, the zooms and the buffer from `look["config"]["tiles"]`). The layers, the metadata and the camera are those of
/// `make_style`; each layer draws the tile layer of its old source (`source-layer`). The tiles keep only the properties that are read:
/// the texts in the layers (all their keys, and more), the popup and tooltip fields of the metadata, the overlays' popup fields (name,
/// kind) and `keep` (the caller's own, for example its popup's).
pub fn make_tiled(parquet: Vec<u8>, look: &str, features: Option<Vec<u8>>, name: Option<String>, prefix: &str, keep: &[String])
                  -> Result<(String, tiles::Tiles), String> {
    let cfg_all: Value = serde_json::from_str(look).map_err(|e| format!("look: not JSON: {e}"))?;
    let cfg = &cfg_all["config"]["tiles"];
    let num = |k: &str| cfg[k].as_f64().ok_or_else(|| format!("look: config.tiles.{k} is not a number"));
    if num("extent")? != tiles::EXTENT {
        return Err(format!("look: config.tiles.extent is {}, the tiles are made with {}", num("extent")?, tiles::EXTENT));
    }
    let (min_zoom, max_zoom) = (num("minzoom")? as u32, num("maxzoom")? as u32);
    let mut tiled = tiles::Tiles::new(min_zoom, max_zoom, num("buffer_px")?);
    let arg = |k: &str| cfg_all["args"][k].as_str().filter(|c| !c.is_empty()).map(String::from);
    let (width_col, highway_col) = (arg("width_m_col"), arg("highway_col").unwrap_or_else(|| "highway".into()));
    let Parts { name, center, zoom, mut layers, sources, metadata, glyphs, state } = make_parts(parquet, look, features, None, name)?;
    let mut read: std::collections::HashSet<String> = keep.iter().cloned().chain(["name".to_string(), "kind".to_string()]).collect();
    fn texts(v: &Value, out: &mut std::collections::HashSet<String>) {
        match v {
            Value::String(s) => {
                out.insert(s.clone());
            }
            Value::Array(a) => a.iter().for_each(|x| texts(x, out)),
            Value::Object(o) => o.values().for_each(|x| texts(x, out)),
            _ => {}
        }
    }
    layers.iter().for_each(|l| texts(l, &mut read));
    texts(&metadata["roadstyle:interaction"], &mut read);
    // the name and arrow slots go whole into the tiles, from the first zoom of their layers (tiles.py: 14, their symbols' minzoom)
    let slots_from = layers.iter().filter(|l| l["source"] == "slots").map(|l| l["minzoom"].as_f64().unwrap_or(0.0) as u32).min().unwrap_or(0);
    // render(tiles=True)'s page (the Python binding): the columns of its road and simple tiles (`tile_keep`; every __rs_* goes too) and
    // the sources in its tiles (`tile_layers`: roads, simple, slots; the page keeps the others inline)
    let exact: Option<std::collections::HashSet<String>> = cfg_all["args"]["tile_keep"].as_array()
        .map(|a| a.iter().filter_map(Value::as_str).map(String::from).collect());
    let only: Option<Vec<&str>> = cfg_all["args"]["tile_layers"].as_array().map(|a| a.iter().filter_map(Value::as_str).collect());
    for (k, s) in sources {
        let slots = k == "slots";
        let from = if slots { slots_from } else { 0 };
        if only.as_ref().is_some_and(|o| !o.contains(&k.as_str())) {
            continue;
        }
        match s {
            Src::Typed(s) if exact.is_some() => tiled.add_typed(&k, s, exact.as_ref().unwrap(), slots, from),
            // render's tiles: the pieces of `simple` keep the class, lvl, the metre width column and the __rs_* marks (not a picked item's fields)
            Src::Typed(s) if k == "simple" => {
                let keep: std::collections::HashSet<String> = [highway_col.clone(), "lvl".into()].into_iter().chain(width_col.clone()).collect();
                tiled.add_typed(&k, s, &keep, slots, from)
            }
            Src::Typed(s) => tiled.add_typed(&k, s, &read, slots, from),
            Src::Json(s) => {
                // render's export: another GeoJSON source (the 3D decks, an overlay) keeps all its properties (keep=None). Python writes
                // its points and polygons whole; the engine clips them with the buffer, as the lines (docs/design/rust_library.md, P0)
                let mut keep = read.clone();
                if !slots {
                    let fs = s["data"]["features"].as_array().map(Vec::as_slice).unwrap_or_default();
                    keep.extend(fs.iter().filter_map(|f| f["properties"].as_object()).flat_map(|p| p.keys().cloned()));
                }
                tiled.add(&k, s, &keep, slots, from) // frees the source's tree
            }
        }
    }
    for l in layers.iter_mut() {
        if let Some(src) = l.get("source").cloned() {
            l["source-layer"] = src;
            l["source"] = tiles::SOURCE.into();
        }
    }
    let vector = json!({tiles::SOURCE: {"type": "vector", "tiles": [format!("{prefix}{}/{{z}}/{{x}}/{{y}}", tiles::SOURCE)],
                                        "minzoom": min_zoom, "maxzoom": max_zoom}});
    let mut style = json!({"version": 8, "name": name, "center": center, "zoom": zoom, "layers": layers, "sources": vector, "metadata": metadata});
    if let Some(g) = glyphs {
        style["glyphs"] = g;
    }
    if let Some(st) = state {
        style["state"] = st;
    }
    Ok((style.to_string(), tiled))
}

