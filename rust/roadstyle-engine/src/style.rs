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
    let (mut ovs, images) = all_overlays(&mut feats, look, features)?;
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
    let mut warnings = std::mem::take(&mut feats.warnings);
    let mut roads = roads::roads_source(feats);
    // render's view_3d: the bridges' extruded decks (_bridge_decks); a casing slab names the user's own `highway` column, whatever highway_col is
    let br = &look.map.bridges;
    let own = (br.heights.is_some() || br.height_col.is_some()).then(|| decks::Own {
        heights: br.heights.as_ref(), id_col: look.map.columns.edge_id.as_deref().unwrap_or("edge_id"), height_col: br.height_col.as_deref() });
    if own.is_some() && !br.decks_3d {
        warnings.push("bridge_heights, bridge_height_col: the page has no 3D bridges (view_3d=False), so the heights do nothing".into());
    }
    // the 3D decks are made in two parts: today's rule writes a complete profile (or the caller gives one: `bridge_profile`), and the maker makes the pieces from it
    let (decks, profile) = if br.decks_3d {
        let (decks, profile) = match &br.profile {
            Some(given) => {
                if own.is_some() {
                    warnings.push("bridge_heights, bridge_height_col: the page has a bridge_profile, so the heights do nothing".into());
                }
                decks::fill_and_make_decks(&roads.roads, &look.deck, &look.model, "highway", given, &mut warnings)?
            }
            None => decks::bridge_decks_and_profile(&roads.roads, &look.deck, &look.model, "highway", own.as_ref(), &mut warnings)?,
        };
        (decks, br.profile_export.then(|| profile.to_value()))
    } else {
        if br.profile.is_some() {
            warnings.push("bridge_profile: the page has no 3D bridges (view_3d=False), so the profile does nothing".into());
        }
        (Vec::new(), None)
    };
    simple.roles = Some(simple::Roles { fills: colors.props.clone(), casing: colors.casing_role });
    simple.colours = (!colors.class_only).then(|| crate::colors::ColourTable::of(&roads.roads, look, &colors.props, colors.casing_role)).map(Box::new);
    let mut half = look_half(look, &roads.roads, &simple, source_features(&slots), !decks.is_empty(), &mut ovs, images, &colors, planned)?;
    if let Some(profile) = profile {
        half.metadata["roadstyle:bridge_profile"] = profile;
    }
    // after the road layers: they attached the features of a layer on the streets and set its groups
    let look_inputs = crate::LookInputs { colors, layers: ovs.iter().filter(|o| o.user.is_none()).map(|o| overlays::LayerFacts {
        name: o.name.clone(), kinds: o.kinds.clone(), height: !o.l["extrude"].is_null(), edge: o.edge, edge_groups: o.edge_groups.clone() }).collect() };
    simple.classes = Some(look.model.classes.clone());     // R8: the road layer reads each feature's class index
    // audit N2 (2026-10-24): stage 1 gives the road-table form for every style (the pieces draw and glow, by their road's row; the road
    // table has the roads); only an export (render's export_inline, export_style: an app with no road table) asks for the roads source
    let export = export(look);
    roads.in_style = export;
    // render's order: the roads, the overlays (_build_overlays), the 3D decks, the pieces
    let mut sources: Vec<(String, Src)> = ovs.into_iter().enumerate().map(|(i, ov)| (format!("ov{i}"), overlay_source(ov))).collect();
    if !decks.is_empty() {
        sources.push(("decks".into(), Src::Json(json!({"type": "geojson", "data": {"type": "FeatureCollection", "features": decks}, "generateId": true}))));
    }
    sources.push(("simple".into(), Src::Simple(simple)));
    if !source_features(&slots).is_empty() {        //: no slots source without slots
        sources.push(("slots".into(), Src::Json(slots_for(slots, export))));
    }
    sources.extend(half.sources);
    let name = name.or_else(|| look.map.output.name.clone()).map_or(Value::Null, Value::from);
    Ok(Parts { name, center, zoom, layers: half.layers, roads, sources, metadata: half.metadata, glyphs: half.glyphs, state: half.state, warnings,
               look_inputs })
}

/// The look half of a style (docs/design/restyle_without_retile.md, D4): the layers, the metadata, the glyphs, the state and the sources that
/// the look adds (the boundary). `style_parts` makes it after the roads and the pieces, and `restyle_layers` makes it for a new look from a
/// held stage 1, so the two give the same style.
pub struct LookHalf {
    pub layers: Vec<Value>,
    pub metadata: Value,
    pub glyphs: Option<Value>,
    pub state: Option<Value>,
    pub sources: Vec<(String, Src)>,
}

#[allow(clippy::too_many_arguments)]
fn look_half(look: &Look, roads: &Roads, simple: &simple::SimpleSource, slots: &[Value], decks: bool, ovs: &mut [overlays::Overlay],
             mut images: Map<String, Value>, colors: &colors::Baked, planned: Option<(&str, Value)>) -> Result<LookHalf, Error> {
    let (mut layers, info) = layers::road_layers(look, roads, simple, slots, decks, ovs, &colors.props, colors.active)?;
    let popups: Map<String, Value> = info.overlays.iter().filter(|o| o["popup"].as_array().is_some_and(|a| !a.is_empty()))
        .filter_map(|o| Some((o["source"].as_str()?.to_string(), o["popup"].clone()))).collect();
    // state "live" (a page with the dashboard, docs/design/rust_library.md "The interaction contract"): the state stays in the expressions,
    // and the style says what the controls show
    let live = look.map.output.state == roadstyle_look::options::State::Live;
    let (contract, state) = if live {
        let st = contract::page_state(look, colors.active, ovs.len());
        (Some((contract::controls(look, roads, info, colors.active)?, st.clone())),
         Some(Value::Object(st.into_iter().map(|(k, v)| (k, json!({"default": v}))).collect())))
    } else { (None, None) };
    let mut glyphs = (look.map.labels.on && !slots.is_empty()).then(|| json!(look.sections.labels.glyphs));
    if glyphs.is_none() && ovs.iter().any(|o| o.kind == "text") {      // _build_overlays: a text overlay needs a font
        glyphs = Some(json!("https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf"));
    }
    let mut sources = Vec::new();
    add_boundary(look, &mut sources, &mut layers);
    // a live style (the dashboard's) has the dark colours too, picked by the global state rs_theme (dark.rs)
    if live {
        let sel = &look.sections.selection;
        let keep: Vec<String> = [Some(sel.select.css()), Some(sel.hover.css()), look.map.interaction.select_color.as_ref().map(|c| c.css()),
                                 look.map.interaction.hover_color.as_ref().map(|c| c.css())].into_iter().flatten().map(String::from).collect();
        crate::dark::layers(&mut layers, &look.sections.dark, &keep);
        crate::dark::images(&mut images, &look.sections.dark)?;
    }
    images.insert(layers::ARROW_IMAGE.into(), look.sections.arrows.image.clone());
    let mut metadata = metadata(look, images, planned, colors.meta.clone(), &layers, contract)?;
    if !popups.is_empty() {
        metadata.insert(roadstyle_model::props::POPUPS.into(), popups.into());
    }
    Ok(LookHalf { layers, metadata: Value::Object(metadata), glyphs, state, sources })
}

/// The look half of the style of `look` over the stage 1 `s` that another look made (docs/design/restyle_without_retile.md, D4): from the
/// roads, the pieces, the slots and the base-map facts that `s` holds, with no read of the roads or the features and no piece made. The sources
/// of `s` stay as they are; the caller checks that the new look makes the same tiles (D2) before it uses the result.
pub fn restyle_layers(s: &crate::sources::Styled, look: &Look) -> Result<LookHalf, Error> {
    let simple = s.sources.iter().find_map(|(k, v)| match v { Src::Simple(x) if k == "simple" => Some(x), _ => None })
        .ok_or_else(|| crate::error::options("restyle: the stage 1 has no pieces (the source `simple`)".to_string()))?;
    let slots = s.sources.iter().find_map(|(k, v)| match v { Src::Json(x) if k == "slots" => Some(source_features(x)), _ => None }).unwrap_or(&[]);
    let decks = s.sources.iter().any(|(k, _)| k == "decks");
    let (mut ovs, images) = overlays::styled_layers(&s.look_inputs.layers, look);
    // the caller's own overlays (render's overlays=), as all_overlays makes them
    let first_user = ovs.len();
    ovs.extend(overlays::user_overlays(&look.map.overlays, ovs.len())?);
    for ov in ovs[first_user..].iter_mut() {
        ov.edge_id_col = look.map.columns.edge_id.clone();
    }
    let planned = ["roadstyle:planner", "roadstyle:planner_skipped"].into_iter().find_map(|k| s.metadata.get(k).map(|v| (k, v.clone())));
    let mut half = look_half(look, &s.roads.roads, simple, slots, decks, &mut ovs, images, &s.look_inputs.colors, planned)?;
    // what `Styled::new` adds to the metadata from the data: the roads' generation and the base-map layers
    for k in [roadstyle_model::props::GENERATION, roadstyle_model::props::BASE_LAYERS] {
        if let Some(v) = s.metadata.get(k) {
            half.metadata[k] = v.clone();
        }
    }
    Ok(half)
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
/// table with no new build; the ramp is the call's cmap (else the palette's data.live_ramp), as 9 colours, and the no-data colour the theme's.
fn live_meta(look: &Look) -> Result<Value, Error> {
    let cmap = look.map.color.cmap.as_ref().map_or_else(|| json!(look.sections.data.live_ramp), |c| serde_json::to_value(c).unwrap_or(Value::Null));
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
    metadata.insert(roadstyle_model::props::CLASSES.into(), json!(look.model.classes));
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
