use super::*;

pub(super) fn kind_match(colors: &Value, default: &Value) -> Value {
    match colors.as_object().filter(|m| !m.is_empty()) {
        None => default.clone(),
        Some(m) => {
            let mut e = vec![json!("match"), json!(["get", "kind"])];
            for (k, c) in m {
                e.push(json!(k));
                e.push(c.clone());
            }
            e.push(default.clone());
            Value::Array(e)
        }
    }
}

/// mapstyle.export._swap: a hover / select `case` kept around a new base colour.
pub(super) fn ms_swap(expr: Option<&Value>, value: Value) -> Value {
    match expr.and_then(Value::as_array) {
        Some(a) if a.first() == Some(&json!("case")) => {
            let mut a = a.clone();
            a.pop();
            a.push(value);
            Value::Array(a)
        }
        _ => value,
    }
}

/// The id of the overlay `i`'s 3D layer (the fill-extrusion of a base-map layer with heights).
pub(super) fn ov_3d(i: usize) -> String {
    format!("ov{i}-3d")
}

/// mapstyle.export._restyle: the base-map layers styled as layers.js styles them on the page (colour and outline by kind, dashes, textures,
/// icons, 3D buildings, zoom ranges). A 3D layer goes under the arrows, names and highlight; the others right after the layer they belong to.
pub(super) fn restyle(layers: Vec<Value>, ovs: &[Overlay]) -> Vec<Value> {
    let mut layers = layers;
    let mut by_ov: IndexMap<usize, Vec<usize>> = IndexMap::new();
    for (k, l) in layers.iter().enumerate() {
        if let Some(i) = l["source"].as_str().and_then(|s| s.strip_prefix("ov")).and_then(|n| n.parse::<usize>().ok()) {
            by_ov.entry(i).or_default().push(k);
        }
    }
    let mut extra: IndexMap<String, Vec<Value>> = IndexMap::new();
    for (i, lys) in &by_ov {
        let ll = &ovs[*i].l;
        if ll.is_null() {
            continue; // a caller's overlay: no restyle of mapstyle's
        }
        let first = layers[lys[0]].clone();
        let body_type = first["type"].as_str().unwrap_or("").to_string();
        let bodies: Vec<usize> = lys.iter().copied().filter(|&k| layers[k]["type"] == body_type.as_str()).collect();
        let meta = first.get("metadata").cloned().unwrap_or(json!({}));
        let vis = first["layout"].get("visibility").cloned().unwrap_or(json!("visible"));
        let p = match body_type.as_str() { "fill" => Some("fill-color"), "line" => Some("line-color"), "circle" => Some("circle-color"), _ => None };
        for &b in &bodies {
            if let (Some(cb), Some(p)) = (ll.get("color_by").filter(|v| crate::roads::yes(v)), p) {
                let v = ms_swap(layers[b]["paint"].get(p), kind_match(&cb["map"], &cb["default"]));
                layers[b]["paint"][p] = v;
            }
            if ll.get("dash").is_some_and(crate::roads::yes) && body_type == "line" {
                layers[b]["paint"]["line-dasharray"] = ll["dash"].clone();
            }
            if let Some(wz) = ll.get("width_zoom").and_then(Value::as_array).filter(|a| !a.is_empty()) {
                if body_type == "line" {
                    let mut e = vec![json!("interpolate"), json!(["linear"]), json!(["zoom"])];
                    e.extend(wz.iter().flat_map(|s| s.as_array().cloned().unwrap_or_default()));
                    layers[b]["paint"]["line-width"] = Value::Array(e);
                }
            }
        }
        if let Some(ob) = ll.get("outline_by").filter(|v| crate::roads::yes(v)) {
            for &k in lys {
                if layers[k]["id"].as_str().is_some_and(|x| x.ends_with("-outline")) {
                    layers[k]["paint"]["line-color"] = kind_match(&ob["map"], &ob["default"]);
                }
            }
        }
        let mut news: Vec<(String, Value)> = Vec::new(); // (after which layer, the spec)
        let source = first["source"].clone();
        let new = |spec: Value| -> Value {
            let mut s = spec.as_object().unwrap().clone();
            s.insert("source".into(), source.clone());
            let mut m = meta.as_object().cloned().unwrap_or_default();
            for (k, v) in spec.get("metadata").and_then(Value::as_object).into_iter().flatten() {
                m.insert(k.clone(), v.clone());
            }
            s.insert("metadata".into(), Value::Object(m));
            let mut lay = spec.get("layout").and_then(Value::as_object).cloned().unwrap_or_default();
            if !lay.contains_key("visibility") {
                lay.insert("visibility".into(), vis.clone());
            }
            s.insert("layout".into(), Value::Object(lay));
            Value::Object(s)
        };
        if let Some(pats) = ll.get("patterns").and_then(Value::as_object).filter(|m| !m.is_empty()) {
            let keys: Vec<Value> = pats.keys().map(|k| json!(k)).collect();
            let mut fp = vec![json!("match"), json!(["get", "kind"])];
            for (k, v) in pats {
                fp.push(json!(k));
                fp.push(v.clone());
            }
            fp.push(pats.values().next().unwrap().clone());
            let mut spec = json!({"id": format!("ov{i}-pattern"), "type": "fill", "filter": ["match", ["get", "kind"], keys, true, false],
                                  "paint": {"fill-pattern": fp}});
            // a theme's landcover_pattern_style: no texture below its minzoom, and its opacity by zoom ([zoom, opacity] pairs, linear)
            let ps = ll.get("pattern_style").cloned().unwrap_or(Value::Null);
            if let Some(z) = ps.get("minzoom").filter(|z| z.is_number()) {
                spec["minzoom"] = z.clone();
            }
            if let Some(stops) = ps.get("opacity").and_then(Value::as_array) {
                let mut e = vec![json!("interpolate"), json!(["linear"]), json!(["zoom"])];
                e.extend(stops.iter().filter_map(Value::as_array).flatten().cloned());
                spec["paint"]["fill-opacity"] = Value::Array(e);
            }
            news.push((layers[bodies[0]]["id"].as_str().unwrap().to_string(), new(spec)));
        }
        if let Some(ic) = ll.get("icon").filter(|v| crate::roads::yes(v)) {
            let pairs = ic["size"].as_array().cloned().unwrap_or_default();
            let curve = |f: f64| -> Value {
                let mut e = vec![json!("interpolate"), json!(["linear"]), json!(["zoom"])];
                for zs in &pairs {
                    e.push(zs[0].clone());
                    e.push(json!(zs[1].as_f64().unwrap() * f));
                }
                Value::Array(e)
            };
            let on_edge = bodies.iter().any(|&b| layers[b].get("filter").is_some_and(|f| f.to_string().contains(Mark::FillLevel.name())));
            for (k, &b) in bodies.iter().enumerate() {
                let mut spec = json!({"id": format!("ov{i}-icon{}", if k == 0 { String::new() } else { k.to_string() }), "type": "symbol",
                                      "layout": {"icon-image": ic["image"], "icon-allow-overlap": true, "icon-size": curve(1.0),
                                                 "icon-rotate": ["coalesce", ["get", "bearing"], 0], "icon-rotation-alignment": "map"},
                                      "paint": {"icon-opacity": ic["opacity"]}});
                if on_edge {
                    if let Some(f) = layers[b].get("filter") {
                        spec["filter"] = f.clone();
                    }
                }
                news.push((layers[b]["id"].as_str().unwrap().to_string(), new(spec)));
                layers[b]["paint"]["circle-opacity"] = json!(0);
                layers[b]["paint"]["circle-stroke-width"] = json!(0);
                layers[b]["paint"]["circle-radius"] = curve(24.0);
            }
        }
        if let Some(ex) = ll.get("extrude").filter(|v| crate::roads::yes(v)) {
            let last = news.last().map(|n| n.1["id"].as_str().unwrap().to_string()).unwrap_or_else(|| layers[*lys.last().unwrap()]["id"].as_str().unwrap().to_string());
            news.push((last, new(json!({"id": ov_3d(*i), "type": "fill-extrusion", "metadata": {"roadstyle:group": "buildings 3D", "roadstyle:over": true},
                                        "layout": {"visibility": "none"},
                                        "paint": {"fill-extrusion-color": ex["color"], "fill-extrusion-height": ["get", "height"],
                                                  "fill-extrusion-base": ["coalesce", ["get", "base"], 0], "fill-extrusion-opacity": ex["opacity"]}}))));
        }
        if let Some(mz) = ll.get("min_zoom").filter(|v| crate::roads::yes(v)) {
            for &k in lys {
                layers[k]["minzoom"] = mz.clone();
            }
            for n in news.iter_mut() {
                n.1["minzoom"] = mz.clone();
            }
        }
        for (after, spec) in news {
            extra.entry(after).or_default().push(spec);
        }
    }
    let is_over = |x: &Value| x["metadata"].get("roadstyle:over").is_some_and(crate::roads::yes);
    let mut out = Vec::new();
    for l in layers {
        let id = l["id"].as_str().unwrap_or("").to_string();
        out.push(l);
        if let Some(xs) = extra.get(&id) {
            out.extend(xs.iter().filter(|x| !is_over(x)).cloned());
        }
    }
    let over: Vec<Value> = extra.values().flatten().filter(|x| is_over(x)).cloned().collect();
    if !over.is_empty() {
        let at = out.iter().position(|x| matches!(x["id"].as_str(), Some("roads-arrows" | "roads-labels" | "roads-highlight"))).unwrap_or(out.len());
        out.splice(at..at, over);
    }
    out
}

