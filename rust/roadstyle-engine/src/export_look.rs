//! export_look (approach 2 of docs/design/style_export.md): the simple look for a data layer that another app draws (the GeoLibre
//! plugin): MapLibre layers with no source that read the raw duckOSM columns, one casing and one fill layer per position, the arrows and
//! the names, the hover layer, the popup, the outline of the area.

use roadstyle_model::mark::Mark;
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

/// The fill and casing colours by class, the tunnel look baked in, the classes that have no casing, and the fill's dash by class (none: no
/// class has a dash). The colours are the class styles that the map draws with (`roads.styles`, ClassStyler: the look's palette with the
/// design's colours; a link class has its own entry), so another app's layer has the colours of the map.
fn class_colours(look: &crate::Look, hw: &str, tun: &Value, bri: &Value) -> Result<(Value, Value, Vec<Value>, Option<Value>), crate::Error> {
    let s = &look.sections;
    let st = &s.roads.styles;
    let mut classes: Vec<(String, &Value)> = Vec::new();
    for (c, [plain, link]) in &st.classes {
        classes.push((c.clone(), plain));
        classes.push((format!("{c}_link"), link));
    }
    let (fb, tu) = (&st.fallback[0], &s.tunnels);
    let toward = color::parse(tu.toward_color())?;
    let strength = tu.strength.f() / 100.0;
    // a colour that is not a colour is an error that names it (review D4: "#fff" is one, "#zzz" is not)
    for c in classes.iter().map(|(_, e)| *e).chain([fb]).flat_map(|e| [&e["fill"], &e["casing"]]).filter_map(Value::as_str).filter(|c| c.starts_with('#')) {
        color::parse(c)?;
    }
    // the tunnel look baked: a colour moved toward the tunnel colour (an app has no slider)
    let mixed = |c: &Value| match c.as_str().and_then(color::rgb) { Some(rgb) => json!(color::hex(color::mix(rgb, toward, strength))), None => c.clone() };
    let by_class = |field: &str, f: &dyn Fn(&Value) -> Value| {
        let mut vals = Vec::new();
        for (c, e) in &classes {
            if e.get(field).is_some_and(crate::roads::yes) {
                vals.push(json!(c));
                vals.push(f(&e[field]));
            }
        }
        let fallback = if fb.get(field).is_some_and(crate::roads::yes) { &fb[field] } else { &s.roads.fallback[field] };
        if vals.is_empty() { f(fallback) } else {
            let mut e = vec![json!("match"), json!(["get", hw])];
            e.extend(vals);
            e.push(f(fallback));
            Value::Array(e)
        }
    };
    let same = |v: &Value| v.clone();
    let fill = json!(["case", tun, by_class("fill", &mixed), by_class("fill", &same)]);
    let pair = tu.pair();
    let tun_dash = mixed(pair.map_or(&tu.to["dash"], |p| &p[0]));
    let casing = json!(["case", bri, s.bridges.casing_color, tun, tun_dash, by_class("casing", &same)]);
    let mut no_casing: Vec<Value> = classes.iter().filter(|(_, e)| !e.get("casing").is_some_and(crate::roads::yes)).map(|(c, _)| json!(c)).collect();
    let mut flagged = s.roads.flagged("no_casing");
    flagged.sort();        // the config's sorted minor_no_casing
    no_casing.extend(flagged.into_iter().map(Value::from));
    // a class's dash ("0.6,0.5": dash and gap, in widths of the line), as the map draws `steps`
    let dash_of = |e: &Value| -> Option<Value> {
        let parts: Vec<f64> = e.get("dash")?.as_str()?.split(',').map(|x| x.trim().parse().ok()).collect::<Option<_>>()?;
        (parts.len() >= 2).then(|| json!(["literal", parts]))
    };
    let mut dash = vec![json!("match"), json!(["get", hw])];
    for (c, e) in &classes {
        if let Some(d) = dash_of(e) {
            dash.push(json!(c));
            dash.push(d);
        }
    }
    dash.push(json!(["literal", [1, 0]]));
    let dash = (dash.len() > 3).then_some(Value::Array(dash));
    Ok((fill, casing, no_casing, dash))
}

/// The arrows' and the names' layers (symbols along the lines). `mz`: the class minzoom filter.
fn symbol_layers(look: &crate::Look, cols: &LookCols, mz: Option<&Value>) -> Value {
    let (s, m, hw) = (&look.sections, &look.model, cols.highway);
    let arw = &s.arrows;
    let lbl = &s.labels;
    let minor = s.roads.flagged("minor");
    let minor_or = |z: &Value| json!(["any", ["!", ["match", ["get", hw], minor, true, false]], [">=", ["zoom"], z]]);
    let sort = json!(["*", -1, m.sort_key(hw)]);
    let mut af = vec![json!(["==", ["get", cols.oneway], true]), minor_or(&json!(arw.minor_minzoom))];
    af.extend(mz.cloned());
    let mut spacing = vec![json!("interpolate"), json!(["linear"]), json!(["zoom"])];
    for zp in arw.spacing.as_array().into_iter().flatten() {
        spacing.extend(zp.as_array().cloned().unwrap_or_default());
    }
    let mut size = vec![json!("interpolate"), json!(["exponential", arw.size["base"]]), json!(["zoom"])];
    for zb in arw.size["stops"].as_array().into_iter().flatten() {
        size.push(zb[0].clone());
        size.push(json!(["*", zb[1], ["match", ["get", hw], minor, arw.size["minor"], 1.0]]));
    }
    let fixed = lbl.size.as_ref().filter(|v| crate::roads::yes(v));
    let mut lf = vec![json!(["to-boolean", ["get", "name"]]), minor_or(&json!(lbl.minor_minzoom))];
    lf.extend(mz.cloned());
    if fixed.is_none() {
        lf.push(label_readable_filter(m, lbl));
    }
    let mut lpaint = json!({"text-color": lbl.color, "text-opacity": arw.opacity});
    if let Some(halo) = lbl.halo_color.as_ref().filter(|_| lbl.halo_width.f() != 0.0) {
        lpaint["text-halo-color"] = json!(halo);
        lpaint["text-halo-width"] = json!(lbl.halo_width);
    }
    let all = |v: Vec<Value>| { let mut a = vec![json!("all")]; a.extend(v); Value::Array(a) };
    json!([
        {"id": "arrows", "type": "symbol", "minzoom": arw.minzoom, "filter": all(af),
         "layout": {"symbol-placement": "line", "icon-image": crate::layers::ARROW_IMAGE, "icon-rotation-alignment": "map", "symbol-spacing": spacing,
                    "symbol-sort-key": sort, "icon-size": size},
         "paint": {"icon-opacity": arw.opacity, "icon-color": arw.color}},
        {"id": "labels", "type": "symbol", "minzoom": lbl.minzoom, "filter": all(lf),
         "layout": {"symbol-placement": "line-center", "text-field": ["get", "name"], "text-font": lbl.font,
                    "text-size": label_size_expr(m, lbl, fixed), "text-max-angle": lbl.max_angle, "text-padding": lbl.padding,
                    "symbol-sort-key": sort},
         "paint": lpaint}])
}

/// The look of `look` (a resolved look: render's theme, config and road tables) for the positions `positions` (in order).
pub fn export_look(look: &crate::Look, cols: &LookCols, positions: &[i64]) -> Result<Value, crate::Error> {
    let s = &look.sections;
    let m = &look.model;
    let hw = cols.highway;
    let key = &look.palette;          // the palette of the map (the class styles are made from it)
    // the yes/no tags by the engine's rule (roadstyle_model::flags): tunnel=covered is a tunnel here as on the map
    let two = json!(["!", flags::maplibre_yes(json!(["get", cols.oneway]))]);
    let tun = flags::maplibre_yes(json!(["get", cols.tunnel]));
    let bri = flags::maplibre_yes(json!(["get", cols.bridge]));
    let tw = json!(["to-boolean", ["get", Mark::Twoway.name()]]);
    let (fb, tu) = (&s.roads.fallback, &s.tunnels);
    let (fill, casing, no_casing, fill_dash) = class_colours(look, hw, &tun, &bri)?;
    let fw = swap(&m.width_expr(hw, false, 1.0, false), &tw, &two);
    let cw = swap(&m.width_expr(hw, true, 1.0, false), &tw, &two);
    let bcw = swap(&m.width_expr(hw, true, s.bridges.wing_scale.f(), false), &tw, &two);
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
    let mz = Some(s.roads.class_values("minzoom")).filter(|t| !t.is_empty()).map(|t| minzoom_filter(hw, &t));
    let lay = json!({"line-cap": s.roads.cap, "line-join": s.roads.join, "line-sort-key": order});
    // a casing has a flat end, as the map's pieces have where a road goes on: a round end lies over the fill of the next edge when that
    // edge is drawn lower
    let mut casing_lay = lay.clone();
    casing_lay["line-cap"] = json!("butt");
    let flt = |f: Value| match &mz { Some(z) => json!(["all", f, z]), None => f };
    let ratio: Vec<Value> = Some(&tu.casing_dash).filter(|a| !a.is_empty()).map(|a| a.iter().map(|x| json!(x.f())).collect())
        .unwrap_or_else(|| vec![json!(1.0), json!(1.0)]);
    let mut layers = Vec::new();
    let mut ps = positions.to_vec();
    ps.sort();
    for p in ps {
        let at = |col: &str| json!(["==", ["coalesce", ["get", col], 0], p]);
        // the opacity is the map's: its road pieces are drawn at 1 (casing.opacity and fill_opacity are for folium)
        layers.push(json!({"id": format!("casing-{p}"), "type": "line", "metadata": {"roadstyle:position": p},
            "filter": flt(json!(["all", at("casing_level"), ["!", ["in", ["get", hw], ["literal", no_casing]]]])),
            "layout": casing_lay, "paint": {"line-color": casing, "line-width": cw, "line-offset": off,
                                            "line-dasharray": ["case", tun, ["literal", ratio], ["literal", [1, 0]]]}}));
        let mut fill_paint = json!({"line-color": fill, "line-width": fw, "line-offset": off});
        if let Some(d) = &fill_dash {
            fill_paint["line-dasharray"] = d.clone();
        }
        layers.push(json!({"id": format!("fill-{p}"), "type": "line", "metadata": {"roadstyle:position": p}, "filter": flt(at("fill_level")),
            "layout": lay, "paint": fill_paint}));
    }
    let (bd, sel, arw) = (&s.boundary, &s.selection, &s.arrows);
    let symbols = symbol_layers(look, cols, mz.as_ref());
    let img = &arw.image;
    let images = json!({crate::layers::ARROW_IMAGE: {"url": img["url"], "sdf": true, "pixelRatio": arw.icon["pixel_ratio"]}});
    let mut hover_lay: Map<String, Value> = lay.as_object().cloned().unwrap_or_default();
    hover_lay.shift_remove("line-sort-key");
    let popup: Vec<&String> = s.interaction.popup.iter().filter(|c| *c != "name").collect();
    Ok(json!({"name": format!("{} / {key}", s.active.profile),
              "columns": [hw, cols.oneway, cols.tunnel, cols.bridge, "casing_level", "fill_level"],
              "layers": layers, "symbols": symbols, "images": images,
              "hover": {"id": cols.id, "layers": [{"id": "hover", "type": "line", "layout": hover_lay,
                                                   "paint": {"line-color": sel.hover, "line-opacity": sel.opacity, "line-width": fw, "line-offset": off}}]},
              "popup": {"title": "name", "columns": popup, "only_true": [cols.bridge, cols.tunnel]},
              "head_m": 5.0, "hover_delay_ms": 300,
              "boundary": {"columns": [], "layers": [{"id": "boundary", "type": "line", "paint": {"line-color": bd.color, "line-width": bd.width,
                                                                                                 "line-opacity": bd.opacity, "line-dasharray": bd.dash}}]}}))
}
