//! The overlays: the base map's (full port step 3: mapstyle.map.edge_attach and feature_overlays) and the caller's own (render's
//! `overlays=`, `user_overlays`), then roadstyle's _edge_overlay and _overlay_layers: the overlay sources and their layers before the
//! placement and the passes (layers.rs).

use roadstyle_look::sections::Num;
use roadstyle_look::options::{EdgeLink, Overlay as Spec, OverlayKind, Placement, Select};
use roadstyle_model::mark::{self, Mark};
use crate::road::{Road, Roads};
use roadstyle_model::{Cell, Role};
use crate::roads::is_yes;
use crate::slots::point_line_dist;
use roadstyle_model::feature_table::{FeatureTable, GeomType};
use serde_json::{json, Map, Value};

const EDGE_ATTACHED: [&str; 2] = ["crossings", "traffic_signals"];
use roadstyle_levels::PATH_CLASSES;
const CLASS_RANK: [&str; 9] = ["motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street", "service"];

/// One overlay, as mapstyle's feature_overlays gives it to roadstyle (rs.Overlay), and its entry of the restyle's config (`l`).
pub struct Overlay {
    pub name: String,
    pub kind: &'static str, // fill | line | circle
    pub under: bool,
    pub edge: bool,
    pub color: Value,
    pub outline: Value,
    pub opacity: Value,
    pub width: Value,
    pub radius: Value,
    pub visible: bool,
    pub data: Data,
    pub l: Value,
    /// A caller's overlay: its map options (popup, color_column, width_m, dash, min_zoom, text, edge, ...; `data` taken out); None for the
    /// base map's.
    pub user: Option<Box<Spec>>,
    /// the roads' id column (edge_id_col), for the error of an overlay on edges when the roads have none
    pub edge_id_col: Option<String>,
    /// A base-map layer's start value of "clickable" for the page (mapstyle's rule); None: the overlay's own rule
    pub clickable: Option<bool>,
    /// A base-map layer's kinds with their counts, most first (mapstyle's Counter.most_common); empty: none
    pub kinds: Vec<(String, usize)>,
    /// A base-map layer's start values of its hover tooltip and its click popup (render_map's `interaction`); None: the overlay's own
    pub tooltip_on: Option<bool>,
    pub popup_on: Option<bool>,
}

/// An overlay's features: a caller's as a FeatureCollection, the base map's as a typed table (audit R10).
pub enum Data {
    Json(Value),
    Table(Box<FeatureTable>),
}

impl Data {
    /// detect_kind: the kind of the first feature with a geometry (polygon: fill, line: line, point: circle; else fill).
    fn detect_kind(&self) -> &'static str {
        match self {
            Data::Json(fc) => detect_kind(fc),
            Data::Table(t) => (0..t.len()).find_map(|r| t.geometries_of().kind(r).and_then(|k| kind_of_type(k.name()))).unwrap_or("fill"),
        }
    }
}

fn detect_kind(fc: &Value) -> &'static str {
    fc["features"].as_array().into_iter().flatten().find_map(|f| kind_of_type(f["geometry"]["type"].as_str().unwrap_or(""))).unwrap_or("fill")
}

fn kind_of_type(t: &str) -> Option<&'static str> {
    if t.contains("Polygon") { Some("fill") } else if t.contains("Line") { Some("line") } else if t.contains("Point") { Some("circle") } else { None }
}

/// _band: below (-1 ...), on (0) or over (1 ...) the ground: the OSM layer if it is a number, else 1 for a bridge, -1 for a tunnel.
fn band(r: Road) -> f64 {
    let p: std::collections::HashMap<&str, Value> = [("layer", Role::Layer), ("bridge", Role::Bridge), ("tunnel", Role::Tunnel)].into_iter()
        .filter_map(|(k, role)| r.role(role).map(|c| (k, c.to_value()))).collect();
    let layer = match p.get("layer") {
        Some(Value::String(s)) => s.trim().parse::<f64>().ok(),
        Some(Value::Number(n)) => n.as_f64(),
        _ => None,
    }
    .filter(|v| v.is_finite())
    .map_or(0.0, f64::trunc);
    let yes = |k: &str| match p.get(k) {
        None | Some(Value::Null) => false,
        Some(Value::String(s)) => !matches!(s.as_str(), "" | "no" | "None" | "nan"),
        Some(_) => true,
    };
    if layer != 0.0 { layer } else if yes("bridge") { 1.0 } else if yes("tunnel") { -1.0 } else { 0.0 }
}

/// edge_attach: `edge_id` on every crossing and traffic signal: of the streets within 1e-5 deg, the one drawn on top (the highest fill
/// number, then band, then class); else the nearest street within 3e-5 deg (within 2e-6 of the nearest); else the nearest road.
/// Returns the names of the layers that got one.
pub fn edge_attach(tables: &mut [(String, FeatureTable)], roads: &Roads) -> Result<Vec<String>, crate::Error> {
    let n = roads.len();
    let klass: Vec<f64> = roads.iter().map(|r| {
        let h = r.role(Role::Class).and_then(Cell::as_str).unwrap_or("");
        let h = h.strip_suffix("_link").unwrap_or(h);
        CLASS_RANK.iter().position(|c| *c == h).map_or(99.0, |i| (i + 1) as f64)
    }).collect();
    let fill: Vec<f64> = roads.iter().map(|r| r.role(Role::FillLevel).and_then(Cell::as_f64).unwrap_or(0.0)).collect();
    let bands: Vec<f64> = roads.iter().map(band).collect();
    // np.lexsort((-klass, band, fill))[::-1]: by fill, then band, then -klass, ascending and stable; reversed
    let mut order: Vec<usize> = (0..n).collect();
    order.sort_by(|&a, &b| fill[a].total_cmp(&fill[b]).then(bands[a].total_cmp(&bands[b])).then((-klass[a]).total_cmp(&-klass[b])).then(a.cmp(&b)));
    let mut rank = vec![0usize; n];
    for (k, &i) in order.iter().rev().enumerate() {
        rank[i] = k;
    }
    let street: Vec<bool> = roads.iter().map(|r| !r.role(Role::Class).and_then(Cell::as_str).is_some_and(|h| PATH_CLASSES.contains(&h))).collect();
    let topo = roads.topo();        // its R-tree: every road with a point or more
    let dist = |p: [f64; 2], i: usize| roads.line(i).map_or(f64::INFINITY, |c| point_line_dist(p, c));
    let within = |p: [f64; 2], d: f64| -> Vec<usize> {
        let mut v: Vec<usize> = topo.near([p[0] - d, p[1] - d], [p[0] + d, p[1] + d]).filter(|&i| dist(p, i) <= d).collect();
        v.sort();
        v
    };
    let mut done = Vec::new();
    for name in EDGE_ATTACHED {
        let Some((_, t)) = tables.iter_mut().find(|(n, _)| n == name).filter(|(_, t)| !t.is_empty()) else { continue };
        let g = t.geometries_of();
        let mut ids = Vec::with_capacity(t.len());
        for row in 0..t.len() {
            // a point's coordinates (another geometry: 0, 0[0] of a line is no number)
            let p = match g.kind(row) { Some(GeomType::Point) => g.parts(row).next().and_then(|mut r| r.next()).map_or([0.0, 0.0], |r| r[0]), _ => [0.0, 0.0] };
            let mut hits: Vec<usize> = within(p, 1e-5).into_iter().filter(|&i| street[i]).collect();
            if hits.is_empty() {
                let near = within(p, 3e-5);
                hits = if near.iter().any(|&i| street[i]) { near.into_iter().filter(|&i| street[i]).collect() } else { near };
                if !hits.is_empty() {
                    let d: Vec<f64> = hits.iter().map(|&i| dist(p, i)).collect();
                    let min = d.iter().copied().fold(f64::INFINITY, f64::min);
                    hits = hits.into_iter().zip(d).filter(|(_, d)| *d <= min + 2e-6).map(|(i, _)| i).collect();
                }
            }
            let j = if hits.is_empty() {
                (0..n).min_by(|&a, &b| dist(p, a).total_cmp(&dist(p, b))).unwrap_or(0) // query_nearest
            } else {
                *hits.iter().min_by_key(|&&i| rank[i]).unwrap()
            };
            ids.push(match roads.role(j, Role::EdgeId).map(Cell::to_value) { Some(Value::String(s)) => s, Some(v) => v.to_string(), None => String::new() });
        }
        t.set_column("edge_id", &ids.iter().map(|s| Cell::Str(s)).collect::<Vec<_>>(), true)?;
        done.push(name.to_string());
    }
    Ok(done)
}

/// A table of the style keyed by zoom (YAML numbers, text in JSON) as [[zoom, value], ...], the zooms as numbers.
fn zoom_pairs(t: &Value, f: impl Fn(f64) -> f64) -> Value {
    Value::Array(t.as_object().into_iter().flatten().map(|(z, v)| {
        let zf: f64 = z.parse().unwrap_or(0.0);
        let z = if zf.fract() == 0.0 { json!(zf as i64) } else { json!(zf) };
        json!([z, f(v.as_f64().unwrap_or(0.0))])
    }).collect())
}

/// feature_overlays: one overlay per layer (in the collections' order), its look from the theme's "features" style, and what the restyle adds
/// (colour by kind, outlines, textures, icons, zoom ranges, 3D); and the images of the layers there are.
/// render_map's `interaction` (`{layer: {clickable, tooltip, popup}}`) sets a layer's start values; a layer that the map does not have is
/// a warning, as mapstyle's.
pub fn feature_overlays(tables: Vec<(String, FeatureTable)>, look: &crate::Look, edge_attached: &[String], warnings: &mut Vec<String>)
                        -> (Vec<Overlay>, Map<String, Value>) {
    let interaction = look.map.base_map.as_ref().map(|b| b.layers.clone()).unwrap_or_default();
    let mut unknown: Vec<&String> = interaction.keys().filter(|k| !tables.iter().any(|(n, _)| n == *k)).collect();
    if !unknown.is_empty() {
        unknown.sort();
        warnings.push(format!("interaction: no layer {} on this map", unknown.iter().map(|s| s.as_str()).collect::<Vec<_>>().join(", ")));
    }
    let bm = look.sections.base_map.as_ref();
    let st = bm.map_or(&Value::Null, |b| &b.style);
    let specs = bm.and_then(|b| b.layers_yaml["layers"].as_array()).cloned().unwrap_or_default();
    let all_images = bm.and_then(|b| b.images.as_object()).cloned().unwrap_or_default();
    let (areas, lines, points, icon) = (&st["areas"], &st["lines"], &st["points"], &st["icon"]);
    let mut out = Vec::new();
    let mut images = Map::new();
    for (name, t) in tables {
        let spec = specs.iter().find(|s| s["name"] == name.as_str()).cloned().unwrap_or(Value::Null);
        let kind = spec["kind"].as_str().unwrap_or("");
        let ov_kind = match kind { "polygon" => "fill", "line" => "line", _ => "circle" };
        let ticked = spec.get("ticked").is_none_or(|v| v != false);
        let mut l = json!({"label": name, "kind": ov_kind, "ticked": ticked});
        let mut ov = Overlay { name: name.clone(), kind: ov_kind, under: kind != "point", edge: edge_attached.contains(&name), color: Value::Null,
                               outline: Value::Null, opacity: Value::Null, width: Value::Null, radius: Value::Null, visible: ticked, data: Data::Json(Value::Null),
                               l: Value::Null, user: None, edge_id_col: None, clickable: Some(clickable(&name, kind)), kinds: kinds(&t),
                               tooltip_on: None, popup_on: None };
        // mapstyle's start values (clickable by the rule above, no tooltip, the popup), with the layer's `interaction` over them
        if let Some(i) = interaction.get(&name) {
            let set = |k: &str| i.get(k).map(|v| is_yes(Some(v)));
            ov.clickable = set("clickable").or(ov.clickable);
            (ov.tooltip_on, ov.popup_on) = (set("tooltip"), set("popup"));
        }
        if name == "landcover" {
            let mut fills = areas["landcover"].as_object().cloned().unwrap_or_default();
            let default = fills.shift_remove("default").unwrap_or(Value::Null);
            ov.color = default.clone();
            ov.opacity = json!(1.0);
            ov.width = json!(1);
            l["color_by"] = json!({"map": fills, "default": default});
            l["outline_by"] = json!({"map": st["landcover_outline"], "default": "rgba(0,0,0,0)"});
            let mut pats = Map::new();
            for k in st["landcover_pattern"].as_object().into_iter().flatten().filter(|(_, p)| !p.is_null()).map(|(k, _)| k) {
                let id = format!("ms-pat-{k}");
                if let Some(img) = all_images.get(&id) {
                    images.insert(id.clone(), img.clone());
                }
                pats.insert(k.clone(), id.into());
            }
            l["patterns"] = Value::Object(pats);
            l["pattern_style"] = st["landcover_pattern_style"].clone();   // a theme's: the textures' first zoom and opacity by zoom
        } else if kind == "polygon" {
            let a = areas.get(&name).cloned().unwrap_or(json!({}));
            ov.color = a.get("fill").cloned().unwrap_or(Value::Null);
            ov.outline = a.get("outline").cloned().unwrap_or(Value::Null);
            ov.opacity = a.get("opacity").cloned().unwrap_or(json!(1.0));
            ov.width = json!(0.5);
            l["min_zoom"] = a.get("min_zoom").cloned().unwrap_or(Value::Null);
            if !t.is_empty() && t.has_key(0, "height") {
                l["extrude"] = json!({"color": a.get("fill").cloned().unwrap_or(Value::Null), "opacity": st["buildings_3d"]["opacity"]});
            }
        } else if kind == "line" {
            let ln = lines.get(&name).cloned().unwrap_or(json!({}));
            ov.color = ln.get("color").cloned().unwrap_or(Value::Null);
            ov.width = ln.get("width").cloned().unwrap_or(Value::Null);
            l["dash"] = ln.get("dash").cloned().unwrap_or(Value::Null);
            // width_zoom: px by zoom (a road's width), the zooms in order
            l["width_zoom"] = match ln.get("width_zoom").and_then(Value::as_object).filter(|m| !m.is_empty()) {
                None => Value::Null,
                Some(m) => {
                    let mut pairs: Vec<(f64, &str, &Value)> = m.iter().map(|(z, w)| (z.parse::<f64>().unwrap_or(0.0), z.as_str(), w)).collect();
                    pairs.sort_by(|a, b| a.0.total_cmp(&b.0));
                    Value::Array(pairs.into_iter().map(|(z, _, w)| json!([if z.fract() == 0.0 { json!(z as i64) } else { json!(z) }, w])).collect())
                }
            };
        } else {
            let mut p = points["default"].as_object().cloned().unwrap_or_default();
            for (k, v) in points.get(&name).and_then(Value::as_object).into_iter().flatten() {
                p.insert(k.clone(), v.clone());
            }
            ov.color = p.get("color").cloned().unwrap_or(Value::Null);
            ov.radius = json!(4);
            l["min_zoom"] = p.get("min_zoom").cloned().unwrap_or(Value::Null);
            if p.get("icon").is_some_and(|v| is_yes(Some(v))) {
                let id = format!("ms-icon-{name}");
                if let Some(img) = all_images.get(&id) {
                    images.insert(id.clone(), img.clone());
                }
                let size = p.get("size").and_then(Value::as_f64).unwrap_or(1.0);
                l["icon"] = json!({"image": id, "opacity": icon["opacity"], "size": zoom_pairs(&icon["size"], |px| px * size / 48.0)});
            }
        }
        ov.data = Data::Table(Box::new(t));
        ov.l = l;
        out.push(ov);
    }
    (out, images)
}

/// mapstyle's start value of a base-map layer's clickable: the decoration (landcover, water, paved and the lines but the raceway and the
/// other ways) is not, so that a click reaches the road under it.
fn clickable(name: &str, kind: &str) -> bool {
    !(matches!(name, "landcover" | "water" | "paved") || (kind == "line" && !matches!(name, "raceway" | "other_ways")))
}

/// The kinds of a layer's features with their counts, most first, a tie in the order in which they come first (Counter.most_common).
fn kinds(t: &FeatureTable) -> Vec<(String, usize)> {
    let mut out: Vec<(String, usize)> = Vec::new();
    for k in (0..t.len()).filter_map(|r| t.get(r, "kind").and_then(Cell::as_str)) {
        match out.iter_mut().find(|(x, _)| x == k) {
            Some(e) => e.1 += 1,
            None => out.push((k.to_string(), 1)),
        }
    }
    out.sort_by_key(|k| std::cmp::Reverse(k.1));
    out
}

/// _ov_hl: an interactive overlay's colour lights up on hover and select (feature-state).
fn ov_hl(base: &Value, hover: &Value, select: &Value) -> Value {
    json!(["case", ["boolean", ["feature-state", "select"], false], select, ["boolean", ["feature-state", "hover"], false], hover, base])
}

fn or(v: &Value, d: &Value) -> Value {
    if v.is_null() || v.as_str() == Some("") { d.clone() } else { v.clone() }
}

/// The first point of a GeoJSON geometry's coordinates.
fn first_point(c: &Value) -> Option<&Value> {
    let mut c = c;
    while c.get(0).is_some_and(Value::is_array) {
        c = &c[0];
    }
    c.as_array().filter(|a| a.len() >= 2).map(|_| c)
}

/// render's `overlays=`: the caller's overlays (the Python binding gives each rs.Overlay as its fields, its style of the settings filled in,
/// and its data as a FeatureCollection in `fc`), numbered after the base map's (`first`). _bake_wm: a width in metres on each feature.
pub fn user_overlays(specs: &[Spec], first: usize) -> Result<Vec<Overlay>, crate::Error> {
    let mut out = Vec::new();
    for (k, u) in specs.iter().enumerate() {
        let mut fc = u.data.clone();
        let kind: &'static str = match u.kind {
            None => detect_kind(&fc),
            Some(OverlayKind::Fill) => "fill",
            Some(OverlayKind::Line) => "line",
            Some(OverlayKind::Circle) => "circle",
            Some(OverlayKind::Text) => "text",
        };
        if kind == "text" && u.text.as_ref().and_then(|t| t.column.as_ref()).is_none() {
            return Err(crate::error::options("an overlay of kind 'text' needs text_col (the property that holds the text)"));
        }
        if let Some(wm) = u.width_m {
            for f in fc["features"].as_array_mut().into_iter().flatten() {
                let lat = first_point(&f["geometry"]["coordinates"]).and_then(|p| p[1].as_f64()).unwrap_or(0.0);
                if !f["properties"].is_object() {
                    f["properties"] = json!({});
                }
                f["properties"][Mark::WidthM.name()] = json!(wm / lat.to_radians().cos().max(0.01));
            }
        }
        let user = Spec { data: Value::Null, ..u.clone() };
        // export's _tag_groups: the group of the overlay's layers is its label, else "overlay <i>"
        let name = u.label.as_deref().filter(|l| !l.is_empty()).map_or_else(|| format!("overlay {}", first + k), String::from);
        out.push(Overlay { name, kind, under: u.placement == Placement::Under, edge: u.edge.as_ref().is_some_and(|e| !e.column.is_empty()),
                           color: css(u.color.as_ref()), outline: css(u.outline.as_ref()), opacity: number(u.opacity), width: number(u.width),
                           radius: number(u.radius), visible: u.visible, data: Data::Json(fc), l: Value::Null, user: Some(Box::new(user)),
                           edge_id_col: None, clickable: None, kinds: Vec::new(), tooltip_on: None, popup_on: None });
    }
    Ok(out)
}

/// A colour of the map options as the style writes it (its text), or null.
fn css(c: Option<&roadstyle_look::color::Color>) -> Value {
    c.map_or(Value::Null, |c| c.css().into())
}

/// A number of the map options as the style writes it (crate::given: a whole number as an integer), or null.
fn number(v: Option<f64>) -> Value {
    v.map_or(Value::Null, crate::given)
}

/// _wm_width_expr: a line width in px for the metres in __rs_wm, exact from `min_zoom` (default 0) to 22 (base-2 interpolation).
fn wm_width_expr(min_zoom: &Value) -> Value {
    let mut e = vec![json!("interpolate"), json!(["exponential", 2]), json!(["zoom"])];
    let z0 = min_zoom.as_f64().unwrap_or(0.0).max(0.0);
    let zs: Vec<f64> = if z0 == 22.0 { vec![22.0] } else { vec![z0.min(22.0), z0.max(22.0)] };
    for z in zs {
        e.push(json!(z));
        e.push(json!(["*", ["get", Mark::WidthM.name()], crate::layers::round_to(512.0 * 2f64.powf(z) / 40075016.686, 6)]));
    }
    Value::Array(e)
}

/// _overlay_layers: the layer(s) of one overlay source: a fill and its outline, a circle, a line or a text. An interactive overlay (a popup
/// or none given, or an item selected itself) lights up on hover and select (feature-state).
pub fn overlay_layers(sid: &str, ov: &Overlay, look: &crate::Look) -> Vec<Value> {
    let (s, u) = (&look.sections, ov.user.as_deref());
    let c = &s.overlays;
    // render's hover_color / select_color go to the overlays too (_build_overlays), else the theme's selection colours
    let it = &look.map.interaction;
    let pick = |c: Option<&roadstyle_look::color::Color>, theme| json!(c.unwrap_or(theme).css());
    let (hover, select) = (&pick(it.hover_color.as_ref(), &s.selection.hover), &pick(it.select_color.as_ref(), &s.selection.select));
    let mut base = or(&ov.color, &json!(c.color));
    if let Some(cc) = u.and_then(|u| u.color_column.as_deref()).filter(|s| !s.is_empty()) {        // a colour per feature (null / missing: the overlay's)
        base = json!(["coalesce", ["get", cc], base]);
    }
    let width = match u.filter(|u| u.width_m.is_some()) { Some(u) => wm_width_expr(&number(u.min_zoom)), None => or(&ov.width, &json!(c.width)) };
    let radius = or(&ov.radius, &json!(c.radius));
    let popup = u.and_then(|u| u.popup.as_ref());
    let interactive = popup.is_none_or(|a| !a.is_empty()) || (u.is_some_and(|u| u.select == Select::Item) && ov.edge);
    let col = if interactive { ov_hl(&base, hover, select) } else { base.clone() };
    let lay = json!({"visibility": if ov.visible { "visible" } else { "none" }});
    let op = |d: &Num| or(&ov.opacity, &json!(d));
    let dash: Option<Value> = u.and_then(|u| u.dash.as_ref()).filter(|a| !a.is_empty()).map(|a| Value::Array(a.iter().map(|x| json!(x)).collect()));
    // a layer's keys in a fixed order: id, type, source, then the zoom range before or after the layout
    let layer = |id: String, t: &str, zooms_first: bool, layout: Value, mut paint: Map<String, Value>, paint_dash: bool| {
        let mut l = Map::new();
        l.insert("id".into(), id.into());
        l.insert("type".into(), t.into());
        l.insert("source".into(), sid.into());
        let zooms = |l: &mut Map<String, Value>| {
            for (k, z) in [("minzoom", u.and_then(|u| u.min_zoom)), ("maxzoom", u.and_then(|u| u.max_zoom))] {
                if let Some(z) = z {
                    l.insert(k.into(), json!(z));
                }
            }
        };
        if zooms_first {
            zooms(&mut l);
            l.insert("layout".into(), layout);
        } else {
            l.insert("layout".into(), layout);
            zooms(&mut l);
        }
        if let (true, Some(d)) = (paint_dash, &dash) {     // the dash right after the width
            paint = std::mem::take(&mut paint).into_iter().flat_map(|(k, v)| {
                let after = (k == "line-width").then(|| ("line-dasharray".to_string(), d.clone()));
                std::iter::once((k, v)).chain(after)
            }).collect();
        }
        l.insert("paint".into(), Value::Object(paint));
        Value::Object(l)
    };
    let pm = |v: Value| v.as_object().cloned().unwrap();
    match ov.kind {
        "text" => {
            let along = ov.data.detect_kind() != "circle";
            let mut layout = pm(lay);
            layout.insert("symbol-placement".into(), if along { "line-center" } else { "point" }.into());
            let text = u.and_then(|u| u.text.as_ref());
            layout.insert("text-field".into(), json!(["get", text.and_then(|t| t.column.as_deref())]));
            layout.insert("text-font".into(), json!(s.labels.font));
            layout.insert("text-size".into(), or(&number(text.and_then(|t| t.size)), &json!(c.text_size)));
            layout.insert("text-max-angle".into(), json!(c.text_max_angle));
            layout.insert("text-padding".into(), json!(c.text_padding));
            let mut paint = Map::new();
            paint.insert("text-color".into(), or(&css(text.and_then(|t| t.color.as_ref())), &base));
            if let Some(h) = text.and_then(|t| t.halo.as_ref()).filter(|h| !h.css().is_empty()) {
                paint.insert("text-halo-color".into(), h.css().into());
                paint.insert("text-halo-width".into(), json!(c.text_halo_width));
            }
            vec![layer(format!("{sid}-text"), "symbol", true, Value::Object(layout), paint, false)]
        }
        "fill" => vec![
            layer(format!("{sid}-fill"), "fill", false, lay.clone(), pm(json!({"fill-color": col, "fill-opacity": op(&c.fill_opacity)})), false),
            layer(format!("{sid}-outline"), "line", false, lay,
                  pm(json!({"line-color": or(&ov.outline, &base), "line-width": width, "line-opacity": c.outline_opacity})), true),
        ],
        "circle" => vec![layer(format!("{sid}-circle"), "circle", false, lay,
                               pm(json!({"circle-radius": radius, "circle-color": col, "circle-opacity": op(&c.circle_opacity),
                                         "circle-stroke-color": or(&ov.outline, &json!(c.circle_stroke)),
                                         "circle-stroke-width": or(&ov.width, &json!(c.circle_stroke_width))})), false)],
        _ => {
            let mut l = pm(lay);
            l.insert("line-cap".into(), json!(if dash.is_some() { &s.tunnels.cap } else { &s.roads.cap }));
            vec![layer(format!("{sid}-line"), "line", true, Value::Object(l),
                       pm(json!({"line-color": col, "line-width": width, "line-opacity": op(&c.line_opacity)})), true)]
        }
    }
}

/// _eid: an edge id as text, the same for an integer, a float with a whole value and a text (ids past 2**53 match).
pub fn eid<'a>(v: impl Into<Cell<'a>>) -> String {
    match &v.into().to_value() {
        Value::String(s) => s.clone(),
        Value::Number(n) if n.is_f64() && n.as_f64().is_some_and(|f| f.fract() == 0.0 && f.abs() < 1e18) => (n.as_f64().unwrap() as i64).to_string(),
        Value::Null => "None".into(),
        v => v.to_string(),
    }
}

/// _edge_overlay: on each feature of an overlay on a street, what it takes from its edge (`roads`: the roads source's properties, by edge id
/// as text, _eid); returns the (fill number, order) pairs, sorted. The base map's overlays name their edge in `edge_id`, a caller's in its
/// `edge_col` (and its order in `order_col`).
pub fn edge_overlay(ov: &mut Overlay, roads: &std::collections::HashMap<String, Road>) -> Result<Vec<(i64, i64)>, crate::Error> {
    let link = ov.user.as_ref().and_then(|u| u.edge.as_ref());
    let col = link.map_or("edge_id", |e| e.column.as_str()).to_string();
    if roads.is_empty() && ov.user.is_some() {
        let id = ov.edge_id_col.as_deref().unwrap_or("edge_id");
        return Err(crate::error::column(id, "an overlay with edge_col needs the roads' id column (edge_id_col), and it is not in the edges"));
    }
    let order_col = link.and_then(|e| e.order_column.clone());
    let mut orders = std::collections::BTreeSet::new();
    let mut unknown = Vec::new();
    // what a feature takes from its edge (`e`: its edge id; `order`: its order_col value), in the order of the keys; None: no such edge
    let mut marks = |e: String, order: Option<f64>| -> Option<[Value; 6]> {
        let Some(&r) = roads.get(&e) else {
            unknown.push(e);
            return None;
        };
        let o = order.filter(|o| o.is_finite()).map_or(0, |o| o.trunc() as i64);
        let fl = r.get(Mark::FillLevel.name()).and_then(Cell::as_i64).unwrap_or(0);
        orders.insert((fl, o));
        Some([r.get(Mark::Edge.name()).map_or(Value::Null, Cell::to_value), fl.into(), o.into(), r.cls(), r.get("lvl").map_or(json!(0), Cell::to_value),
              if is_yes(r.get(Mark::Tunnel.name())) { true.into() } else { Value::Null }])
    };
    const KEYS: [&str; 6] = [Mark::Edge.name(), Mark::FillLevel.name(), Mark::ItemOrder.name(), Mark::Class.name(), Mark::ItemLvl.name(), Mark::Tunnel.name()];
    match &mut ov.data {
        Data::Json(fc) => for f in fc["features"].as_array_mut().into_iter().flatten() {
            if !f["properties"].is_object() {
                f["properties"] = json!({});
            }
            let p = f["properties"].as_object_mut().unwrap();
            let order = order_col.as_ref().and_then(|c| p.get(c)).and_then(Value::as_f64);
            let Some(m) = marks(eid(p.get(&col).unwrap_or(&Value::Null)), order) else { continue };
            for (k, v) in KEYS.into_iter().zip(m).filter(|(k, v)| *k != Mark::Tunnel.name() || !v.is_null()) {      // __rs_tunnel only when true
                p.insert(k.into(), v);
            }
        },
        Data::Table(t) => {
            let rows: Vec<Option<[Value; 6]>> = (0..t.len()).map(|r| {
                let order = order_col.as_ref().and_then(|c| t.get(r, c)).and_then(Cell::as_f64);
                marks(eid(t.get(r, &col).unwrap_or(Cell::Null)), order)
            }).collect();
            if unknown.is_empty() {
                for (k, key) in KEYS.into_iter().enumerate() {
                    let cells: Vec<Cell> = rows.iter().map(|m| m.as_ref().map_or(Cell::Null, |m| Cell::from(&m[k]))).collect();
                    t.set_column(key, &cells, key != Mark::Tunnel.name())?;
                }
            }
        }
    }
    if !unknown.is_empty() {        // the names, each in quotes
        let label = ov.user.as_ref().and_then(|u| u.label.as_deref()).unwrap_or("");
        let first: Vec<String> = unknown.iter().take(5).map(|u| format!("'{u}'")).collect();
        return Err(crate::error::data(format!("overlay {label}: {} feature(s) have an '{col}' that is not an edge of the roads (first: [{}])", unknown.len(), first.join(", "))));
    }
    Ok(orders.into_iter().collect())
}

/// The text of a dash value: a whole number without its ".0".
fn g_text(x: f64) -> String {
    if x.fract() == 0.0 && x.abs() < 1e15 { format!("{}", x as i64) } else { format!("{x}") }
}

/// Is an overlay's line drawn as items in the road layer (simple mode): on edges, a line, with a width in metres.
pub fn metre_items(ov: &Overlay) -> bool {
    let u = ov.user.as_deref();
    ov.edge && ov.kind == "line"
        && (u.is_some_and(|u| u.width_m.is_some()) || u.and_then(|u| u.edge.as_ref()?.width_m_column.as_deref()).is_some_and(|c| !c.is_empty()))
}

/// _item_pieces: the line items of the overlay `i` on its edges (after edge_overlay) as pieces of the one road layer (`__rs_k` 5): what the
/// filters read from their edge, `lvl`, their colour `__rs_ic`, their width and offset in metres over cos(latitude) (`__rs_iwm`,
/// `__rs_iom`, also on the overlay's own features) and their dash as text.
pub fn item_pieces(ov: &mut Overlay, i: usize, look: &crate::Look) -> Result<Vec<crate::simple::Item>, crate::Error> {
    let default = json!(look.sections.overlays.color);
    let u = ov.user.as_deref().cloned().unwrap_or_default();
    let col = |c: Option<&String>| c.filter(|c| !c.is_empty()).cloned();
    let link = u.edge.clone().unwrap_or_default();
    let (wcol, ocol, dcol, ccol) = (col(link.width_m_column.as_ref()), col(link.offset_m_column.as_ref()), col(link.dash_column.as_ref()),
                                    col(u.color_column.as_ref()));
    let label = u.label.as_deref().filter(|l| !l.is_empty()).map_or_else(|| i.to_string(), String::from);
    let mut out = Vec::new();
    let Data::Json(fc) = &mut ov.data else { return Err(crate::Error::Unsupported(crate::Unsupported::TableItems { overlay: label.to_string() })) };
    for (j, f) in fc["features"].as_array_mut().into_iter().flatten().enumerate() {
        let g = f["geometry"].clone();
        let p = f["properties"].as_object_mut().ok_or_else(|| crate::error::data("an overlay feature with no properties"))?;
        let w = match &wcol { Some(c) => p.get(c).cloned().unwrap_or(Value::Null), None => number(u.width_m) };
        let w = w.as_f64().filter(|w| w.is_finite())
            .ok_or_else(|| crate::error::data(format!("overlay {label}: item {j} has no width in metres ({})", wcol.as_deref().unwrap_or("width_m"))))?;
        let o = ocol.as_ref().and_then(|c| p.get(c)).and_then(Value::as_f64).filter(|o| o.is_finite());
        let line: Vec<crate::simple::Pt> = match g["type"].as_str() {
            Some("LineString") => serde_json::from_value(g["coordinates"].clone()).map_err(|e| crate::error::data(format!("overlay {label}: item {j}: {e}")))?,
            Some("MultiLineString") => return Err(crate::Error::Unsupported(crate::Unsupported::MultiLineItem { overlay: label.to_string(), item: j })),
            _ => Vec::new(),
        };
        let lat = if line.is_empty() { 0.0 } else { line.iter().map(|c| c[1]).sum::<f64>() / line.len() as f64 };
        let sec = 1.0 / lat.to_radians().cos().max(0.01);
        let d = dcol.as_ref().and_then(|c| p.get(c)).filter(|d| !d.is_null()).cloned().unwrap_or_else(|| json!(u.dash));
        p.insert(Mark::ItemWidthM.name().into(), json!(crate::layers::round_to(w * sec, 4)));
        p.insert(Mark::ItemOffsetM.name().into(), o.map_or(json!(0), |o| json!(crate::layers::round_to(o * sec, 4))));
        let mut q: crate::props::Props<'static> = p.iter().filter(|(k, _)| k.starts_with(mark::PREFIX)).map(|(k, v)| (std::borrow::Cow::Owned(k.clone()), v.clone())).collect();
        q.insert("lvl", p.get(Mark::ItemLvl.name()).cloned().unwrap_or(json!(0)));
        q.insert(Mark::PieceKind.name(), json!(5));
        q.insert(Mark::ItemOverlay.name(), json!(i));
        q.insert(Mark::Item.name(), json!(j));
        let ic = ccol.as_ref().and_then(|c| p.get(c)).filter(|c| is_yes(Some(c))).cloned().unwrap_or_else(|| or(&css(u.color.as_ref()), &default));
        q.insert(Mark::ItemColor.name(), ic);
        // the road layer's dash pattern is a text ("3,3"), as a dashed class's __rs_dash
        let dash: Vec<String> = match &d {
            Value::String(t) => t.split(',').filter_map(|x| x.trim().parse::<f64>().ok()).map(g_text).collect(),
            Value::Array(a) => a.iter().filter_map(Value::as_f64).map(g_text).collect(),
            _ => Vec::new(),
        };
        if !dash.is_empty() {
            q.insert(Mark::Dash.name(), json!(dash.join(",")));
        }
        out.push(crate::simple::Item { props: q, coords: (!line.is_empty()).then_some(line) });
    }
    Ok(out)
}

/// _road_items: render's `items=` (the road's own line items, as a FeatureCollection) as pieces of the road layer, with no source or layer
/// of their own: each names its road in the roads' id column and has `width_m`, and can have `order`, `offset_m`, `color`, `dash`, `pick` (a
/// picked item is clicked and lit as itself, with its own fields) and `minzoom` (`__rs_imz`). `k`: the items' overlay number.
pub fn road_items(fc: &Value, roads: &std::collections::HashMap<String, Road>, edge_col: &str, k: usize, look: &crate::Look)
                  -> Result<Vec<crate::simple::Item>, crate::Error> {
    let mut ov = Overlay { name: "items".into(), kind: "line", under: false, edge: true, color: Value::Null, outline: Value::Null, opacity: Value::Null,
                           width: Value::Null, radius: Value::Null, visible: true, data: Data::Json(fc.clone()), l: Value::Null, clickable: None, kinds: Vec::new(), tooltip_on: None, popup_on: None,
                           user: Some(Box::new(Spec { label: Some("items".into()), color_column: Some("color".into()),
                                                      edge: Some(EdgeLink { column: edge_col.into(), order_column: Some("order".into()),
                                                                            width_m_column: Some("width_m".into()), offset_m_column: Some("offset_m".into()),
                                                                            dash_column: Some("dash".into()) }), ..Spec::default() })),
                           edge_id_col: None };
    edge_overlay(&mut ov, roads)?;
    let mut out = item_pieces(&mut ov, k, look)?;
    let Data::Json(fc) = &ov.data else { unreachable!("road_items makes a JSON overlay") };
    let feats = fc["features"].as_array().cloned().unwrap_or_default();
    for q in out.iter_mut() {
        let j = q.props.get(Mark::Item.name()).and_then(Value::as_u64).unwrap_or(0) as usize;
        let src = feats[j]["properties"].as_object().cloned().unwrap_or_default();
        if is_yes(src.get("pick")) {
            for (c, v) in src.iter().filter(|(c, _)| !c.starts_with(mark::PREFIX) && *c != "pick") {
                q.props.insert(c, v.clone());
            }
            q.props.insert(Mark::Pick.name(), json!(true));
        }
        if let Some(z) = src.get("minzoom").and_then(Value::as_f64).filter(|z| z.is_finite()) {
            q.props.insert(Mark::ItemMinZoom.name(), json!(z));
        }
    }
    Ok(out)
}
