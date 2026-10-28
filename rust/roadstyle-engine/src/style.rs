//! The parts of a style from roads that are prepared (the roles, the levels): `make_parts`'s second half.

use crate::mark::Mark;
use crate::{camera, boundary_fc, colors, contract, decks, export, features, layers, overlays, planner, roads, simple, slots, source_features};
use crate::{Error, FeatureTable, Parts, Road, Roads, Role, Roles, RoadTable, Row, Src};
use crate::look::Look;
use serde_json::{json, Map, Value};
use std::collections::HashMap;

/// make_parts after the roads are prepared (the roles, the levels).
/// `slots`: the slots source to take as it is (None: made from the roads).
#[allow(clippy::too_many_arguments)]
pub(crate) fn style_parts(table: RoadTable, roles: Roles, solved: Option<Vec<[i16; 4]>>, look: &Look, features: Option<FeatureTable>,
                          planner: Option<Vec<Row>>, name: Option<String>, slots: Option<Value>) -> Result<Parts, Error> {
    let mut feats = Roads::new(table, roles, solved);
    // render's filter_col, else the class role's column
    if let Some(f) = roads::named(&look.map.columns.filter) {
        feats.cls = f.to_string();
    }
    let colors = roads::mark_roads(&mut feats, &look.road, &look.map)?;
    // render's arrows and labels (both on by default): the slots exist only for them
    let (arrows, labels) = (look.map.arrows.on, look.map.labels.on);
    let slots = if let Some(s) = slots { s } else if arrows || labels { slots::slots_source(&feats, &look.slot) }
                else { json!({"type": "geojson", "data": {"type": "FeatureCollection", "features": []}}) };
    let (mut ovs, mut images) = all_overlays(&mut feats, look, features)?;
    let items = line_items(&feats, &mut ovs, look)?;
    let mut simple = simple::simple_source(&feats, look.road.head_m, look.road.bridge_shadow, roads::named(&look.map.columns.width_m), items)?;
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
    // render's view_3d: the bridges' extruded decks (_bridge_decks); a casing slab names the user's own `highway` column, whatever highway_col is
    let decks = if look.map.bridges.decks_3d { decks::bridge_decks(&roads.roads, &look.deck, &look.model, "highway") } else { Vec::new() };
    simple.class_colours = colors.class_only.then(|| crate::colors::ClassColours::of(&look.road, &look.model.classes));
    let (mut layers, info) = layers::road_layers(look, &roads.roads, &simple, source_features(&slots), !decks.is_empty(), &mut ovs,
                                                 &colors.props, colors.active)?;
    simple.classes = Some(look.model.classes.clone());     // R8: the road layer reads each feature's class index
    // audit N2 (2026-10-24): stage 1 gives the road-table form for every style (the pieces draw and glow, by their road's row; the road
    // table has the roads); only an export (render's export_inline, export_style: an app with no road table) asks for the roads source
    let export = export(look);
    roads.in_style = export;
    let popups: Map<String, Value> = info.overlays.iter().filter(|o| o["popup"].as_array().is_some_and(|a| !a.is_empty()))
        .filter_map(|o| Some((o["source"].as_str()?.to_string(), o["popup"].clone()))).collect();
    // state "live" (a page with the dashboard, docs/design/rust_library.md "The interaction contract"): the state stays in the expressions,
    // and the style says what the controls show
    let live = look.map.output.state == roadstyle_look::options::State::Live;
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
    let mut sources: Vec<(String, Src)> = ovs.into_iter().enumerate().map(|(i, ov)| (format!("ov{i}"), overlay_source(ov))).collect();
    if !decks.is_empty() {
        sources.push(("decks".into(), Src::Json(json!({"type": "geojson", "data": {"type": "FeatureCollection", "features": decks}, "generateId": true}))));
    }
    sources.push(("simple".into(), Src::Simple(simple)));
    if !source_features(&slots).is_empty() {        //: no slots source without slots
        sources.push(("slots".into(), Src::Json(slots_for(slots, export))));
    }
    add_boundary(look, &mut sources, &mut layers);
    images.insert("oneway".into(), look.sections.arrows.image.clone());
    let mut metadata = metadata(look, images, planned, colors.meta, &layers, contract)?;
    if !popups.is_empty() {
        metadata.insert(roadstyle_model::props::POPUPS.into(), popups.into());
    }
    let name = name.or_else(|| look.map.output.name.clone()).map_or(Value::Null, Value::from);
    Ok(Parts { name, center, zoom, layers, roads, sources, metadata: Value::Object(metadata), glyphs, state, warnings })
}

/// The base map's overlays (from `features`, the base map's rows), then the caller's own (render's overlays=), and the images of the base map.
fn all_overlays(feats: &mut Roads, look: &Look, features: Option<FeatureTable>) -> Result<(Vec<overlays::Overlay>, Map<String, Value>), Error> {
    let (mut ovs, mut images) = (Vec::new(), Map::new());
    if let Some(f) = features {
        let mut tables = features::feature_tables(&f, look)?;
        drop(f);
        let attached = overlays::edge_attach(&mut tables, feats)?;
        (ovs, images) = overlays::feature_overlays(tables, look, &attached, &mut feats.warnings);
    }
    // each of the caller's overlays knows the roads' id column, for its error
    let first_user = ovs.len();
    ovs.extend(overlays::user_overlays(&look.map.overlays, ovs.len())?);
    for ov in ovs[first_user..].iter_mut() {
        ov.edge_id_col = look.map.columns.edge_id.clone();
    }
    Ok((ovs, images))
}

/// The line items on the edges (an overlay's lines in metres, render's items=): pieces of the one road layer.
fn line_items(feats: &Roads, ovs: &mut [overlays::Overlay], look: &Look) -> Result<Vec<simple::Item>, Error> {
    let mut items = Vec::new();
    if ovs.iter().any(overlays::metre_items) || look.map.items.is_some() {
        let by_id: HashMap<String, Road> = feats.iter().filter_map(|f| f.role(Role::EdgeId).map(|e| (overlays::eid(e), f))).collect();
        for (i, ov) in ovs.iter_mut().enumerate().filter(|(_, o)| overlays::metre_items(o)) {
            overlays::edge_overlay(ov, &by_id)?;
            items.extend(overlays::item_pieces(ov, i, look)?);
        }
        if let Some(it) = &look.map.items {
            let col = look.map.columns.edge_id.as_deref().unwrap_or("edge_id");
            items.extend(overlays::road_items(&it.data, &by_id, col, ovs.len(), look)?);
        }
    }
    Ok(items)
}

/// The source of an overlay.
fn overlay_source(ov: overlays::Overlay) -> Src {
    match ov.data {
        overlays::Data::Table(table) => Src::Features(features::FeatureSource { table: *table, maxzoom: None }),
        overlays::Data::Json(fc) => Src::Json(json!({"type": "geojson", "data": fc, "generateId": true})),
    }
}

/// The slots source for the style: the road's key is each slot's feature id (every slot of a road has it), not a property; only the
/// export keeps the arrow slots' numbers (they are for its thinning).
fn slots_for(mut slots: Value, export: bool) -> Value {
    for f in slots["data"]["features"].as_array_mut().into_iter().flatten() {
        let Some(p) = f["properties"].as_object_mut() else { continue };
        let edge = p.shift_remove(Mark::Edge.name());
        p.shift_remove(Mark::Edge2.name());          // the filter takes the twin from the road table
        if !export {
            p.shift_remove(Mark::SlotArrow.name());
        }
        if let Some(e) = edge {
            f["id"] = e;
        }
    }
    slots
}

/// render's boundary: a dashed outline over the roads (GeoJSON: a geometry, a Feature or a FeatureCollection; the Python binding
/// converts a shapely geometry or a GeoDataFrame).
fn add_boundary(look: &Look, sources: &mut Vec<(String, Src)>, layers: &mut Vec<Value>) {
    if let Some(fc) = look.map.boundary.as_ref().and_then(boundary_fc) {
        sources.push(("boundary".into(), Src::Json(json!({"type": "geojson", "data": fc}))));
        let (r, b) = (&look.sections.roads, &look.sections.boundary);
        layers.push(json!({"id": "boundary", "type": "line", "source": "boundary", "metadata": {"roadstyle:group": "roads"},
                           "layout": {"line-cap": r.cap, "line-join": r.join},
                           "paint": {"line-color": b.color, "line-width": b.width, "line-opacity": b.opacity, "line-dasharray": b.dash}}));
    }
}

/// The export's page metadata: the road popup's fields, the hover tooltip and the hover delay (roadstyle:interaction).
/// render's road_popup: true (or not given) the default fields, a list those fields, "panel" the default fields in the side panel,
/// another text every column (null), false no popup; road_tooltip, else none.
fn interaction_meta(look: &Look) -> Value {
    use roadstyle_look::options::{Popup, Tooltip};
    let it = &look.sections.interaction;
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
    json!({"popup": popup, "tooltip": tooltip, "hover_delay_ms": it.hover_delay_ms})
}

/// R22, live data: the feature states that the road layer reads, so a page's dashboard (rs.setData) colours and sizes the roads from a
/// table with no new build; the ramp is the call's cmap (else viridis), as 9 colours, and the no-data colour the theme's.
fn live_meta(look: &Look) -> Result<Value, Error> {
    let cmap = look.map.color.cmap.as_ref().map_or_else(|| json!("viridis"), |c| serde_json::to_value(c).unwrap_or(Value::Null));
    let ramp = colors::Ramp::new(&cmap)?;
    Ok(json!({"color": layers::LIVE_COLOR, "width": layers::LIVE_WIDTH, "types": {layers::LIVE_COLOR: "color", layers::LIVE_WIDTH: "factor"},
              "ramp": ramp.stops(9), "nodata": look.sections.data.nodata}))
}

/// The style's metadata. `contract`: the page's controls and state (a live page).
fn metadata(look: &Look, images: Map<String, Value>, planned: Option<(&str, Value)>, color_options: Vec<Value>, layers: &[Value],
            contract: Option<(Value, Map<String, Value>)>) -> Result<Map<String, Value>, Error> {
    let mut metadata = Map::new();
    metadata.insert("roadstyle:interaction".into(), interaction_meta(look));
    metadata.insert("roadstyle:images".into(), Value::Object(images));
    if let Some((k, v)) = planned {
        metadata.insert(k.into(), v);
    }
    // the legend data of a data-coloured map, as the page's COLOR_OPTIONS
    if !color_options.is_empty() {
        metadata.insert("roadstyle:color_options".into(), Value::Array(color_options));
    }
    if look.map.output.live_data {
        metadata.insert("roadstyle:live".into(), live_meta(look)?);
    }
    // audit N7, R7: the road roles and the pick layers from the final layers, in every style, so that a host's dashboard finds and picks
    // the roads with no contract too (contract::describe; tiled_style writes them again for the tiles)
    let pick = contract::pick_layers(layers);
    metadata.insert("roadstyle:sources".into(), contract::roles(layers));
    match contract {
        None => {
            metadata.insert("roadstyle:controls".into(), json!({"pick": pick}));
        }
        Some((mut controls, st)) => {
            controls["pick"] = pick;
            metadata.insert("roadstyle:arrows".into(), contract::arrow_kind(layers));
            metadata.insert("roadstyle:contract".into(), json!(contract::CONTRACT));
            metadata.insert("roadstyle:state".into(), Value::Object(st));
            metadata.insert("roadstyle:controls".into(), controls);
        }
    }
    Ok(metadata)
}
