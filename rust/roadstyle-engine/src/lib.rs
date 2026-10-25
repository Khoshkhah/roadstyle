//! roadstyle's rendering engine (docs/design/rust_library.md, "The crates"): the style of a map from the roads, the look, the
//! data-driven paint, the legend data and the base-map layers. The vector tiles are in roadstyle-tiles, the levels in roadstyle-levels.

// Ported numeric code: index loops over parallel arrays and tuple types of the Python stages read as they are in Python.
#![allow(clippy::needless_range_loop, clippy::type_complexity)]

pub mod colors;
pub mod contract;
pub mod decks;
pub mod draw;
pub mod error;
pub mod export_look;
pub mod features;
pub mod layers;
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
pub use roadstyle_model::{feature_table, geom, mark, props, table, Cell, RoadTable, Row};
pub use roadstyle_model::feature_table::FeatureTable;
pub use error::{Error, Limit, Unsupported};

/// A number that the caller gave (a map option), as JSON: a whole number as an integer, as the caller's keyword wrote it (`1` stays `1` in
/// the outputs, as in Python); NaN or an infinity: null.
pub(crate) fn given(v: f64) -> Value {
    if v.fract() == 0.0 && v.abs() < 9.0e15 { Value::from(v as i64) } else { serde_json::Number::from_f64(v).map_or(Value::Null, Value::Number) }
}
pub use road::{Road, Roads};
pub use roadstyle_look::{self as look, Look};
pub(crate) use roadstyle_model::obj;

use roadstyle_model::mark::Mark;
use serde_json::{json, Value};

/// The most roads of one map: a browser keeps the module's memory under 4 GB. Tartu (63,965 roads) peaks at 1.13 GB natively (2.13 GB
/// before the typed sources, docs/design/rust_engine.md), and the wasm module used 0.65 to 0.77 times the native peak in the earlier
/// measurements: about 14 KB a road, so 200,000 roads are about 2.8 GB.
/// ponytail: an estimate from Tartu only; measure a larger area in a browser before the limit goes higher.
pub const MAX_ROADS: usize = 200_000;

/// A source of the style: the roads, the simple pieces (both typed, written from the roads), a base-map layer (typed, audit R10) or a
/// GeoJSON source as JSON (a caller's overlays, slots, decks).
pub enum Src {
    Roads(road::RoadsSource),
    Simple(simple::SimpleSource),
    Features(features::FeatureSource),
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
    /// the warnings of the stages (Python's warnings.warn in render_web)
    pub warnings: Vec<String>,
}

/// The style's layers and sources: the roads ("roads", "simple", "slots") and, with `features` (the base map's rows as the worker's SQL
/// writes them, `read::read_feature_table`), the base map ("ov<i>"). `look`: look.json (the resolved look); `table`: the roads (roadstyle-io reads them from the
/// GeoParquet of tools/make_spike_fixture.py or the worker's SQL); `planner`: the route planner's rows.
pub fn make_parts(mut table: RoadTable, look: &Look, features: Option<FeatureTable>, planner: Option<Vec<Row>>, name: Option<String>) -> Result<Parts, Error> {
    if table.len() > MAX_ROADS {
        return Err(Error::Limit { what: Limit::Roads, found: table.len(), max: MAX_ROADS });
    }
    ColumnMap::of(&look.map.columns).to_engine(&mut table);
    let mut warnings = Vec::new();
    let levels = compute_levels(&mut table, &look.map, look.road.head_m, &mut warnings)?;
    let mut parts = style_parts(table, levels, look, features, planner, name)?;
    parts.warnings.splice(0..0, warnings);
    Ok(parts)
}

/// The parts of another palette of the same call (a view's palette, palettes.rs): the roads of `s` as they were before their marks
/// (their columns in the engine's names, their levels solved), with the look `look` (the same keywords, another palette). No base map
/// and no route planner, as a page's views have none.
pub fn restyle(s: &sources::Sources, look: &Look) -> Result<sources::Sources, Error> {
    Ok(sources::Sources::new(style_parts(s.roads.roads.table.clone(), s.roads.roads.solved.clone(), look, None, None, None)?))
}

/// make_parts after the roads are prepared (the engine's column names, the levels).
fn style_parts(table: RoadTable, solved: Option<Vec<[i16; 4]>>, look: &Look, features: Option<FeatureTable>, planner: Option<Vec<Row>>,
               name: Option<String>) -> Result<Parts, Error> {
    let cols = ColumnMap::of(&look.map.columns);
    // render's filter_col: in the engine's names (a keyword's column has the engine's name; a column with an engine name is kept aside)
    let fcol = roads::named(&look.map.columns.filter).map_or_else(|| "highway".to_string(), |f| {
        cols.0.iter().find(|(_, user)| user == f).map(|(own, _)| own.to_string())
            .or_else(|| cols.0.iter().find(|(own, _)| *own == f).map(|(own, _)| ColumnMap::kept(own)))
            .unwrap_or_else(|| f.to_string())
    });
    let mut feats = Roads::new(table);
    feats.solved = solved;
    feats.cls = fcol;
    let colors = roads::mark_roads(&mut feats, &look.road, &look.map)?;
    let width_col = roads::named(&look.map.columns.width_m);
    // render's arrows and labels (both on by default): the slots exist only for them
    let (arrows, labels) = (look.map.arrows.on, look.map.labels.on);
    let slots = if arrows || labels { slots::slots_source(&feats, &look.slot) }
                else { json!({"type": "geojson", "data": {"type": "FeatureCollection", "features": []}}) };
    let mut ovs = Vec::new();
    let mut images = serde_json::Map::new();
    if let Some(f) = features {
        let mut tables = features::feature_tables(&f, look)?;
        drop(f);
        let attached = overlays::edge_attach(&mut tables, &feats)?;
        (ovs, images) = overlays::feature_overlays(tables, look, &attached, &mut feats.warnings);
    }
    // render's overlays=: the caller's own, after the base map's (each knows the roads' id column, for its error)
    let first_user = ovs.len();
    ovs.extend(overlays::user_overlays(&look.map.overlays, ovs.len())?);
    for ov in ovs[first_user..].iter_mut() {
        ov.edge_id_col = look.map.columns.edge_id.clone();
    }
    // render's simple=False (the full look: a layer for each drawing position) is the Python engine's only (plan decision 2)
    if look.other.get("simple") == Some(&Value::Bool(false)) {
        return Err(Error::Unsupported(Unsupported::FullLook));
    }
    // the line items on the edges (an overlay's lines in metres, render's items=): pieces of the one road layer
    let mut items = Vec::new();
    if ovs.iter().any(overlays::metre_items) || look.map.items.is_some() {
        let by_id: std::collections::HashMap<String, Road> =
            feats.iter().filter_map(|f| f.get("edge_id").map(|e| (overlays::eid(e), f))).collect();
        for (i, ov) in ovs.iter_mut().enumerate().filter(|(_, o)| overlays::metre_items(o)) {
            overlays::edge_overlay(ov, &by_id)?;
            items.extend(overlays::item_pieces(ov, i, look)?);
        }
        if let Some(it) = &look.map.items {
            let col = look.map.columns.edge_id.as_deref().unwrap_or("edge_id");
            items.extend(overlays::road_items(&it.data, &by_id, col, ovs.len(), look)?);
        }
    }
    let mut simple = simple::simple_source(&feats, look.road.head_m, look.road.bridge_shadow, width_col, items)?;
    // everything that reads the roads is done before this: the roads source takes them
    // export_inline(planner=True): the route planner's graphs, or the number of roads past the limit
    let planned = match planner {
        Some(_) if feats.len() > planner::PLANNER_MAX_EDGES => Some(("roadstyle:planner_skipped", json!(feats.len()))),
        Some(p) => Some(("roadstyle:planner", planner::planner_data(&feats, p)?)),
        None => None,
    };
    let (center, zoom) = camera(&feats);
    let warnings = std::mem::take(&mut feats.warnings);
    let mut roads = roads::roads_source(feats);
    // render's view_3d: the bridges' extruded decks (_bridge_decks)
    let decks = if look.map.bridges.decks_3d {
        // a casing slab names the user's own `highway` column (Python's props.get("highway")): kept aside when highway_col is another
        let hw = if cols.0.iter().any(|(own, _)| *own == "highway") { ColumnMap::kept("highway") } else { "highway".into() };
        decks::bridge_decks(&roads.roads, &look.deck, &look.model, &hw)
    } else { Vec::new() };
    let (layers, info) = layers::road_layers(look, &roads.roads, &simple, source_features(&slots), !decks.is_empty(), &mut ovs,
                                             &colors.props, colors.active)?;
    simple.classes = Some(look.model.classes.clone());     // R8: the road layer reads each feature's class index
    // state "live" (a page with the dashboard, docs/design/rust_library.md "The interaction contract"): the state stays in the expressions,
    // and the style says what the controls show
    let live = look.map.output.state == roadstyle_look::options::State::Live;
    // audit N2 (2026-10-24): stage 1 gives the road-table form for every style (the pieces draw and glow, by their road's row; the road
    // table has the roads); only an export (render's export_inline, export_style: an app with no road table) asks for the roads source
    let export = export(look);
    (roads.in_style, simple.promote) = (export, true);
    let (contract, state) = if live {
        let st = contract::page_state(look, colors.active, ovs.len());
        (Some((contract::controls(look, &roads.roads, info, colors.active)?, st.clone())),
         Some(Value::Object(st.into_iter().map(|(k, v)| (k, json!({"default": v}))).collect())))
    } else { (None, None) };
    let mut glyphs = (labels && !source_features(&slots).is_empty()).then(|| json!(look.sections.labels.glyphs));
    if glyphs.is_none() && ovs.iter().any(|o| o.kind == "text") {      // _build_overlays: a text overlay needs a font
        glyphs = Some(json!("https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf"));
    }
    // render's order: the roads, the overlays (_build_overlays), the 3D decks, the pieces
    let mut sources = vec![("roads".to_string(), Src::Roads(roads))];
    for (i, ov) in ovs.into_iter().enumerate() {
        let src = match ov.data {
            overlays::Data::Table(table) => Src::Features(features::FeatureSource { table: *table, maxzoom: None }),
            overlays::Data::Json(fc) => {
                let mut s = serde_json::Map::new();
                s.insert("type".into(), "geojson".into());
                s.insert("data".into(), fc);
                s.insert("generateId".into(), true.into());
                Src::Json(Value::Object(s))
            }
        };
        sources.push((format!("ov{i}"), src));
    }
    if !decks.is_empty() {
        sources.push(("decks".into(), Src::Json(json!({"type": "geojson", "data": {"type": "FeatureCollection", "features": decks}, "generateId": true}))));
    }
    sources.push(("simple".into(), Src::Simple(simple)));
    if !source_features(&slots).is_empty() {        // as Python: no slots source without slots
        let mut slots = slots;
        if !export {        // the arrow slots' numbers are for the export's thinning
            for f in slots["data"]["features"].as_array_mut().into_iter().flatten() {
                f["properties"].as_object_mut().map(|p| p.shift_remove(Mark::SlotArrow.name()));
            }
        }
        sources.push(("slots".into(), Src::Json(slots)));
    }
    // render's boundary: a dashed outline over the roads (GeoJSON: a geometry, a Feature or a FeatureCollection; the Python binding
    // converts a shapely geometry or a GeoDataFrame)
    let mut layers = layers;
    if let Some(fc) = look.map.boundary.as_ref().and_then(boundary_fc) {
        sources.push(("boundary".into(), Src::Json(json!({"type": "geojson", "data": fc}))));
        let (r, b) = (&look.sections.roads, &look.sections.boundary);
        layers.push(json!({"id": "boundary", "type": "line", "source": "boundary", "metadata": {"roadstyle:group": "roads"},
                           "layout": {"line-cap": r.cap, "line-join": r.join},
                           "paint": {"line-color": b.color, "line-width": b.width, "line-opacity": b.opacity, "line-dasharray": b.dash}}));
    }
    images.insert("oneway".into(), look.sections.arrows.image.clone());
    let mut metadata = serde_json::Map::new();
    // the export's page metadata: the road popup's fields, the hover tooltip and the hover delay (roadstyle:interaction)
    let it = &look.sections.interaction;
    // render's road_popup: true (or not given) the default fields, a list those fields, "panel" the default fields in the side panel,
    // another text every column (null), false no popup; road_tooltip, else the folium name tooltip, else none
    use roadstyle_look::options::{Popup, Tooltip};
    let popup = match &look.map.interaction.popup {
        Popup::Off => json!(false),
        Popup::Fields(a) => json!(a),
        Popup::All => Value::Null,
        Popup::Default | Popup::Panel => json!(it.popup),
    };
    let tooltip = match &look.map.interaction.tooltip {
        Some(Tooltip::All) => json!(true),
        Some(Tooltip::Fields(f)) => json!(f),
        None => json!(false),
    };
    // the look's hover delay: render's hover_delay_ms is a page key (the page's options, a host's own)
    metadata.insert("roadstyle:interaction".into(), json!({"popup": popup, "tooltip": tooltip, "hover_delay_ms": it.hover_delay_ms}));
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
    if look.map.output.live_data {
        let cmap = look.map.color.cmap.as_ref().map_or_else(|| json!("viridis"), |c| serde_json::to_value(c).unwrap_or(Value::Null));
        let ramp = colors::Ramp::new(&cmap)?;
        metadata.insert("roadstyle:live".into(), json!({
            "color": layers::LIVE_COLOR, "width": layers::LIVE_WIDTH, "types": {layers::LIVE_COLOR: "color", layers::LIVE_WIDTH: "factor"},
            "ramp": ramp.stops(9), "nodata": look.sections.data.nodata}));
    }
    // audit N7, R7: the road roles and the pick layers from the final layers, in every style, so that a host's dashboard finds and picks
    // the roads with no contract too (contract::describe; tiled_style writes them again for the tiles)
    let pick = contract::pick_layers(&layers);
    if contract.is_none() {
        metadata.insert("roadstyle:sources".into(), contract::roles(&layers));
        metadata.insert("roadstyle:controls".into(), json!({"pick": pick}));
    }
    if let Some((mut controls, st)) = contract {
        controls["pick"] = pick;
        metadata.insert("roadstyle:sources".into(), contract::roles(&layers));
        metadata.insert("roadstyle:arrows".into(), contract::arrow_kind(&layers));
        metadata.insert("roadstyle:contract".into(), json!(contract::CONTRACT));
        metadata.insert("roadstyle:state".into(), Value::Object(st));
        metadata.insert("roadstyle:controls".into(), controls);
    }
    let name = name.or_else(|| look.map.output.name.clone()).map_or(Value::Null, Value::from);
    data_settings(&mut sources, &look.other);
    cols.to_user(&mut sources, &mut layers);
    Ok(Parts { name, center, zoom, layers, sources, metadata: Value::Object(metadata), glyphs, state, warnings })
}

/// The style as one JSON text, with each source's GeoJSON in it (roadstyle's export_inline): stage 1 (`sources::Sources`), written.
pub fn make_style(table: RoadTable, look: &Look, features: Option<FeatureTable>, planner: Option<Vec<Row>>, name: Option<String>) -> Result<String, Error> {
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
                                            in_style: r.in_style, read: None };
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

/// render's level step. The drawing positions come from, in this order: the columns that `casing_level_col` / `fill_level_col` name;
/// else the contract columns `casing_level` / `fill_level` of the input (duckOSM's stored levels: an input column of the name is the
/// level input); else `compute_levels(method="solve")` with its defaults (render_web.render), on the roads in their order. The keyword
/// `levels` (roads_sql.js makeRoads): "tags" computes them with the tags rule and "solve" with the solver, whatever the input has;
/// `{edge_hash, n_edges}` (edge_levels_meta) checks that the stored levels are for these edges. Computed, they are not written into the
/// table: they come back (casing_start, casing_level, casing_end, fill_level for each road), and the roads give them under the contract
/// names (`Roads::solved`). A user column with a contract name, when the levels are computed, is kept aside as `__rs_kept_<name>`, with
/// a warning.
fn compute_levels(table: &mut RoadTable, m: &roadstyle_look::options::MapOptions, head_m: f64, warnings: &mut Vec<String>) -> Result<Option<Vec<[i16; 4]>>, Error> {
    use roadstyle_look::options::Levels;
    if let Levels::Stored { edge_hash, n_edges } = &m.levels {
        let ids = (0..table.len()).map(|i| match table.get(i, "edge_id").map(Cell::to_value) {
            Some(Value::Number(n)) => n.as_i64(),
            Some(Value::String(s)) => s.parse().ok(),
            _ => None,
        }).collect::<Option<Vec<i64>>>().ok_or_else(|| error::column("edge_id", "levels: an edge_id that is not a whole number"))?;
        if ids.len() as u64 != *n_edges || roadstyle_levels::edge_hash(&ids) != *edge_hash {
            return Err(error::data(format!("the edges are not the edges the stored levels were solved for ({} given, {n_edges} stored, or other \
                                edge_id values): run duckosm levels again", ids.len())));
        }
    }
    let (tags, forced) = (m.levels == Levels::Tags, matches!(m.levels, Levels::Tags | Levels::Solve));
    let contract = [Mark::CasingLevelColumn, Mark::FillLevelColumn].iter().any(|m| table.col(m.name()).is_some());
    if m.levels == Levels::Given || (!forced && contract) {
        return Ok(None);
    }
    const COLUMNS: [Mark; 4] = [Mark::CasingStartColumn, Mark::CasingLevelColumn, Mark::CasingEndColumn, Mark::FillLevelColumn];
    let present: Vec<Mark> = COLUMNS.into_iter().filter(|m| table.col(m.name()).is_some()).collect();
    for m in present {
        table.rename(m.name(), &road::kept(m.name()));
        warnings.push(format!("the column {} is not the levels (levels={}): it is kept as {}", m.name(), if tags { "tags" } else { "solve" },
                              road::kept(m.name())));
    }
    // the engine's own names: ColumnMap gave the user's columns these names before this step
    let edges = level_edges(table, ["highway", "layer", "bridge", "tunnel", "junction", "", ""]);
    let method = if tags { roadstyle_levels::Method::Tags } else { roadstyle_levels::Method::Solve };
    let Some(levels) = roadstyle_levels::levels(&edges, &roadstyle_levels::Options { method, head_m, ..Default::default() })? else { return Ok(None) };
    // one row for each edge, in the edges' order (the edge id is the row)
    if levels.rows.len() != table.len() || levels.rows.iter().enumerate().any(|(i, r)| r.edge_id != i as i64) {
        return Err(error::data(format!("compute_levels: {} rows for {} roads, not one for each road in its order", levels.rows.len(), table.len())));
    }
    let small = |v: i64| v.clamp(i16::MIN.into(), i16::MAX.into()) as i16;
    Ok(Some(levels.rows.iter().map(|r| [r.casing_start, r.casing_level, r.casing_end, r.fill_level].map(small)).collect()))
}

/// The column keywords of render (highway_col, tunnel_col, ...): the engine reads its own names (highway, tunnel, ...), so a user's
/// column gets the engine's name on the way in and its own name back on the way out, in the data and the expressions of the sources
/// `roads` and `simple`. As in Python, the slots and their layers keep `highway`, and the popup fields stay as given. A column that has
/// the engine's name but is not the named one is kept under another name in between, and gets its name back.
struct ColumnMap(Vec<(&'static str, String)>);

impl ColumnMap {
    /// The columns that the caller names with another name than the engine's (MapOptions' columns).
    fn of(c: &roadstyle_look::options::Columns) -> ColumnMap {
        let l = c.levels.clone().unwrap_or_default();
        let given: [(&'static str, Option<&String>); 15] = [
            ("highway", Some(&c.class)), ("tunnel", c.tunnel.as_ref()), ("bridge", c.bridge.as_ref()), ("layer", c.layer.as_ref()),
            ("edge_id", c.edge_id.as_ref()), ("casing_level", l.casing_level.as_ref()), ("fill_level", l.fill_level.as_ref()),
            ("casing_start", l.casing_start.as_ref()), ("casing_end", l.casing_end.as_ref()), ("head_start_m", l.head_start_m.as_ref()),
            ("head_end_m", l.head_end_m.as_ref()), ("cap_start", l.cap_start.as_ref()), ("cap_end", l.cap_end.as_ref()),
            ("is_directed", c.directed.as_ref()), ("has_arrows", c.driving.as_ref()),
        ];
        ColumnMap(given.into_iter().filter_map(|(own, u)| u.filter(|u| !u.is_empty() && *u != own).map(|u| (own, u.clone()))).collect())
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
                        if let Some(p) = f["properties"].as_object_mut().filter(|p| !p.contains_key(Mark::CasingSlab.name())) {
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
                // the base map's layers have no road column
                Src::Features(_) => {}
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

/// render's export (export_inline, export_style: a style for an app with no road table). A key of the style writer: read from the look's
/// `other` until T4 moves it to SourceMode::Inline.
pub(crate) fn export(look: &Look) -> bool {
    look.other.get("export") == Some(&Value::Bool(true))
}

/// render's data_maxzoom (every GeoJSON source) and data_tolerance (every GeoJSON source that has a tolerance). Keys of the style writer:
/// read from the look's `other` until T4 moves them to SourceMode::Inline.
fn data_settings(sources: &mut [(String, Src)], other: &serde_json::Map<String, Value>) {
    let maxzoom = other.get("data_maxzoom").and_then(Value::as_f64).map(|z| z as i64);
    let tolerance = other.get("data_tolerance").and_then(Value::as_f64);
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
            Src::Features(s) => s.maxzoom = maxzoom.or(s.maxzoom),
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
/// the columns of the class, the layer, the bridge, the tunnel, the junction, the band and the order ("" for none). A value is the text
/// that the tag rules read (Python's _truthy and int(float(layer)) on the GeoDataFrame's values).
pub fn level_edges(table: &RoadTable, cols: [&str; 7]) -> roadstyle_levels::LevelEdges {
    let [hw, layer, bridge, tunnel, junction, band, order] = cols;
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
            band: text(table.get(i, band)),
            order: text(table.get(i, order)).and_then(|s| s.trim().parse::<f64>().ok()).filter(|x| !x.is_nan()),
            geometry: table.line(i).map_or_else(Vec::new, |c| c.iter().map(|p| (p[0], p[1])).collect()),
        });
    }
    edges
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Two roads with whole-number columns of these names.
    fn table(names: &[&str]) -> RoadTable {
        let mut lines = table::Lines::default();
        lines.push(Some(&[[0.0, 0.0], [1.0, 0.0]]));
        lines.push(Some(&[[0.0, 1.0], [1.0, 1.0]]));
        let mut t = RoadTable::new(Vec::new(), Vec::new(), lines).unwrap();
        for (i, n) in names.iter().enumerate() {
            t.set_ints(n, vec![i as i64, 10 + i as i64]);
        }
        t
    }

    #[test]
    fn column_map_gives_the_engine_its_names_and_the_user_theirs() {
        // only a column keyword with another name than the engine's own: tunnel_col "tunnel" and an empty one change nothing
        let args = json!({"highway_col": "fclass", "tunnel_col": "tunnel", "edge_id_col": "", "cap_start_col": "cs"});
        let m = ColumnMap::of(&roadstyle_look::options::MapOptions::from_args(&args).unwrap().0.columns);
        assert_eq!(m.0, vec![("highway", "fclass".to_string()), ("cap_start", "cs".to_string())]);
        // the user's column gets the engine's name; a column that already has it is kept under another name in between
        let mut t = table(&["highway", "fclass"]);
        m.to_engine(&mut t);
        assert_eq!(t.names(), [ColumnMap::kept("highway"), "highway".to_string()]);
        assert_eq!(t.get(0, "highway").map(|c| c.to_value()), Some(json!(1)), "the user's fclass is the engine's highway");
        // a named column that the table does not have: nothing changes
        let mut t = table(&["highway"]);
        m.to_engine(&mut t);
        assert_eq!(t.names(), ["highway".to_string()]);
        // the expressions of the roads and simple layers read the user's names again; another source's layer keeps its names
        let mut layers = vec![json!({"id": "a", "source": "roads", "filter": ["==", ["get", "highway"], "primary"],
                                     "paint": {"line-color": ["case", ["has", "cap_start"], "#000000", "#ffffff"]}}),
                              json!({"id": "b", "source": "slots", "filter": ["get", "highway"]})];
        m.to_user(&mut [], &mut layers);
        assert_eq!(layers[0]["filter"], json!(["==", ["get", "fclass"], "primary"]));
        assert_eq!(layers[0]["paint"]["line-color"][1], json!(["has", "cs"]));
        assert_eq!(layers[1]["filter"], json!(["get", "highway"]));
    }
}
