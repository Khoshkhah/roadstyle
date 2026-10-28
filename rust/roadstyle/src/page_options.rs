//! Stage 3 of a page in one call (audit R3): `page_from` makes the page of a look's roads, as render_edges(backend="web") with the Rust
//! engine (`_engine.render_page`). It runs stage 1 (`sources_of`), the page's arrows or its tiles, a view's palettes, and it builds the
//! options of rsDashboard (`PageOptions`) from the style's interaction contract and the page's own keywords. Then `page::page_html`
//! writes the page. The Python binding, the CLI and the studio call it; the caller resolves only what it alone knows: a base map that is not in
//! data/basemaps.json, the base map's API key and the Google Maps key.

use crate::look::Options;
use crate::page::{escape, gzip_b64, page_html, Camera, PageOptions, PageParts};
use crate::sources::Styled;
use crate::tiles::stage::{TileOptions, COLUMNS, TILES};
use crate::{FeatureTable, Look, RoadTable};
use serde_json::{json, Map, Value};

const BASEMAPS: &str = roadstyle_assets::text!("data/basemaps.json");

/// defaults of the keywords that only the page reads (tests/test_engine_parity.py checks them against render's
/// signature). The look's args are the caller's keywords only, so each one that the caller did not give takes its default here.
const DEFAULTS: &str = r#"{"basemap": null, "basemaps": null, "api_key": null, "basemap_switcher": true, "name": "roadstyle", "pitch": null,
    "bearing": null, "max_pitch": null, "view_3d": false, "find_control": false, "zoom_readout": true, "overlay_control": true,
    "overlay_popup": true, "side_panel_html": null, "host_panel_width": 320, "road_popup": true, "popup_mode": null, "street_view": "window",
    "street_view_key": null, "google_3d": false, "hover_color": null, "compress": true, "views": null, "tiles": false,
    "sidebar": null, "filter_control": true, "legend": true}"#;

/// The bundled sidebars (`sidebar=`, pages.render_dashboard and render_report): the template that goes on the page, and the keywords
/// that it changes when the caller does not give them (pages.py's defaults; tests/test_pages.py checks them).
const SIDEBARS: [(&str, &str, &str); 2] = [
    ("dashboard", roadstyle_assets::text!("templates/dashboard.html"),
     r#"{"name": "Roads dashboard", "basemap_switcher": false, "filter_control": false, "road_popup": false}"#),
    ("report", roadstyle_assets::text!("templates/report.html"),
     r#"{"name": "Roads report", "basemap_switcher": true, "filter_control": false, "road_popup": false}"#),
];

/// The two map options that a sidebar's defaults give way to when the call gives them (page_from: `mine`): they go into `given` too.
const SIDEBAR_YIELDS: [&str; 2] = ["name", "road_popup"];

/// The page's keys of a call (render_edges' keywords), the `given` of page_from: the look's `other` (the call's keywords that are not map
/// options; a look file has none) and `SIDEBAR_YIELDS` of the call's `args`. It has no API key (Look::other has none): the caller adds its
/// own values (street_view_key, api_key, resolved_basemaps) over it. The one rule of the Python binding and the wasm page.
pub fn given_of(look: &Look, args: &Value) -> Map<String, Value> {
    let mut g = look.other.clone();
    for k in SIDEBAR_YIELDS {
        if let Some(v) = args.get(k) {
            g.insert(k.into(), v.clone());
        }
    }
    g
}

/// The keywords that each sidebar changes, and their values.
pub fn sidebar_keys() -> Map<String, Value> {
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

/// The page's keys of a call, typed: a key that the call does not give has its default (DEFAULTS, put in before), a value of another
/// type is an error.
/// The keys that other parts read (`data_maxzoom`, `tile_keep`, ...) stay in the map that this is made from.
#[derive(serde::Deserialize)]
struct PageKeys {
    basemap: Value,
    basemaps: Option<Vec<Value>>,
    api_key: Option<String>,
    basemap_switcher: bool,
    name: String,
    pitch: Option<Value>,
    bearing: Option<Value>,
    max_pitch: Option<Value>,
    find_control: bool,
    zoom_readout: bool,
    overlay_control: bool,
    overlay_popup: bool,
    side_panel_html: Option<String>,
    host_panel_width: f64,
    popup_mode: Option<String>,
    street_view: Value,
    street_view_key: Option<String>,
    google_3d: bool,
    compress: bool,
    views: Value,
    tiles: bool,
    filter_control: bool,
    legend: bool,
    #[serde(default)]
    hover_delay_ms: Option<f64>,
    #[serde(default)]
    box_layout: Value,
    #[serde(default)]
    resolved_basemaps: Vec<Value>,
}

/// A value that is there: not null, and not an empty text, list or mapping.
fn present(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::String(s) => !s.is_empty(),
        Value::Array(l) => !l.is_empty(),
        Value::Object(m) => !m.is_empty(),
        _ => true,
    }
}

/// The page's own keywords and their defaults.
pub fn page_key_defaults() -> Map<String, Value> {
    serde_json::from_str(DEFAULTS).expect("DEFAULTS is a JSON object")
}

/// A page and the warnings of its stages (warnings of the host), for the caller to give.
pub struct Page {
    pub html: String,
    pub warnings: Vec<String>,
}

/// The page of `roads` with `look` (resolved from `options`, which a view's palette resolves again with its palette). `given`: the
/// page's keys (render's keywords: name, basemap_switcher, sidebar, views, hover_delay_ms, ...; a look has none), over the base map's page
/// defaults (`look.base_map_page`), and the caller's values: `street_view_key`, `api_key` (put into a base map's URL), and
/// `resolved_basemaps`, the entries (as data/basemaps.json's) of the base map keys that the caller resolved itself (the caller's key of
/// each provider). `features`: the base map's rows (`read_features`, a duckOSM map's features.parquet), or None.
pub fn page_from(roads: RoadTable, features: Option<FeatureTable>, look: &Look, options: &Options, given: &Map<String, Value>)
                 -> Result<Page, crate::Error> {
    let sidebar = match given.get("sidebar").filter(|v| !v.is_null()) {
        None => None,
        Some(v) => Some(SIDEBARS.iter().find(|s| v == s.0).ok_or_else(|| crate::error::options(format!("sidebar must be \"dashboard\" or \"report\", got {}", repr(v))))?),
    };
    // a sidebar's keywords, where the caller gave none: the page's keys, and one map option (the popup), which stage 1 reads
    let mut owned = None;
    let mut a = page_key_defaults();
    a.extend(look.base_map_page.iter().map(|(k, v)| (k.clone(), v.clone())));
    let named = look.map.output.name.as_ref();         // the map's name: the call's or the base map's, over a sidebar's
    if let Some(n) = named {
        a.insert("name".into(), n.as_str().into());
    }
    if let Some((_, _, d)) = sidebar {
        let mut l = look.clone();
        let mine = |k: &str| given.contains_key(k) || (k == "name" && named.is_some());
        for (k, v) in serde_json::from_str::<Map<String, Value>>(d).expect("a sidebar's defaults are JSON").into_iter().filter(|(k, _)| !mine(k)) {
            if k == "road_popup" {
                l = l.with_arg(&k, v)?;
            } else {
                a.insert(k, v);
            }
        }
        owned = Some(l);
    }
    let look = owned.as_ref().unwrap_or(look);
    a.extend(given.iter().map(|(k, v)| (k.clone(), v.clone())));
    let k: PageKeys = serde_json::from_value(Value::Object(a.clone())).map_err(|e| crate::error::options(format!("a page key: {e}")))?;
    // the map options that the page reads too: the popup panel, the 3D view, the hover colour, the colour options, the columns
    let mo = &look.map;
    let mode = if mo.interaction.popup == crate::look::options::Popup::Panel { "panel" } else { k.popup_mode.as_deref().filter(|m| !m.is_empty()).unwrap_or("popup") };
    if k.side_panel_html.is_some() && mode == "panel" {
        return Err(crate::error::options("side_panel_html and popup_mode='panel' are two panels on the right: use one"));
    }
    if !k.street_view.is_boolean() && k.street_view != "window" {
        return Err(crate::error::options(format!("street_view must be True, False or \"window\", got {}", repr(&k.street_view))));
    }
    let key = k.street_view_key.clone().filter(|v| !v.is_empty());
    if k.google_3d && key.is_none() {
        return Err(crate::error::options("google_3d=True needs a Google Maps JavaScript API key: pass street_view_key=... or set GOOGLE_MAPS_KEY"));
    }
    let bounds = bounds_of(&roads);
    let tiled = k.tiles;
    let mut src = crate::sources_of(roads, look, features, None, look.map.output.name.clone())?;
    let (active, bms, base) = basemaps(&k, look, &mut src.warnings)?;
    let bg = bg_color(&active, look);
    let keys: Vec<Value> = bms.iter().map(|b| b["key"].clone()).collect();
    let (views, pals) = if present(&k.views) { views(&mut src, &k, look, options, &keys)? } else { (Vec::new(), Vec::new()) };
    if tiled && views.iter().any(|v| v["set"].get("palette").is_some()) {
        return Err(crate::Error::Engine(roadstyle_engine::Error::Unsupported(roadstyle_engine::Unsupported::TiledPalettes)));
    }
    let (mut style, archive) = if tiled { tiled_page(&src, look, &a)? } else {
        src.page_arrows();          // stage 3 of the inline page: the arrows are points that the page puts itself (audit N2)
        // the style without its sources' data, which the page writer writes from `src` (audit D3, N29)
        (src.style_with(crate::sources::SourceMode::inline_of(&a), false), None)
    };
    let mut table = Vec::new();
    crate::write_road_table(&src, None, true, &mut table).map_err(|e| crate::error::file(crate::ROAD_TABLE, e))?;
    if !pals.is_empty() {
        palette_swatches(&mut style, &src.table_rows(), &pals, look);       // the rows, not the written table parsed again (N29)
    }
    let st = style.as_object_mut().ok_or_else(|| crate::error::options("the style is not a JSON object"))?;
    let meta = st.shift_remove("metadata").unwrap_or_default();
    let (ctl, inter) = (&meta["roadstyle:controls"], &meta["roadstyle:interaction"]);
    let mut layers = base["layers"].as_array().cloned().unwrap_or_default();
    for l in &mut layers {
        if let Some(o) = l.as_object_mut() {
            o.entry("paint").or_insert_with(|| json!({}));         // every layer of the page
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
    let (ls, c) = (&look.sections, &look.sections.camera);
    let mut cam = json!({"pitch": c.pitch, "bearing": c.bearing, "pitch_3d": c.pitch_3d, "max_pitch": c.max_pitch});
    if mo.bridges.decks_3d {
        cam["pitch"] = cam["pitch_3d"].clone();
    }
    for key in ["pitch", "max_pitch", "bearing"] {
        if let Some(v) = k_cam(&k, key) {
            cam[key] = v.clone();
        }
    }
    let mut tunnel = ctl["tunnel"].clone();
    tunnel["bg"] = bg.into();
    let opts = PageOptions {
        basemaps: bms, basemap_switcher: k.basemap_switcher, tiles: tiled, simple: ctl["simple"].clone(),
        sources: meta["roadstyle:sources"].clone(), arrows: meta["roadstyle:arrows"].clone(), live: meta["roadstyle:live"].clone(),
        popup_mode: mode.into(), find_control: k.find_control, zoom_readout: k.zoom_readout, pitch_3d: number(&ctl["pitch_3d"])?,
        street_view: k.street_view.clone(), street_view_key: key.unwrap_or_default(), google_3d: k.google_3d,
        select_color: ctl["select_color"].clone(), filter: ctl["filter"].clone(), filter_control: k.filter_control,
        color_options: Some(&meta["roadstyle:color_options"]).filter(|v| present(v)).cloned().unwrap_or_else(|| json!([])), legend: k.legend,
        color_active: ctl["color_active"].clone(), overlays: ctl["overlays"].clone(), overlay_control: k.overlay_control,
        overlay_popup: k.overlay_popup, tunnel, fill_layers: ctl["fill_layers"].clone(), pick: ctl["pick"].clone(), road_fill: ctl["road_fill"].clone(),
        views: Value::Array(views), items: ctl["items"].clone(), road_popup: inter["popup"].clone(), road_tooltip: inter["tooltip"].clone(),
        // the page's hover_delay_ms, else the look's (roadstyle:interaction)
        hover_delay_ms: k.hover_delay_ms.map(|d| d as i64).or_else(|| inter["hover_delay_ms"].as_i64())
            .ok_or_else(|| crate::error::options("roadstyle:interaction has no hover_delay_ms"))?,
        edge_id_col: ctl["edge_id_col"].as_str().unwrap_or("edge_id").into(), arrow_icon: ctl["arrow_icon"].clone(),
        arrow_color: ctl["arrow_color"].clone(), arrow_rules: ctl["arrow_rules"].clone(),
        modes: ctl["modes"].clone(), box_layout: k.box_layout.clone(),
    };
    let hover = json!(mo.interaction.hover_color.as_ref().unwrap_or(&ls.selection.hover).css());
    let simple_js = json!({"layer": "roads-simple", "bridge": ls.bridges.casing_color, "shadow": ls.bridges.shadow.color,
                           "select": ctl["select_color"], "hover": hover, "tunnels": present(&ctl["tunnel"]["layers"]),
                           "dashes": ctl["dashes"]});
    let side = gzip_b64(&table);
    let cam = Camera { pitch: number(&cam["pitch"])?, bearing: number(&cam["bearing"])?, max_pitch: number(&cam["max_pitch"])? };
    let parts = PageParts {
        name: &k.name, cam, bounds, side_panel_html: k.side_panel_html.as_deref(),
        host_panel_width: k.host_panel_width, compress: k.compress, gz: None, tiles: archive.as_deref(),
        side: Some((&Value::Null, Some(&side))), simple_js: Some(&simple_js), sources: Some(&src),
    };
    let mut html = page_html(page_style, &opts, &parts);
    if let Some((_, template, _)) = sidebar {
        html = add_sidebar(html, template, parts.name);
    }
    Ok(Page { html, warnings: std::mem::take(&mut src.warnings) })
}

fn number(v: &Value) -> Result<serde_json::Number, crate::Error> {
    v.as_number().cloned().ok_or_else(|| crate::error::options(format!("not a number: {v}")))
}

/// the name in quotes of a JSON value, for the messages that name a value.
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
fn basemap(v: &Value, api_key: Option<&str>, resolved: &[Value], warnings: &mut Vec<String>) -> Result<Value, crate::Error> {
    if v.is_object() {
        return Ok(v.clone());
    }
    let k = v.as_str().ok_or_else(|| crate::error::options(format!("basemap must be a key or a base map entry, got {v}")))?;
    if let Some(b) = resolved.iter().find(|b| b["key"] == k) {
        return Ok(b.clone());
    }
    let all: Value = serde_json::from_str(BASEMAPS).expect("data/basemaps.json is JSON");
    let mut bm = match all["basemaps"].as_array().and_then(|l| l.iter().find(|b| b["key"] == k)) {
        Some(b) => b.clone(),
        None if ["{z}", "{x}", "{y}"].iter().all(|p| k.contains(p)) => json!({"key": "custom", "label": "Custom Basemap", "url": k, "attr": ""}),
        None => {
            let keys: Vec<Value> = all["basemaps"].as_array().into_iter().flatten().map(|b| b["key"].clone()).collect();
            return Err(crate::error::options(format!("unknown basemap '{k}'; choose from {}", repr(&Value::Array(keys)))));
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

/// the URL template as MapLibre's raster `tiles` (each subdomain, no @2x).
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

/// the canvas colour behind the tiles.
fn bg_color(bm: &Value, look: &Look) -> String {
    let bg = bm["bg"].as_str().unwrap_or("#444");
    if bg.starts_with('#') {
        return bg.into();
    }
    let dark = bm["is_dark"] == true;
    let b = &look.sections.background;
    (if dark { &b.dark } else { &b.light }).css().into()
}

/// the active base map, the switcher's list (the active one first) and the style that draws it.
fn basemaps(k: &PageKeys, look: &Look, warnings: &mut Vec<String>) -> Result<(Value, Vec<Value>, Value), crate::Error> {
    let api = k.api_key.as_deref();
    let resolved = k.resolved_basemaps.clone();
    let active = Some(&k.basemap).filter(|v| present(v)).cloned().unwrap_or_else(|| json!(look.sections.page.basemap));
    let active_bm = basemap(&active, api, &resolved, warnings)?;
    let all: Value = serde_json::from_str(BASEMAPS).expect("data/basemaps.json is JSON");
    let keys = k.basemaps.clone().filter(|l| !l.is_empty()).unwrap_or_else(|| all["switcher"].as_array().cloned().unwrap_or_default());
    let key_of = |v: &Value| if v.is_object() { v["key"].clone() } else { v.clone() };
    let mut list = vec![active_bm.clone()];
    for b in keys.iter().filter(|b| key_of(b) != active_bm["key"] && key_of(b) != key_of(&active)) {
        list.push(basemap(b, api, &resolved, warnings)?);
    }
    let mut bms: Vec<Value> = list.iter().map(|b| json!({"key": b["key"], "label": b["label"], "tiles": tiles_of(b), "bg": bg_color(b, look),
                                                         "maxzoom": b.get("maxzoom").cloned().unwrap_or(json!(19)), "attr": b["attr"]})).collect();
    if !k.basemap_switcher && k.basemaps.as_ref().is_none_or(|l| l.is_empty()) {
        bms.truncate(1);        // no switcher and no list given: only the fixed backdrop (window.rsSetBasemap reaches a given list)
    }
    let mut style = json!({"version": 8, "sources": {}, "layers": [{"id": "bg", "type": "background", "paint": {"background-color": bg_color(&active_bm, look)}}]});
    let tiles = tiles_of(&active_bm);
    if !tiles.is_empty() {
        style["sources"]["bm"] = json!({"type": "raster", "tiles": tiles, "tileSize": 256, "maxzoom": active_bm.get("maxzoom").cloned().unwrap_or(json!(19)),
                                        "attribution": active_bm["attr"]});
        style["layers"].as_array_mut().unwrap().push(json!({"id": "basemap", "type": "raster", "source": "bm"}));
    } else if let Some(b) = bms.iter().find(|b| present(&b["tiles"])) {
        // a blank base map is active but the switcher offers tiled ones: the raster layer is there, hidden (no tile is fetched)
        style["sources"]["bm"] = json!({"type": "raster", "tiles": b["tiles"], "tileSize": 256, "maxzoom": b["maxzoom"], "attribution": b["attr"]});
        style["layers"].as_array_mut().unwrap().push(json!({"id": "basemap", "type": "raster", "source": "bm", "layout": {"visibility": "none"}}));
    }
    Ok((active_bm, bms, style))
}

const VIEW_BOOLS: [&str; 4] = ["road_fill", "bridges", "tunnels", "view3d"];

/// `views` as the page reads it, [{name, set}]; a setting that is not known, or that names a colour option, an
/// overlay, a class, a base map or a palette that the page does not have, is an error.
fn check_views(views: &Value, have: [(&str, Vec<Value>); 5]) -> Result<Vec<Value>, crate::Error> {
    let mut out = Vec::new();
    for (name, sets) in views.as_object().into_iter().flatten() {
        let s = sets.as_object().ok_or_else(|| crate::error::options(format!("view '{name}': not a mapping of settings")))?;
        let mut unknown: Vec<&String> = s.keys().filter(|k| !["color", "overlays", "classes", "basemap", "palette"].contains(&k.as_str())
                                                          && !VIEW_BOOLS.contains(&k.as_str())).collect();
        if !unknown.is_empty() {
            unknown.sort();
            return Err(crate::error::options(format!("view '{name}': unknown setting(s) {}", repr(&json!(unknown)))));
        }
        for k in VIEW_BOOLS {
            if s.get(k).is_some_and(|v| !v.is_boolean()) {
                return Err(crate::error::options(format!("view '{name}': {k} must be True or False, got {}", repr(&s[k]))));
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
                return Err(crate::error::options(format!("view '{name}': {k} {} not in the page (it has {})", repr(&json!(missing)), repr(&json!(have)))));
            }
        }
        out.push(json!({"name": name, "set": sets}));
    }
    Ok(out)
}

/// _engine._views: the views as the page reads them, and the palettes that they name other than the page's. Each such palette is
/// resolved with the look's options and map options (its colours), and merged into stage 1's output (palettes::add).
fn views(src: &mut Styled, k: &PageKeys, look: &Look, options: &Options, basemaps: &[Value]) -> Result<(Vec<Value>, Vec<String>), crate::Error> {
    let meta = &src.metadata;
    let ctl = &meta["roadstyle:controls"];
    let colors: Vec<Value> = if !look.map.color.options.is_empty() {
        meta["roadstyle:color_options"].as_array().into_iter().flatten().map(|o| o["name"].clone()).collect()
    } else { Vec::new() };
    let overlays: Vec<Value> = ctl["overlays"].as_array().into_iter().flatten().map(|o| o["label"].clone()).collect();
    let classes = ctl["filter"]["classes"].as_array().cloned().unwrap_or_default();
    let palettes: Vec<Value> = options.style_names("palettes").into_iter().map(Value::from).collect();
    let views = check_views(&k.views, [("color", colors), ("overlays", overlays), ("classes", classes), ("basemap", basemaps.to_vec()),
                                           ("palette", palettes)])?;
    let mut pals: Vec<String> = Vec::new();
    for p in views.iter().filter_map(|v| v["set"]["palette"].as_str()) {
        if p != look.palette && !pals.iter().any(|q| q == p) {
            pals.push(p.into());
        }
    }
    if !pals.is_empty() {
        let looks = pals.iter().map(|n| {
            let o = Options { palette: Some(n.clone()), ..options.clone() };
            Ok((n.clone(), Look::resolve(&o)?.with_map(look.map.clone())?))
        }).collect::<Result<Vec<_>, crate::Error>>()?;
        crate::palettes::add(src, &look.palette, &looks)?;
    }
    Ok((views, pals))
}

/// _engine._palette_swatches: the filter panel's colour of each class in each palette of the views (the fill of the class's first road
/// in that palette), and the page's palette's (the swatches).
fn palette_swatches(style: &mut Value, rows: &[crate::sources::TableRow], pals: &[String], look: &Look) {
    let fb = &look.sections.roads.fallback["fill"];
    let state = style["metadata"]["roadstyle:state"]["rs_palette"].as_str().unwrap_or_default().to_string();
    let flt = &mut style["metadata"]["roadstyle:controls"]["filter"];
    let col = flt["col"].as_str().unwrap_or_default().to_string();
    // a road's field as the road table writes it (none when it has none)
    fn get(r: &crate::sources::TableRow, k: &str) -> Option<Value> {
        r.props.iter().find(|(n, _)| *n == k).map(|(_, c)| crate::table::js_value(c.to_value()))
    }
    let mut first: Vec<(Value, &crate::sources::TableRow)> = Vec::new();
    for r in rows {
        let k = get(r, &col).unwrap_or(Value::Null);
        if !first.iter().any(|(x, _)| *x == k) {
            first.push((k, r));
        }
    }
    let row = |c: &Value| first.iter().find(|(k, _)| k == c).map(|(_, r)| *r);
    let classes = flt["classes"].as_array().cloned().unwrap_or_default();
    let mut out = Map::new();
    for n in pals {
        let of: Map<String, Value> = classes.iter().map(|c| {
            let fill = roadstyle_model::mark::Mark::Fill.name();
            let v = row(c).and_then(|r| get(r, &roadstyle_model::mark::in_palette(fill, n)).or_else(|| get(r, fill))).filter(present)
                .unwrap_or_else(|| fb.clone());
            (c.as_str().unwrap_or_default().to_string(), v)
        }).collect();
        out.insert(n.clone(), Value::Object(of));
    }
    out.insert(state, flt["swatches"].clone());
    flt["palettes"] = Value::Object(out);
}

/// _engine._tiled_page: the tiled page's style and its PMTiles archive, from stage 2 of the same stage 1 (no second build). The style
/// has one vector source `roads` (the embedded archive) with the layers `simple` and `slots`; the other sources stay inline.
fn tiled_page(s: &Styled, look: &Look, a: &Map<String, Value>) -> Result<(Value, Option<Vec<u8>>), crate::Error> {
    let c = &look.map.columns;
    let hw = Some(c.class.as_str()).filter(|h| !h.is_empty()).unwrap_or("highway");
    fn col(v: &Option<String>) -> Option<&str> {
        v.as_deref().filter(|c| !c.is_empty())
    }
    let keep = [Some(hw), Some(col(&c.filter).unwrap_or(hw)), Some(roadstyle_model::mark::Mark::Twoway.name()), Some(roadstyle_model::mark::Mark::Edge.name()), Some("lvl"), col(&c.width_m)];
    let mut o = TileOptions::new(&s.layers, &s.metadata, &s.saved[TILES], &s.saved[COLUMNS], &[])?;
    o.exact = Some(keep.into_iter().flatten().map(String::from).collect());
    o.only = Some(["roads", "simple", "slots"].map(String::from).to_vec());
    let (style, t) = crate::tile_stage(s, &o, &json!({"url": "pmtiles://roads"}), crate::sources::SourceMode::inline_of(a))?;
    let archive = t.archive(t.bounds().ok_or(crate::tiles::Error::Empty)?, &t.layer_names())?;
    Ok((style, Some(archive)))
}

/// A camera key of the call, when it gave one.
fn k_cam<'a>(k: &'a PageKeys, name: &str) -> Option<&'a Value> {
    match name {
        "pitch" => k.pitch.as_ref(),
        "bearing" => k.bearing.as_ref(),
        _ => k.max_pitch.as_ref(),
    }
    .filter(|v| !v.is_null())
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
        assert_eq!(e.to_string(), "view 'a': classes ['motorway'] not in the page (it has ['primary'])");
        assert_eq!(check_views(&json!({"a": {"zoom": 3}}), have()).unwrap_err().to_string(), "view 'a': unknown setting(s) ['zoom']");
        assert!(matches!(check_views(&json!({"a": {"bridges": 1}}), have()), Err(crate::Error::Options(m)) if m == "view 'a': bridges must be True or False, got 1"));
    }

    #[test]
    fn given_of_has_the_page_keys_of_a_call() {
        let o = Options::from_value(&json!({"args": {"state": "live", "sidebar": "dashboard", "popup_mode": "panel", "name": "N",
                                                     "road_popup": ["highway"], "color_by": "lanes"}})).unwrap();
        let g = given_of(&Look::resolve(&o).unwrap(), &o.args);
        assert_eq!(g["sidebar"], "dashboard");
        assert_eq!(g["popup_mode"], "panel");
        assert_eq!((&g["name"], &g["road_popup"]), (&json!("N"), &json!(["highway"])));   // a sidebar's defaults give way to them
        assert!(!g.contains_key("color_by") && !g.contains_key("state"), "map options are the look's: {g:?}");
    }
}
