//! roadstyle's rendering engine (docs/design/rust_library.md, "The crates"): the style of a map from the roads, the look, the
//! data-driven paint, the legend data and the base-map layers. The vector tiles are in roadstyle-tiles, the levels in roadstyle-levels.

// Ported numeric code: index loops over parallel arrays and tuple types of the Python stages read as they are in Python.
#![allow(clippy::needless_range_loop, clippy::type_complexity)]

pub mod colors;
pub mod contract;
pub mod decks;
pub mod draw;
pub mod export_look;
pub mod features;
pub mod layers;
pub mod look;
pub mod overlays;
pub mod palettes;
pub mod planner;
pub mod road;
pub mod roads;
pub mod simple;
pub mod slots;
pub mod sources;

// The core has no I/O (docs/design/rust_library.md, rule 3 of the layers): the engine takes the model's types, and the readers
// (roadstyle-io) are the facade's.
pub use roadstyle_model::{geom, props, Cell, RoadTable, Row};
pub use road::{Road, Roads};
pub(crate) use roadstyle_model::obj;

use serde_json::{json, Value};

thread_local! {
    static WARNINGS: std::cell::RefCell<Vec<String>> = const { std::cell::RefCell::new(Vec::new()) };
}

/// A warning of the engine (Python's warnings.warn in render_web): the caller takes them after a call (`take_warnings`).
pub fn warn(msg: String) {
    WARNINGS.with(|w| w.borrow_mut().push(msg));
}

thread_local! {
    static CLS: std::cell::RefCell<String> = std::cell::RefCell::new("highway".into());
}

/// The column of the class filter (render's filter_col, else highway_col; in the engine's names): `__rs_cls` on every piece is its value.
pub(crate) fn cls_col() -> String {
    CLS.with(|c| c.borrow().clone())
}

/// The class filter's value of a road (render's fcol).
pub(crate) fn cls_of(r: Road) -> Value {
    CLS.with(|c| r.get(&c.borrow()).map_or(Value::Null, Cell::to_value))
}

/// The warnings of the last calls on this thread, and none after.
pub fn take_warnings() -> Vec<String> {
    WARNINGS.with(|w| std::mem::take(&mut *w.borrow_mut()))
}

/// The most roads of one map: a browser keeps the module's memory under 4 GB. Tartu (63,965 roads) peaks at 1.13 GB natively (2.13 GB
/// before the typed sources, docs/design/rust_engine.md), and the wasm module used 0.65 to 0.77 times the native peak in the earlier
/// measurements: about 14 KB a road, so 200,000 roads are about 2.8 GB.
/// ponytail: an estimate from Tartu only; measure a larger area in a browser before the limit goes higher.
pub const MAX_ROADS: usize = 200_000;

/// A source of the style: the roads, the simple pieces (both typed, written from the roads) or a GeoJSON source as JSON (the base
/// map, slots).
pub enum Src {
    Roads(road::RoadsSource),
    Simple(simple::SimpleSource),
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
    /// state "live": MapLibre's global state, each name with its start value (`{"rs_co": {"default": 0}, ...}`)
    pub state: Option<Value>,
}

/// The style's layers and sources: the roads ("roads", "simple", "slots") and, with `features` (the base-map tables as the worker's SQL
/// writes them), the base map ("ov<i>"). `look`: look.json (the resolved look); `table`: the roads (roadstyle-io reads them from the
/// GeoParquet of tools/make_spike_fixture.py or the worker's SQL); `planner`: the route planner's rows.
pub fn make_parts(mut table: RoadTable, look: &str, features: Option<Vec<Row>>, planner: Option<Vec<Row>>, name: Option<String>) -> Result<Parts, String> {
    let look_json: Value = serde_json::from_str(look).map_err(|e| format!("look: not JSON: {e}"))?;
    let head_m = roads::Look::from_json(&look_json)?.head_m;
    if table.len() > MAX_ROADS {
        return Err(format!("this area has {} roads, and the plugin draws at most {MAX_ROADS} (the browser's memory): use a smaller area",
                           table.len()));
    }
    ColumnMap::from_args(&look_json["args"]).to_engine(&mut table);
    compute_levels(&mut table, &look_json["args"], head_m)?;
    style_parts(table, &look_json, features, planner, name)
}

/// The parts of another palette of the same call (a view's palette, palettes.rs): the roads of `s` as they were before their marks
/// (their columns in the engine's names, their levels solved), with the look `look` (the same keywords, another palette). No base map
/// and no route planner, as a page's views have none.
pub fn restyle(s: &sources::Sources, look: &str) -> Result<sources::Sources, String> {
    let look_json: Value = serde_json::from_str(look).map_err(|e| format!("look: not JSON: {e}"))?;
    Ok(sources::Sources::new(style_parts(s.roads.roads.table.clone(), &look_json, None, None, None)?))
}

/// make_parts after the roads are prepared (the engine's column names, the levels).
fn style_parts(table: RoadTable, look_json: &Value, features: Option<Vec<Row>>, planner: Option<Vec<Row>>, name: Option<String>) -> Result<Parts, String> {
    let look_json = look_json.clone();
    let look = roads::Look::from_json(&look_json)?;
    let cols = ColumnMap::from_args(&look_json["args"]);
    // render's filter_col: in the engine's names (a keyword's column has the engine's name; a column with an engine name is kept aside)
    let fcol = look_json["args"]["filter_col"].as_str().filter(|c| !c.is_empty()).map_or_else(|| "highway".to_string(), |f| {
        cols.0.iter().find(|(_, user)| user == f).map(|(own, _)| own.to_string())
            .or_else(|| cols.0.iter().find(|(own, _)| *own == f).map(|(own, _)| ColumnMap::kept(own)))
            .unwrap_or_else(|| f.to_string())
    });
    CLS.with(|c| *c.borrow_mut() = fcol);
    let mut feats = Roads::new(table);
    let colors = roads::mark_roads(&mut feats, &look, &look_json["args"])?;
    let width_col = look_json["args"]["width_m_col"].as_str().filter(|c| !c.is_empty());
    // render's arrows and labels (both on by default): the slots exist only for them
    let (arrows, labels) = (look_json["args"]["arrows"] != false, look_json["args"]["labels"] != false);
    let slots = if arrows || labels { slots::slots_source(&feats, &slots::SlotLook::from_json(&look_json)?) }
                else { json!({"type": "geojson", "data": {"type": "FeatureCollection", "features": []}}) };
    let mut ovs = Vec::new();
    let mut images = serde_json::Map::new();
    if let Some(f) = features {
        let mut fcs = features::feature_collections(f, &look_json)?;
        let attached = overlays::edge_attach(&mut fcs, &feats);
        (ovs, images) = overlays::feature_overlays(fcs, &look_json, &attached);
    }
    // render's overlays=: the caller's own, after the base map's (each knows the roads' id column, for its error)
    let first_user = ovs.len();
    ovs.extend(overlays::user_overlays(&look_json["args"]["overlays"], ovs.len())?);
    for ov in ovs[first_user..].iter_mut() {
        ov.user["edge_id_col"] = look_json["args"]["edge_id_col"].clone();
    }
    // render's simple=False (the full look: a layer for each drawing position) is the Python engine's only (plan decision 2)
    if look_json["args"]["simple"] == false {
        return Err("simple=False (the full look) is in the Python engine only: use engine=\"python\", or simple mode (the default)".into());
    }
    // the line items on the edges (an overlay's lines in metres, render's items=): pieces of the one road layer
    let mut items = Vec::new();
    if ovs.iter().any(overlays::metre_items) || !look_json["args"]["items"].is_null() {
        let by_id: std::collections::HashMap<String, Road> =
            feats.iter().filter_map(|f| f.get("edge_id").map(|e| (overlays::eid(e), f))).collect();
        for (i, ov) in ovs.iter_mut().enumerate().filter(|(_, o)| overlays::metre_items(o)) {
            overlays::edge_overlay(ov, &by_id)?;
            items.extend(overlays::item_pieces(ov, i, &look_json)?);
        }
        if !look_json["args"]["items"].is_null() {
            let col = look_json["args"]["edge_id_col"].as_str().unwrap_or("edge_id");
            items.extend(overlays::road_items(&look_json["args"]["items"], &by_id, col, ovs.len(), &look_json)?);
        }
    }
    let mut simple = simple::simple_source(&feats, look.head_m, look.bridge_shadow, width_col, items)?;
    // everything that reads the roads is done before this: the roads source takes them
    // export_inline(planner=True): the route planner's graphs, or the number of roads past the limit
    let planned = match planner {
        Some(_) if feats.len() > planner::PLANNER_MAX_EDGES => Some(("roadstyle:planner_skipped", json!(feats.len()))),
        Some(p) => Some(("roadstyle:planner", planner::planner_data(&feats, p)?)),
        None => None,
    };
    let (center, zoom) = camera(&feats);
    let mut roads = roads::roads_source(feats);
    // render's view_3d: the bridges' extruded decks (_bridge_decks)
    let decks = if look_json["args"]["view_3d"] == true {
        // a casing slab names the user's own `highway` column (Python's props.get("highway")): kept aside when highway_col is another
        let hw = if cols.0.iter().any(|(own, _)| *own == "highway") { ColumnMap::kept("highway") } else { "highway".into() };
        decks::bridge_decks(&roads.roads, &decks::DeckLook::from_config(&look_json["config"]["bridge_decks"]), &layers::Model::from_look(&look_json)?, &hw)
    } else { Vec::new() };
    let (layers, info) = layers::road_layers(&look_json, &roads.roads, &simple, source_features(&slots), !decks.is_empty(), &mut ovs,
                                             &colors.props, colors.active)?;
    // state "live" (a page with the dashboard, docs/design/rust_library.md "The interaction contract"): the state stays in the expressions,
    // and the style says what the controls show
    let live = look_json["args"]["state"] == "live";
    // a page has no roads source: its pieces draw and glow (one feature state for each road's row), and the road table has the roads
    // the pieces carry their road's row as the feature id on a page, and with live data (R22: rs.setData keys the states by the row)
    (roads.in_style, simple.promote) = (!live, live || look_json["args"]["live_data"] == true);
    let (mut contract, state) = if live {
        let st = contract::page_state(&look_json, colors.active, ovs.len());
        (Some((contract::controls(&look_json, &roads.roads, info, colors.active)?, st.clone())),
         Some(Value::Object(st.into_iter().map(|(k, v)| (k, json!({"default": v}))).collect())))
    } else { (None, None) };
    let mut glyphs = (labels && !source_features(&slots).is_empty()).then(|| look_json["theme"]["labels"]["glyphs"].clone());
    if glyphs.is_none() && ovs.iter().any(|o| o.kind == "text") {      // _build_overlays: a text overlay needs a font
        glyphs = Some(json!("https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf"));
    }
    // render's order: the roads, the overlays (_build_overlays), the 3D decks, the pieces
    let mut sources = vec![("roads".to_string(), Src::Roads(roads))];
    for (i, ov) in ovs.into_iter().enumerate() {
        let mut s = serde_json::Map::new();
        s.insert("type".into(), "geojson".into());
        s.insert("data".into(), ov.fc);
        s.insert("generateId".into(), true.into());
        sources.push((format!("ov{i}"), Src::Json(Value::Object(s))));
    }
    if !decks.is_empty() {
        sources.push(("decks".into(), Src::Json(json!({"type": "geojson", "data": {"type": "FeatureCollection", "features": decks}, "generateId": true}))));
    }
    sources.push(("simple".into(), Src::Simple(simple)));
    if !source_features(&slots).is_empty() {        // as Python: no slots source without slots
        let mut slots = slots;
        if live {        // the arrow slots' numbers are for the export's thinning; the page puts the arrows itself
            for f in slots["data"]["features"].as_array_mut().into_iter().flatten() {
                f["properties"].as_object_mut().map(|p| p.shift_remove("__rs_arw"));
            }
        }
        sources.push(("slots".into(), Src::Json(slots)));
        if live && arrows && look_json["args"]["tiles"] != true {        // the page fills it: one arrow per one-way road in the window
            sources.push(("arrows".into(), Src::Json(json!({"type": "geojson", "data": {"type": "FeatureCollection", "features": []}}))));
        }
    }
    // render's boundary: a dashed outline over the roads (GeoJSON: a geometry, a Feature or a FeatureCollection; the Python binding
    // converts a shapely geometry or a GeoDataFrame)
    let mut layers = layers;
    if let Some(fc) = boundary_fc(&look_json["args"]["boundary"]) {
        sources.push(("boundary".into(), Src::Json(json!({"type": "geojson", "data": fc}))));
        let (th, b) = (&look_json["theme"], &look_json["theme"]["boundary"]);
        layers.push(json!({"id": "boundary", "type": "line", "source": "boundary", "metadata": {"roadstyle:group": "roads"},
                           "layout": {"line-cap": th["roads"]["cap"], "line-join": th["roads"]["join"]},
                           "paint": {"line-color": b["color"], "line-width": b["width"], "line-opacity": b["opacity"], "line-dasharray": b["dash"]}}));
    }
    if let Some((controls, _)) = contract.as_mut() {        // the page's roles and arrows, from its final layers
        controls["sources"] = contract::roles(&layers);
        controls["arrows"] = contract::arrow_kind(&layers);
    }
    images.insert("oneway".into(), look_json["oneway_image"].clone());
    let mut metadata = serde_json::Map::new();
    // the export's page metadata: the road popup's fields, the hover tooltip and the hover delay (roadstyle:interaction)
    let it = &look_json["interaction"];
    let args = &look_json["args"];
    // render's road_popup: true (or not given) the default fields, a list those fields, "panel" the default fields in the side panel,
    // another text every column (null), false no popup; road_tooltip, else the folium name tooltip, else none
    let popup = match &args["road_popup"] {
        Value::Bool(false) => json!(false),
        Value::Array(a) => Value::Array(a.clone()),
        Value::String(s) if s != "panel" => Value::Null,
        _ => it["popup"].clone(),
    };
    let truthy = |v: &Value| !matches!(v, Value::Null | Value::Bool(false)) && v != "" && v.as_array().is_none_or(|a| !a.is_empty());
    let tooltip = if truthy(&args["road_tooltip"]) { args["road_tooltip"].clone() }
                  else if !args["tooltip"].is_null() { args["tooltip"].clone() } else { args["road_tooltip"].clone() };
    let tooltip = if tooltip.is_null() { json!(false) } else { tooltip };
    let delay = args["hover_delay_ms"].as_f64().map_or_else(|| it["hover_delay_ms"].clone(), |d| json!(d as i64));
    metadata.insert("roadstyle:interaction".into(), json!({"popup": popup, "tooltip": tooltip, "hover_delay_ms": delay}));
    metadata.insert("roadstyle:images".into(), Value::Object(images));
    if let Some((k, v)) = planned {
        metadata.insert(k.into(), v);
    }
    // the legend data of a data-coloured map, as the page's COLOR_OPTIONS (render_web: {name, prop, legend} for each colour option)
    if !colors.meta.is_empty() {
        metadata.insert("roadstyle:color_options".into(), Value::Array(colors.meta));
    }
    // R22, live data: the feature states that the road layer reads, so a page's dashboard (rs.setData) colours and sizes the roads from a
    // table with no new build; the ramp is the call's cmap (else viridis), as 9 colours, and the no-data colour the theme's
    if look_json["args"]["live_data"] == true {
        let cmap = if look_json["args"]["cmap"].is_null() { json!("viridis") } else { look_json["args"]["cmap"].clone() };
        let ramp = colors::Ramp::new(&cmap)?;
        metadata.insert("roadstyle:live".into(), json!({
            "color": layers::LIVE_COLOR, "width": layers::LIVE_WIDTH, "types": {layers::LIVE_COLOR: "color", layers::LIVE_WIDTH: "factor"},
            "ramp": (0..9).map(|i| ramp.hex(i as f64 / 8.0)).collect::<Vec<_>>(), "nodata": look_json["theme"]["data"]["nodata"]}));
    }
    if let Some((controls, st)) = contract {
        metadata.insert("roadstyle:contract".into(), json!(contract::CONTRACT));
        metadata.insert("roadstyle:state".into(), Value::Object(st));
        metadata.insert("roadstyle:controls".into(), controls);
    }
    let name = name.map_or_else(|| look_json["args"]["name"].clone(), Value::from);
    data_settings(&mut sources, &look_json["args"]);
    cols.to_user(&mut sources, &mut layers);
    Ok(Parts { name, center, zoom, layers, sources, metadata: Value::Object(metadata), glyphs, state })
}

/// The style as one JSON text, with each source's GeoJSON in it (roadstyle's export_inline): stage 1 (`sources::Sources`), written.
pub fn make_style(table: RoadTable, look: &str, features: Option<Vec<Row>>, planner: Option<Vec<Row>>, name: Option<String>) -> Result<String, String> {
    let s = sources::Sources::new(make_parts(table, look, features, planner, name)?);
    let mut out = Vec::new();
    s.write_style(&mut out).expect("a Vec takes every byte");
    Ok(String::from_utf8(out).expect("serde_json writes UTF-8"))
}

/// The roads source out of the sources (its place keeps an empty `Src::Roads` mark): the other typed sources are written from it.
pub fn take_roads(mut sources: Vec<(String, Src)>) -> (Vec<(String, Src)>, Option<road::RoadsSource>) {
    let mut roads = None;
    for (_, s) in sources.iter_mut() {
        if let Src::Roads(r) = s {
            let empty = road::RoadsSource { roads: Roads::new(RoadTable::empty()), tolerance: r.tolerance, maxzoom: r.maxzoom, names: Vec::new(),
                                            in_style: r.in_style };
            roads = Some(std::mem::replace(r, empty));
        }
    }
    (sources, roads)
}

/// roadstyle.export._camera: the centre and the zoom that fit the roads' bounds in a 1024 x 768 px view, as the page's fitBounds.
fn camera(feats: &Roads) -> (Value, Value) {
    let (mut x0, mut y0, mut x1, mut y1) = (f64::INFINITY, f64::INFINITY, f64::NEG_INFINITY, f64::NEG_INFINITY);
    for c in feats.iter().filter_map(|f| f.line()).flatten() {
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


fn source_features(source: &Value) -> &[Value] {
    source["data"]["features"].as_array().map_or(&[][..], |v| v.as_slice())
}

/// render's level step: with no `casing_level_col` and no `fill_level_col` in the keywords, the drawing positions come from
/// `compute_levels(method="solve")` with its defaults (render_web.render), on the roads in their order. It writes the columns that
/// compute_levels writes: casing_start, casing_level, casing_end and fill_level.
fn compute_levels(table: &mut RoadTable, args: &Value, head_m: f64) -> Result<(), String> {
    let given = |k: &str| matches!(&args[k], Value::String(s) if !s.is_empty());
    if given("casing_level_col") || given("fill_level_col") {
        return Ok(());
    }
    if head_m != 5.0 {
        return Err(format!("head_m={head_m}: the Rust engine computes the levels with head_m=5 only (compute them first, or use the Python engine)"));
    }
    // the engine's own names: ColumnMap gave the user's columns these names before this step
    let edges = level_edges(table, ["highway", "layer", "bridge", "tunnel", "junction"]);
    let Some(levels) = roadstyle_levels::compute(&edges, roadstyle_levels::Method::Solve)? else { return Ok(()) };
    // one row for each edge, in the edges' order (the edge id is the row)
    if levels.rows.len() != table.len() || levels.rows.iter().enumerate().any(|(i, r)| r.edge_id != i as i64) {
        return Err(format!("compute_levels: {} rows for {} roads, not one for each road in its order", levels.rows.len(), table.len()));
    }
    let col = |f: fn(&roadstyle_levels::Row) -> i64| levels.rows.iter().map(f).collect::<Vec<i64>>();
    table.set_ints("casing_start", col(|r| r.casing_start));
    table.set_ints("casing_level", col(|r| r.casing_level));
    table.set_ints("casing_end", col(|r| r.casing_end));
    table.set_ints("fill_level", col(|r| r.fill_level));
    Ok(())
}

/// The column keywords of render (highway_col, tunnel_col, ...): the engine reads its own names (highway, tunnel, ...), so a user's
/// column gets the engine's name on the way in and its own name back on the way out, in the data and the expressions of the sources
/// `roads` and `simple`. As in Python, the slots and their layers keep `highway`, and the popup fields stay as given. A column that has
/// the engine's name but is not the named one is kept under another name in between, and gets its name back.
struct ColumnMap(Vec<(&'static str, String)>);

impl ColumnMap {
    const KEYWORDS: [(&'static str, &'static str); 15] = [
        ("highway_col", "highway"), ("tunnel_col", "tunnel"), ("bridge_col", "bridge"), ("layer_col", "layer"), ("edge_id_col", "edge_id"),
        ("casing_level_col", "casing_level"), ("fill_level_col", "fill_level"), ("casing_start_col", "casing_start"),
        ("casing_end_col", "casing_end"), ("head_start_m_col", "head_start_m"), ("head_end_m_col", "head_end_m"),
        ("cap_start_col", "cap_start"), ("cap_end_col", "cap_end"), ("directed_col", "is_directed"), ("driving_col", "has_arrows"),
    ];

    fn from_args(args: &Value) -> ColumnMap {
        ColumnMap(Self::KEYWORDS.iter()
            .filter_map(|(k, own)| args[*k].as_str().filter(|u| !u.is_empty() && u != own).map(|u| (*own, u.to_string())))
            .collect())
    }

    fn kept(own: &str) -> String {
        road::kept(own)
    }

    fn to_engine(&self, table: &mut RoadTable) {
        for (own, user) in &self.0 {
            if table.col(user).is_some() {
                table.rename(own, &Self::kept(own));
                table.rename(user, own);
            }
        }
    }

    fn to_user(&self, sources: &mut [(String, Src)], layers: &mut [Value]) {
        if self.0.is_empty() {
            return;
        }
        for (name, src) in sources.iter_mut() {
            match src {
                // the roads keep every column, with the user's names at the output; a kept one gets its own name back
                Src::Roads(s) => s.names = self.0.clone(),
                // the pieces of `simple` have only the class and the __rs_* marks: the user's names at the output, and a kept column
                // (an __rs_ name in between) goes away there
                Src::Simple(s) => s.names = self.0.clone(),
                // the 3D decks are copies of the roads' properties: the user's names, as the roads
                Src::Json(s) if name == "decks" => {
                    for f in s["data"]["features"].as_array_mut().into_iter().flatten() {
                        if let Some(p) = f["properties"].as_object_mut().filter(|p| !p.contains_key("__rs_casing_slab")) {
                            for (own, user) in &self.0 {
                                if p.contains_key(*own) {
                                    let kept = Self::kept(own);
                                    let name = |k: &String| if k == own { user.clone() } else if *k == kept { own.to_string() } else { k.clone() };
                                    *p = std::mem::take(p).into_iter().map(|(k, v)| (name(&k), v)).collect();
                                }
                            }
                        }
                    }
                }
                Src::Json(s) => {
                    for f in s["data"]["features"].as_array_mut().into_iter().flatten() {
                        if let Some(p) = f["properties"].as_object_mut() {
                            self.0.iter().for_each(|(own, _)| { p.shift_remove(&Self::kept(own)); });
                        }
                    }
                }
            }
        }
        fn gets(v: &mut Value, own: &str, user: &str) {
            match v {
                Value::Array(a) => {
                    if a.len() == 2 && matches!(a[0].as_str(), Some("get" | "has")) && a[1] == own {
                        a[1] = user.into();
                    }
                    a.iter_mut().for_each(|x| gets(x, own, user));
                }
                Value::Object(o) => o.values_mut().for_each(|x| gets(x, own, user)),
                _ => {}
            }
        }
        for l in layers.iter_mut().filter(|l| matches!(l["source"].as_str(), Some("roads" | "simple"))) {
            for (own, user) in &self.0 {
                gets(l, own, user);
            }
        }
    }
}

/// render's data_maxzoom (every GeoJSON source) and data_tolerance (every GeoJSON source that has a tolerance).
fn data_settings(sources: &mut [(String, Src)], args: &Value) {
    let maxzoom = args["data_maxzoom"].as_f64().map(|z| z as i64);
    let tolerance = args["data_tolerance"].as_f64();
    for (_, src) in sources.iter_mut() {
        match src {
            Src::Roads(s) => {
                s.maxzoom = maxzoom.or(s.maxzoom);
                s.tolerance = tolerance.unwrap_or(s.tolerance);
            }
            Src::Simple(s) => {
                s.maxzoom = maxzoom.or(s.maxzoom);
                s.tolerance = tolerance.unwrap_or(s.tolerance);
            }
            Src::Json(s) if s["type"] == "geojson" => {
                if let (Some(t), Some(o)) = (tolerance, s.as_object_mut()) {
                    if o.contains_key("tolerance") {
                        o.insert("tolerance".into(), t.into());
                    }
                }
                if let (Some(z), Some(o)) = (maxzoom, s.as_object_mut()) {
                    o.insert("maxzoom".into(), z.into());
                }
            }
            Src::Json(_) => {}
        }
    }
}

/// render_web._boundary_fc for GeoJSON: a FeatureCollection as it is, a Feature in one, a geometry in a Feature with no properties.
fn boundary_fc(b: &Value) -> Option<Value> {
    match b["type"].as_str() {
        _ if b.is_null() || b == &Value::Bool(false) => None,
        Some("FeatureCollection") => Some(b.clone()),
        Some("Feature") => Some(json!({"type": "FeatureCollection", "features": [b]})),
        _ => Some(json!({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": b}]})),
    }
}

/// The roads as the level solver reads them, in their order (the edge id is the row: compute_levels works on the frame's rows). `cols`:
/// the columns of the class, the layer, the bridge, the tunnel and the junction. A value is the text that the tag rules read (Python's
/// _truthy and int(float(layer)) on the GeoDataFrame's values).
pub fn level_edges(table: &RoadTable, cols: [&str; 5]) -> roadstyle_levels::LevelEdges {
    let [hw, layer, bridge, tunnel, junction] = cols;
    let text = |v: Option<Cell>| -> Option<String> {
        match v?.to_value() {
            Value::Null => None,
            Value::Bool(b) => Some(if b { "1" } else { "0" }.to_string()),
            Value::Number(n) => n.as_f64().filter(|x| !x.is_nan()).map(|_| n.to_string()),
            Value::String(s) => Some(s),
            other => Some(other.to_string()),
        }
    };
    let mut edges = roadstyle_levels::LevelEdges::default();
    for i in 0..table.len() {
        edges.add(0, roadstyle_levels::LevelEdge {
            edge_id: i as i64,
            highway: text(table.get(i, hw)).unwrap_or_default(),
            tunnel: text(table.get(i, tunnel)),
            bridge: text(table.get(i, bridge)),
            layer: text(table.get(i, layer)),
            junction: text(table.get(i, junction)),
            geometry: table.line(i).map_or_else(Vec::new, |c| c.iter().map(|p| (p[0], p[1])).collect()),
        });
    }
    edges
}
