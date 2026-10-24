//! `roadstyle-mcp`: roadstyle as tools for AI agents, an MCP server over stdio on the rmcp SDK (docs/design/agent-tools.md; plan step A2
//! in docs/design/rust_library.md). The tools of the Python server (src/roadstyle/mcp_server.py) with the same names, inputs and
//! outputs: render_file, render_place and snapshot. A map is saved to a file and only its path goes back to the agent (a page is
//! megabytes). Nothing may print to stdout, which carries the protocol. An error goes back to the agent as the tool's result, with its
//! message, so the agent can fix a wrong path, a missing column or a misspelt option.

use std::path::{Path, PathBuf};

use rmcp::handler::server::{router::tool::ToolRouter, wrapper::Parameters};
use rmcp::model::{CallToolResult, ContentBlock, Implementation, ServerCapabilities, ServerConfig};
use base64::Engine;
use rmcp::{schemars, tool, tool_handler, tool_router, ServerHandler, ServiceExt};
use roadstyle_snapshot::{Camera, Shot};
use serde_json::{Map, Value};

const INSTRUCTIONS: &str = "\
roadstyle draws road networks as styled, interactive, offline HTML maps (MapLibre, one file).
- render_place: any place name -> OpenStreetMap roads (osmnx) -> map. render_file: a road file.
- Each returns the saved .html path and a PNG preview. Look at the preview before reporting back.
- A street name shows where it fits inside its road: main roads from zoom 15-16, side streets from 17.
  One-way arrows: main roads from zoom 15, side streets from 17. The preview is zoomed out, so use
  snapshot(html_path, lon, lat, zoom=17) to check them.
- options = render_edges keywords, e.g. {\"color_by\": \"maxspeed\", \"legend\": true},
  {\"palette\": \"carto\"} (amber is the default; also highsat, mono), {\"view_3d\": true}.
- Edges are directed: a two-way street is two edges drawn side by side. Don't merge them.
Docs: https://khoshkhah.github.io/roadstyle/ (every keyword: /reference/parameters/).";

/// The Python server that has what this one does not have yet (render_place).
const PYTHON: &str = "the Python server (pip install roadstyle-mcp==0.25.0)";

/// The vendored MapLibre (WebMap.save and the CLI's `roadstyle page` put the same in), so a saved map works offline.
const MAPLIBRE_JS: &str = include_str!("../../../src/roadstyle/vendor/maplibre-gl.js");
const MAPLIBRE_CSS: &str = include_str!("../../../src/roadstyle/vendor/maplibre-gl.css");

/// The options that stage 1 (the look and the sources) reads: render_edges keywords. The page's own keywords (basemap, popup_mode, ...)
/// are page_from's (`page_options::page_defaults`). `overlays` and `items` are not here: they are GeoDataFrames.
const STAGE1: &[&str] = &[
    "access_col", "arrows", "boundary", "bridge_col", "cap_col", "cap_end_col", "cap_start_col", "casing_end_col", "casing_level_col",
    "casing_m", "casing_min_px", "casing_start_col", "cmap", "color_active", "color_by", "color_col", "color_key", "color_options",
    "color_table", "colors", "data_maxzoom", "data_tolerance", "directed_col", "driving_col", "edge_id_col", "fill_level_col",
    "filter_col", "filter_control", "head_end_m_col", "head_m", "head_start_m_col", "highway_col", "hover_color", "hover_delay_ms",
    "items_popup", "labels", "layer_col", "legend", "minzoom", "name", "offset_frac", "offset_zoom", "palette", "profile", "road_fill",
    "road_popup", "road_tooltip", "select_color", "settings", "simple", "style", "tiles", "tooltip", "tunnel_col", "tunnel_control",
    "view_3d", "views", "vmax", "vmin", "width_by", "width_frac", "width_m_col", "width_m_zoom",
];

#[derive(serde::Deserialize, schemars::JsonSchema)]
struct RenderFile {
    /// The road file: GeoParquet, GeoJSON, a Shapefile (its .dbf and .prj beside it) or a GeoPackage.
    path: String,
    /// render_edges keywords, e.g. {"color_by": "speed", "cmap": "viridis", "legend": true}.
    options: Option<Map<String, Value>>,
    /// Where to save the .html (default ~/roadstyle-maps/<file name>.html).
    output_path: Option<String>,
}

fn drive() -> String {
    "drive".into()
}

#[derive(serde::Deserialize, schemars::JsonSchema)]
struct RenderPlace {
    /// Any name OpenStreetMap's geocoder knows, e.g. "Södermalm, Stockholm" or "Tartu, Estonia".
    place: String,
    /// "drive", "walk", "bike", "all", "drive_service" or "all_public".
    #[serde(default = "drive")]
    network_type: String,
    /// render_edges keywords, e.g. {"color_by": "maxspeed", "legend": true}.
    options: Option<Map<String, Value>>,
    /// Where to save the .html (default ~/roadstyle-maps/<place>.html).
    output_path: Option<String>,
}

#[derive(serde::Deserialize, schemars::JsonSchema)]
struct Snapshot {
    /// A saved roadstyle map (.html).
    html_path: String,
    lon: Option<f64>,
    lat: Option<f64>,
    /// 0-22.
    zoom: Option<f64>,
    bearing: Option<f64>,
    pitch: Option<f64>,
}

#[derive(Clone)]
struct Server {
    tool_router: ToolRouter<Self>,
}

#[tool_router]
impl Server {
    #[tool(description = "Draw the road edges in a file (GeoParquet, GeoJSON, Shapefile or GeoPackage) as an interactive HTML map.\n\nThe \
        file needs line geometry (any CRS) and a road-class column, \"highway\" by default (another name: options={\"highway_col\": \"...\"}).\n\
        options: render_edges keywords, e.g. {\"color_by\": \"speed\", \"cmap\": \"viridis\", \"legend\": true}.\nReturns the saved path, a \
        summary and a PNG preview.")]
    async fn render_file(&self, Parameters(a): Parameters<RenderFile>) -> CallToolResult {
        // the page and its preview (Chromium) take seconds: on a thread of their own, away from the runtime that answers the agent
        match tokio::task::spawn_blocking(move || render_file(a)).await {
            Ok(Ok((text, out))) => CallToolResult::success(std::iter::once(ContentBlock::text(text)).chain(preview(&out, &Camera::default())).collect()),
            Ok(Err(e)) => result(Err(e)),
            Err(e) => result(Err(e.to_string())),
        }
    }

    #[tool(description = "Download the OpenStreetMap road network of a place and draw it as an interactive HTML map.\n\nKeep the place \
        to a district or a city: a county takes minutes to download.\nReturns the saved path, a summary and a PNG preview.")]
    fn render_place(&self, Parameters(a): Parameters<RenderPlace>) -> CallToolResult {
        let _ = (a.place, a.network_type, a.options, a.output_path);
        // a road download in Rust waits for duckosm-rust's polygon clip (docs/design/rust_library.md, A2)
        result(Err(format!("render_place is not in the Rust server yet. Use {PYTHON}, or save the roads to a file and use render_file.")))
    }

    #[tool(description = "PNG of a saved roadstyle map, optionally with a camera (centre lon/lat, zoom 0-22).\n\nStreet names: main roads \
        from zoom 15-16, side streets from 17; one-way arrows: main roads from 15, side streets from 17.\nWithout a camera the map's own \
        opening view is captured.")]
    async fn snapshot(&self, Parameters(a): Parameters<Snapshot>) -> CallToolResult {
        let cam = Camera { center: a.lon.zip(a.lat).map(|(lon, lat)| [lon, lat]), zoom: a.zoom, pitch: a.pitch, bearing: a.bearing };
        let html = std::path::absolute(expand(&a.html_path)).unwrap_or_else(|_| expand(&a.html_path));
        // headless_chrome waits on its own thread: away from the runtime that answers the agent
        match tokio::task::spawn_blocking(move || preview(&html, &cam)).await {
            Ok(c) => CallToolResult::success(c),
            Err(e) => result(Err(e.to_string())),
        }
    }
}

/// The PNG of a saved page beside it (<page>.png), as an image for the agent, and its warning (a map that did not load). Without a
/// browser it is a note, not an error: the map still stands (as in the Python server).
fn preview(html: &Path, cam: &Camera) -> Vec<ContentBlock> {
    let png = html.with_extension("png");
    match roadstyle_snapshot::snapshot(html, &png, cam, &Shot::default()).and_then(|p| Ok((std::fs::read(&p.path)?, p.warning))) {
        Ok((bytes, warning)) => std::iter::once(ContentBlock::image(base64::engine::general_purpose::STANDARD.encode(bytes), "image/png"))
            .chain(warning.map(|w| ContentBlock::text(format!("warning: {w}")))).collect(),
        Err(e) => vec![ContentBlock::text(format!("(no preview: {e})"))],
    }
}

#[tool_handler(router = self.tool_router)]
impl ServerHandler for Server {
    fn get_info(&self) -> ServerConfig {
        ServerConfig::new(ServerCapabilities::builder().enable_tools().build())
            .with_server_info(Implementation::new("roadstyle", env!("CARGO_PKG_VERSION")))
            .with_instructions(INSTRUCTIONS)
    }
}

fn result(r: Result<String, String>) -> CallToolResult {
    match r {
        Ok(text) => CallToolResult::success(vec![ContentBlock::text(text)]),
        Err(e) => CallToolResult::error(vec![ContentBlock::text(e)]),
    }
}

/// render_edges ignores a misspelt keyword; an agent needs to hear about it (with the close names, as Python's difflib gives them). The
/// keywords: stage 1's and the page's (page_from's defaults).
fn check_options(options: &Map<String, Value>) -> Result<(), String> {
    let page = roadstyle::page_options::page_defaults();
    let mut valid: Vec<&str> = STAGE1.iter().copied().chain(page.keys().map(String::as_str)).collect();
    valid.sort();
    valid.dedup();
    let mut bad: Vec<&String> = options.keys().filter(|k| !valid.contains(&k.as_str())).collect();
    if bad.is_empty() {
        return Ok(());
    }
    bad.sort();
    let hints: Vec<String> = bad.iter().map(|k| {
        let mut close: Vec<(f64, &str)> = valid.iter().map(|v| (strsim::normalized_levenshtein(k, v), *v)).filter(|(s, _)| *s >= 0.6).collect();
        close.sort_by(|a, b| b.0.total_cmp(&a.0));
        let close: Vec<String> = close.iter().take(3).map(|(_, v)| format!("'{v}'")).collect();
        if close.is_empty() { format!("'{k}'") } else { format!("'{k}' (did you mean {}?)", close.join(", ")) }
    }).collect();
    Err(format!("unknown option(s): {}. Valid options: {}", hints.join("; "), valid.join(", ")))
}

/// The roads of a road file, by its extension, and a reader's warning (a GeoPackage with more tables: geopandas' words).
fn read_file(src: &Path) -> Result<(roadstyle::RoadTable, Option<String>), String> {
    let what = src.file_name().unwrap_or_default().to_string_lossy().to_string();
    let read = |p: &Path| std::fs::read(p).map_err(|e| format!("{}: {e}", p.display()));
    match src.extension().and_then(|e| e.to_str()).unwrap_or("").to_lowercase().as_str() {
        "parquet" | "geoparquet" => Ok((roadstyle::read::read_roads(read(src)?, "geometry")?, None)),
        "geojson" | "json" => Ok((roadstyle::geojson::read_roads(&read(src)?)?, None)),
        "shp" => {
            let prj = std::fs::read_to_string(src.with_extension("prj")).ok();     // no .prj: no CRS, the reader's error (as Python)
            Ok((roadstyle::shp::read_roads(&read(src)?, &read(&src.with_extension("dbf"))?, prj.as_deref(), &what)?, None))
        }
        "gpkg" => Ok(roadstyle::gpkg::read_roads(&read(src)?, &what)?),
        e => Err(format!("{}: a .{e} file is not read: GeoParquet, GeoJSON, a Shapefile or a GeoPackage", src.display())),
    }
}

fn expand(p: &str) -> PathBuf {
    match (p.strip_prefix("~/"), std::env::var_os("HOME")) {
        (Some(rest), Some(home)) => Path::new(&home).join(rest),
        _ => PathBuf::from(p),
    }
}

/// The page's path: `output_path` with the suffix .html, else ~/roadstyle-maps/<stem as a slug>.html.
fn out_path(output_path: Option<&str>, stem: &str) -> Result<PathBuf, String> {
    if let Some(p) = output_path {
        return std::path::absolute(expand(p)).map(|p| p.with_extension("html")).map_err(|e| e.to_string());
    }
    let mut slug = String::new();
    for c in stem.chars() {
        if c.is_alphanumeric() || c == '_' || c == '-' {
            slug.extend(c.to_lowercase());
        } else if !slug.ends_with('_') {
            slug.push('_');
        }
    }
    let slug = slug.trim_matches('_');
    Ok(expand("~/roadstyle-maps").join(format!("{}.html", if slug.is_empty() { "map" } else { slug })))
}

/// The summary for the agent: the edges, the most common classes, the bounds (as the Python server writes them).
fn summary(roads: &roadstyle::read::RoadTable, class_col: &str) -> Result<String, String> {
    let col = roads.col(class_col)
        .ok_or_else(|| format!("no road-class column {class_col:?} (another name: options={{\"highway_col\": \"...\"}})"))?;
    let mut counts: Vec<(String, usize)> = Vec::new();
    let (mut lo, mut hi) = ([f64::INFINITY; 2], [f64::NEG_INFINITY; 2]);
    for r in 0..roads.len() {
        let c = roads.cell(col, r);
        let c = c.as_str().map_or_else(|| if c.is_null() { "None".to_string() } else { c.to_value().to_string() }, str::to_string);
        match counts.iter_mut().find(|(k, _)| *k == c) {
            Some((_, n)) => *n += 1,
            None => counts.push((c, 1)),
        }
        for p in roads.line(r).into_iter().flatten() {
            (0..2).for_each(|i| { lo[i] = lo[i].min(p[i]); hi[i] = hi[i].max(p[i]); });
        }
    }
    counts.sort_by_key(|c| std::cmp::Reverse(c.1));         // stable: ties keep the order of the first row (pandas' value_counts)
    let classes: Vec<String> = counts.iter().take(8).map(|(k, n)| format!("{k} {n}")).collect();
    Ok(format!("{} edges; classes: {}\nbounds (w, s, e, n): {:.5}, {:.5}, {:.5}, {:.5}",
               thousands(roads.len()), classes.join(", "), lo[0], lo[1], hi[0], hi[1]))
}

fn thousands(n: usize) -> String {
    let s = n.to_string();
    let mut out = String::new();
    for (i, c) in s.chars().enumerate() {
        if i > 0 && (s.len() - i).is_multiple_of(3) {
            out.push(',');
        }
        out.push(c);
    }
    out
}

/// The page of a road file, saved; its answer for the agent (Python's mcp_server._render) and the page's path (for the preview).
fn render_file(a: RenderFile) -> Result<(String, PathBuf), String> {
    let mut options = a.options.unwrap_or_default();
    check_options(&options)?;
    let src = expand(&a.path);
    let (roads, read_warning) = read_file(&src)?;
    let class_col = options.get("highway_col").and_then(Value::as_str).unwrap_or("highway").to_string();
    let text = summary(&roads, &class_col)?;
    let out = out_path(a.output_path.as_deref(), &src.file_stem().unwrap_or_default().to_string_lossy())?;
    // the default CARTO tiles come back stamped "API KEY REQUIRED" without a key: then a keyless base map, as the Python server
    let key = ["CARTO_API_KEY", "ROADSTYLE_API_KEY"].iter().find_map(|k| std::env::var(k).ok().filter(|v| !v.is_empty()));
    let mut notes = Vec::new();
    if !options.contains_key("basemap") && key.is_none() {
        options.insert("basemap".into(), "esri_street".into());
        notes.push("basemap: esri_street (the default CARTO map needs CARTO_API_KEY)".to_string());
    }
    // the look of render_page: palette, profile and settings apart, the rest as the render's keywords, with state "live"
    let mut args = options;
    let mut look = Map::new();
    for k in ["palette", "profile", "settings"] {
        if let Some(v) = args.remove(k) {
            look.insert(k.into(), v);
        }
    }
    args.insert("highway_col".into(), class_col.into());
    args.insert("state".into(), "live".into());
    look.insert("args".into(), Value::Object(args));
    let o = roadstyle::look::Options::from_value(&Value::Object(look))?;
    let resolved = roadstyle::Look::resolve(&o)?;
    let mut given = Map::new();
    given.insert("api_key".into(), key.map_or(Value::Null, Value::String));
    given.insert("street_view_key".into(), std::env::var("GOOGLE_MAPS_KEY").ok().filter(|v| !v.is_empty()).map_or(Value::Null, Value::String));
    let page = roadstyle::page_options::page_from(roads, &resolved, &o, &given)?;
    let html = page.html.replacen("__MAPLIBRE_CSS__", MAPLIBRE_CSS, 1).replacen("__MAPLIBRE_JS__", &MAPLIBRE_JS.replace("</script>", "<\\/script>"), 1);
    if let Some(d) = out.parent() {
        std::fs::create_dir_all(d).map_err(|e| format!("{}: {e}", d.display()))?;
    }
    std::fs::write(&out, &html).map_err(|e| format!("{}: {e}", out.display()))?;
    // the warnings once each, in order; with our keyless base map, CARTO's warning is about the switcher's other entries
    let mut warnings: Vec<String> = read_warning.into_iter().chain(page.warnings).collect();
    warnings.dedup();
    if !notes.is_empty() {
        warnings.retain(|w| !w.starts_with("CARTO base map requested"));
    }
    let lines: Vec<String> = std::iter::once(format!("Saved {}", out.display())).chain(std::iter::once(text)).chain(notes)
        .chain(warnings.into_iter().map(|w| format!("warning: {w}"))).collect();
    Ok((lines.join("\n"), out))
}

#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let server = Server { tool_router: Server::tool_router() }.serve(rmcp::transport::stdio()).await?;
    server.waiting().await?;
    Ok(())
}
