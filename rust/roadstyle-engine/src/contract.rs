//! The output side of the interaction contract (docs/design/rust_library.md, "The interaction contract"): what a page's dashboard reads
//! from a style made with `state: "live"`. `roadstyle:state` has each global state's start value (render_web: style["state"]),
//! `roadstyle:controls` the options of rsDashboard that come from the style (render_web.render's `page`: the filter panel, the overlays,
//! the tunnel look, the road fill, the arrows' rules, ...). The page's own options (the base maps, Street View, the panel) are not here.

use crate::layers::{Model, PageInfo};
use crate::props::Feat;
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
pub fn page_state(look: &Value, active: usize, n_overlays: usize) -> Map<String, Value> {
    let (th, cfg) = (&look["theme"], &look["config"]);
    let towards = cfg["tunnel_towards"].as_object().cloned().unwrap_or_default();
    let toward = &cfg["tunnel_toward"];
    let colour = toward.as_str().and_then(|t| towards.get(t)).cloned().unwrap_or_else(|| toward.clone());
    let pair = cfg["tunnel_palette"].as_str().and_then(|p| cfg["tunnel_palettes"].get(p)).filter(|v| !v.is_null()).cloned();
    let dash = &th["tunnels"]["to"]["dash"];
    let ratio: Vec<f64> = cfg["tunnel_casing_dash"].as_array().filter(|a| !a.is_empty()).map(|a| a.iter().filter_map(Value::as_f64).collect())
        .unwrap_or_else(|| vec![1.0, 1.0]);
    // render's road_fill: the start value of rs_fill_on (off: each fill's opacity is 0)
    let road_fill = !matches!(look["args"]["road_fill"], Value::Bool(false));
    let mut state = json!({"rs_co": active, "rs_colors": {}, "rs_base": {}, "rs_fill_on": road_fill,
        "rs_tun_strength": cfg["tunnel_strength"].as_f64().unwrap_or(0.0), "rs_tun_toward": colour, "rs_tun_two": pair.is_some(),
        "rs_tun_c0": pair.as_ref().map_or(dash, |p| &p[0]), "rs_tun_c1": pair.as_ref().map_or(dash, |p| &p[1]), "rs_tun_ratio": ratio})
        .as_object().unwrap().clone();
    for i in 0..n_overlays {
        state.insert(format!("rs_ov_{i}"), json!({}));
    }
    // a palette made in code has no name
    let palette = look["palette"].as_str().or_else(|| look["active"]["palette"].as_str()).unwrap_or("custom");
    state.insert("rs_palette".into(), palette.into());
    state
}

/// The filter panel (render_web: `flt`): the classes present, most important first, a swatch for each (a road of the class that is not a
/// restricted one), the access kinds with their counts (access_col), and whether there are bridges and tunnels.
fn filter_panel(look: &Value, roads: &[Feat], m: &Model) -> Value {
    let args = &look["args"];
    let fb_fill = &look["theme"]["roads"]["fallback"]["fill"];
    let col = args["filter_col"].as_str().or_else(|| args["highway_col"].as_str()).filter(|c| !c.is_empty()).unwrap_or("highway");
    let (mut classes, mut seen, mut swatches, mut by_access) = (Vec::<String>::new(), std::collections::HashSet::new(), Map::new(),
                                                               std::collections::HashSet::new());
    let restricted = |p: &crate::props::Props| p.get("__rs_access").is_some_and(|a| !a.is_null() && a != false && a != "");
    for f in roads {
        let p = &f.props;
        let Some(c) = p.get("highway").and_then(Value::as_str).filter(|c| !c.is_empty()) else { continue };
        if !seen.contains(c) || (by_access.contains(c) && !restricted(p)) {
            if !seen.contains(c) {
                classes.push(c.to_string());
            }
            seen.insert(c.to_string());
            by_access.remove(c);
            if restricted(p) {
                by_access.insert(c.to_string());
            }
            swatches.insert(c.into(), p.get("__rs_fill").filter(|v| crate::layers::py_truth(v)).cloned().unwrap_or_else(|| fb_fill.clone()));
        }
    }
    classes.sort_by(|a, b| m.z_of(b).total_cmp(&m.z_of(a)).then_with(|| a.cmp(b)));
    let mut access = Vec::new();
    if args["access_col"].as_str().is_some_and(|c| !c.is_empty()) {
        let n = |k: &str| roads.iter().filter(|f| f.props.get("__rs_access").and_then(Value::as_str) == Some(k)).count();
        access = ACCESS.iter().filter(|(k, _)| n(k) > 0).map(|(k, label)| json!([k, look["theme"]["access"][*k], label, n(k)])).collect();
        // driving's pedestrian streets that cars may not use have their own row: where no usable road is of the class, a class row would
        // be a second switch for them
        if n("pedestrian") > 0 && classes.iter().any(|c| c == "pedestrian")
            && !roads.iter().any(|f| !restricted(&f.props) && f.props.get("highway").and_then(Value::as_str) == Some("pedestrian")) {
            classes.retain(|c| c != "pedestrian");
        }
    }
    let lvl = |f: &Feat| f.props.get("lvl").and_then(Value::as_f64).unwrap_or(0.0);
    json!({"on": args["filter_control"] != false && !classes.is_empty(), "col": col, "classes": classes, "access": access, "swatches": swatches,
           "bridges": roads.iter().any(|f| lvl(f) > 0.0), "tunnels": roads.iter().any(|f| lvl(f) < 0.0)})
}

/// _fill_layer_ids: the layers the page recolours: every road fill layer, and the fill layers of each drawing position.
pub(crate) fn fill_layer_ids(roads: &[Feat]) -> Vec<String> {
    let fills = ["roads-fill", "roads-fill-sq", "roads-fill-sx", "roads-fill-h", "roads-fill-hsq", "roads-fill-hsx"];
    let mut levels: Vec<i64> = roads.iter().flat_map(|f| ["__rs_cl", "__rs_fl", "__rs_cs", "__rs_ce"].map(|k| f.props.get(k).and_then(Value::as_i64)))
        .flatten().chain([0]).collect();
    levels.sort();
    levels.dedup();
    let mut ids: Vec<String> = fills.iter().map(|s| s.to_string()).collect();
    for l in levels.into_iter().filter(|&l| l != 0) {
        ids.extend(fills.iter().map(|f| format!("roads-fill-lv{l}{}", &f["roads-fill".len()..])));
    }
    ids
}

/// roadstyle:controls: the options of rsDashboard that the style gives (render_web.render's `page`, in its order).
pub fn controls(look: &Value, roads: &[Feat], info: PageInfo, active: usize) -> Result<Value, String> {
    let (th, cfg, args) = (&look["theme"], &look["config"], &look["args"]);
    let m = Model::from_look(look)?;
    let tiles = args["tiles"] == true;
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
    let views: Vec<Value> = args["views"].as_object().into_iter().flatten().map(|(n, s)| json!({"name": n, "set": s})).collect();
    let items = if args["items"].is_null() { Value::Null } else { json!({"label": "items", "popup": args["items_popup"], "layer": "roads-simple"}) };
    // render's lean mode: simple mode with inline data
    let lean = !tiles && args["simple"] != false;
    Ok(json!({"tiles": tiles, "simple": if lean { json!("roads-simple") } else { json!(false) }, "pitch_3d": cam["pitch_3d"],
        "select_color": select, "filter": filter_panel(look, roads, &m), "color_active": active, "overlays": info.overlays, "tunnel": tunnel,
        "fill_layers": fill_layer_ids(roads), "road_fill": {"on": args["road_fill"] != false, "paint": info.fill_paint}, "views": views,
        "items": items, "edge_id_col": args["edge_id_col"].as_str().unwrap_or("edge_id"), "arrow_icon": arw["icon"], "arrow_color": arw["color"],
        "arrow_rules": {"mainBelow": arw["main_below"], "main": arw["main"], "minLenPx": place["min_len_px"], "minGapPx": place["min_gap_px"],
                        "nameGapPx": place["name_gap_px"], "edgePx": place["edge_px"], "charWidth": place["char_width"],
                        "baseSize": th["labels"]["base_size"]}}))
}
