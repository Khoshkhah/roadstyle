//! Stage 3 of a page in one call (audit R3): `page_from` makes the page of a look's roads, as render_edges(backend="web") with the Rust
//! engine (`_engine.render_page`). It runs stage 1 (`sources_of`), the page's arrows or its tiles, a view's palettes, and it builds the
//! options of rsDashboard (`PageOptions`) from the style's interaction contract and the page's own keywords. Then `page::page_html`
//! writes the page. Python, the CLI and the studio call it; the caller resolves only what it alone knows: a base map that is not in
//! data/basemaps.json, the base map's API key and the Google Maps key.

use crate::look::Options;
use crate::page::{escape, gzip_b64, page_html, Camera, PageOptions, PageParts};
use crate::sources::Sources;
use crate::tiles::stage::{TileOptions, COLUMNS, TILES};
use crate::{layers::py_truth, FeatureTable, Look, RoadTable};
use serde_json::{json, Map, Value};

const BASEMAPS: &str = roadstyle_assets::text!("data/basemaps.json");

/// render_web.render's defaults of the keywords that only the page reads (tests/test_engine_parity.py checks them against render's
/// signature). The look's args are the caller's keywords only, so each one that the caller did not give takes its default here.
const DEFAULTS: &str = r#"{"basemap": null, "basemaps": null, "api_key": null, "basemap_switcher": true, "name": "roadstyle", "pitch": null,
    "bearing": null, "max_pitch": null, "view_3d": false, "find_control": false, "zoom_readout": true, "overlay_control": true,
    "overlay_popup": true, "side_panel_html": null, "host_panel_width": 320, "road_popup": true, "popup_mode": null, "street_view": "window",
    "street_view_key": null, "google_3d": false, "hover_color": null, "compress": true, "simple": true, "views": null, "tiles": false,
    "sidebar": null}"#;

/// The bundled sidebars (`sidebar=`, pages.render_dashboard and render_report): the template that goes on the page, and the keywords
/// that it changes when the caller does not give them (pages.py's defaults; tests/test_pages.py checks them).
const SIDEBARS: [(&str, &str, &str); 2] = [
    ("dashboard", roadstyle_assets::text!("templates/dashboard.html"),
     r#"{"name": "Roads dashboard", "basemap_switcher": false, "filter_control": false, "road_popup": false}"#),
    ("report", roadstyle_assets::text!("templates/report.html"),
     r#"{"name": "Roads report", "basemap_switcher": true, "filter_control": false, "road_popup": false}"#),
];

/// The keywords that each sidebar changes, and their values.
pub fn sidebar_defaults() -> Map<String, Value> {
    SIDEBARS.iter().map(|(k, _, d)| (k.to_string(), serde_json::from_str(d).expect("a sidebar's defaults are JSON"))).collect()
}

/// pages._page: the sidebar's template with the page's name as its heading (its first <h2>), before the end of the body.
fn add_sidebar(html: String, template: &str, name: &str) -> String {
    let frag = match (template.find("<h2>"), template.find("</h2>")) {
        (Some(i), Some(j)) if i < j => format!("{}<h2>{}</h2>{}", &template[..i], escape(name), &template[j + 5..]),
        _ => template.to_string(),
    };
    html.replacen("</body>", &(frag + "</body>"), 1)
}

/// The page's own keywords and their defaults.
pub fn page_defaults() -> Map<String, Value> {
    serde_json::from_str(DEFAULTS).expect("DEFAULTS is a JSON object")
}

/// A page and the warnings of its stages (Python's warnings.warn), for the caller to give.
pub struct Page {
    pub html: String,
    pub warnings: Vec<String>,
}

/// The page of `roads` with `look` (resolved from `options`, which a view's palette resolves again with its palette). `given`: the
/// caller's values over the look's args: `street_view_key`, `api_key` (put into a base map's URL), and `resolved_basemaps`, the
/// entries (as data/basemaps.json's) of the base map keys that the caller resolved itself (Python: its key of each provider). `features`:
/// the base map's rows (`read_features`, a duckOSM map's features.parquet), or None.
pub fn page_from(roads: RoadTable, features: Option<FeatureTable>, look: &Look, options: &Options, given: &Map<String, Value>)
                 -> Result<Page, String> {
    let sidebar = match given.get("sidebar").or(look.args.get("sidebar")).filter(|v| !v.is_null()) {
        None => None,
        Some(v) => Some(SIDEBARS.iter().find(|s| v == s.0).ok_or_else(|| format!("sidebar must be \"dashboard\" or \"report\", got {}", repr(v)))?),
    };
    // a sidebar's keywords, where the caller gave none, as keywords of the call: stage 1 reads two of them (the filter, the popup)
    let mut owned = None;
    if let Some((_, _, d)) = sidebar {
        let mut l = look.clone();
        for (k, v) in serde_json::from_str::<Map<String, Value>>(d).expect("a sidebar's defaults are JSON") {
            if look.args.get(&k).is_none() && !given.contains_key(&k) {
                l = l.with_arg(&k, v)?;
            }
        }
        owned = Some(l);
    }
    let look = owned.as_ref().unwrap_or(look);
    let mut a = page_defaults();
    a.extend(look.args.as_object().into_iter().flatten().map(|(k, v)| (k.clone(), v.clone())));
    a.extend(given.iter().map(|(k, v)| (k.clone(), v.clone())));
    let on = |k: &str| py_truth(&a[k]);
    let mode = if a["road_popup"] == "panel" { "panel" } else { a["popup_mode"].as_str().filter(|m| !m.is_empty()).unwrap_or("popup") };
    if !a["side_panel_html"].is_null() && mode == "panel" {
        return Err("side_panel_html and popup_mode='panel' are two panels on the right: use one".into());
    }
    if !a["street_view"].is_boolean() && a["street_view"] != "window" {
        return Err(format!("street_view must be True, False or \"window\", got {}", repr(&a["street_view"])));
    }
    let key = a["street_view_key"].as_str().filter(|k| !k.is_empty()).map(String::from);
    if on("google_3d") && key.is_none() {
        return Err("google_3d=True needs a Google Maps JavaScript API key: pass street_view_key=... or set GOOGLE_MAPS_KEY".into());
    }
    let bounds = bounds_of(&roads);
    let tiled = on("tiles");
    let mut src = crate::sources_of(roads, look, features, None, look.args["name"].as_str().map(String::from))?;
    let (active, bms, base) = basemaps(&a, look, &mut src.warnings)?;
    let bg = bg_color(&active, look);
    let keys: Vec<Value> = bms.iter().map(|b| b["key"].clone()).collect();
    let (views, pals) = if on("views") { views(&mut src, &a, look, options, &keys)? } else { (Vec::new(), Vec::new()) };
    if tiled && views.iter().any(|v| v["set"].get("palette").is_some()) {
        return Err("engine='rust': tiles=True with a view's palette (the tiles have one palette); use engine='python'".into());
    }
    let (mut style, archive) = if tiled { tiled_page(&src, &a)? } else {
        src.page_arrows();          // stage 3 of the inline page: the arrows are points that the page puts itself (audit N2)
        // the style without its sources' data, which the page writer writes from `src` (audit D3, N29)
        (src.style_with(|_| Value::Null, false), None)
    };
    let mut table = Vec::new();
    crate::write_road_table(&src, &mut table).map_err(|e| e.to_string())?;
    if !pals.is_empty() {
        let t: Value = serde_json::from_slice(&table).map_err(|e| e.to_string())?;
        palette_swatches(&mut style, &t["props"], &pals, look);
    }
    let st = style.as_object_mut().ok_or("the style is not a JSON object")?;
    let meta = st.shift_remove("metadata").unwrap_or_default();
    let (ctl, inter) = (&meta["roadstyle:controls"], &meta["roadstyle:interaction"]);
    let mut layers = base["layers"].as_array().cloned().unwrap_or_default();
    for l in &mut layers {
        if let Some(o) = l.as_object_mut() {
            o.entry("paint").or_insert_with(|| json!({}));         // as render_web._state_expressions gives every layer of the page
        }
    }
    for mut l in st["layers"].as_array().cloned().unwrap_or_default() {
        if let Some(o) = l.as_object_mut() {
            o.shift_remove("metadata");                             // the page gives the dashboard its options; its style has no metadata
        }
        layers.push(l);
    }
    let mut sources = base["sources"].as_object().cloned().unwrap_or_default();
    sources.extend(st["sources"].as_object().into_iter().flatten().map(|(k, v)| (k.clone(), v.clone())));
    let mut page_style = json!({"version": 8, "sources": sources, "layers": layers});
    for k in ["glyphs", "state"] {
        if let Some(v) = st.get(k) {
            page_style[k] = v.clone();
        }
    }
    let (cfg, th) = (&look.config, &look.theme);
    let mut cam = json!({"pitch": 0, "bearing": 0, "pitch_3d": 55, "max_pitch": 70});
    cam.as_object_mut().unwrap().extend(cfg["camera"].as_object().into_iter().flatten().map(|(k, v)| (k.clone(), v.clone())));
    if on("view_3d") {
        cam["pitch"] = cam["pitch_3d"].clone();
    }
    for k in ["pitch", "max_pitch", "bearing"] {
        if !a[k].is_null() {
            cam[k] = a[k].clone();
        }
    }
    let mut tunnel = ctl["tunnel"].clone();
    tunnel["bg"] = bg.into();
    let opts = PageOptions {
        basemaps: bms, basemap_switcher: on("basemap_switcher"), tiles: tiled, simple: ctl["simple"].clone(),
        sources: meta["roadstyle:sources"].clone(), arrows: meta["roadstyle:arrows"].clone(), live: meta["roadstyle:live"].clone(),
        popup_mode: mode.into(), find_control: on("find_control"), zoom_readout: on("zoom_readout"), pitch_3d: number(&ctl["pitch_3d"])?,
        street_view: a["street_view"].clone(), street_view_key: key.unwrap_or_default(), google_3d: on("google_3d"),
        select_color: ctl["select_color"].clone(), filter: ctl["filter"].clone(),
        color_options: Some(&meta["roadstyle:color_options"]).filter(|v| py_truth(v)).cloned().unwrap_or_else(|| json!([])),
        color_active: ctl["color_active"].clone(), overlays: ctl["overlays"].clone(), overlay_control: on("overlay_control"),
        overlay_popup: on("overlay_popup"), tunnel, fill_layers: ctl["fill_layers"].clone(), pick: ctl["pick"].clone(), road_fill: ctl["road_fill"].clone(),
        views: Value::Array(views), items: ctl["items"].clone(), road_popup: inter["popup"].clone(), road_tooltip: inter["tooltip"].clone(),
        hover_delay_ms: inter["hover_delay_ms"].as_i64().ok_or("roadstyle:interaction has no hover_delay_ms")?,
        edge_id_col: ctl["edge_id_col"].as_str().unwrap_or("edge_id").into(), arrow_icon: ctl["arrow_icon"].clone(),
        arrow_color: ctl["arrow_color"].clone(), arrow_rules: ctl["arrow_rules"].clone(),
        modes: ctl["modes"].clone(), box_layout: ctl["box_layout"].clone(),
    };
    let hover = Some(&a["hover_color"]).filter(|v| py_truth(v)).unwrap_or(&th["selection"]["hover"]);
    let simple_js = json!({"layer": "roads-simple", "bridge": cfg["bridge_casing_color"], "shadow": cfg["bridge_shadow_color"],
                           "select": ctl["select_color"], "hover": hover, "tunnels": py_truth(&ctl["tunnel"]["layers"]),
                           "dashes": ctl["dashes"]});
    let side = gzip_b64(&table);
    let cam = Camera { pitch: number(&cam["pitch"])?, bearing: number(&cam["bearing"])?, max_pitch: number(&cam["max_pitch"])? };
    let parts = PageParts {
        name: a["name"].as_str().unwrap_or("roadstyle"), cam, bounds, side_panel_html: a["side_panel_html"].as_str(),
        host_panel_width: a["host_panel_width"].as_f64().unwrap_or(320.0), compress: on("compress"), gz: None, tiles: archive.as_deref(),
        side: Some((&Value::Null, Some(&side))), simple_js: on("simple").then_some(&simple_js), sources: Some(&src),
    };
    let mut html = page_html(page_style, &opts, &parts);
    if let Some((_, template, _)) = sidebar {
        html = add_sidebar(html, template, parts.name);
    }
    Ok(Page { html, warnings: std::mem::take(&mut src.warnings) })
}

fn number(v: &Value) -> Result<serde_json::Number, String> {
    v.as_number().cloned().ok_or_else(|| format!("not a number: {v}"))
}

/// Python's repr of a JSON value, for the messages that name a value as render_web's do.
fn repr(v: &Value) -> String {
    match v {
        Value::Null => "None".into(),
        Value::Bool(b) => (if *b { "True" } else { "False" }).into(),
        Value::String(s) => format!("'{s}'"),
        Value::Array(a) => format!("[{}]", a.iter().map(repr).collect::<Vec<_>>().join(", ")),
        Value::Object(o) => format!("{{{}}}", o.iter().map(|(k, v)| format!("'{k}': {}", repr(v))).collect::<Vec<_>>().join(", ")),
        Value::Number(_) => v.to_string(),
    }
}

/// GeoPandas' total_bounds of the roads: [min lon, min lat, max lon, max lat].
fn bounds_of(roads: &RoadTable) -> [f64; 4] {
    let mut b = [f64::INFINITY, f64::INFINITY, f64::NEG_INFINITY, f64::NEG_INFINITY];
    for p in (0..roads.len()).filter_map(|r| roads.line(r)).flatten() {
        b = [b[0].min(p[0]), b[1].min(p[1]), b[2].max(p[0]), b[3].max(p[1])];
    }
    b
}

/// basemaps._inject_token: the key into a tile URL, by its placeholder, else as a query parameter.
fn inject_token(url: &str, token: &str) -> String {
    const HOLDERS: [&str; 7] = ["{api_key}", "{accessToken}", "{apikey}", "{apiKey}", "{token}", "{key}", "{access_token}"];
    if url.is_empty() || token.is_empty() {
        return url.into();
    }
    if HOLDERS.iter().any(|h| url.contains(h)) {
        return HOLDERS.iter().fold(url.to_string(), |u, h| u.replace(h, token));
    }
    let (param, sep) = (if url.contains("cartocdn.com") { "key" } else { "api_key" }, if url.contains('?') { "&" } else { "?" });
    format!("{url}{sep}{param}={token}")
}

/// A base map: an entry (a JSON object), a key that the caller resolved (`resolved`), a key of data/basemaps.json, or a tile URL with
/// {z}, {x} and {y} (basemaps.get_basemap, with `api_key` put in; a CARTO base map with no key is a warning, as get_basemap's).
fn basemap(v: &Value, api_key: Option<&str>, resolved: &[Value], warnings: &mut Vec<String>) -> Result<Value, String> {
    if v.is_object() {
        return Ok(v.clone());
    }
    let k = v.as_str().ok_or_else(|| format!("basemap must be a key or a base map entry, got {v}"))?;
    if let Some(b) = resolved.iter().find(|b| b["key"] == k) {
        return Ok(b.clone());
    }
    let all: Value = serde_json::from_str(BASEMAPS).expect("data/basemaps.json is JSON");
    let mut bm = match all["basemaps"].as_array().and_then(|l| l.iter().find(|b| b["key"] == k)) {
        Some(b) => b.clone(),
        None if ["{z}", "{x}", "{y}"].iter().all(|p| k.contains(p)) => json!({"key": "custom", "label": "Custom Basemap", "url": k, "attr": ""}),
        None => {
            let keys: Vec<Value> = all["basemaps"].as_array().into_iter().flatten().map(|b| b["key"].clone()).collect();
            return Err(format!("unknown basemap '{k}'; choose from {}", repr(&Value::Array(keys))));
        }
    };
    match api_key.filter(|t| !t.is_empty()) {
        Some(t) => bm["url"] = inject_token(bm["url"].as_str().unwrap_or(""), t).into(),
        None if bm["url"].as_str().is_some_and(|u| u.contains("cartocdn.com")) => {
            let w = "CARTO base map requested with no API key: the tiles will come back stamped 'API KEY REQUIRED'. Set one in roadstyle.json, \
                     or use a keyless base map (esri_street, esri_dark_gray, osm).";
            if !warnings.iter().any(|x| x == w) {
                warnings.push(w.into());        // one for the page, not one for each CARTO base map of the switcher
            }
        }
        None => {}
    }
    Ok(bm)
}

/// render_web._tiles: the URL template as MapLibre's raster `tiles` (each subdomain, no @2x).
fn tiles_of(bm: &Value) -> Vec<String> {
    let url = bm["url"].as_str().unwrap_or("");
    if url.is_empty() {
        return Vec::new();
    }
    if url.contains("{s}") {
        let subs = bm["subdomains"].as_str().filter(|s| !s.is_empty()).unwrap_or("a");
        return subs.chars().map(|s| url.replace("{s}", &s.to_string()).replace("{r}", "")).collect();
    }
    vec![url.replace("{r}", "")]
}

/// render_web._bg_color: the canvas colour behind the tiles.
fn bg_color(bm: &Value, look: &Look) -> String {
    let bg = bm["bg"].as_str().unwrap_or("#444");
    if bg.starts_with('#') {
        return bg.into();
    }
    let dark = bm["is_dark"] == true;
    look.theme["background"][if dark { "dark" } else { "light" }].as_str().unwrap_or_default().into()
}

/// render_web._page_basemaps: the active base map, the switcher's list (the active one first) and the style that draws it.
fn basemaps(a: &Map<String, Value>, look: &Look, warnings: &mut Vec<String>) -> Result<(Value, Vec<Value>, Value), String> {
    let api = a["api_key"].as_str();
    let resolved = a.get("resolved_basemaps").and_then(Value::as_array).cloned().unwrap_or_default();
    let active = Some(&a["basemap"]).filter(|v| py_truth(v)).unwrap_or(&look.config["basemap"]).clone();
    let active_bm = basemap(&active, api, &resolved, warnings)?;
    let all: Value = serde_json::from_str(BASEMAPS).expect("data/basemaps.json is JSON");
    let keys = a["basemaps"].as_array().filter(|l| !l.is_empty()).cloned().unwrap_or_else(|| all["switcher"].as_array().cloned().unwrap_or_default());
    let key_of = |v: &Value| if v.is_object() { v["key"].clone() } else { v.clone() };
    let mut list = vec![active_bm.clone()];
    for k in keys.iter().filter(|k| key_of(k) != active_bm["key"] && key_of(k) != key_of(&active)) {
        list.push(basemap(k, api, &resolved, warnings)?);
    }
    let mut bms: Vec<Value> = list.iter().map(|b| json!({"key": b["key"], "label": b["label"], "tiles": tiles_of(b), "bg": bg_color(b, look),
                                                         "maxzoom": b.get("maxzoom").cloned().unwrap_or(json!(19)), "attr": b["attr"]})).collect();
    if !py_truth(&a["basemap_switcher"]) && !py_truth(&a["basemaps"]) {
        bms.truncate(1);        // no switcher and no list given: only the fixed backdrop (window.rsSetBasemap reaches a given list)
    }
    let mut style = json!({"version": 8, "sources": {}, "layers": [{"id": "bg", "type": "background", "paint": {"background-color": bg_color(&active_bm, look)}}]});
    let tiles = tiles_of(&active_bm);
    if !tiles.is_empty() {
        style["sources"]["bm"] = json!({"type": "raster", "tiles": tiles, "tileSize": 256, "maxzoom": active_bm.get("maxzoom").cloned().unwrap_or(json!(19)),
                                        "attribution": active_bm["attr"]});
        style["layers"].as_array_mut().unwrap().push(json!({"id": "basemap", "type": "raster", "source": "bm"}));
    } else if let Some(b) = bms.iter().find(|b| py_truth(&b["tiles"])) {
        // a blank base map is active but the switcher offers tiled ones: the raster layer is there, hidden (no tile is fetched)
        style["sources"]["bm"] = json!({"type": "raster", "tiles": b["tiles"], "tileSize": 256, "maxzoom": b["maxzoom"], "attribution": b["attr"]});
        style["layers"].as_array_mut().unwrap().push(json!({"id": "basemap", "type": "raster", "source": "bm", "layout": {"visibility": "none"}}));
    }
    Ok((active_bm, bms, style))
}

const VIEW_BOOLS: [&str; 4] = ["road_fill", "bridges", "tunnels", "view3d"];

/// render_web._check_views: `views` as the page reads it, [{name, set}]; a setting that is not known, or that names a colour option, an
/// overlay, a class, a base map or a palette that the page does not have, is an error.
fn check_views(views: &Value, have: [(&str, Vec<Value>); 5]) -> Result<Vec<Value>, String> {
    let mut out = Vec::new();
    for (name, sets) in views.as_object().into_iter().flatten() {
        let s = sets.as_object().ok_or_else(|| format!("view '{name}': not a mapping of settings"))?;
        let mut unknown: Vec<&String> = s.keys().filter(|k| !["color", "overlays", "classes", "basemap", "palette"].contains(&k.as_str())
                                                          && !VIEW_BOOLS.contains(&k.as_str())).collect();
        if !unknown.is_empty() {
            unknown.sort();
            return Err(format!("view '{name}': unknown setting(s) {}", repr(&json!(unknown))));
        }
        for k in VIEW_BOOLS {
            if s.get(k).is_some_and(|v| !v.is_boolean()) {
                return Err(format!("view '{name}': {k} must be True or False, got {}", repr(&s[k])));
            }
        }
        for (k, have) in &have {
            let given: Vec<Value> = match (*k, s.get(*k)) {
                (_, None) => Vec::new(),
                ("overlays", Some(v)) => v.as_object().into_iter().flatten().map(|(n, _)| json!(n)).collect(),
                ("classes", Some(v)) => v.as_array().cloned().unwrap_or_default(),
                (_, Some(v)) => vec![v.clone()],
            };
            let missing: Vec<Value> = given.into_iter().filter(|x| !have.contains(x)).collect();
            if !missing.is_empty() {
                return Err(format!("view '{name}': {k} {} not in the page (it has {})", repr(&json!(missing)), repr(&json!(have))));
            }
        }
        out.push(json!({"name": name, "set": sets}));
    }
    Ok(out)
}

/// _engine._views: the views as the page reads them, and the palettes that they name other than the page's. Each such palette is
/// resolved with the look's options and args (its colours), and merged into stage 1's output (palettes::add).
fn views(src: &mut Sources, a: &Map<String, Value>, look: &Look, options: &Options, basemaps: &[Value]) -> Result<(Vec<Value>, Vec<String>), String> {
    let meta = &src.metadata;
    let ctl = &meta["roadstyle:controls"];
    let colors: Vec<Value> = if py_truth(&a.get("color_options").cloned().unwrap_or_default()) {
        meta["roadstyle:color_options"].as_array().into_iter().flatten().map(|o| o["name"].clone()).collect()
    } else { Vec::new() };
    let overlays: Vec<Value> = ctl["overlays"].as_array().into_iter().flatten().map(|o| o["label"].clone()).collect();
    let classes = ctl["filter"]["classes"].as_array().cloned().unwrap_or_default();
    let palettes: Vec<Value> = options.style_names("palettes").into_iter().map(Value::from).collect();
    let views = check_views(&a["views"], [("color", colors), ("overlays", overlays), ("classes", classes), ("basemap", basemaps.to_vec()),
                                           ("palette", palettes)])?;
    let mut pals: Vec<String> = Vec::new();
    for p in views.iter().filter_map(|v| v["set"]["palette"].as_str()) {
        if p != look.palette && !pals.iter().any(|q| q == p) {
            pals.push(p.into());
        }
    }
    if !pals.is_empty() {
        let looks = pals.iter().map(|n| {
            let o = Options { palette: Some(n.clone()), args: look.args.clone(), ..options.clone() };
            Ok((n.clone(), Look::resolve(&o)?))
        }).collect::<Result<Vec<_>, String>>()?;
        crate::palettes::add(src, &look.palette, &looks)?;
    }
    Ok((views, pals))
}

/// _engine._palette_swatches: the filter panel's colour of each class in each palette of the views (the fill of the class's first road
/// in that palette), and the page's palette's (the swatches).
fn palette_swatches(style: &mut Value, props: &Value, pals: &[String], look: &Look) {
    let fb = &look.theme["roads"]["fallback"]["fill"];
    let state = style["metadata"]["roadstyle:state"]["rs_palette"].as_str().unwrap_or_default().to_string();
    let flt = &mut style["metadata"]["roadstyle:controls"]["filter"];
    let col = flt["col"].as_str().unwrap_or_default().to_string();
    let mut first: Vec<(&Value, &Value)> = Vec::new();
    for p in props.as_array().into_iter().flatten() {
        if !first.iter().any(|(k, _)| **k == p[col.as_str()]) {
            first.push((&p[col.as_str()], p));
        }
    }
    let row = |c: &Value| first.iter().find(|(k, _)| *k == c).map(|(_, p)| *p).unwrap_or(&Value::Null);
    let classes = flt["classes"].as_array().cloned().unwrap_or_default();
    let mut out = Map::new();
    for n in pals {
        let of: Map<String, Value> = classes.iter().map(|c| {
            let r = row(c);
            let v = r.get(format!("__rs_fill@{n}")).or_else(|| r.get("__rs_fill")).filter(|v| py_truth(v)).unwrap_or(fb);
            (c.as_str().unwrap_or_default().to_string(), v.clone())
        }).collect();
        out.insert(n.clone(), Value::Object(of));
    }
    out.insert(state, flt["swatches"].clone());
    flt["palettes"] = Value::Object(out);
}

/// _engine._tiled_page: the tiled page's style and its PMTiles archive, from stage 2 of the same stage 1 (no second build). The style
/// has one vector source `roads` (the embedded archive) with the layers `simple` and `slots`; the other sources stay inline.
fn tiled_page(s: &Sources, a: &Map<String, Value>) -> Result<(Value, Option<Vec<u8>>), String> {
    let hw = a.get("highway_col").and_then(Value::as_str).unwrap_or("highway");
    let col = |k: &str| a.get(k).and_then(Value::as_str).filter(|c| !c.is_empty());
    let keep = [Some(hw), Some(col("filter_col").unwrap_or(hw)), Some("__rs_twoway"), Some("__rs_edge"), Some("lvl"), col("width_m_col")];
    let mut o = TileOptions::new(&s.layers, &s.metadata, &s.saved[TILES], &s.saved[COLUMNS], &[])?;
    o.exact = Some(keep.into_iter().flatten().map(String::from).collect());
    o.only = Some(["roads", "simple", "slots"].map(String::from).to_vec());
    let (style, t) = crate::tile_stage(s, &o, &json!({"url": "pmtiles://roads"}))?;
    let archive = t.archive(t.bounds().ok_or(crate::tiles::Error::Empty)?, &t.layer_names())?;
    Ok((style, Some(archive)))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_key_goes_into_a_tile_url_as_basemaps_puts_it() {
        assert_eq!(inject_token("https://a.basemaps.cartocdn.com/x/{z}/{x}/{y}.png", "T"), "https://a.basemaps.cartocdn.com/x/{z}/{x}/{y}.png?key=T");
        assert_eq!(inject_token("https://t.example/{z}/{x}/{y}?s=1", "T"), "https://t.example/{z}/{x}/{y}?s=1&api_key=T");
        assert_eq!(inject_token("https://t.example/{z}/{x}/{y}?token={token}", "T"), "https://t.example/{z}/{x}/{y}?token=T");
        assert_eq!(inject_token("", "T"), "");
    }

    #[test]
    fn a_view_names_only_what_the_page_has() {
        let have = || [("color", vec![]), ("overlays", vec![]), ("classes", vec![json!("primary")]), ("basemap", vec![]), ("palette", vec![json!("mono")])];
        assert!(check_views(&json!({"a": {"classes": ["primary"], "palette": "mono", "bridges": true}}), have()).is_ok());
        let e = check_views(&json!({"a": {"classes": ["motorway"]}}), have()).unwrap_err();
        assert_eq!(e, "view 'a': classes ['motorway'] not in the page (it has ['primary'])");
        assert_eq!(check_views(&json!({"a": {"zoom": 3}}), have()).unwrap_err(), "view 'a': unknown setting(s) ['zoom']");
        assert_eq!(check_views(&json!({"a": {"bridges": 1}}), have()).unwrap_err(), "view 'a': bridges must be True or False, got 1");
    }
}
