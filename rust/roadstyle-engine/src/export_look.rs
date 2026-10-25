//! export_look (approach 2 of docs/design/style_export.md): the simple look for a data layer that another app draws (the GeoLibre
//! plugin): MapLibre layers with no source that read the raw duckOSM columns, one casing and one fill layer per position, the arrows and
//! the names, the hover layer, the popup, the outline of the area.

use crate::layers::{by_feature, label_readable_filter, label_size_expr, minzoom_filter, swap, Exprs};
use roadstyle_look::color;
use roadstyle_model::flags;
use serde_json::{json, Map, Value};

/// The columns that export_look reads (its keywords).
pub struct LookCols<'a> {
    pub highway: &'a str,
    pub oneway: &'a str,
    pub tunnel: &'a str,
    pub bridge: &'a str,
    pub id: &'a str,
}

/// The look of `look` (a resolved look: render's theme, config and road tables) for the positions `positions` (in order).
pub fn export_look(look: &crate::Look, cols: &LookCols, positions: &[i64]) -> Result<Value, String> {
    let (t, cfg) = (&look.theme, &look.config);
    let m = &look.model;
    let hw = cols.highway;
    let key = match &t["active"]["palette"] {
        Value::Array(a) => a.iter().filter_map(Value::as_str).collect::<Vec<_>>().join("+"),
        v => v.as_str().unwrap_or("").to_string(),
    };
    let classes = t["palettes"][&key].as_object().cloned().unwrap_or_default();
    // the yes/no tags by the engine's rule (roadstyle_model::flags): tunnel=covered is a tunnel here as on the map
    let two = json!(["!", flags::maplibre_yes(json!(["get", cols.oneway]))]);
    let tun = flags::maplibre_yes(json!(["get", cols.tunnel]));
    let bri = flags::maplibre_yes(json!(["get", cols.bridge]));
    let tw = json!(["to-boolean", ["get", "__rs_twoway"]]);
    let fb = &t["roads"]["fallback"];
    let towards = cfg["tunnel_towards"].as_object().cloned().unwrap_or_default();
    let toward = &cfg["tunnel_toward"];
    let colour = toward.as_str().and_then(|n| towards.get(n)).cloned().unwrap_or_else(|| toward.clone());
    let toward = color::parse(colour.as_str().unwrap_or("#000000"))?;
    let strength = cfg["tunnel_strength"].as_f64().unwrap_or(0.0) / 100.0;
    // a palette colour that is not a colour is an error that names it (review D4: "#fff" is one, "#zzz" is not)
    for c in classes.values().flat_map(|e| [&e["fill"], &e["casing"]]).filter_map(Value::as_str).filter(|c| c.starts_with('#')) {
        color::parse(c)?;
    }
    // the tunnel look baked: a colour moved toward the tunnel colour (an app has no slider)
    let mixed = |c: &Value| match c.as_str().and_then(color::rgb) { Some(rgb) => json!(color::hex(color::mix(rgb, toward, strength))), None => c.clone() };
    let by_class = |field: &str, f: &dyn Fn(&Value) -> Value| {
        let mut vals = Vec::new();
        for (c, e) in &classes {
            if e.get(field).is_some_and(crate::layers::py_truth) {
                vals.push(json!(c));
                vals.push(f(&e[field]));
            }
        }
        let default = f(&fb[if field == "fill" { "fill" } else { "casing" }]);
        if vals.is_empty() { default } else {
            let mut e = vec![json!("match"), json!(["get", hw])];
            e.extend(vals);
            e.push(default);
            Value::Array(e)
        }
    };
    let same = |v: &Value| v.clone();
    let fill = json!(["case", tun, by_class("fill", &mixed), by_class("fill", &same)]);
    let pair = cfg["tunnel_palette"].as_str().and_then(|p| cfg["tunnel_palettes"].get(p)).filter(|v| !v.is_null());
    let tun_dash = mixed(pair.map_or(&t["tunnels"]["to"]["dash"], |p| &p[0]));
    let casing = json!(["case", bri, cfg["bridge_casing_color"], tun, tun_dash, by_class("casing", &same)]);
    let mut no_casing: Vec<Value> = classes.iter().filter(|(_, e)| !e.get("casing").is_some_and(crate::layers::py_truth)).map(|(c, _)| json!(c)).collect();
    no_casing.extend(cfg["minor_no_casing"].as_array().cloned().unwrap_or_default());
    let fw = swap(&m.width_expr(hw, false, 1.0), &tw, &two);
    let cw = swap(&m.width_expr(hw, true, 1.0), &tw, &two);
    let bcw = swap(&m.width_expr(hw, true, t["bridges"]["wing_scale"].as_f64().unwrap_or(1.0)), &tw, &two);
    let cw = by_feature(&[(bri.clone(), bcw)], &cw);
    let mut off = vec![json!("interpolate"), json!(["linear"]), json!(["zoom"])];
    for (z, zv) in m.stops() {
        off.push(zv.clone());
        off.push(json!(["case", two, m.offset_match(hw, z), 0]));
    }
    let off = Value::Array(off);
    let mut order = vec![json!("match"), json!(["get", hw])];
    for c in &m.classes {
        order.push(json!(c));
        order.push(m.class_order(c));
    }
    order.push(fb["order"].clone());
    let mz = cfg["minzoom"].as_object().filter(|t| !t.is_empty()).map(|t| minzoom_filter(hw, t));
    let lay = json!({"line-cap": t["roads"]["cap"], "line-join": t["roads"]["join"], "line-sort-key": order});
    let flt = |f: Value| match &mz { Some(z) => json!(["all", f, z]), None => f };
    let ratio: Vec<Value> = cfg["tunnel_casing_dash"].as_array().filter(|a| !a.is_empty()).map(|a| a.iter().map(|x| json!(x.as_f64().unwrap_or(1.0))).collect())
        .unwrap_or_else(|| vec![json!(1.0), json!(1.0)]);
    let mut layers = Vec::new();
    let mut ps = positions.to_vec();
    ps.sort();
    for p in ps {
        let at = |col: &str| json!(["==", ["coalesce", ["get", col], 0], p]);
        layers.push(json!({"id": format!("casing-{p}"), "type": "line", "metadata": {"roadstyle:position": p},
            "filter": flt(json!(["all", at("casing_level"), ["!", ["in", ["get", hw], ["literal", no_casing]]]])),
            "layout": lay, "paint": {"line-color": casing, "line-width": cw, "line-offset": off, "line-opacity": t["casing"]["opacity"],
                                     "line-dasharray": ["case", tun, ["literal", ratio], ["literal", [1, 0]]]}}));
        layers.push(json!({"id": format!("fill-{p}"), "type": "line", "metadata": {"roadstyle:position": p}, "filter": flt(at("fill_level")),
            "layout": lay, "paint": {"line-color": fill, "line-width": fw, "line-offset": off, "line-opacity": t["roads"]["fill_opacity"]}}));
    }
    let (bd, sel, arw, lbl) = (&t["boundary"], &t["selection"], &t["arrows"], &t["labels"]);
    let minor: Vec<Value> = t["roads"]["classes"].as_object().into_iter().flatten()
        .filter(|(_, e)| e.get("minor").is_some_and(crate::layers::py_truth)).map(|(c, _)| json!(c)).collect();
    let minor_or = |z: &Value| json!(["any", ["!", ["match", ["get", hw], minor, true, false]], [">=", ["zoom"], z]]);
    let sort = json!(["*", -1, m.sort_key(hw)]);
    let mut af = vec![json!(["==", ["get", cols.oneway], true]), minor_or(&arw["minor_minzoom"])];
    af.extend(mz.clone());
    let mut spacing = vec![json!("interpolate"), json!(["linear"]), json!(["zoom"])];
    for zp in arw["spacing"].as_array().into_iter().flatten() {
        spacing.extend(zp.as_array().cloned().unwrap_or_default());
    }
    let mut size = vec![json!("interpolate"), json!(["exponential", arw["size"]["base"]]), json!(["zoom"])];
    for zb in arw["size"]["stops"].as_array().into_iter().flatten() {
        size.push(zb[0].clone());
        size.push(json!(["*", zb[1], ["match", ["get", hw], minor, arw["size"]["minor"], 1.0]]));
    }
    let fixed = lbl.get("size").filter(|v| crate::layers::py_truth(v));
    let mut lf = vec![json!(["to-boolean", ["get", "name"]]), minor_or(&lbl["minor_minzoom"])];
    lf.extend(mz.clone());
    if fixed.is_none() {
        lf.push(label_readable_filter(m, t));
    }
    let mut lpaint = json!({"text-color": lbl["color"], "text-opacity": lbl.get("opacity").unwrap_or(&arw["opacity"])});
    if lbl.get("halo_color").is_some_and(crate::layers::py_truth) && lbl.get("halo_width").is_some_and(crate::layers::py_truth) {
        lpaint["text-halo-color"] = lbl["halo_color"].clone();
        lpaint["text-halo-width"] = lbl["halo_width"].clone();
    }
    let all = |v: Vec<Value>| { let mut a = vec![json!("all")]; a.extend(v); Value::Array(a) };
    let symbols = json!([
        {"id": "arrows", "type": "symbol", "minzoom": arw["minzoom"], "filter": all(af),
         "layout": {"symbol-placement": "line", "icon-image": "oneway", "icon-rotation-alignment": "map", "symbol-spacing": spacing,
                    "symbol-sort-key": sort, "icon-size": size},
         "paint": {"icon-opacity": arw["opacity"], "icon-color": arw["color"]}},
        {"id": "labels", "type": "symbol", "minzoom": lbl["minzoom"], "filter": all(lf),
         "layout": {"symbol-placement": "line-center", "text-field": ["get", "name"], "text-font": lbl["font"],
                    "text-size": label_size_expr(m, t, fixed), "text-max-angle": lbl["max_angle"], "text-padding": lbl["padding"],
                    "symbol-sort-key": sort},
         "paint": lpaint}]);
    let img = &look.oneway_image;
    let images = json!({"oneway": {"url": img["url"], "sdf": true, "pixelRatio": arw["icon"]["pixel_ratio"]}});
    let mut hover_lay: Map<String, Value> = lay.as_object().cloned().unwrap_or_default();
    hover_lay.shift_remove("line-sort-key");
    let popup: Vec<Value> = look.interaction["default_popup"].as_array().or_else(|| look.interaction["popup"].as_array()).into_iter().flatten()
        .filter(|c| c.as_str() != Some("name")).cloned().collect();
    Ok(json!({"name": format!("{} / {key}", t["active"]["profile"].as_str().unwrap_or("")),
              "columns": [hw, cols.oneway, cols.tunnel, cols.bridge, "casing_level", "fill_level"],
              "layers": layers, "symbols": symbols, "images": images,
              "hover": {"id": cols.id, "layers": [{"id": "hover", "type": "line", "layout": hover_lay,
                                                   "paint": {"line-color": sel["hover"], "line-opacity": sel["opacity"], "line-width": fw, "line-offset": off}}]},
              "popup": {"title": "name", "columns": popup, "only_true": [cols.bridge, cols.tunnel]},
              "head_m": 5.0, "hover_delay_ms": 300,
              "boundary": {"columns": [], "layers": [{"id": "boundary", "type": "line", "paint": {"line-color": bd["color"], "line-width": bd["width"],
                                                                                                 "line-opacity": bd["opacity"], "line-dasharray": bd["dash"]}}]}}))
}
