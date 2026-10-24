//! The output side of the interaction contract (docs/design/rust_library.md, "The interaction contract"): what a page's dashboard reads
//! from a style made with `state: "live"`. `roadstyle:state` has each global state's start value (render_web: style["state"]),
//! `roadstyle:controls` the options of rsDashboard that come from the style (render_web.render's `page`: the filter panel, the overlays,
//! the tunnel look, the road fill, the arrows' rules, ...). The page's own options (the base maps, Street View, the panel) are not here.

use crate::layers::{Model, PageInfo};
use crate::road::{Road, Roads};
use roadstyle_model::Cell;
use serde_json::{json, Map, Value};

/// The version of the contract (metadata roadstyle:contract).
pub const CONTRACT: i64 = 1;

/// _ACCESS: the access kinds and the text of their row in the filter panel.
const ACCESS: [(&str, &str); 4] = [("private", "Private roads"), ("bus", "Bus lanes"), ("pedestrian", "Pedestrian streets"), ("delivery", "Delivery only")];

fn merged(a: &Value, b: &Value) -> Map<String, Value> {
    let mut m = a.as_object().cloned().unwrap_or_default();
    m.extend(b.as_object().into_iter().flatten().map(|(k, v)| (k.clone(), v.clone())));
    m
}

/// The page's global state and the start value of each (render_web: style["state"]), in Python's order. `active`: the colour option.
pub fn page_state(look: &crate::Look, active: usize, n_overlays: usize) -> Map<String, Value> {
    let (th, cfg) = (&look.theme, &look.config);
    let towards = cfg["tunnel_towards"].as_object().cloned().unwrap_or_default();
    let toward = &cfg["tunnel_toward"];
    let colour = toward.as_str().and_then(|t| towards.get(t)).cloned().unwrap_or_else(|| toward.clone());
    let pair = cfg["tunnel_palette"].as_str().and_then(|p| cfg["tunnel_palettes"].get(p)).filter(|v| !v.is_null()).cloned();
    let dash = &th["tunnels"]["to"]["dash"];
    let ratio: Vec<f64> = cfg["tunnel_casing_dash"].as_array().filter(|a| !a.is_empty()).map(|a| a.iter().filter_map(Value::as_f64).collect())
        .unwrap_or_else(|| vec![1.0, 1.0]);
    // render's road_fill: the start value of rs_fill_on (off: each fill's opacity is 0)
    let road_fill = !matches!(look.args["road_fill"], Value::Bool(false));
    let mut state = json!({"rs_co": active, "rs_top": [], "rs_fill_on": road_fill,
        "rs_tun_strength": cfg["tunnel_strength"].as_f64().unwrap_or(0.0), "rs_tun_toward": colour, "rs_tun_two": pair.is_some(),
        "rs_tun_c0": pair.as_ref().map_or(dash, |p| &p[0]), "rs_tun_c1": pair.as_ref().map_or(dash, |p| &p[1]), "rs_tun_ratio": ratio})
        .as_object().unwrap().clone();
    for i in 0..n_overlays {
        state.insert(format!("rs_ov_{i}"), json!({}));
    }
    // a palette made in code has no name
    let palette = look.palette.as_str();
    state.insert("rs_palette".into(), palette.into());
    state
}

/// The filter panel (render_web: `flt`): the classes present, most important first, a swatch for each (a road of the class that is not a
/// restricted one), the access kinds with their counts (access_col), and whether there are bridges and tunnels.
fn filter_panel(look: &crate::Look, roads: &Roads, m: &Model) -> Value {
    let args = &look.args;
    let fb_fill = &look.theme["roads"]["fallback"]["fill"];
    let col = args["filter_col"].as_str().or_else(|| args["highway_col"].as_str()).filter(|c| !c.is_empty()).unwrap_or("highway");
    let (mut classes, mut seen, mut swatches, mut by_access) = (Vec::<String>::new(), std::collections::HashSet::new(), Map::new(),
                                                               std::collections::HashSet::new());
    let restricted = |p: Road| p.get("__rs_access").map(Cell::to_value).is_some_and(|a| !a.is_null() && a != false && a != "");
    for p in roads.iter() {
        let cls = p.cls();
        let Some(c) = cls.as_str().filter(|c| !c.is_empty()) else { continue };
        if !seen.contains(c) || (by_access.contains(c) && !restricted(p)) {
            if !seen.contains(c) {
                classes.push(c.to_string());
            }
            seen.insert(c.to_string());
            by_access.remove(c);
            if restricted(p) {
                by_access.insert(c.to_string());
            }
            swatches.insert(c.into(), p.get("__rs_fill").filter(|v| crate::layers::py_truth(*v)).map_or_else(|| fb_fill.clone(), Cell::to_value));
        }
    }
    classes.sort_by(|a, b| m.z_of(b).total_cmp(&m.z_of(a)).then_with(|| a.cmp(b)));
    let mut access = Vec::new();
    if args["access_col"].as_str().is_some_and(|c| !c.is_empty()) {
        let n = |k: &str| roads.iter().filter(|f| f.get("__rs_access").and_then(Cell::as_str) == Some(k)).count();
        access = ACCESS.iter().filter(|(k, _)| n(k) > 0).map(|(k, label)| json!([k, look.theme["access"][*k], label, n(k)])).collect();
        // driving's pedestrian streets that cars may not use have their own row: where no usable road is of the class, a class row would
        // be a second switch for them
        if n("pedestrian") > 0 && classes.iter().any(|c| c == "pedestrian")
            && !roads.iter().any(|f| !restricted(f) && f.cls().as_str() == Some("pedestrian")) {
            classes.retain(|c| c != "pedestrian");
        }
    }
    let lvl = |f: Road| f.get("lvl").and_then(Cell::as_f64).unwrap_or(0.0);
    json!({"on": args["filter_control"] != false && !classes.is_empty(), "col": col, "classes": classes, "access": access, "swatches": swatches,
           "bridges": roads.iter().any(|f| lvl(f) > 0.0), "tunnels": roads.iter().any(|f| lvl(f) < 0.0)})
}

/// roadstyle:sources: each road role of the page (a source's name in the GeoJSON way, a tile layer's in the tile way), in the order of
/// its first layer, with its source and its source layer (null for a GeoJSON source); render_web._roles. The overlays are not roles
/// (their own list: `overlays`), and the boundary is not a road (R7).
pub fn roles(layers: &[Value]) -> Value {
    const ROLES: [&str; 9] = ["roads", "simple", "slots", "arrows", "decks", "shadows", "casings", "halves", "ends"];
    let mut out = Map::new();
    for l in layers {
        let (src, sl) = (l["source"].as_str(), l["source-layer"].as_str());
        let Some(role) = sl.or(src) else { continue };
        if ROLES.contains(&role) && !out.contains_key(role) {
            out.insert(role.into(), json!({"source": src, "layer": sl}));
        }
    }
    Value::Object(out)
}

/// The one writer of what the dashboard reads about a style's layers (audit N7): `roadstyle:sources` (`roles`), `roadstyle:arrows`
/// (`arrow_kind`) and the controls' `pick` (`pick_layers`) from its final layers, in a style with the interaction contract. Stage 2
/// calls it again on the tiled style.
pub fn describe(style: &mut Value) {
    if style["metadata"]["roadstyle:contract"].is_null() {
        return;
    }
    let layers = style["layers"].as_array().cloned().unwrap_or_default();
    style["metadata"]["roadstyle:sources"] = roles(&layers);
    style["metadata"]["roadstyle:arrows"] = arrow_kind(&layers);
    if style["metadata"]["roadstyle:controls"].is_object() {
        style["metadata"]["roadstyle:controls"]["pick"] = pick_layers(&layers);
    }
}

/// The layers that a road is picked on (clicked, hovered), render_web._pick_layers: the road layer of simple mode (the full look: its
/// fill layers, not the halves'), and the 3D decks' tops (not their casing, roads-deck-casing). A caller's items are in `overlays`.
pub fn pick_layers(layers: &[Value]) -> Value {
    let fill = |id: &str| ["roads-fill", "roads-low-fill", "roads-high-fill", "roads-bridge-fill"].iter().any(|p| id.starts_with(p));
    let simple = layers.iter().any(|l| l["id"] == "roads-simple");
    layers.iter().filter(|l| {
        let id = l["id"].as_str().unwrap_or("");
        (if simple { id == "roads-simple" } else { fill(id) && l["source"] != "halves" }) || id.starts_with("roads-bridge-decks")
    }).map(|l| l["id"].clone()).collect()
}

/// roadstyle:arrows: "points" (the page puts one arrow on each one-way road in view: the source "arrows"), "line" (along the slots), or
/// null (no arrows); render_web._arrow_kind.
pub fn arrow_kind(layers: &[Value]) -> Value {
    match layers.iter().find(|l| l["id"].as_str().is_some_and(|i| i.starts_with("roads-arrows"))) {
        None => Value::Null,
        Some(l) if l["source"] == "arrows" => "points".into(),
        Some(_) => "line".into(),
    }
}

/// roadstyle:controls: the options of rsDashboard that the style gives (render_web.render's `page`, in its order).
pub fn controls(look: &crate::Look, roads: &Roads, info: PageInfo, active: usize) -> Result<Value, String> {
    let (th, cfg, args) = (&look.theme, &look.config, &look.args);
    let m = &look.model;
    let cam = merged(&json!({"pitch": 0, "bearing": 0, "pitch_3d": 55, "max_pitch": 70}), &cfg["camera"]);
    let select = match &args["select_color"] { Value::Null => th["selection"]["select"].clone(), v => v.clone() };
    let arw = merged(&th["arrows"], &cfg["arrows"]);
    let place = &arw["place"];
    let towards = cfg["tunnel_towards"].as_object().cloned().unwrap_or_default();
    let toward = &cfg["tunnel_toward"];
    let colour = toward.as_str().and_then(|t| towards.get(t)).cloned().unwrap_or_else(|| toward.clone());
    let mut to = th["tunnels"]["to"].as_object().cloned().unwrap_or_default();
    to.insert("fill".into(), colour);
    let control = args["tunnel_control"] == true && !info.tunnel_layers.is_empty();
    let ratio = cfg["tunnel_casing_dash"].as_array().filter(|a| !a.is_empty()).cloned().unwrap_or_else(|| vec![json!(1), json!(1)]);
    let tunnel = json!({"layers": info.tunnel_layers, "dash": info.tunnel_dash, "casing": info.tunnel_casing, "strength": cfg["tunnel_strength"].as_f64().unwrap_or(0.0),
        "palette": cfg["tunnel_palette"], "palettes": cfg["tunnel_palettes"], "ratio": ratio,
        // the canvas colour of the base map: the page that adds a base map sets its own
        "bg": th["background"]["light"], "steps": th["tunnels"]["steps"], "ratios": th["tunnels"]["ratios"],
        "toward": toward, "towards": cfg["tunnel_towards"], "to": to, "control": control});
    let items = if args["items"].is_null() { Value::Null } else { json!({"label": "items", "popup": args["items_popup"], "layer": "roads-simple"}) };
    // a page is in simple mode, in both ways: the pieces pick and glow (the road layer roads-simple), and there are no fill layers
    // the facts of the look and of the roads that a host's dashboard needs; the caller's page keywords (tiles, views, the base maps, ...)
    // are not here: the page gives them (RS_OPTIONS, page_options::page_from), as a host does (rule 5, R3)
    let mut out = json!({"simple": "roads-simple", "pitch_3d": cam["pitch_3d"],
        "select_color": select, "filter": filter_panel(look, roads, m), "color_active": active, "overlays": info.overlays, "tunnel": tunnel,
        "fill_layers": [], "road_fill": {"on": args["road_fill"] != false, "paint": info.fill_paint}, "dashes": info.dashes,
        "items": items, "edge_id_col": args["edge_id_col"].as_str().unwrap_or("edge_id"), "arrow_icon": arw["icon"], "arrow_color": arw["color"],
        "arrow_rules": {"mainBelow": arw["main_below"], "main": arw["main"], "minLenPx": place["min_len_px"], "minGapPx": place["min_gap_px"],
                        "nameGapPx": place["name_gap_px"], "edgePx": place["edge_px"], "charWidth": place["char_width"],
                        "baseSize": th["labels"]["base_size"]}});
    // the map option `modes` (a base map's look: the road table's mode columns): each mode that some road has, with its count, in order
    if let Some(modes) = args["modes"].as_array() {
        let yes = |c: Option<Cell>| matches!(c, Some(Cell::Bool(true))) || c.and_then(Cell::as_str) == Some("true");
        out["modes"] = modes.iter().filter_map(Value::as_str)
            .map(|m| (m, roads.iter().filter(|r| yes(r.get(m))).count())).filter(|(_, n)| *n > 0).map(|(m, n)| json!([m, n])).collect();
    }
    if let Some(b) = args["box_layout"].as_str() {      // a base map's page: the Roads and Layers boxes in one stack
        out["box_layout"] = b.into();
    }
    Ok(out)
}
