//! The page writer: the HTML page of a live style (state "live") and the options of
//! its dashboard. The frame, the popup, the dashboard bundle and the
//! page's scripts are roadstyle's static files, read when the crate is built. The JSON values are serde_json's text (the Rust API is
//! the design, 2026-10-24: the values of the page are the design, not its bytes), each "<" as \u003c. MapLibre stays a
//! placeholder (`__MAPLIBRE_JS__`, `__MAPLIBRE_CSS__`): the caller inlines it or loads it from a CDN.

use base64::Engine;
use serde::{Deserialize, Serialize};
use crate::sources::Styled;
use roadstyle_engine::table::JsSafe;
use serde_json::{Map, Number, Value};

macro_rules! asset {
    ($p:literal) => {
        roadstyle_assets::text!($p)
    };
}
const TEMPLATE: &str = asset!("static/web_template.html");
const POPUP_CSS: &str = asset!("static/popup.css");
const POPUP_JS: &str = asset!("static/popup.js");
const DASH_CSS: &str = asset!("static/dashboard/dashboard.css");
// the dashboard's modules in the order of static/dashboard/files.txt
const DASH_JS: [&str; roadstyle_assets::DASHBOARD_JS.len()] = roadstyle_assets::DASHBOARD_JS;
const INFLATE: &str = asset!("static/page/inflate.html");
const SIMPLE: &str = asset!("static/page/simple.html");
const TILES: &str = asset!("static/page/tiles.html");
const SIDE: &str = asset!("static/page/side.html");
const PMTILES_JS: &str = asset!("vendor/pmtiles.js");

/// The options of rsDashboard that the page gives, in the page's order. Each has
/// the name of a `render` keyword. A number stays as the caller gave it (`55` or `55.0`).
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PageOptions {
    pub basemaps: Vec<Value>,
    pub basemap_switcher: bool,
    /// a tiled page (the roads in the embedded PMTiles archive)
    pub tiles: bool,
    /// the road layer ("roads-simple")
    pub simple: Value,
    /// roadstyle:sources and roadstyle:arrows (contract::roles, contract::arrow_kind); live: roadstyle:live, or null
    pub sources: Value,
    pub arrows: Value,
    pub live: Value,
    pub popup_mode: String,
    pub find_control: bool,
    pub zoom_readout: bool,
    pub pitch_3d: Number,
    /// true, false or "window"
    pub street_view: Value,
    pub street_view_key: String,
    pub google_3d: bool,
    pub select_color: Value,
    pub filter: Value,
    /// the Roads box (render's filter_control; the dashboard shows it when the filter has classes)
    pub filter_control: bool,
    pub color_options: Value,
    /// the legend box of the colour options (render's legend)
    pub legend: bool,
    pub color_active: Value,
    pub overlays: Value,
    pub overlay_control: bool,
    pub overlay_popup: bool,
    pub tunnel: Value,
    pub fill_layers: Value,
    /// the layers that a road is picked on (contract::pick_layers)
    pub pick: Value,
    pub road_fill: Value,
    pub views: Value,
    pub items: Value,
    pub road_popup: Value,
    pub road_tooltip: Value,
    pub hover_delay_ms: i64,
    pub edge_id_col: String,
    pub arrow_icon: Value,
    pub arrow_color: Value,
    pub arrow_rules: Value,
    /// a duckOSM map's modes with their counts (roadstyle:controls.modes) and its boxes' layout ("stack"); a page with no base map has none
    #[serde(default, skip_serializing_if = "Value::is_null")]
    pub modes: Value,
    #[serde(default, skip_serializing_if = "Value::is_null")]
    pub box_layout: Value,
}

/// The page's start camera (the camera settings with the call's pitch, bearing and max_pitch).
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Camera {
    pub pitch: Number,
    pub bearing: Number,
    pub max_pitch: Number,
}

/// What the page needs besides the style and the options.
pub struct PageParts<'a> {
    pub name: &'a str,
    pub cam: Camera,
    /// [minx, miny, maxx, maxy] of the roads
    pub bounds: [f64; 4],
    pub side_panel_html: Option<&'a str>,
    pub host_panel_width: f64,
    /// gzip the big GeoJSON sources (_compress_sources); `gz`: the blobs made by the caller (the caller's zlib), else the crate gzips
    pub compress: bool,
    pub gz: Option<Map<String, Value>>,
    /// a tiled page: the PMTiles archive
    pub tiles: Option<&'a [u8]>,
    /// the road table (tiles.sidecar's form), in both ways: the table, or its gzipped base64 made by the caller
    pub side: Option<(&'a Value, Option<&'a str>)>,
    /// the settings of simple mode's recolouring script, when the page is in simple mode
    pub simple_js: Option<&'a Value>,
    /// the Styled of the style's null `data` (page_from's style: `Styled::style_with`); None: the style has its data
    pub sources: Option<&'a Styled>,
}

/// The dashboard bundle.
fn dashboard_js() -> String {
    DASH_JS.iter().map(|src| {
        let mut out = String::with_capacity(src.len());
        for line in src.split_inclusive('\n') {
            if line.starts_with("import ") && line.ends_with('\n') {
                continue;
            }
            out.push_str(line.strip_prefix("export ").unwrap_or(line));
        }
        out
    }).collect()
}

/// the frame with the popup and the dashboard in it.
fn frame() -> String {
    TEMPLATE.replace("__POPUP_CSS__", POPUP_CSS).replace("__POPUP_JS__", &POPUP_JS.replace("export ", ""))
        .replace("__DASHBOARD_CSS__", DASH_CSS).replace("__DASHBOARD_JS__", &dashboard_js())
}

/// JSON text for a <script> of the page (audit N23): each "<" as \u003c, the same value in JSON and in JavaScript. A data value with
/// "</script>" in it (a legend's label, a road's field) cannot end the script and run what follows.
fn script_json(v: &Value) -> String {
    script_text(serde_json::to_string(&JsSafe(v)).expect("a JSON value"))
}

/// script_json of a JSON text: "<" occurs in JSON text only inside a string, so each "<" can be written as \u003c.
fn script_text(json: String) -> String {
    json.replace('<', "\\u003c")
}

/// `text` with each token of `values` in it replaced, in one pass: a value is not searched again.
fn fill(text: &str, values: &[(&str, String)]) -> String {
    let mut out = String::with_capacity(text.len() + values.iter().map(|(_, v)| v.len()).sum::<usize>());
    let mut rest = text;
    while let Some((at, (k, v))) = values.iter().filter_map(|kv| rest.find(kv.0).map(|i| (i, kv))).min_by_key(|(i, _)| *i) {
        out.push_str(&rest[..at]);
        out.push_str(v);
        rest = &rest[at + k.len()..];
    }
    out.push_str(rest);
    out
}

/// html.escape (quote=True).
pub(crate) fn escape(s: &str) -> String {
    s.replace('&', "&amp;").replace('<', "&lt;").replace('>', "&gt;").replace('"', "&quot;").replace('\'', "&#x27;")
}

pub(crate) fn gzip_b64(raw: &[u8]) -> String {
    use std::io::Write;
    let mut e = flate2::GzBuilder::new().mtime(0).write(Vec::new(), flate2::Compression::new(6));
    e.write_all(raw).unwrap();
    base64::engine::general_purpose::STANDARD.encode(e.finish().unwrap())
}

/// _compress_sources: every GeoJSON source of 256 KB or more out of the style, as gzipped base64; the source starts empty. A null
/// `data` is the source's of `fill` (page_from's style, audit D3).
fn compress_sources(style: &mut Value, fill: Option<&Styled>) -> Map<String, Value> {
    let mut blobs = Map::new();
    for (sid, src) in style["sources"].as_object_mut().into_iter().flatten() {
        if src["type"] != "geojson" {
            continue;
        }
        let mut raw = Vec::new();
        match (&src["data"], fill) {
            (Value::Object(_), _) => serde_json::to_writer(&mut raw, &JsSafe(&src["data"])).expect("a Vec takes every byte"),
            (Value::Null, Some(s)) if s.write_source_data(sid, &mut raw).expect("a Vec takes every byte") => {}
            _ => continue,
        }
        if raw.len() < 262144 {
            continue;
        }
        blobs.insert(sid.clone(), Value::from(gzip_b64(&raw)));
        src["data"] = serde_json::json!({"type": "FeatureCollection", "features": []});
    }
    blobs
}

/// _host_panel: the host page's own panel on the right.
fn host_panel(html: Option<&str>, width: f64, name: &str) -> String {
    let Some(html) = html else { return String::new() };
    let w = width as i64;
    format!("<style>body{{--rs-side:{w}px}}#map{{right:{w}px}}body.rs-side-hidden{{--rs-side:0px}}body.rs-side-hidden #map{{right:0}}.rs-host{{width:{w}px}}</style>\
             <div class=\"rs-side rs-host\"><div class=\"rs-side-hd\"><span>{}</span><span class=\"rs-side-min\" title=\"Hide panel\">&raquo;</span></div>\
             <div class=\"rs-side-host\">{html}</div></div>", escape(name))
}

/// the page of `style` (the base map's and the roads' sources and layers) with the dashboard's options `page`.
pub fn page_html(mut style: Value, page: &PageOptions, p: &PageParts) -> String {
    let gz = match (&p.gz, p.compress) {
        (Some(g), _) => g.clone(),
        (None, true) => compress_sources(&mut style, p.sources),
        (None, false) => Map::new(),
    };
    // the style once as text, each null `data` with its source's FeatureCollection (audit D3, N29: no copy of a source)
    let style_json = match p.sources {
        Some(s) => {
            let mut out = Vec::new();
            s.write_with(&style, &mut out).expect("a Vec takes every byte");
            script_text(String::from_utf8(out).expect("JSON text is UTF-8"))
        }
        None => script_json(&style),
    };
    let [x0, y0, x1, y1] = p.bounds;
    let Ok(Value::Object(mut opts)) = serde_json::to_value(page) else { unreachable!("PageOptions is a JSON object") };
    let c = &p.cam;
    opts.insert("camera".into(), serde_json::json!({"center": [(x0 + x1) / 2.0, (y0 + y1) / 2.0], "pitch": c.pitch, "bearing": c.bearing,
                                                    "max_pitch": c.max_pitch, "bounds": [[x0, y0], [x1, y1]]}));
    // the frame's tokens in one pass (audit R3): a value is not read again, so the host's own text may hold any token
    let mut html = fill(&frame(), &[("__TITLE__", escape(p.name)), ("__STYLE__", style_json),
                                    ("__RS_OPTIONS__", script_json(&Value::Object(opts))),
                                    ("__HOST_PANEL_HTML__", host_panel(p.side_panel_html, p.host_panel_width, p.name))]);
    let mut parts = String::new();
    if let Some(pmt) = p.tiles {
        parts = format!("<script>{}</script>{}", PMTILES_JS.replace("</script>", "<\\/script>"),
                        TILES.replace("__RS_PMTILES_B64__", &base64::engine::general_purpose::STANDARD.encode(pmt)));
    }
    if let Some((side, side_b64)) = p.side {
        let side_b64 = side_b64.map_or_else(|| gzip_b64(&serde_json::to_vec(&JsSafe(side)).expect("a JSON value")), String::from);
        parts.push_str(&SIDE.replace("__RS_SIDE_B64__", &side_b64));
    }
    html = html.replacen("<script>__RS_TILES__</script>", &parts, 1);
    if let Some(s) = p.simple_js {
        html = html.replacen("</body>", &(SIMPLE.replace("__RS_SIMPLE__", &script_json(s)) + "</body>"), 1);
    }
    if !gz.is_empty() {
        html = html.replacen("</body>", &(INFLATE.replace("__RS_GZ__", &script_json(&Value::Object(gz))) + "</body>"), 1);
    }
    html
}

/// The page from JSON texts (the Python binding and the browser): `style`, `page` (the options) and `parts` ({name, cam, bounds,
/// side_panel_html, host_panel_width, compress, gz, side, side_b64, simple_js}); `pmtiles`: the archive of a tiled page.
pub fn page_of_json(style: &str, page: &str, parts: &str, pmtiles: Option<&[u8]>) -> Result<String, crate::Error> {
    let read = |t: &str, what: &str| serde_json::from_str::<Value>(t).map_err(|e| crate::error::options(format!("{what}: not JSON: {e}")));
    let (style, p) = (read(style, "style")?, read(parts, "parts")?);
    let page: PageOptions = serde_json::from_str(page).map_err(|e| crate::error::options(format!("page: {e}")))?;
    let cam: Camera = serde_json::from_value(p["cam"].clone()).map_err(|e| crate::error::options(format!("parts.cam: {e}")))?;
    let b = |i: usize| p["bounds"][i].as_f64().unwrap_or(0.0);
    let parts = PageParts {
        name: p["name"].as_str().unwrap_or(""), cam, bounds: [b(0), b(1), b(2), b(3)], side_panel_html: p["side_panel_html"].as_str(),
        host_panel_width: p["host_panel_width"].as_f64().unwrap_or(320.0), compress: p["compress"] == true, gz: p["gz"].as_object().cloned(),
        tiles: pmtiles, side: (p["side_b64"].is_string() || !p["side"].is_null()).then(|| (&p["side"], p["side_b64"].as_str())),
        simple_js: (!p["simple_js"].is_null()).then_some(&p["simple_js"]), sources: None,
    };
    Ok(page_html(style, &page, &parts))
}
