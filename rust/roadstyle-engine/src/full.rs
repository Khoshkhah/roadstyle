//! The full look (render's `simple=False`): a casing and a fill layer for each drawing position, with their twins for the end caps, the
//! dashed classes and the tunnel and bridge looks, over the sources `roads`, `casings` (the divided casing), `halves` (an edge with two
//! different ends) and `shadows` (the bridge shadows). Each function names the part of render_web.render it ports.

use crate::layers::py_truth;
use crate::props::Props;
use crate::read::Feature;
use crate::simple::{Piece, Pt};
use serde_json::{json, Map, Value};
use std::collections::HashMap;

const CASING_FAMILY: [&str; 8] = ["roads-casing", "roads-casing-sq", "roads-casing-sx", "roads-casing-dash", "roads-casing-bridge-shadow",
                                  "roads-casing-bridge", "roads-casing-sq-bridge", "roads-casing-sx-bridge"];
const FILL_FAMILY: [&str; 7] = ["roads-fill", "roads-fill-sq", "roads-fill-sx", "roads-fill-h", "roads-fill-hsq", "roads-fill-hsx", "roads-fill-pat"];

/// `{**l, k: v, ...}`: the layer with these keys set (a key it has keeps its place, a new one goes last).
pub(crate) fn with(l: &Value, kv: Vec<(&str, Value)>) -> Value {
    let mut o = l.as_object().cloned().unwrap_or_default();
    for (k, v) in kv {
        o.insert(k.into(), v);
    }
    Value::Object(o)
}

fn id(l: &Value) -> &str {
    l["id"].as_str().unwrap_or("")
}

/// _level_id: the id of a ground layer for a position: unchanged for 0; else `-lv<n>` after the family root (roads-fill-lv2-sq).
pub(crate) fn level_id(lid: &str, level: i64) -> String {
    if level == 0 {
        return lid.into();
    }
    let root = if lid.starts_with("roads-casing") { "roads-casing" } else { "roads-fill" };
    format!("{root}-lv{level}{}", &lid[root.len()..])
}

/// The drawing positions of the roads (_mark_levels): 0 and every casing, fill and head number, in order.
pub(crate) fn levels_of(rp: &[&Props]) -> Vec<i64> {
    let mut v: Vec<i64> = rp.iter().flat_map(|p| ["__rs_cl", "__rs_fl", "__rs_cs", "__rs_ce"].map(|k| p.get(k).and_then(Value::as_i64)))
        .flatten().chain([0]).collect();
    v.sort();
    v.dedup();
    v
}

/// The data of the full look: the casing pieces (when the casing is divided), the halves (edges with two different ends) and the
/// bridge shadows, as GeoJSON features in render's order.
pub struct FullSources {
    pub casings: Option<Vec<Value>>,
    pub halves: Option<Vec<Value>>,
    pub shadows: Vec<Value>,
}

fn feature(p: Piece) -> Value {
    json!({"type": "Feature", "properties": Value::Object(p.props.to_map()), "geometry": {"type": "LineString", "coordinates": p.coords}})
}

/// _mark_cls on a piece: the class and the access kind of its edge.
fn mark_cls(mut p: Piece, roads: &[Feature]) -> Piece {
    let e = p.props.get("__rs_edge").and_then(Value::as_u64).unwrap_or(0) as usize;
    let road = roads.get(e).map(|r| &r.props);
    p.props.insert("__rs_cls", road.and_then(|r| r.get("highway")).cloned().unwrap_or(Value::Null));
    if let Some(a) = road.and_then(|r| r.get("__rs_access")).filter(|a| !a.is_null()) {
        p.props.insert("__rs_access", a.clone());
    }
    p
}

/// render's divided casing (_casing_parts, when the casing has heads, two different ends or a two-way pair's one casing), its halves
/// (_halves) and its bridge shadows (_bridge_shadows, when the config has bridge_shadow).
pub fn sources(roads: &[Feature], look: &Value, head_m: f64, width_col: Option<&str>, divided: bool, order: &[String]) -> FullSources {
    let cfg = &look["config"];
    let parts: Option<Vec<Piece>> = divided.then(|| crate::simple::casing_parts(roads, head_m, width_col));
    let splits = roads.iter().any(|f| f.props.get("__rs_split").is_some_and(py_truth));
    let halves = splits.then(|| {
        let mut by = crate::simple::halves(roads);
        let mut out = Vec::new();
        for (i, f) in roads.iter().enumerate() {
            let e = f.props.get("__rs_edge").and_then(Value::as_i64).unwrap_or(i as i64);
            out.extend(by.remove(&e).unwrap_or_default().into_iter().map(|p| feature(mark_cls(p, roads))));
        }
        out
    });
    let shadows = if cfg["bridge_shadow"].as_bool().unwrap_or(false) {
        bridge_shadows(roads, parts.as_deref(), cfg["bridge_shadow_trim_m"].as_f64().unwrap_or(0.0), order)
    } else { Vec::new() };
    let casings = parts.map(|ps| ps.into_iter().map(|p| feature(mark_cls(p, roads))).collect());
    FullSources { casings, halves, shadows }
}

/// What the full look's layers read (render's locals).
pub struct FullIn<'a> {
    pub look: &'a Value,
    pub rp: &'a [&'a Props],
    pub levels: &'a [i64],
    pub cw: Value,
    pub fw: Value,
    pub bcw: Value,
    pub off: Value,
    pub shadow_w: Value,
    pub lay: Value,
    pub mz: Option<Value>,
    pub divided: bool,
    pub parts_caps: bool,
    pub shadows: bool,
    pub pairs: Option<Box<dyn Fn(&Value) -> Value + 'a>>,
    pub decks: Option<f64>,
    pub any_tunnel: bool,
    pub dashes: &'a [String],
    pub select: Value,
    pub hover: Value,
}

/// render's layers of the full look in position mode, up to the arrows and the names: the three bands' casings and fills, the bridge
/// look and the highlight; the dashed classes (their own fill layers, under the casings), the end caps' twins (-sq, -sx, the halves),
/// the positions (_level_layers), the bridge look of each position and its shadow, and the 3D decks' zooms.
pub fn layers(f: &FullIn) -> Vec<Value> {
    let (th, cfg) = (&f.look["theme"], &f.look["config"]);
    let fb = &th["roads"]["fallback"];
    let (fb_fill, fb_casing) = (&fb["fill"], &fb["casing"]);
    let lay = &f.lay;
    let tlay = with(lay, vec![("line-cap", th["tunnels"]["cap"].clone())]);
    let blay = with(lay, vec![("line-cap", th["bridges"]["cap"].clone())]);
    let (cw, fw, bcw, off) = (&f.cw, &f.fw, &f.bcw, &f.off);
    let lv = json!(["coalesce", ["get", "lvl"], 0]);
    let (is_t, is_b) = (json!(["to-boolean", ["get", "__rs_tunnel"]]), json!(["to-boolean", ["get", "__rs_bridge"]]));
    let auto = f.rp.iter().any(|p| p.get("__rs_band").is_some_and(|b| !b.is_null()));
    let bd = if auto { json!(["coalesce", ["get", "__rs_band"], ["case", ["<", lv, 0], -1, [">", lv, 0], 1, 0]]) } else { lv.clone() };
    let z = |x: Value| match &f.mz { Some(m) => json!(["all", m, x]), None => x };
    let (surface, low) = (json!(["==", bd, 0]), json!(["<", bd, 0]));
    let bridge = json!(["!", ["to-boolean", 1]]);
    let high = json!(["all", [">", bd, 0], ["!", is_b]]);
    let (tunnel, tunnel_g, tunnel_h) = (json!(["all", low, is_t]), json!(["all", surface, is_t]), json!(["all", high, is_t]));
    let (surface, low, bridge, high, tunnel, tunnel_g, tunnel_h) = (z(surface), z(low), z(bridge), z(high), z(tunnel), z(tunnel_g), z(tunnel_h));
    // a tunnel's band (in position mode every road is in band 0)
    let band = |p: &Props| {
        let b = p.get("__rs_band").filter(|b| !b.is_null()).or_else(|| p.get("lvl")).and_then(Value::as_f64).unwrap_or(0.0);
        (b > 0.0) as i64 - (b < 0.0) as i64
    };
    let tuns: Vec<i64> = f.rp.iter().filter(|p| p.get("__rs_tunnel").is_some_and(py_truth)).map(|p| band(p)).collect();
    let (tun_g, tun_h) = (tuns.contains(&0), tuns.contains(&1));
    let casing = |lid: &str, flt: &Value| json!({"id": lid, "type": "line", "source": "roads", "layout": lay, "filter": flt,
        "paint": {"line-color": ["coalesce", ["get", "__rs_casing"], fb_casing], "line-width": cw, "line-offset": off}});
    let fill = |lid: &str, flt: &Value| json!({"id": lid, "type": "line", "source": "roads", "layout": lay, "filter": flt,
        "paint": {"line-color": ["coalesce", ["get", "__rs_fill"], fb_fill], "line-width": fw, "line-offset": off}});
    let ratio = cfg["tunnel_casing_dash"].as_array().filter(|a| !a.is_empty()).cloned().unwrap_or_else(|| vec![json!(1), json!(1)]);
    let extra = th["tunnels"]["dash_extra_px"].clone();
    // _tunnel_casing_dash and _tunnel_fill_dash
    let cdash = |lid: &str, flt: &Value, on: bool| -> Vec<Value> {
        if !on {
            return Vec::new();
        }
        vec![json!({"id": lid, "type": "line", "source": "roads", "layout": tlay, "filter": flt,
                    "paint": {"line-color": th["tunnels"]["to"]["dash"], "line-width": crate::layers::plus_px(cw, |_| extra.clone(), None),
                              "line-offset": off, "line-dasharray": ratio}})]
    };
    let fdash = |lid: &str, flt: &Value, on: bool| -> Vec<Value> {
        let d: Vec<Value> = cfg["tunnel_fill_dash"].as_array().cloned().unwrap_or_default();
        if !on || d.is_empty() {
            return Vec::new();
        }
        vec![json!({"id": lid, "type": "line", "source": "roads", "layout": tlay, "filter": ["all", flt, ["!", ["to-boolean", ["get", "__rs_dash"]]]],
                    "paint": {"line-color": cfg["tunnel_fill_dash_color"], "line-width": fw, "line-offset": off,
                              "line-dasharray": d.iter().map(|x| json!(x.as_f64().unwrap_or(0.0))).collect::<Vec<_>>()}})]
    };
    let mut ls: Vec<Value> = Vec::new();
    ls.push(casing("roads-low-casing", &low));
    ls.extend(cdash("roads-low-casing-dash", &tunnel, f.any_tunnel));
    ls.push(fill("roads-low-fill", &low));
    ls.extend(fdash("roads-low-fill-pat", &tunnel, f.any_tunnel));
    ls.push(casing("roads-casing", &surface));
    ls.extend(cdash("roads-casing-dash", &tunnel_g, tun_g));
    ls.push(fill("roads-fill", &surface));
    ls.extend(fdash("roads-fill-pat", &tunnel_g, tun_g));
    ls.push(casing("roads-high-casing", &high));
    ls.extend(cdash("roads-high-casing-dash", &tunnel_h, tun_h));
    ls.push(fill("roads-high-fill", &high));
    ls.extend(fdash("roads-high-fill-pat", &tunnel_h, tun_h));
    ls.push(json!({"id": "roads-bridge-casing", "type": "line", "source": "roads", "layout": blay, "filter": bridge,
                   "paint": {"line-color": cfg["bridge_casing_color"], "line-width": bcw, "line-offset": off}}));
    ls.push(json!({"id": "roads-bridge-fill", "type": "line", "source": "roads", "layout": lay, "filter": bridge,
                   "paint": {"line-color": ["coalesce", ["get", "__rs_fill"], fb_fill], "line-width": fw, "line-offset": off}}));
    let (s_on, h_on) = (json!(["boolean", ["feature-state", "select"], false]), json!(["boolean", ["feature-state", "hover"], false]));
    ls.push(json!({"id": "roads-highlight", "type": "line", "source": "roads", "layout": lay,
                   "paint": {"line-color": ["case", s_on, f.select, f.hover],
                             "line-opacity": ["case", ["any", h_on, s_on], th["selection"]["opacity"], 0], "line-width": fw, "line-offset": off}}));
    // the 3D decks: the flat bridge lines below flat_below, the decks from it up (the deck layers come after the arrows, layers.rs)
    if let Some(fbz) = f.decks {
        let mut extra_hl = None;
        for l in ls.iter_mut() {
            if matches!(id(l), "roads-bridge-casing" | "roads-bridge-fill") {
                l["maxzoom"] = json!(fbz);
            } else if id(l) == "roads-highlight" {
                l["filter"] = json!(["!", bridge]);
                extra_hl = Some(with(l, vec![("id", json!("roads-highlight-bridge")), ("maxzoom", json!(fbz)), ("filter", bridge.clone())]));
                break;
            }
        }
        ls.extend(extra_hl);
    }
    // the dashed classes: a fill layer for each dash value, butt-capped, out of the solid fill and casing layers, under the casings
    if !f.dashes.is_empty() {
        let nod = json!(["!", ["to-boolean", ["get", "__rs_dash"]]]);
        let mut out = Vec::new();
        for l in ls {
            let lid = id(&l).to_string();
            let base_f = l.get("filter").cloned().unwrap_or(Value::Null);
            let butt = with(&l["layout"], vec![("line-cap", json!("butt"))]);
            let mut extra = Vec::new();
            if matches!(lid.as_str(), "roads-fill" | "roads-low-fill" | "roads-high-fill" | "roads-bridge-fill") {
                for (di, ds) in f.dashes.iter().enumerate() {
                    let flt = json!(["all", base_f, ["==", ["get", "__rs_dash"], ds]]);
                    if lid == "roads-bridge-fill" {
                        extra.push(with(&l, vec![("id", json!(format!("{lid}-deck{di}"))), ("layout", butt.clone()), ("filter", flt.clone()),
                            ("paint", with(&l["paint"], vec![("line-color", json!(["coalesce", ["get", "__rs_casing"], th["bridges"]["decks"]["underlay"]]))]))]));
                    }
                    let da: Vec<Value> = ds.split(',').filter_map(|x| x.trim().parse::<f64>().ok()).map(|x| json!(x)).collect();
                    extra.push(with(&l, vec![("id", json!(format!("{lid}-dash{di}"))), ("layout", butt.clone()), ("filter", flt),
                                             ("paint", with(&l["paint"], vec![("line-dasharray", Value::Array(da))]))]));
                }
                out.push(with(&l, vec![("filter", json!(["all", base_f, nod]))]));
            } else if matches!(lid.as_str(), "roads-casing" | "roads-casing-dash" | "roads-low-casing" | "roads-low-casing-dash" | "roads-high-casing"
                                            | "roads-high-casing-dash") {
                out.push(with(&l, vec![("filter", json!(["all", base_f, nod]))]));
            } else {
                out.push(l);
            }
            out.extend(extra);
        }
        for (casing_id, prefix) in [("roads-low-casing", "roads-low-fill-dash"), ("roads-high-casing", "roads-high-fill-dash"), ("roads-casing", "roads-fill-dash")] {
            let (moved, rest): (Vec<Value>, Vec<Value>) = out.into_iter().partition(|l| id(l).starts_with(prefix));
            out = rest;
            if !moved.is_empty() {
                let at = out.iter().position(|l| id(l) == casing_id).unwrap_or(out.len());
                out.splice(at..at, moved);
            }
        }
        ls = out;
    }
    // the end caps (cap_col): a butt-capped twin (-sq) and a square-capped one (-sx) of each band's casing and fill; an edge with two
    // different ends draws its fill from the halves (-h, -hsq, -hsx), and the whole-edge fill keeps it, transparent
    let p_true = |k: &str| f.rp.iter().any(|p| p.get(k).is_some_and(py_truth));
    let splits = p_true("__rs_split");
    if splits || p_true("__rs_cap") || f.parts_caps {
        let sq = json!(["to-boolean", ["get", "__rs_cap"]]);
        let sx = json!(["==", ["get", "__rs_cap"], "square"]);
        let squares = f.rp.iter().any(|p| ["__rs_cap", "__rs_cap0", "__rs_cap1"].iter().any(|k| p.get(k).is_some_and(|v| v == "square")));
        let whole = json!(["!", ["to-boolean", ["get", "__rs_split"]]]);
        let mut out = Vec::new();
        for l in ls {
            let lid = id(&l).to_string();
            if !matches!(lid.as_str(), "roads-low-casing" | "roads-low-fill" | "roads-casing" | "roads-fill" | "roads-high-casing" | "roads-high-fill") {
                out.push(l);
                continue;
            }
            let l = if splits && lid == "roads-fill" {
                let op = l["paint"].get("line-opacity").cloned().unwrap_or(json!(1));
                with(&l, vec![("paint", with(&l["paint"], vec![("line-opacity", json!(["case", ["!", whole], 0, op]))]))])
            } else { l };
            let flt = l["filter"].clone();
            let cap = |c: &str| with(&l["layout"], vec![("line-cap", json!(c))]);
            out.push(with(&l, vec![("filter", json!(["all", flt, ["!", sq]]))]));
            out.push(with(&l, vec![("id", json!(format!("{lid}-sq"))), ("layout", cap("butt")), ("filter", json!(["all", flt, sq, ["!", sx]]))]));
            if squares {
                out.push(with(&l, vec![("id", json!(format!("{lid}-sx"))), ("layout", cap("square")), ("filter", json!(["all", flt, sx]))]));
            }
            if splits && lid == "roads-fill" {
                for (sfx, c, h) in [("-h", "round", json!(["!", sq])), ("-hsq", "butt", json!(["all", sq, ["!", sx]])), ("-hsx", "square", sx.clone())] {
                    out.push(with(&l, vec![("id", json!(format!("{lid}{sfx}"))), ("source", json!("halves")), ("layout", cap(c)),
                                           ("filter", json!(["all", flt, h]))]));
                }
            }
        }
        ls = out;
    }
    // positions only: the three bands go
    ls.retain(|l| !id(l).starts_with("roads-low-") && !id(l).starts_with("roads-high-") && !matches!(id(l), "roads-bridge-casing" | "roads-bridge-fill"));
    // the bridge look of a position: a heavier black twin of each casing layer, and the bridge shadow (its own source) under them
    if f.rp.iter().any(|p| p.get("__rs_bridge").is_some_and(py_truth)) {
        let (mut out, mut at, mut twins) = (Vec::new(), 0, Vec::new());
        for l in ls {
            let lid = id(&l).to_string();
            if matches!(lid.as_str(), "roads-casing" | "roads-casing-sq" | "roads-casing-sx" | "roads-casing-dash") {
                if lid != "roads-casing-dash" {
                    twins.push(json!({"id": format!("{lid}-bridge"), "type": "line", "source": "roads", "layout": l["layout"],
                                      "filter": ["all", l["filter"], is_b],
                                      "paint": {"line-color": cfg["bridge_casing_color"], "line-width": bcw, "line-offset": off}}));
                }
                at = out.len();
                out.push(with(&l, vec![("filter", json!(["all", l["filter"], ["!", is_b]]))]));
            } else {
                out.push(l);
            }
        }
        if f.shadows {
            let offset: Vec<Value> = cfg["bridge_shadow_offset"].as_array().cloned().unwrap_or_default();
            twins.insert(0, json!({"id": "roads-casing-bridge-shadow", "type": "line", "source": "shadows", "layout": with(lay, vec![("line-cap", json!("butt"))]),
                                   "filter": ["literal", true],
                                   "paint": {"line-color": cfg["bridge_shadow_color"], "line-blur": cfg["bridge_shadow_blur"], "line-width": f.shadow_w,
                                             "line-translate": offset, "line-translate-anchor": "viewport"}}));
        }
        out.splice(at + 1..at + 1, twins);
        ls = out;
    }
    if f.divided {        // the round seams at the cuts only from zoom 17, the flat laps below it
        let seam = crate::layers::seam_filter();
        for l in ls.iter_mut().filter(|l| matches!(id(l), "roads-casing" | "roads-casing-bridge" | "roads-casing-sq" | "roads-casing-sq-bridge")) {
            *l = with(l, vec![("filter", json!(["all", l["filter"], seam]))]);
        }
    }
    let mut ls = level_layers(ls, f.levels, f.divided.then_some("casings"));
    if let Some(pw) = &f.pairs {        // a two-way pair's one casing as wide as its two directions
        for l in ls.iter_mut().filter(|l| l["source"] == "casings") {
            l["paint"]["line-width"] = pw(&l["paint"]["line-width"]);
        }
    }
    if let Some(fbz) = f.decks {
        for l in ls.iter_mut() {
            let lid = id(l).to_string();
            if lid.ends_with("-bridge") && lid.starts_with("roads-casing") {
                l["maxzoom"] = json!(fbz);
            } else if (lid.starts_with("roads-casing") || lid.starts_with("roads-fill")) && matches!(l["source"].as_str(), Some("roads" | "casings")) {
                l["filter"] = json!(["all", l["filter"], ["any", ["<", ["zoom"], fbz], ["!", is_b]]]);
            }
        }
    }
    ls
}

/// _level_layers: the casing and fill layers repeated for each position, in position order (an edge is in the casing layers of its
/// casing position, the fill layers of its fill position); the casing layers of the roads read the casing pieces when the casing is
/// divided.
fn level_layers(layers: Vec<Value>, levels: &[i64], casing_source: Option<&str>) -> Vec<Value> {
    let in_block = |l: &Value| CASING_FAMILY.contains(&id(l)) || FILL_FAMILY.contains(&id(l)) || id(l).starts_with("roads-fill-dash");
    let Some(first) = layers.iter().position(in_block) else { return layers };
    let (block, rest): (Vec<Value>, Vec<Value>) = layers.into_iter().partition(in_block);
    let mut groups = Vec::new();
    for &level in levels {
        for l in &block {
            let casing = CASING_FAMILY.contains(&id(l));
            let key = if casing { "__rs_cl" } else { "__rs_fl" };
            let mut kv = Vec::new();
            if let (Some(src), true) = (casing_source, casing && l.get("source").and_then(Value::as_str).unwrap_or("roads") == "roads") {
                kv.push(("source", json!(src)));
            }
            kv.push(("id", json!(level_id(id(l), level))));
            kv.push(("filter", json!(["all", l["filter"], ["==", ["coalesce", ["get", key], 0], level]])));
            groups.push(with(l, kv));
        }
    }
    let mut out: Vec<Value> = rest[..first].to_vec();
    out.extend(groups);
    out.extend(rest[first..].iter().cloned());
    out
}

/// The full look's arrows and names: for each position, its arrow layer right after its fill layers, its name layer after that.
/// `arrow(id, the position's condition)` and `label(id, filter)` make the layers.
pub fn annotate(layers: &mut Vec<Value>, levels: &[i64], arrow: Option<&dyn Fn(&str, Value) -> Value>, label: Option<&dyn Fn(&str, Value) -> Value>) {
    let fills_end = |layers: &[Value], pos: i64| {
        let fam: Vec<String> = FILL_FAMILY.iter().map(|x| level_id(x, pos)).collect();
        let dash = level_id("roads-fill", pos) + "-dash";
        layers.iter().enumerate().filter(|(_, l)| fam.iter().any(|x| x == id(l)) || id(l).starts_with(&dash)).map(|(i, _)| i).max()
    };
    let here = |pos: i64| json!(["==", ["coalesce", ["get", "fl"], 0], pos]);
    if let Some(arrow) = arrow {
        for &pos in levels {
            if let Some(i) = fills_end(layers, pos) {
                let lid = if pos == 0 { "roads-arrows".to_string() } else { format!("roads-arrows-lv{pos}") };
                layers.insert(i + 1, arrow(&lid, here(pos)));
            }
        }
    }
    if let Some(label) = label {
        for &pos in levels {
            let after = if pos == 0 { "roads-arrows".to_string() } else { format!("roads-arrows-lv{pos}") };
            let at = match layers.iter().position(|l| id(l) == after) {
                Some(i) => i + 1,
                None => match fills_end(layers, pos) { Some(i) => i + 1, None => continue },
            };
            let lid = if pos == 0 { "roads-labels".to_string() } else { format!("roads-labels-lv{pos}") };
            layers.insert(at, label(&lid, here(pos)));
        }
    }
}

/// _place_edge_overlays: the layers of the overlays on edges, for each position after its fills and before its arrows (else its names,
/// else right after its fills), by order, then by overlay; `pat_over`: the position's tunnel pattern after them.
pub fn place_edge_overlays(layers: &mut Vec<Value>, edge: &[(i64, i64, usize, Vec<Value>)], levels: &[i64], pat_over: bool) {
    for &pos in levels {
        let mut mine: Vec<&(i64, i64, usize, Vec<Value>)> = edge.iter().filter(|x| x.0 == pos).collect();
        if mine.is_empty() {
            continue;
        }
        mine.sort_by_key(|x| (x.1, x.2));
        let stops = if pos == 0 { ["roads-arrows".to_string(), "roads-labels".to_string()] } else { [format!("roads-arrows-lv{pos}"), format!("roads-labels-lv{pos}")] };
        let at = match stops.iter().find_map(|s| layers.iter().position(|l| id(l) == s)) {
            Some(i) => i,
            None => {
                let fam: Vec<String> = FILL_FAMILY.iter().map(|x| level_id(x, pos)).collect();
                let dash = level_id("roads-fill", pos) + "-dash";
                layers.iter().enumerate().filter(|(_, l)| fam.iter().any(|x| x == id(l)) || id(l).starts_with(&dash)).map(|(i, _)| i).max().map_or(layers.len(), |i| i + 1)
            }
        };
        let group: Vec<Value> = mine.iter().flat_map(|x| x.3.iter().cloned()).collect();
        let last = group.last().map(|l| id(l).to_string());
        layers.splice(at..at, group);
        if pat_over {
            let pid = level_id("roads-fill-pat", pos);
            let (pats, rest): (Vec<Value>, Vec<Value>) = std::mem::take(layers).into_iter().partition(|l| id(l) == pid);
            *layers = rest;
            if let Some(i) = last.and_then(|g| layers.iter().rposition(|l| id(l) == g)) {
                layers.splice(i + 1..i + 1, pats);
            }
        }
    }
}

/// _bridge_shadows: every part of a bridge (its casing pieces, or the edge) casts a shadow at its own casing number; the parts at one
/// number that touch are one line, and where three or more meet the two going on most straight (45 degrees at most) go on through; no
/// shadow over the last `trim_m` metres where the bridge comes down to the road. The union and the line merge are the engine's own, not
/// GEOS's: the lines have the same shape, their order and direction can differ.
fn bridge_shadows(roads: &[Feature], parts: Option<&[Piece]>, trim_m: f64, order: &[String]) -> Vec<Value> {
    let br: Vec<usize> = roads.iter().enumerate()
        .filter(|(_, f)| f.props.get("__rs_bridge").is_some_and(py_truth) && f.coords.as_ref().is_some_and(|c| c.len() >= 2)).map(|(i, _)| i).collect();
    if br.is_empty() {
        return Vec::new();
    }
    let line = |i: usize| roads[i].coords.as_ref().unwrap();
    let cl = |p: &Props| p.get("__rs_cl").and_then(Value::as_i64).unwrap_or(0);
    let pieces: Vec<(i64, Vec<Pt>)> = match parts {
        Some(ps) => ps.iter().filter(|p| p.props.get("__rs_edge").and_then(Value::as_u64).is_some_and(|e| br.contains(&(e as usize)))
                                          && !p.props.get("__rs_seam").is_some_and(py_truth) && p.coords.as_ref().is_some_and(|c| c.len() >= 2))
            .map(|p| (cl(&p.props), p.coords.clone().unwrap())).collect(),
        None => br.iter().map(|&i| (cl(&roads[i].props), line(i).clone())).collect(),
    };
    let mut lvls: Vec<i64> = pieces.iter().map(|p| p.0).collect();
    lvls.sort();
    lvls.dedup();
    let (mut chains, mut clvl): (Vec<Vec<Pt>>, Vec<i64>) = (Vec::new(), Vec::new());
    for lvl in lvls {
        for ch in line_merge(pieces.iter().filter(|p| p.0 == lvl).map(|p| p.1.clone()).collect()) {
            chains.push(ch);
            clvl.push(lvl);
        }
    }
    let key = |p: &Pt| ((p[0] * 1e7).round() as i64, (p[1] * 1e7).round() as i64);
    let kx0 = chains[0][0][1].to_radians().cos();
    let heading = |c: &[Pt], first: bool| {
        let (a, b) = if first { (c[0], c[1]) } else { (c[c.len() - 1], c[c.len() - 2]) };
        (b[1] - a[1]).atan2((b[0] - a[0]) * kx0)
    };
    let mut node: Vec<((i64, i64), Vec<(usize, bool)>)> = Vec::new();
    for (k, c) in chains.iter().enumerate() {
        for first in [true, false] {
            let kk = key(if first { &c[0] } else { &c[c.len() - 1] });
            match node.iter_mut().find(|n| n.0 == kk) {
                Some(n) => n.1.push((k, first)),
                None => node.push((kk, vec![(k, first)])),
            }
        }
    }
    let mut link: HashMap<(usize, bool), (usize, bool)> = HashMap::new();
    for (_, here) in &node {
        if here.len() < 3 {
            continue;
        }
        let mut free = here.clone();
        while free.len() >= 2 {
            let mut best: Option<(f64, usize, usize)> = None;
            for x in 0..free.len() {
                for y in x + 1..free.len() {
                    let ((k1, e1), (k2, e2)) = (free[x], free[y]);
                    if k1 == k2 || clvl[k1] != clvl[k2] {
                        continue;
                    }
                    let turn = 180.0 - (((heading(&chains[k1], e1) - heading(&chains[k2], e2)).to_degrees() + 180.0).rem_euclid(360.0) - 180.0).abs();
                    if turn <= 45.0 && best.is_none_or(|b| turn < b.0) {
                        best = Some((turn, x, y));
                    }
                }
            }
            let Some((_, x, y)) = best else { break };
            link.insert(free[x], free[y]);
            link.insert(free[y], free[x]);
            free = free.into_iter().enumerate().filter(|(j, _)| *j != x && *j != y).map(|(_, f)| f).collect();
        }
    }
    // walk each run of linked chains into one line
    let mut lines: Vec<(Vec<Pt>, i64)> = Vec::new();
    let mut seen = vec![false; chains.len()];
    for k in 0..chains.len() {
        if seen[k] {
            continue;
        }
        let (mut start, mut end) = (k, true);
        let mut guard = 0;
        while let Some(&(nk, ne)) = link.get(&(start, end)) {
            if nk == k || guard >= chains.len() {
                break;
            }
            (start, end) = (nk, !ne);
            guard += 1;
        }
        let (mut coords, mut ck, mut entry): (Vec<Pt>, Option<usize>, bool) = (Vec::new(), Some(start), end);
        while let Some(c) = ck.filter(|&c| !seen[c]) {
            seen[c] = true;
            let ch: Vec<Pt> = if entry { chains[c].clone() } else { chains[c].iter().rev().copied().collect() };
            coords.extend(if coords.is_empty() { &ch[..] } else { &ch[1..] });
            match link.get(&(c, !entry)) {
                Some(&(nk, ne)) => {
                    ck = Some(nk);
                    entry = ne;
                }
                None => ck = None,
            }
        }
        lines.push((coords, clvl[start]));
    }
    let near = |p: &Pt, i: usize| point_line(p, line(i)) < 1e-7;
    let mut out = Vec::new();
    // one order for every engine (render_web's too): each line from its lower end, by casing number, then by first point
    let mut lines: Vec<(Vec<Pt>, i64)> = lines.into_iter().map(|(mut c, l)| {
        if (c[0][0], c[0][1]) > (c[c.len() - 1][0], c[c.len() - 1][1]) {
            c.reverse();
        }
        (c, l)
    }).collect();
    lines.sort_by(|a, b| a.1.cmp(&b.1).then(a.0[0][0].total_cmp(&b.0[0][0])).then(a.0[0][1].total_cmp(&b.0[0][1])));
    for (c, lvl) in lines {
        // the bridge edges that the line goes along
        let member: Vec<usize> = br.iter().copied().filter(|&i| {
            c.windows(2).filter(|w| near(&w[0], i) && near(&w[1], i)).map(|w| (w[1][0] - w[0][0]).hypot(w[1][1] - w[0][1])).sum::<f64>() > 1e-6
        }).collect();
        if member.is_empty() {
            continue;
        }
        let cut = |p: &Pt| {
            let here: Vec<usize> = br.iter().copied().filter(|&i| near(p, i)).collect();
            let at_end = |i: usize| { let l = line(i); (l[0][0] - p[0]).hypot(l[0][1] - p[1]).min((l[l.len() - 1][0] - p[0]).hypot(l[l.len() - 1][1] - p[1])) < 1e-7 };
            if here.is_empty() || here.iter().any(|&i| !at_end(i)) {
                return 0.0;
            }
            let mut pairs: Vec<[(u64, u64); 2]> = here.iter().map(|&i| {
                let l = line(i);
                let (a, b) = ((l[0][0].to_bits(), l[0][1].to_bits()), (l[l.len() - 1][0].to_bits(), l[l.len() - 1][1].to_bits()));
                if a < b { [a, b] } else { [b, a] }
            }).collect();
            pairs.sort();
            pairs.dedup();
            if pairs.len() > 1 { 0.0 } else { trim_m }
        };
        let [lon0, lat0] = c[0];
        let (kx, ky) = (111320.0 * lat0.to_radians().cos(), 111320.0);
        let xy: Vec<Pt> = c.iter().map(|p| [(p[0] - lon0) * kx, (p[1] - lat0) * ky]).collect();
        let mut cum = vec![0.0];
        for w in xy.windows(2) {
            cum.push(cum[cum.len() - 1] + (w[1][0] - w[0][0]).hypot(w[1][1] - w[0][1]));
        }
        let n = cum[cum.len() - 1];
        let (a, b) = (cut(&c[0]), n - cut(&c[c.len() - 1]));
        if b - a <= 0.5 {
            continue;
        }
        let pts = part(&xy, &cum, a, b);
        let rank = |i: &usize| roads[*i].props.get("highway").and_then(Value::as_str).and_then(|h| order.iter().position(|o| o == h)).unwrap_or(order.len());
        let cls = member.iter().min_by_key(|i| rank(i)).map(|&i| roads[i].props.get("highway").cloned().unwrap_or(Value::Null)).unwrap_or(Value::Null);
        let r7 = |x: f64| (x * 1e7).round_ties_even() / 1e7;        // numpy's round(x, 7)
        let coords: Vec<[f64; 2]> = pts.iter().map(|p| [r7(p[0] / kx + lon0), r7(p[1] / ky + lat0)]).collect();
        let mut props = Map::new();
        props.insert("highway".into(), cls);
        props.insert("__rs_cl".into(), json!(lvl));
        props.insert("__rs_fl".into(), json!(lvl));
        props.insert("__rs_edges".into(), json!(member));
        out.push(json!({"type": "Feature", "properties": props, "geometry": {"type": "LineString", "coordinates": coords}}));
    }
    out
}

/// The distance from a point to a polyline (in the units of the coordinates).
fn point_line(p: &Pt, l: &[Pt]) -> f64 {
    l.windows(2).map(|w| {
        let (a, b) = (w[0], w[1]);
        let (dx, dy) = (b[0] - a[0], b[1] - a[1]);
        let t = if dx == 0.0 && dy == 0.0 { 0.0 } else { (((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)).clamp(0.0, 1.0) };
        (a[0] + t * dx - p[0]).hypot(a[1] + t * dy - p[1])
    }).fold(f64::INFINITY, f64::min)
}

/// _part: the polyline between the distances a and b along it (`cum`: the distance at each point).
fn part(xy: &[Pt], cum: &[f64], a: f64, b: f64) -> Vec<Pt> {
    let at = |d: f64| {
        let j = cum.partition_point(|&c| c <= d).saturating_sub(1).min(xy.len() - 2);
        let w = cum[j + 1] - cum[j];
        let t = if w > 0.0 { (d - cum[j]) / w } else { 0.0 };
        [xy[j][0] + t * (xy[j + 1][0] - xy[j][0]), xy[j][1] + t * (xy[j + 1][1] - xy[j][1])]
    };
    let (i0, i1) = (cum.partition_point(|&c| c <= a), cum.partition_point(|&c| c < b));
    let mut out = vec![at(a)];
    out.extend_from_slice(&xy[i0..i1.max(i0)]);
    out.push(at(b));
    out
}

/// unary_union then linemerge of lines: a line that is another's copy (the second direction of a two-way bridge) goes, and the lines
/// that meet end to end at a point where only they meet are one line.
// ponytail: no noding where two lines cross (GEOS's union cuts them there); two bridges of one number that cross in the middle are rare
fn line_merge(lines: Vec<Vec<Pt>>) -> Vec<Vec<Pt>> {
    // the points to 1e-7 degrees (the pieces' rounding): a head's cut end and the next edge's own first point are one node
    let key = |p: &Pt| ((p[0] * 1e7).round() as i64, (p[1] * 1e7).round() as i64);
    let mut uniq: Vec<Vec<Pt>> = Vec::new();
    for l in lines {
        let rev: Vec<Pt> = l.iter().rev().copied().collect();
        let same = |u: &Vec<Pt>| u.len() == l.len() && (u.iter().zip(&l).all(|(a, b)| key(a) == key(b)) || u.iter().zip(&rev).all(|(a, b)| key(a) == key(b)));
        if !uniq.iter().any(same) {
            uniq.push(l);
        }
    }
    let mut deg: HashMap<(i64, i64), usize> = HashMap::new();
    for l in &uniq {
        *deg.entry(key(&l[0])).or_default() += 1;
        *deg.entry(key(&l[l.len() - 1])).or_default() += 1;
    }
    let mut used = vec![false; uniq.len()];
    let mut out = Vec::new();
    let grow = |chain: &mut Vec<Pt>, used: &mut Vec<bool>| loop {
        let end = key(&chain[chain.len() - 1]);
        if deg[&end] != 2 {
            return;
        }
        let Some(j) = (0..uniq.len()).find(|&j| !used[j] && (key(&uniq[j][0]) == end || key(&uniq[j][uniq[j].len() - 1]) == end)) else { return };
        used[j] = true;
        let next: Vec<Pt> = if key(&uniq[j][0]) == end { uniq[j].clone() } else { uniq[j].iter().rev().copied().collect() };
        chain.extend_from_slice(&next[1..]);
    };
    for i in 0..uniq.len() {
        if used[i] {
            continue;
        }
        used[i] = true;
        let mut chain = uniq[i].clone();
        grow(&mut chain, &mut used);
        chain.reverse();
        grow(&mut chain, &mut used);
        chain.reverse();
        out.push(chain);
    }
    out
}
