//! render_edges' flat keywords (`args` of a look of version 1) as nested map options.

use super::*;
use serde_json::json;

/// The fields of render_edges' flat keywords (`flat`).
pub(super) struct Flat {
    /// the sparse options: the fields that the keywords set
    pub(super) out: Map<String, Value>,
    /// the paths of those fields, in order
    pub(super) paths: Vec<String>,
    /// the names of the keywords that are not map options
    pub(super) rest: Vec<String>,
}

/// The fields of render_edges' flat keywords `args`.
pub(super) fn flat(args: &Value) -> Result<Flat, Error> {
    let empty = Map::new();
    let a = match args {
        Value::Object(a) => a,
        Value::Null => &empty,
        other => return Err(Error::Options(format!("map options: a mapping of keywords, not {other}"))),
    };
    let mut out = Map::new();
    let mut paths: Vec<String> = Vec::new();
    let mut rest = Vec::new();
    for (k, v) in a {
        if v.is_null() && k != "minzoom" {
            continue;       // a keyword given as None: its default
        }
        if let Some(path) = FLAT.iter().find(|f| f.0 == k).map(|f| f.1) {
            put(&mut out, &mut paths, path, v.clone());
        } else if !SPECIAL.contains(&k.as_str()) {
            rest.push(k.clone());
        }
    }
    let get = |k: &str| a.get(k).filter(|v| !v.is_null());
    // the drawing positions: stored ({edge_hash, n_edges}), the tags rule ("tags"), solved whatever the input has ("solve", 2026-10-25:
    // the engine reads an input's contract columns casing_level / fill_level when no keyword is given), the caller's columns, else solved
    let levels = match (get("levels"), out.get("columns").and_then(|c| c.get("levels"))) {
        (Some(Value::Object(m)), _) => json!({"stored": m}),
        (Some(Value::String(s)), _) if s == "tags" || s == "solve" => json!(s),
        (Some(other), _) => return Err(Error::Options(format!("levels: {{edge_hash, n_edges}}, \"tags\" or \"solve\", not {other}"))),
        (None, Some(c)) if c.get("casing_level").is_some() || c.get("fill_level").is_some() => json!("given"),
        (None, _) => Value::Null,        // the default (auto)
    };
    if !levels.is_null() {
        put(&mut out, &mut paths, "levels", levels);
    }
    match a.get("minzoom") {
        None | Some(Value::Null) | Some(Value::Bool(true)) => {}
        Some(Value::Bool(false)) => put(&mut out, &mut paths, "roads.minzoom", json!("off")),
        Some(Value::Object(t)) => put(&mut out, &mut paths, "roads.minzoom", json!({"table": t})),
        Some(other) => return Err(Error::Options(format!("minzoom: True, False, None or a {{class: zoom}} mapping, not {other}"))),
    }
    if let Some(p) = get("road_popup") {
        put(&mut out, &mut paths, "interaction.popup", match p {
            Value::Bool(true) => json!("default"),
            Value::Bool(false) => json!("off"),
            Value::Array(f) => json!({"fields": f}),
            Value::String(s) if s == "panel" => json!("panel"),
            Value::String(_) => json!("all"),
            other => return Err(Error::Options(format!("road_popup: True, False, a list of columns, \"all\" or \"panel\", not {other}"))),
        });
    }
    // the hover tooltip: road_tooltip, else the folium name tooltip
    let given = |v: &&Value| !matches!(v, Value::Bool(false)) && *v != "" && v.as_array().is_none_or(|f| !f.is_empty());
    if let Some(t) = get("road_tooltip").filter(given).or_else(|| get("tooltip")).filter(given) {
        put(&mut out, &mut paths, "interaction.tooltip", match t {
            Value::Bool(true) => json!("all"),
            Value::Array(f) => json!({"fields": f}),
            Value::String(s) => json!({"fields": [s]}),
            other => return Err(Error::Options(format!("road_tooltip: True or a list of columns, not {other}"))),
        });
    }
    if let Some(t) = get("color_table") {
        put(&mut out, &mut paths, "color.table", json!({"colors": t, "key": get("color_key").cloned().unwrap_or_else(|| json!("edge_id"))}));
    }
    if let Some(o) = get("color_options") {
        let named: Vec<(String, Value)> = match o {
            Value::Object(m) => m.iter().map(|(k, v)| (k.clone(), v.clone())).collect(),
            Value::Array(l) => l.iter().map(|x| (x["name"].as_str().unwrap_or_default().to_string(), x.clone())).collect(),
            other => return Err(Error::Options(format!("color_options: a {{name: options}} mapping or a list, not {other}"))),
        };
        let opts = named.into_iter().map(|(name, o)| {
            let mut n = Map::new();
            n.insert("name".into(), name.into());
            for (k, v) in o.as_object().into_iter().flatten().filter(|(k, v)| *k != "name" && !v.is_null()) {
                let to = COLOR_OPTION.iter().find(|f| f.0 == k).map(|f| f.1)
                    .ok_or_else(|| Error::Options(format!("color_options: unknown key {k:?}{}", nearest(k, COLOR_OPTION.iter().map(|f| f.0)))))?;
                n.insert(to.into(), v.clone());
            }
            Ok(Value::Object(n))
        }).collect::<Result<Vec<_>, Error>>()?;
        put(&mut out, &mut paths, "color.options", Value::Array(opts));
    }
    if let Some(l) = get("overlays") {
        let l = l.as_array().ok_or_else(|| Error::Options(format!("overlays: a list, not {l}")))?;
        put(&mut out, &mut paths, "overlays", Value::Array(l.iter().map(overlay_from_flat).collect::<Result<_, _>>()?));
    }
    if let Some(d) = get("items") {
        put(&mut out, &mut paths, "items", json!({"data": d, "popup": get("items_popup")}));
    }
    let modes = get("modes");
    let layers = get("interaction");
    if modes.is_some() || layers.is_some() {
        put(&mut out, &mut paths, "base_map", json!({"modes": modes.cloned().unwrap_or(json!([])), "layers": layers.cloned().unwrap_or(json!({}))}));
    }
    Ok(Flat { out, paths, rest })
}

/// The flat keywords that are one field each: (keyword, the field's path).
const FLAT: &[(&str, &str)] = &[
    ("highway_col", "columns.class"), ("tunnel_col", "columns.tunnel"), ("bridge_col", "columns.bridge"), ("layer_col", "columns.layer"),
    ("edge_id_col", "columns.edge_id"), ("directed_col", "columns.directed"), ("driving_col", "columns.driving"),
    ("access_col", "columns.access"), ("filter_col", "columns.filter"), ("width_m_col", "columns.width_m"), ("cap_col", "columns.cap"),
    ("casing_start_col", "columns.levels.casing_start"), ("casing_level_col", "columns.levels.casing_level"),
    ("casing_end_col", "columns.levels.casing_end"), ("fill_level_col", "columns.levels.fill_level"),
    ("head_start_m_col", "columns.levels.head_start_m"), ("head_end_m_col", "columns.levels.head_end_m"),
    ("cap_start_col", "columns.levels.cap_start"), ("cap_end_col", "columns.levels.cap_end"),
    ("color_by", "color.by"), ("colors", "color.colors"), ("cmap", "color.cmap"), ("vmin", "color.vmin"), ("vmax", "color.vmax"),
    ("missing", "color.missing"), ("style", "color.style"), ("color_active", "color.active"),
    ("width_by", "width.range"), ("width_m_zoom", "width.m_zoom"),
    ("road_fill", "roads.fill"), ("head_m", "roads.head_m"), ("casing_m", "roads.casing_m"), ("casing_min_px", "roads.casing_min_px"),
    ("offset_frac", "roads.offset_frac"), ("width_frac", "roads.width_frac"), ("offset_zoom", "roads.offset_zoom"),
    ("hover_color", "interaction.hover_color"), ("select_color", "interaction.select_color"),
    ("labels", "labels.on"), ("arrows", "arrows.on"), ("tunnel_control", "tunnels.control"), ("view_3d", "bridges.decks_3d"),
    ("boundary", "boundary"), ("name", "output.name"), ("state", "output.state"), ("live_data", "output.live_data"),
    ("export", "output.export"),
];

/// The flat keywords of more than one field, or of a value in another form: `from_args` reads them itself.
const SPECIAL: &[&str] = &["levels", "minzoom", "road_popup", "road_tooltip", "tooltip", "color_table", "color_key", "color_options",
                           "overlays", "items", "items_popup", "modes", "interaction"];

/// The keys of a colour option (a data styler's keywords): (keyword, the field of `ColorOption`).
const COLOR_OPTION: &[(&str, &str)] = &[("color_by", "by"), ("colors", "colors"), ("cmap", "cmap"), ("vmin", "vmin"), ("vmax", "vmax"),
                                        ("width_by", "width"), ("missing", "missing"), ("palette", "palette"), ("style", "style")];

/// The fields of rs.Overlay that are one field each of `Overlay`: (field, the field's path).
const OVERLAY: &[(&str, &str)] = &[
    ("label", "label"), ("fc", "data"), ("kind", "kind"), ("placement", "placement"), ("color", "color"), ("color_col", "color_column"),
    ("outline", "outline"), ("opacity", "opacity"), ("width", "width"), ("width_m", "width_m"), ("radius", "radius"), ("dash", "dash"),
    ("popup", "popup"), ("popup_window", "popup_window"), ("tooltip", "tooltip"), ("visible", "visible"), ("min_zoom", "min_zoom"),
    ("max_zoom", "max_zoom"), ("select", "select"), ("style", "style"), ("edge_col", "edge.column"), ("order_col", "edge.order_column"),
    ("width_m_col", "edge.width_m_column"), ("offset_m_col", "edge.offset_m_column"), ("dash_col", "edge.dash_column"),
    ("text_col", "text.column"), ("text_size", "text.size"), ("text_color", "text.color"), ("text_halo", "text.halo"),
];

/// An overlay as the engine reads it today (rs.Overlay's fields, its data in `fc`) in the nested form.
fn overlay_from_flat(o: &Value) -> Result<Value, Error> {
    let o = o.as_object().ok_or_else(|| Error::Options(format!("overlays: each overlay is a mapping, not {o}")))?;
    let mut n = serde_json::to_value(Overlay::defaults()).expect("an overlay is JSON").as_object().cloned().unwrap_or_default();
    for (k, v) in o.iter().filter(|(_, v)| !v.is_null()) {
        let to = OVERLAY.iter().find(|f| f.0 == k).map(|f| f.1)
            .ok_or_else(|| Error::Options(format!("overlays: unknown field {k:?}{}", nearest(k, OVERLAY.iter().map(|f| f.0)))))?;
        set(&mut n, to, v.clone());
    }
    Ok(Value::Object(n))
}

/// `set`, and the path in `paths` (the fields that the flat keywords set, for `with_args`).
pub(super) fn put(m: &mut Map<String, Value>, paths: &mut Vec<String>, path: &str, v: Value) {
    set(m, path, v);
    paths.push(path.into());
}

/// The value at the dotted `path` of `m`.
pub(super) fn at<'a>(m: &'a Map<String, Value>, path: &str) -> Option<&'a Value> {
    match path.split_once('.') {
        None => m.get(path),
        Some((head, tail)) => at(m.get(head)?.as_object()?, tail),
    }
}

/// `v` at the dotted `path` of `m`, with the mappings on the way.
pub(super) fn set(m: &mut Map<String, Value>, path: &str, v: Value) {
    match path.split_once('.') {
        None => {
            m.insert(path.into(), v);
        }
        Some((head, tail)) => {
            let e = m.entry(head).or_insert_with(|| Value::Object(Map::new()));
            if !e.is_object() {
                *e = Value::Object(Map::new());
            }
            set(e.as_object_mut().expect("a mapping"), tail, v);
        }
    }
}

/// render_edges' flat keywords that are map options (`from_args` reads them).
pub fn keywords() -> impl Iterator<Item = &'static str> {
    FLAT.iter().map(|f| f.0).chain(SPECIAL.iter().copied())
}
