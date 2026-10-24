//! The page writer (render_web._page_html, docs/design/rust_library.md P6): the HTML page of a live style (state "live") and the options of
//! its dashboard (`page`: the options of rsDashboard, as render_web.render's `page`). The frame, the popup, the dashboard bundle and the
//! page's scripts are roadstyle's static files, read when the crate is built. The text of each JSON value is Python's json.dumps, so the
//! page is the Python page byte for byte. MapLibre stays a placeholder (`__MAPLIBRE_JS__`, `__MAPLIBRE_CSS__`), as in Python's
//! WebMap.html: the caller inlines it or loads it from a CDN.

use base64::Engine;
use serde_json::{Map, Value};

macro_rules! asset {
    ($p:literal) => {
        include_str!(concat!("../../../src/roadstyle/", $p))
    };
}
const TEMPLATE: &str = asset!("static/web_template.html");
const POPUP_CSS: &str = asset!("static/popup.css");
const POPUP_JS: &str = asset!("static/popup.js");
const DASH_CSS: &str = asset!("static/dashboard/dashboard.css");
/// render_web._DASH_FILES, in its order
const DASH_JS: [&str; 20] = [asset!("static/dashboard/core.js"), asset!("static/dashboard/panel.js"), asset!("static/dashboard/find.js"),
    asset!("static/dashboard/zoom.js"), asset!("static/dashboard/view3d.js"), asset!("static/dashboard/float.js"),
    asset!("static/dashboard/streetview.js"), asset!("static/dashboard/google3d.js"), asset!("static/dashboard/basemap.js"),
    asset!("static/dashboard/filter.js"), asset!("static/dashboard/color.js"), asset!("static/dashboard/legend.js"),
    asset!("static/dashboard/overlays.js"), asset!("static/dashboard/tunnel.js"), asset!("static/dashboard/views.js"),
    asset!("static/dashboard/arrows.js"), asset!("static/dashboard/svspot.js"), asset!("static/dashboard/select.js"),
    asset!("static/dashboard/api.js"), asset!("static/dashboard/index.js")];
const INFLATE: &str = asset!("static/page/inflate.html");
const SIMPLE: &str = asset!("static/page/simple.html");
const TILES: &str = asset!("static/page/tiles.html");
const SIDE: &str = asset!("static/page/side.html");
const PMTILES_JS: &str = asset!("vendor/pmtiles.js");

/// What the page needs besides the style and the options (render_web._page_html's keywords).
pub struct PageParts<'a> {
    pub name: &'a str,
    /// the camera: pitch, bearing, max_pitch
    pub cam: &'a Value,
    /// [minx, miny, maxx, maxy] of the roads
    pub bounds: [f64; 4],
    pub side_panel_html: Option<&'a str>,
    pub host_panel_width: f64,
    /// gzip the big GeoJSON sources (_compress_sources); `gz`: the blobs made by the caller (Python's zlib), else the crate gzips
    pub compress: bool,
    pub gz: Option<Map<String, Value>>,
    /// a tiled page: the PMTiles archive
    pub tiles: Option<&'a [u8]>,
    /// the road table (tiles.sidecar's form), in both ways: the table, or its gzipped base64 made by the caller
    pub side: Option<(&'a Value, Option<&'a str>)>,
    /// the settings of simple mode's recolouring script, when the page is in simple mode
    pub simple_js: Option<&'a Value>,
}

/// The dashboard bundle (render_web: the modules without their import lines and the word export at a line start, one script).
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

/// render_web._HTML: the frame with the popup and the dashboard in it.
fn frame() -> String {
    TEMPLATE.replace("__POPUP_CSS__", POPUP_CSS).replace("__POPUP_JS__", &POPUP_JS.replace("export ", ""))
        .replace("__DASHBOARD_CSS__", DASH_CSS).replace("__DASHBOARD_JS__", &dashboard_js())
}

/// html.escape (quote=True).
fn escape(s: &str) -> String {
    s.replace('&', "&amp;").replace('<', "&lt;").replace('>', "&gt;").replace('"', "&quot;").replace('\'', "&#x27;")
}

fn gzip_b64(raw: &[u8]) -> String {
    use std::io::Write;
    let mut e = flate2::GzBuilder::new().mtime(0).write(Vec::new(), flate2::Compression::new(6));
    e.write_all(raw).unwrap();
    base64::engine::general_purpose::STANDARD.encode(e.finish().unwrap())
}

/// _compress_sources: every GeoJSON source of 256 KB or more out of the style, as gzipped base64; the source starts empty.
fn compress_sources(style: &mut Value) -> Map<String, Value> {
    let mut blobs = Map::new();
    for (sid, src) in style["sources"].as_object_mut().into_iter().flatten() {
        if src["type"] != "geojson" || !src["data"].is_object() {
            continue;
        }
        let raw = pyjson::dumps(&src["data"], true);
        if raw.len() < 262144 {
            continue;
        }
        blobs.insert(sid.clone(), Value::from(gzip_b64(raw.as_bytes())));
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

/// render_web._page_html: the page of `style` (the base map's and the roads' sources and layers) with the dashboard's options `page`.
pub fn page_html(mut style: Value, page: &Value, p: &PageParts) -> String {
    let gz = match (&p.gz, p.compress) {
        (Some(g), _) => g.clone(),
        (None, true) => compress_sources(&mut style),
        (None, false) => Map::new(),
    };
    let j = |k: &str| pyjson::dumps(&page[k], false);
    let [x0, y0, x1, y1] = p.bounds;
    let num = |v: &Value| pyjson::dumps(v, false);
    let reps: Vec<(&str, String)> = vec![
        ("__TITLE__", escape(p.name)), ("__ARROW_COLOR__", j("arrow_color")), ("__ARROW_ICON__", j("arrow_icon")), ("__ARROW_RULES__", j("arrow_rules")),
        ("__STYLE__", pyjson::dumps(&style, false)), ("__BASEMAPS__", j("basemaps")), ("__BM_SWITCHER__", j("basemap_switcher")),
        ("__ZOOM_READOUT__", j("zoom_readout")), ("__FILTER__", j("filter")),
        ("__CENTER__", pyjson::dumps(&serde_json::json!([(x0 + x1) / 2.0, (y0 + y1) / 2.0]), false)), ("__PITCH3D__", j("pitch_3d")),
        ("__MAX_PITCH__", num(&p.cam["max_pitch"])), ("__SELECT_COLOR__", j("select_color")), ("__PITCH__", num(&p.cam["pitch"])),
        ("__BEARING__", num(&p.cam["bearing"])), ("__BOUNDS__", pyjson::dumps(&serde_json::json!([[x0, y0], [x1, y1]]), false)),
        ("__RS_FILL_LAYERS__", j("fill_layers")), ("__COLOR_OPTIONS__", j("color_options")), ("__CO_ACTIVE__", j("color_active")),
        ("__OVERLAYS__", j("overlays")), ("__FIND_CONTROL__", j("find_control")), ("__OVERLAY_CONTROL__", j("overlay_control")),
        ("__OVERLAY_POPUP__", j("overlay_popup")), ("__ROAD_ITEMS__", j("items")), ("__TUNNEL__", j("tunnel")), ("__VIEWS__", j("views")),
        ("__RS_ROAD_FILL__", j("road_fill")), ("__ROAD_POPUP__", j("road_popup")), ("__ROAD_POPUP_MODE__", j("popup_mode")),
        ("__EDGE_ID_COL__", j("edge_id_col")), ("__ROAD_TOOLTIP__", j("road_tooltip")), ("__HOVER_DELAY_MS__", j("hover_delay_ms")),
        ("__STREET_VIEW__", j("street_view")), ("__SV_WINDOW_KEY__", j("street_view_key")), ("__GOOGLE_3D__", j("google_3d")),
        ("__RS_TILED__", j("tiles")), ("__RS_LEAN__", j("simple")), ("__RS_SOURCES__", j("sources")), ("__RS_ARROWS__", j("arrows")),
        // the last: the host's own text may hold any other token
        ("__HOST_PANEL_HTML__", host_panel(p.side_panel_html, p.host_panel_width, p.name)),
    ];
    let mut html = frame();
    for (k, v) in reps {
        html = html.replace(k, &v);
    }
    let mut parts = String::new();
    if let Some(pmt) = p.tiles {
        parts = format!("<script>{}</script>{}", PMTILES_JS.replace("</script>", "<\\/script>"),
                        TILES.replace("__RS_PMTILES_B64__", &base64::engine::general_purpose::STANDARD.encode(pmt)));
    }
    if let Some((side, side_b64)) = p.side {
        let side_b64 = side_b64.map_or_else(|| gzip_b64(pyjson::dumps(side, true).as_bytes()), String::from);
        parts.push_str(&SIDE.replace("__RS_SIDE_B64__", &side_b64));
    }
    html = html.replacen("<script>__RS_TILES__</script>", &parts, 1);
    if let Some(s) = p.simple_js {
        html = html.replacen("</body>", &(SIMPLE.replace("__RS_SIMPLE__", &pyjson::dumps(s, false)) + "</body>"), 1);
    }
    if !gz.is_empty() {
        html = html.replacen("</body>", &(INFLATE.replace("__RS_GZ__", &pyjson::dumps(&Value::Object(gz), false)) + "</body>"), 1);
    }
    html
}

/// The page from JSON texts (the Python and the browser bindings): `style`, `page` (the options) and `parts` ({name, cam, bounds,
/// side_panel_html, host_panel_width, compress, gz, side, side_b64, simple_js}); `pmtiles`: the archive of a tiled page.
pub fn make_page(style: &str, page: &str, parts: &str, pmtiles: Option<&[u8]>) -> Result<String, String> {
    let read = |t: &str, what: &str| serde_json::from_str::<Value>(t).map_err(|e| format!("{what}: not JSON: {e}"));
    let (style, page, p) = (read(style, "style")?, read(page, "page")?, read(parts, "parts")?);
    let b = |i: usize| p["bounds"][i].as_f64().unwrap_or(0.0);
    let parts = PageParts {
        name: p["name"].as_str().unwrap_or(""), cam: &p["cam"], bounds: [b(0), b(1), b(2), b(3)], side_panel_html: p["side_panel_html"].as_str(),
        host_panel_width: p["host_panel_width"].as_f64().unwrap_or(320.0), compress: p["compress"] == true, gz: p["gz"].as_object().cloned(),
        tiles: pmtiles, side: (p["side_b64"].is_string() || !p["side"].is_null()).then(|| (&p["side"], p["side_b64"].as_str())),
        simple_js: (!p["simple_js"].is_null()).then_some(&p["simple_js"]),
    };
    Ok(page_html(style, &page, &parts))
}

/// Python's json.dumps of a JSON value: `", "` and `": "` between items (`compact`: `","` and `":"`), every character past ASCII as
/// `\uXXXX`, and a float as Python's repr writes it (`1e-05`, `1e+16`, `60.0`).
pub mod pyjson {
    use serde_json::Value;
    use std::fmt::Write;

    pub fn dumps(v: &Value, compact: bool) -> String {
        let mut out = String::new();
        write(v, compact, &mut out);
        out
    }

    fn write(v: &Value, compact: bool, out: &mut String) {
        match v {
            Value::Null => out.push_str("null"),
            Value::Bool(b) => out.push_str(if *b { "true" } else { "false" }),
            Value::Number(n) => match (n.as_i64(), n.as_u64(), n.as_f64()) {
                (Some(i), _, _) if !n.is_f64() => write!(out, "{i}").unwrap(),
                (_, Some(u), _) if !n.is_f64() => write!(out, "{u}").unwrap(),
                (_, _, Some(f)) => out.push_str(&float(f)),
                _ => out.push_str(&n.to_string()),
            },
            Value::String(s) => string(s, out),
            Value::Array(a) => {
                out.push('[');
                for (i, x) in a.iter().enumerate() {
                    if i > 0 {
                        out.push_str(if compact { "," } else { ", " });
                    }
                    write(x, compact, out);
                }
                out.push(']');
            }
            Value::Object(o) => {
                out.push('{');
                for (i, (k, x)) in o.iter().enumerate() {
                    if i > 0 {
                        out.push_str(if compact { "," } else { ", " });
                    }
                    string(k, out);
                    out.push_str(if compact { ":" } else { ": " });
                    write(x, compact, out);
                }
                out.push('}');
            }
        }
    }

    /// json's ensure_ascii string.
    fn string(s: &str, out: &mut String) {
        out.push('"');
        for c in s.chars() {
            match c {
                '"' => out.push_str("\\\""),
                '\\' => out.push_str("\\\\"),
                '\n' => out.push_str("\\n"),
                '\r' => out.push_str("\\r"),
                '\t' => out.push_str("\\t"),
                '\u{8}' => out.push_str("\\b"),
                '\u{c}' => out.push_str("\\f"),
                c if (c as u32) < 0x20 || (c as u32) > 0x7e => {
                    let mut buf = [0u16; 2];
                    for u in c.encode_utf16(&mut buf) {
                        write!(out, "\\u{u:04x}").unwrap();
                    }
                }
                c => out.push(c),
            }
        }
        out.push('"');
    }

    /// float.__repr__: the shortest digits that read back, fixed from 1e-4 to below 1e16, else with an exponent of two digits or more.
    pub fn float(f: f64) -> String {
        if f.is_nan() {
            return "NaN".into();
        }
        if f.is_infinite() {
            return if f > 0.0 { "Infinity" } else { "-Infinity" }.into();
        }
        let e = format!("{f:e}");            // shortest digits: d.ddde<exp>
        let (mant, exp) = e.split_once('e').unwrap();
        let exp: i32 = exp.parse().unwrap();
        let (sign, mant) = mant.strip_prefix('-').map_or(("", mant), |m| ("-", m));
        let digits: String = mant.chars().filter(|c| *c != '.').collect();
        if (-4..16).contains(&exp) {
            let n = digits.len() as i32;
            let s = if exp >= 0 {
                let int_len = exp + 1;
                if n <= int_len {
                    format!("{digits}{}.0", "0".repeat((int_len - n) as usize))
                } else {
                    format!("{}.{}", &digits[..int_len as usize], &digits[int_len as usize..])
                }
            } else {
                format!("0.{}{digits}", "0".repeat((-exp - 1) as usize))
            };
            format!("{sign}{s}")
        } else {
            let m = if digits.len() > 1 { format!("{}.{}", &digits[..1], &digits[1..]) } else { digits };
            format!("{sign}{m}e{}{:02}", if exp < 0 { '-' } else { '+' }, exp.abs())
        }
    }

    #[cfg(test)]
    mod tests {
        #[test]
        fn floats_as_python_writes_them() {
            for (x, t) in [(60.0, "60.0"), (0.05, "0.05"), (1e-5, "1e-05"), (1e16, "1e+16"), (123456789012345680.0, "1.2345678901234568e+17"),
                           (0.0001, "0.0001"), (-0.0, "-0.0"), (7.4209659, "7.4209659"), (1.5e-7, "1.5e-07"), (2.5e300, "2.5e+300"),
                           (1234567890123456.0, "1234567890123456.0"), (0.1 + 0.2, "0.30000000000000004")] {
                assert_eq!(super::float(x), t);
            }
        }
    }
}
