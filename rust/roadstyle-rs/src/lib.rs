//! roadstyle's engine in Rust (docs/design/rust_engine.md): the style of a map from the roads in a GeoParquet file, its vector
//! tiles, and the drawing levels (`levels`). The front-ends: the native program (main.rs), the browser (crate roadstyle-wasm).

pub mod colors;
pub mod features;
pub mod geom;
pub mod layers;
pub mod levels;
pub mod overlays;
pub mod planner;
pub mod props;
pub mod read;
pub mod roads;
pub mod simple;
pub mod slots;
pub mod tiles;

use serde_json::{json, Value};

/// The most roads of one map: a browser keeps the module's memory under 4 GB. Tartu (63,965 roads) peaks at 1.13 GB natively (2.13 GB
/// before the typed sources, docs/design/rust_engine.md), and the wasm module used 0.65 to 0.77 times the native peak in the earlier
/// measurements: about 14 KB a road, so 200,000 roads are about 2.8 GB.
/// ponytail: an estimate from Tartu only; measure a larger area in a browser before the limit goes higher.
pub const MAX_ROADS: usize = 200_000;

/// A source of the style: typed features (roads, simple) or a GeoJSON source as JSON (the base map, slots).
pub enum Src {
    Typed(props::Source),
    Json(Value),
}

/// The parts of a style: its layers, its sources in their order (roads, ov<i>, simple, slots), its metadata and its camera.
pub struct Parts {
    pub name: Value,
    pub center: Value,
    pub zoom: Value,
    pub layers: Vec<Value>,
    pub sources: Vec<(String, Src)>,
    pub metadata: Value,
    /// The names' font, when there are labels.
    pub glyphs: Option<Value>,
}

/// The style's layers and sources: the roads ("roads", "simple", "slots") and, with `features` (the base-map tables as the worker's SQL
/// writes them), the base map ("ov<i>"). `look`: look.json (the resolved look); `parquet`: the roads as tools/make_spike_fixture.py (or
/// the worker's SQL) writes them.
pub fn make_parts(parquet: Vec<u8>, look: &str, features: Option<Vec<u8>>, planner: Option<Vec<u8>>, name: Option<String>) -> Result<Parts, String> {
    let look_json: Value = serde_json::from_str(look).map_err(|e| format!("look: not JSON: {e}"))?;
    let look = roads::Look::from_json(&look_json)?;
    let mut feats = read::read_roads(parquet, "geometry")?;
    if feats.len() > MAX_ROADS {
        return Err(format!("this area has {} roads, and the plugin draws at most {MAX_ROADS} (the browser's memory): use a smaller area",
                           feats.len()));
    }
    let colors = roads::mark_roads(&mut feats, &look, &look_json["args"])?;
    let simple = simple::simple_source(&feats, look.head_m, look.bridge_shadow)?;
    let slots = slots::slots_source(&feats, &slots::SlotLook::from_json(&look_json)?);
    let mut ovs = Vec::new();
    let mut images = serde_json::Map::new();
    if let Some(f) = features {
        let mut fcs = features::feature_collections(f, &look_json)?;
        let attached = overlays::edge_attach(&mut fcs, &feats);
        (ovs, images) = overlays::feature_overlays(fcs, &look_json, &attached);
    }
    // everything that reads the roads is done before this: the roads source takes them
    // export_inline(planner=True): the route planner's graphs, or the number of roads past the limit
    let planned = match planner {
        Some(_) if feats.len() > planner::PLANNER_MAX_EDGES => Some(("roadstyle:planner_skipped", json!(feats.len()))),
        Some(p) => Some(("roadstyle:planner", planner::planner_data(&feats, p)?)),
        None => None,
    };
    let (center, zoom) = camera(&feats);
    let roads = roads::roads_source(feats);
    let layers = layers::road_layers(&look_json, &roads.feats, &simple.feats, source_features(&slots), &mut ovs, &colors.props, colors.active)?;
    let glyphs = (!source_features(&slots).is_empty()).then(|| look_json["theme"]["labels"]["glyphs"].clone());
    let mut sources = vec![("roads".to_string(), Src::Typed(roads))];
    for (i, ov) in ovs.into_iter().enumerate() {
        let mut s = serde_json::Map::new();
        s.insert("type".into(), "geojson".into());
        s.insert("data".into(), ov.fc);
        s.insert("generateId".into(), true.into());
        sources.push((format!("ov{i}"), Src::Json(Value::Object(s))));
    }
    sources.push(("simple".into(), Src::Typed(simple)));
    sources.push(("slots".into(), Src::Json(slots)));
    images.insert("oneway".into(), look_json["oneway_image"].clone());
    let mut metadata = serde_json::Map::new();
    // the export's page metadata: the road popup's fields, the hover tooltip and the hover delay (roadstyle:interaction)
    let it = &look_json["interaction"];
    metadata.insert("roadstyle:interaction".into(), json!({"popup": it["popup"], "tooltip": look_json["args"]["tooltip"], "hover_delay_ms": it["hover_delay_ms"]}));
    metadata.insert("roadstyle:images".into(), Value::Object(images));
    if let Some((k, v)) = planned {
        metadata.insert(k.into(), v);
    }
    // the legend data of a data-coloured map, as the page's COLOR_OPTIONS (render_web: {name, prop, legend} for each colour option)
    if !colors.meta.is_empty() {
        metadata.insert("roadstyle:color_options".into(), Value::Array(colors.meta));
    }
    let name = name.map_or_else(|| look_json["args"]["name"].clone(), Value::from);
    Ok(Parts { name, center, zoom, layers, sources, metadata: Value::Object(metadata), glyphs })
}

/// The style as one JSON text, with each source's GeoJSON in it (roadstyle's export_inline).
pub fn make_style(parquet: Vec<u8>, look: &str, features: Option<Vec<u8>>, planner: Option<Vec<u8>>, name: Option<String>) -> Result<String, String> {
    let Parts { name, center, zoom, layers, sources, metadata, glyphs } = make_parts(parquet, look, features, planner, name)?;
    // The sources become text one at a time, and each is freed at once: a big area's sources are the most of the memory (Tartu: the
    // peak went from 4.3 GB to 2.5 GB natively).
    let metadata = metadata.to_string();
    let mut out = format!(r#"{{"version":8,"name":{name},"center":{center},"zoom":{zoom},"layers":{},"sources":{{"#, Value::Array(layers)).into_bytes();
    for (i, (k, s)) in sources.into_iter().enumerate() {
        out.extend_from_slice(format!("{}{}:", if i > 0 { "," } else { "" }, Value::from(k)).as_bytes());
        match s {
            Src::Typed(s) => s.write_json(&mut out),
            Src::Json(s) => serde_json::to_writer(&mut out, &s).unwrap(),
        }
    }
    out.extend_from_slice(br#"},"metadata":"#);
    out.extend_from_slice(metadata.as_bytes());
    if let Some(g) = glyphs {
        out.extend_from_slice(format!(r#","glyphs":{g}"#).as_bytes());
    }
    out.push(b'}');
    Ok(String::from_utf8(out).expect("serde_json writes UTF-8"))
}

/// The style with vector-tile sources (`<prefix><source>/{z}/{x}/{y}`), and the tiles to answer them with (tiles.rs). The layers,
/// the metadata and the camera are those of `make_style`; each layer gets `source-layer`, the name of its source. The tiles keep only
/// the properties that are read: the texts in the layers (all their keys, and more), the popup and tooltip fields of the metadata, the
/// overlays' popup fields (name, kind) and `keep` (the caller's own, for example its popup's).
pub fn make_tiled(parquet: Vec<u8>, look: &str, features: Option<Vec<u8>>, name: Option<String>, prefix: &str, keep: &[String])
                  -> Result<(String, tiles::Tiles), String> {
    let Parts { name, center, zoom, mut layers, sources, metadata, glyphs } = make_parts(parquet, look, features, None, name)?;
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
    let mut tiled = tiles::Tiles::default();
    let mut vector = serde_json::Map::new();
    for (k, s) in sources {
        match s {
            Src::Typed(s) => tiled.add_typed(&k, s, &read),
            Src::Json(s) => tiled.add(&k, s, &read), // frees the source's tree
        }
        vector.insert(k.clone(), json!({"type": "vector", "tiles": [format!("{prefix}{k}/{{z}}/{{x}}/{{y}}")], "minzoom": 0,
                                        "maxzoom": tiles::MAX_ZOOM}));
    }
    for l in layers.iter_mut() {
        if let Some(src) = l.get("source").cloned() {
            l["source-layer"] = src;
        }
    }
    let mut style = json!({"version": 8, "name": name, "center": center, "zoom": zoom, "layers": layers, "sources": vector, "metadata": metadata});
    if let Some(g) = glyphs {
        style["glyphs"] = g;
    }
    Ok((style.to_string(), tiled))
}

/// roadstyle.export._camera: the centre and the zoom that fit the roads' bounds in a 1024 x 768 px view, as the page's fitBounds.
fn camera(feats: &[read::Feature]) -> (Value, Value) {
    let (mut x0, mut y0, mut x1, mut y1) = (f64::INFINITY, f64::INFINITY, f64::NEG_INFINITY, f64::NEG_INFINITY);
    for c in feats.iter().filter_map(|f| f.coords.as_ref()).flatten() {
        x0 = x0.min(c[0]);
        y0 = y0.min(c[1]);
        x1 = x1.max(c[0]);
        y1 = y1.max(c[1]);
    }
    let y = |lat: f64| (std::f64::consts::PI / 4.0 + lat.clamp(-85.0, 85.0).to_radians() / 2.0).tan().ln();
    let zx = (1024.0 / 256.0 * 360.0 / (x1 - x0).max(1e-9)).log2();
    let zy = (768.0 / 256.0 * 2.0 * std::f64::consts::PI / (y(y1) - y(y0)).max(1e-9)).log2();
    (json!([(x0 + x1) / 2.0, (y0 + y1) / 2.0]), json!(layers::py_round(zx.min(zy).clamp(0.0, 18.0), 2)))
}

/// A JSON object made by moving its values in. json!({..}) serializes each value by reference: a deep copy of a big tree (a source's features).
pub(crate) fn obj<const N: usize>(kv: [(&str, Value); N]) -> Value {
    Value::Object(kv.into_iter().map(|(k, v)| (k.to_string(), v)).collect())
}

fn source_features(source: &Value) -> &[Value] {
    source["data"]["features"].as_array().map_or(&[][..], |v| v.as_slice())
}
