//! `roadstyle-mcp`: roadstyle as tools for AI agents, an MCP server over stdio on the rmcp SDK (docs/design/agent-tools.md; plan step A2
//! in docs/design/rust_library.md). The tools of the Python server (src/roadstyle/mcp_server.py) with the same names, inputs and
//! outputs: render_file, render_place and snapshot. A map is saved to a file and only its path goes back to the agent (a page is
//! megabytes). Nothing may print to stdout, which carries the protocol. An error goes back to the agent as the tool's result, with its
//! message, so the agent can fix a wrong path, a missing column or a misspelt option.

use std::path::{Path, PathBuf};

use rmcp::handler::server::{router::tool::ToolRouter, wrapper::Parameters};
use rmcp::model::{CallToolResult, ContentBlock, Implementation, ServerCapabilities, ServerConfig};
use rmcp::{schemars, tool, tool_handler, tool_router, ServerHandler, ServiceExt};
use serde_json::{json, Map, Value};

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

/// The Python server that has what this one does not have yet (render_place, the page, the PNG).
const PYTHON: &str = "the Python server (pip install roadstyle-mcp==0.25.0)";

/// The options that stage 1 (the look and the sources) reads: render_edges keywords. TODO(R3): replace this list with R3's typed page
/// options, which also have the page's keywords (basemap, popup_mode, ...). `overlays` and `items` are not here: they are GeoDataFrames.
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
    /// The road file: GeoParquet (GeoJSON, GeoPackage and Shapefile come next).
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
    #[tool(description = "Draw the road edges in a file as an interactive HTML map.\n\nThe file needs line geometry in EPSG:4326 and a \
        road-class column, \"highway\" by default (another name: options={\"highway_col\": \"...\"}).\nReturns the saved path, a summary \
        and a PNG preview.")]
    fn render_file(&self, Parameters(a): Parameters<RenderFile>) -> CallToolResult {
        result(render_file(a))
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
    fn snapshot(&self, Parameters(a): Parameters<Snapshot>) -> CallToolResult {
        let _ = (a.html_path, a.lon, a.lat, a.zoom, a.bearing, a.pitch);
        // TODO(A4): the PNG from the page's style, without a browser
        result(Err(format!("snapshot is not in the Rust server yet (plan step A4). Use {PYTHON}.")))
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

/// render_edges ignores a misspelt keyword; an agent needs to hear about it (with the close names, as Python's difflib gives them).
fn check_options(options: &Map<String, Value>) -> Result<(), String> {
    let mut bad: Vec<&String> = options.keys().filter(|k| !STAGE1.contains(&k.as_str())).collect();
    if bad.is_empty() {
        return Ok(());
    }
    bad.sort();
    let hints: Vec<String> = bad.iter().map(|k| {
        let mut close: Vec<(f64, &str)> = STAGE1.iter().map(|v| (strsim::normalized_levenshtein(k, v), *v)).filter(|(s, _)| *s >= 0.6).collect();
        close.sort_by(|a, b| b.0.total_cmp(&a.0));
        let close: Vec<String> = close.iter().take(3).map(|(_, v)| format!("'{v}'")).collect();
        if close.is_empty() { format!("'{k}'") } else { format!("'{k}' (did you mean {}?)", close.join(", ")) }
    }).collect();
    let mut valid = STAGE1.to_vec();
    valid.sort();
    Err(format!("unknown option(s): {}. Valid options: {}", hints.join("; "), valid.join(", ")))
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

fn render_file(a: RenderFile) -> Result<String, String> {
    let options = a.options.unwrap_or_default();
    check_options(&options)?;
    let src = expand(&a.path);
    let ext = src.extension().and_then(|e| e.to_str()).unwrap_or("").to_lowercase();
    if ext != "parquet" && ext != "geoparquet" {
        return Err(format!("{}: the Rust server reads GeoParquet files only (GeoJSON, GeoPackage and Shapefile come next). Use {PYTHON}.",
                           src.display()));
    }
    let bytes = std::fs::read(&src).map_err(|e| format!("{}: {e}", src.display()))?;
    let class_col = options.get("highway_col").and_then(Value::as_str).unwrap_or("highway").to_string();
    let text = summary(&roadstyle::read::read_roads(bytes.clone(), "geometry")?, &class_col)?;
    let out = out_path(a.output_path.as_deref(), &src.file_stem().unwrap_or_default().to_string_lossy())?;
    // the look of render_page: palette, profile and settings apart, the rest as the render's keywords, with state "live"
    let mut args = options.clone();
    let mut pick = |k: &str| args.remove(k).unwrap_or(Value::Null);
    let look = json!({"palette": pick("palette"), "profile": pick("profile"), "settings": pick("settings")});
    args.insert("highway_col".into(), class_col.into());
    args.insert("state".into(), "live".into());
    let mut look = look;
    look["args"] = Value::Object(args);
    if look["palette"].is_null() {
        look.as_object_mut().unwrap().remove("palette");
    }
    let look = roadstyle::look::make_look(&look)?.to_string();
    let name = options.get("name").and_then(Value::as_str).map(str::to_string);
    roadstyle::make_sources(bytes, &look, None, None, name)?;
    // TODO(R3): the page from the sources (with the keyless base map note: esri_street without CARTO_API_KEY), saved at `out`, and the
    // preview (A4); then the answer is "Saved <out>\n<summary>" and the PNG
    Err(format!("{text}\nno map: the Rust engine has no page writer yet (plan step R3), so {} is not written. Use {PYTHON}.", out.display()))
}

#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let server = Server { tool_router: Server::tool_router() }.serve(rmcp::transport::stdio()).await?;
    server.waiting().await?;
    Ok(())
}
