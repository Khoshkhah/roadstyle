//! Stage 3 of a page in one call (audit R3): `page_from` makes the page of a look's roads, as render_edges(backend="web") with the Rust
//! engine (`_engine.render_page`). It runs stage 1 (`sources_of`), the page's arrows or its tiles, a view's palettes, and it builds the
//! options of rsDashboard (`PageOptions`) from the style's interaction contract and the page's own keywords. Then `page::page_html`
//! writes the page. The Python binding, the CLI and the studio call it; the caller resolves only what it alone knows: a base map that is not in
//! data/basemaps.json, the base map's API key and the Google Maps key.

use crate::dashboard::Template;
use roadstyle_engine::layers::ARROW_IMAGE;
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
    "bearing": null, "max_pitch": null, "view_3d": false, "find_control": false, "zoom_readout": true, "overlay_control": true, "overlays_label": null,
    "overlay_popup": true, "side_panel_html": null, "host_panel_width": 320, "road_popup": true, "popup_mode": null, "street_view": "window",
    "street_view_key": null, "street_view_mode": null, "mapillary_token": null, "google_3d": null, "hover_color": null, "compress": true, "views": null, "tiles": true, "lazy_overlays": false, "files_salt": null,
    "template": null, "layout": null, "dashboard": null, "page_script": null, "vehicles": null, "page_style": null, "boundary_dim": false, "boundary_limit": false, "filter_control": true, "legend": true, "google_3d_layers": [], "google_3d_selected": true, "hillshade": false, "terrain": false, "terrain_exaggeration": null, "terrain_tunnels": "fade", "buildings_opacity": null, "ground": null, "scene_3d": null}"#;

/// The map options that a template's defaults give way to when the call gives them (page_from: `mine`): they go into `given` too.
const SIDEBAR_YIELDS: [&str; 3] = ["name", "road_popup", "minzoom"];

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

/// A template's sidebar with the page's name as its heading (its first <h2>), before the end of the body.
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
    overlays_label: Option<String>,
    overlay_popup: bool,
    side_panel_html: Option<String>,
    host_panel_width: f64,
    popup_mode: Option<String>,
    street_view: Value,
    street_view_key: Option<String>,
    street_view_mode: Option<String>,
    mapillary_token: Option<String>,
    google_3d: Option<bool>,
    google_3d_layers: Vec<crate::dashboard::Layer3d>,
    google_3d_selected: bool,
    boundary_dim: bool,
    /// false, true (the area of `boundary`), or the area itself: a [west, south, east, north] box or GeoJSON
    boundary_limit: Value,
    dashboard: Option<Value>,
    page_script: Option<String>,
    vehicles: Value,
    page_style: Option<String>,
    compress: bool,
    views: Value,
    tiles: bool,
    lazy_overlays: bool,
    files_salt: Option<String>,
    filter_control: bool,
    legend: bool,
    hillshade: bool,
    terrain: bool,
    terrain_exaggeration: Option<f64>,
    terrain_tunnels: String,
    buildings_opacity: Option<f64>,
    ground: Value,
    scene_3d: Value,
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
    /// the files that go next to the page (`lazy_overlays=True`): (the path relative to the page, the bytes). Empty: the page is one file
    pub files: Vec<(String, Vec<u8>)>,
    /// the page's source of each of the caller's overlays (rs.Overlay), in their order: the name of its tile layer (`overlay_files`)
    pub overlay_sources: Vec<String>,
}

impl Page {
    /// Write `files` into `dir`, the folder of the page.
    pub fn write_files(&self, dir: &std::path::Path) -> Result<(), crate::Error> {
        for (path, bytes) in &self.files {
            let p = dir.join(path);
            p.parent().map(std::fs::create_dir_all).transpose().and_then(|_| std::fs::write(&p, bytes))
                .map_err(|e| crate::error::file(p.display(), e))?;
        }
        Ok(())
    }
}

/// The page of `roads` with `look` (resolved from `options`, which a view's palette resolves again with its palette). `given`: the
/// page's keys (render's keywords: name, basemap_switcher, template, views, hover_delay_ms, ...; a look has none), over the base map's page
/// defaults (`look.base_map_page`), and the caller's values: `street_view_key`, `mapillary_token`, `api_key` (put into a base map's URL), and
/// `resolved_basemaps`, the entries (as data/basemaps.json's) of the base map keys that the caller resolved itself (the caller's key of
/// each provider). `features`: the base map's rows (`read_features`, a duckOSM map's features.parquet), or None.
/// The form of the page from `template=` (`map`: no panel; `dashboard`) and `layout=` (`overlay`, the default, or `dock`); none given: `map`.
/// The old forms are errors: `sidebar=`, and the templates `classic` and `report`.
fn form_of(given: &Map<String, Value>) -> Result<(Template, crate::dashboard::Layout), crate::Error> {
    use crate::dashboard::Layout;
    if given.contains_key("sidebar") {
        return Err(crate::error::options("sidebar= is now template=\"dashboard\" (with layout=) or template=\"map\""));
    }
    let word = |k: &str| -> Result<Option<&str>, crate::Error> {
        match given.get(k).filter(|v| !v.is_null()) {
            None => Ok(None),
            Some(v) => v.as_str().map(Some).ok_or_else(|| crate::error::options(format!("{k} must be a name, got {}", repr(v)))),
        }
    };
    let layout = word("layout")?.map(Layout::parse).transpose()?;
    match word("template")? {
        None | Some("map") => match layout {
            None => Ok((Template::Map, Layout::Dock)),
            Some(_) => Err(crate::error::options("layout= is for template=\"dashboard\"; template=\"map\" has no panel")),
        },
        Some("dashboard") => Ok((Template::Dashboard, layout.unwrap_or(Layout::Overlay))),
        Some(old @ ("classic" | "report")) => Err(crate::error::options(format!(
            "template=\"{old}\" is gone: there is one template, \"dashboard\" (layout=\"dock\" is the docked form; there is no report page)"))),
        Some(other) => Err(crate::error::options(format!("template must be \"map\" or \"dashboard\", got '{other}'"))),
    }
}

/// The page's keywords: the defaults of the page keys, the base map's, the name, a template's where the caller gave none, then the caller's.
/// With a sidebar, the look too (it sets the popup, which stage 1 reads).
fn page_args(look: &Look, given: &Map<String, Value>, template: Template) -> Result<(Map<String, Value>, Option<Look>), crate::Error> {
    let mut owned = None;
    let mut a = page_key_defaults();
    a.extend(look.base_map_page.iter().map(|(k, v)| (k.clone(), v.clone())));
    let named = look.map.output.name.as_ref();         // the map's name: the call's or the base map's, over a template's
    if let Some(n) = named {
        a.insert("name".into(), n.as_str().into());
    }
    if let Some((_, d)) = template.sidebar() {
        let mut l = look.clone();
        let mine = |k: &str| given.contains_key(k) || (k == "name" && named.is_some());
        for (k, v) in serde_json::from_str::<Map<String, Value>>(d).expect("a template's defaults are JSON").into_iter().filter(|(k, _)| !mine(k)) {
            if k == "road_popup" || k == "minzoom" {
                l = l.with_arg(&k, v)?;
            } else {
                a.insert(k, v);
            }
        }
        owned = Some(l);
    }
    a.extend(given.iter().map(|(k, v)| (k.clone(), v.clone())));
    Ok((a, owned))
}

/// The checks of the page keys that need two of them or the look: the popup mode ("panel" from the look or the key) and the Google key.
fn check_keys<'a>(k: &'a PageKeys, look: &Look, dashboard: &crate::dashboard::Dashboard) -> Result<(&'a str, Option<String>), crate::Error> {
    let mode = if look.map.interaction.popup == crate::look::options::Popup::Panel { "panel" } else { k.popup_mode.as_deref().filter(|m| !m.is_empty()).unwrap_or("popup") };
    if k.side_panel_html.is_some() && mode == "panel" {
        return Err(crate::error::options("side_panel_html and popup_mode='panel' are two panels on the right: use one"));
    }
    if !["show", "fade", "hide"].contains(&k.terrain_tunnels.as_str()) {
        return Err(crate::error::options(format!("terrain_tunnels must be \"show\", \"fade\" or \"hide\", got {:?}", k.terrain_tunnels)));
    }
    if let Some(o) = k.buildings_opacity.filter(|o| !(0.0..=1.0).contains(o)) {
        return Err(crate::error::options(format!("buildings_opacity must be from 0 to 1, got {o}")));
    }
    if !k.street_view.is_boolean() && k.street_view != "window" && k.street_view != "dock" {
        return Err(crate::error::options(format!("street_view must be True, False, \"window\" or \"dock\", got {}", repr(&k.street_view))));
    }
    crate::dashboard::check_layers(&k.google_3d_layers).map_err(crate::error::options)?;
    let key = k.street_view_key.clone().filter(|v| !v.is_empty());
    match k.street_view_mode.as_deref() {
        None | Some("") | Some("classic") => {}
        Some("linked") if key.is_none() && dashboard.toolbar.is_none() => {
            return Err(crate::error::options("street_view_mode=\"linked\" needs a Google Maps JavaScript API key: pass street_view_key=... or set GOOGLE_MAPS_KEY"));
        }
        Some("linked") => {}
        Some(m) => return Err(crate::error::options(format!("street_view_mode must be \"linked\" or \"classic\" (or None: Linked with a key, else Classic), got {m:?}"))),
    }
    // a page with a toolbar has the settings tool, where the person can type the key; a page without one has no place for it
    if k.google_3d == Some(true) && key.is_none() && dashboard.toolbar.is_none() {
        return Err(crate::error::options("google_3d=True needs a Google Maps JavaScript API key: pass street_view_key=... or set GOOGLE_MAPS_KEY \
                                          (the template \"dashboard\" lets the person add it in the settings)"));
    }
    Ok((mode, key))
}

/// The page's style: the base map's layers and sources, then the map's (without its metadata, which the page gives the dashboard as
/// options). The map's metadata is taken out of `style` and returned.
fn page_style(style: &mut Value, base: &Value) -> Result<(Value, Value), crate::Error> {
    let st = style.as_object_mut().ok_or_else(|| crate::error::options("the style is not a JSON object"))?;
    let meta = st.shift_remove("metadata").unwrap_or_default();
    let mut layers = base["layers"].as_array().cloned().unwrap_or_default();
    for l in &mut layers {
        if let Some(o) = l.as_object_mut() {
            o.entry("paint").or_insert_with(|| json!({}));         // every layer of the page
        }
    }
    for mut l in st["layers"].as_array().cloned().unwrap_or_default() {
        if let Some(o) = l.as_object_mut() {
            o.shift_remove("metadata");
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
    Ok((meta, page_style))
}

/// The camera: the look's, the 3D view's pitch with decks, then the page keys.
fn page_camera(look: &Look, k: &PageKeys) -> Result<Camera, crate::Error> {
    let c = &look.sections.camera;
    let mut cam = json!({"pitch": c.pitch, "bearing": c.bearing, "pitch_3d": c.pitch_3d, "max_pitch": c.max_pitch});
    if look.map.bridges.decks_3d {
        cam["pitch"] = cam["pitch_3d"].clone();
    }
    for key in ["pitch", "max_pitch", "bearing"] {
        if let Some(v) = k_cam(k, key) {
            cam[key] = v.clone();
        }
    }
    Ok(Camera { pitch: number(&cam["pitch"])?, bearing: number(&cam["bearing"])?, max_pitch: number(&cam["max_pitch"])? })
}

/// The bridge profile of a page with the ground that its heights are above. A page with a ground (the page option `ground`) writes it into a profile that has none; a profile and a page whose
/// ground ids differ do not belong together (the standard "The ground reference", section 4): an error that names the two ids. A profile on a ground and a page with none is a warning.
fn profile_on_ground(profile: &Value, ground: &Value, warnings: &mut Vec<String>) -> Result<Value, crate::Error> {
    let id = |g: &Value| g.get("id").and_then(Value::as_str).map(str::to_string);
    let mine = profile.get("ground").filter(|g| g.is_object());
    match (mine, ground.is_object()) {
        (Some(m), true) => {
            if let (Some(a), Some(b)) = (id(m), id(ground)) {
                if a != b {
                    return Err(crate::error::options(format!("bridge_profile: its heights are above the ground {a}, and the page draws the ground {b}: two products of one area with different ground ids do not belong together")));
                }
            }
            Ok(profile.clone())
        }
        (None, true) if profile.is_object() => {
            let mut out = profile.clone();
            let facts: Map<String, Value> = ["id", "source", "product", "vertical_datum"].iter().filter_map(|k| ground.get(*k).filter(|v| !v.is_null()).map(|v| ((*k).to_string(), v.clone()))).collect();
            out["ground"] = Value::Object(facts);
            Ok(out)
        }
        (Some(m), false) if profile.pointer("/parameters/z_reference").and_then(Value::as_str) == Some("elevation") => {
            Err(crate::error::options(format!("bridge_profile: its heights are elevations in the ground {}, and the page has no ground (ground=): an elevation is drawn over the ground that it is measured in, never over another terrain such as the AWS Terrain Tiles", id(m).unwrap_or_else(|| "(no id)".into()))))
        }
        (Some(m), false) => {
            warnings.push(format!("bridge_profile: its heights are above the ground {}, and the page has no ground (it draws the AWS Terrain Tiles)", id(m).unwrap_or_else(|| "(no id)".into())));
            Ok(profile.clone())
        }
        _ => Ok(profile.clone()),
    }
}

/// boundary_limit: whether the camera is limited, and the box of its area. true takes the box of `boundary`; a [west, south, east, north] box or
/// GeoJSON is the area itself. The page then needs no lookup of the area (a tiled page has its boundary only in the tiles).
fn limit_area(v: &Value, look: &Look) -> Result<(bool, Option<[f64; 4]>), crate::Error> {
    let bad = |m: &str| Err(crate::error::options(format!("boundary_limit: {m}")));
    let bx = match v {
        Value::Null | Value::Bool(false) => return Ok((false, None)),
        Value::Bool(true) => match look.map.boundary.as_ref().and_then(crate::dashboard::boundary_bounds) {
            Some(b) => b,
            None => return bad("True takes the area of boundary=, and the page has none; give the area (a box or GeoJSON) to boundary_limit"),
        },
        Value::Array(a) => match a.iter().map(Value::as_f64).collect::<Option<Vec<f64>>>().as_deref() {
            Some(&[w, s, e, n]) if w < e && s < n => [w, s, e, n],
            _ => return bad("a box is [west, south, east, north], with west < east and south < north"),
        },
        Value::Object(_) => match crate::dashboard::boundary_bounds(v) {
            Some(b) => b,
            None => return bad("the GeoJSON has no coordinates"),
        },
        _ => return bad("give true, a [west, south, east, north] box or GeoJSON"),
    };
    Ok((true, Some(bx)))
}

pub fn page_from(roads: RoadTable, features: Option<FeatureTable>, look: &Look, options: &Options, given: &Map<String, Value>)
                 -> Result<Page, crate::Error> {
    let (template, layout) = form_of(given)?;
    let dashboard = template.dashboard(layout);
    let (a, owned) = page_args(look, given, template)?;
    let look = owned.as_ref().unwrap_or(look);
    let k: PageKeys = serde_json::from_value(Value::Object(a.clone())).map_err(|e| crate::error::options(format!("a page key: {e}")))?;
    // the map options that the page reads too: the popup panel, the 3D view, the hover colour, the colour options, the columns
    let mo = &look.map;
    let (mode, key) = check_keys(&k, look, &dashboard)?;
    let bounds = bounds_of(&roads);
    let tiled = k.tiles;
    if k.lazy_overlays && !tiled {
        return Err(crate::error::options("lazy_overlays=True needs tiles=True: the file of an overlay is its own PMTiles archive"));
    }
    let mut src = crate::sources_of(roads, look, features, None, look.map.output.name.clone())?;
    let (active, bms, base) = basemaps(&k, look, &mut src.warnings)?;
    let bg = bg_color(&active, look);
    let keys: Vec<Value> = bms.iter().map(|b| b["key"].clone()).collect();
    let (views, pals) = if present(&k.views) { views(&mut src, &k, look, options, &keys)? } else { (Vec::new(), Vec::new()) };
    if tiled && views.iter().any(|v| v["set"].get("palette").is_some()) {
        return Err(crate::Error::Engine(roadstyle_engine::Error::Unsupported(roadstyle_engine::Unsupported::TiledPalettes)));
    }
    let (mut style, archive, files) = if tiled { tiled_page(&src, look, &a, k.lazy_overlays, k.files_salt.as_deref().unwrap_or(""))? } else {
        src.page_arrows();          // stage 3 of the inline page: the arrows are points that the page puts itself (audit N2)
        // the style without its sources' data, which the page writer writes from `src` (audit D3, N29)
        (src.style_with(crate::sources::SourceMode::inline_of(&a), false), Vec::new(), Vec::new())
    };
    let mut table = Vec::new();
    crate::write_road_table(&src, None, true, &mut table).map_err(|e| crate::error::file(crate::ROAD_TABLE, e))?;
    if !pals.is_empty() {
        palette_swatches(&mut style, &src.table_rows(), &pals, look);       // the rows, not the written table parsed again (N29)
    }
    let (meta, page_style) = page_style(&mut style, &base)?;
    let (ctl, inter) = (&meta["roadstyle:controls"], &meta["roadstyle:interaction"]);
    let mut tunnel = ctl["tunnel"].clone();
    tunnel["bg"] = bg.into();
    let ontop = if bms.len() > 1 { ontop_layers() } else { Value::Null };
    let mut dashboard = dashboard;
    dashboard.google_3d.layers = k.google_3d_layers.clone();
    dashboard.google_3d.selected = k.google_3d_selected;
    dashboard.boundary.dim = k.boundary_dim;
    (dashboard.boundary.limit, dashboard.boundary.bounds) = limit_area(&k.boundary_limit, look)?;
    // street_view="dock": Street View beside the map with a divider (the map and the window share the screen). The page has no panel and the bar is at the
    // left, the map's own edge; `dashboard=` can still give a panel and move the bar
    if k.street_view == "dock" {
        dashboard.panel = None;
        if let Some(t) = dashboard.toolbar.as_mut() {
            t.position = crate::dashboard::Edge::Left;
        }
    }
    if let Some(over) = k.dashboard.as_ref().filter(|v| !v.is_null()) {
        dashboard = crate::dashboard::merge(&dashboard, over)?;
    }
    let has_panel = dashboard.panel.is_some();
    // a page with a toolbar has the Google 3D tool working (the key is typed in the settings); `google_3d=False` takes it away
    let google_3d = k.google_3d.unwrap_or(dashboard.toolbar.is_some());
    let opts = PageOptions {
        dashboard, basemaps: bms, ontop, basemap_switcher: k.basemap_switcher, tiles: tiled, simple: ctl["simple"].clone(),
        sources: meta["roadstyle:sources"].clone(), arrows: meta["roadstyle:arrows"].clone(), live: meta["roadstyle:live"].clone(), bridge_profile: profile_on_ground(&meta["roadstyle:bridge_profile"], &k.ground, &mut src.warnings)?,
        popup_mode: mode.into(), find_control: k.find_control, zoom_readout: k.zoom_readout, pitch_3d: number(&ctl["pitch_3d"])?,
        street_view: k.street_view.clone(), street_view_key: key.unwrap_or_default(), street_view_mode: k.street_view_mode.clone().unwrap_or_default(), google_3d,
        mapillary_token: k.mapillary_token.clone().unwrap_or_default(),
        select_color: ctl["select_color"].clone(), dock: ctl["dock"].clone(), vehicle_look: ctl["vehicle_look"].clone(), vehicles: k.vehicles.clone(), filter: ctl["filter"].clone(), filter_control: k.filter_control,
        color_options: Some(&meta["roadstyle:color_options"]).filter(|v| present(v)).cloned().unwrap_or_else(|| json!([])), legend: k.legend, hillshade: k.hillshade, terrain: k.terrain, terrain_exaggeration: k.terrain_exaggeration, terrain_tunnels: k.terrain_tunnels.clone(), buildings_opacity: k.buildings_opacity, ground: k.ground.clone(), scene_3d: crate::scene3d::option(&k.scene_3d, &k.ground)?,
        color_active: ctl["color_active"].clone(), overlays: overlays_with_rows(&ctl["overlays"], &inter["base_props"]), overlay_control: k.overlay_control, overlays_label: k.overlays_label.clone(), boundary_shape: meta["roadstyle:boundary_shape"].clone(),
        overlay_layers: meta["roadstyle:overlay_layers"].clone(),
        overlay_popup: k.overlay_popup, tunnel, fill_layers: ctl["fill_layers"].clone(), pick: ctl["pick"].clone(), road_fill: ctl["road_fill"].clone(),
        views: Value::Array(views), items: ctl["items"].clone(), road_popup: inter["popup"].clone(), road_tooltip: inter["tooltip"].clone(),
        // the page's hover_delay_ms, else the look's (roadstyle:interaction)
        hover_delay_ms: k.hover_delay_ms.map(|d| d as i64).or_else(|| inter["hover_delay_ms"].as_i64())
            .ok_or_else(|| crate::error::options("roadstyle:interaction has no hover_delay_ms"))?,
        edge_id_col: ctl["edge_id_col"].as_str().unwrap_or("edge_id").into(), arrow_icon: ctl["arrow_icon"].clone(),
        arrow_color: ctl["arrow_color"].clone(), arrow_rules: ctl["arrow_rules"].clone(),
        modes: ctl["modes"].clone(), box_layout: k.box_layout.clone(),
        images: Some(meta["roadstyle:images"].as_object().into_iter().flatten().filter(|(k, _)| *k != ARROW_IMAGE)
            .map(|(k, v)| (k.clone(), v.clone())).collect::<Map<String, Value>>()).filter(|m| !m.is_empty()).map(Value::Object).unwrap_or_default(),
    };
    let (ls, hover) = (&look.sections, json!(mo.interaction.hover_color.as_ref().unwrap_or(&look.sections.selection.hover).css()));
    let simple_js = json!({"layer": "roads-simple", "bridge": ls.bridges.casing_color, "shadow": ls.bridges.shadow.color,
                           "select": ctl["select_color"], "hover": hover, "tunnels": present(&ctl["tunnel"]["layers"]),
                           "dashes": ctl["dashes"]});
    let side = gzip_b64(&table);
    let parts = PageParts {
        name: &k.name, cam: page_camera(look, &k)?, bounds, side_panel_html: k.side_panel_html.as_deref(),
        host_panel_width: k.host_panel_width, compress: k.compress, gz: None, tiles: archive.iter().map(|(k, a)| (k.as_str(), a.as_slice())).collect(),
        tile_files: files.iter().filter(|f| f.kind == FileKind::Tiles).map(|f| (f.source.as_str(), f.path.as_str())).collect(),
        side: Some((&Value::Null, Some(&side))), simple_js: Some(&simple_js), sources: Some(&src),
    };
    let mut html = page_html(page_style, &opts, &parts);
    if let Some((sidebar, _)) = template.sidebar().filter(|_| has_panel) {
        html = add_sidebar(html, sidebar, parts.name);
    }
    // the page's own CSS and JavaScript, the last things of the body: they see the panel and `rs` (the event `rs:ready` says when `window.rs` is there)
    for (tag, text) in [("style", &k.page_style), ("script", &k.page_script)] {
        if let Some(t) = text.as_deref().filter(|t| !t.is_empty()) {
            html = html.replacen("</body>", &format!("<{tag}>{}</{tag}></body>", t.replace(&format!("</{tag}"), &format!("<\\/{tag}"))), 1);
        }
    }
    let overlay_sources = opts.overlays.as_array().into_iter().flatten().filter(|o| o["base_map"] != true)
        .filter_map(|o| o["source"].as_str().map(String::from)).collect();
    Ok(Page { html, warnings: std::mem::take(&mut src.warnings), files: files.into_iter().map(|f| (f.path, f.bytes)).collect(), overlay_sources })
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
    format!("{url}{}api_key={token}", if url.contains('?') { "&" } else { "?" })
}

/// The base maps that roadstyle removed (data/basemaps.json `removed`: the CARTO company maps and OpenFreeMap Bright). A page that asks for one gets
/// the base map `fallback` of the same file and a warning, so an old page does not break. This is the one place of the rule.
fn current_key(v: &Value, warnings: &mut Vec<String>) -> Value {
    let all: Value = serde_json::from_str(BASEMAPS).expect("data/basemaps.json is JSON");
    let (fallback, removed) = (all["fallback"].as_str().expect("basemaps.json has fallback"), &all["removed"]);
    let Some(k) = v.as_str().filter(|k| removed.as_array().is_some_and(|l| l.iter().any(|r| r == k))) else { return v.clone() };
    let w = format!("base map '{k}' was removed; '{fallback}' is used instead");
    if !warnings.contains(&w) {
        warnings.push(w);
    }
    json!(fallback)
}

/// A base map: an entry (a JSON object), a key that the caller resolved (`resolved`), a key of data/basemaps.json, or a tile URL with
/// {z}, {x} and {y}. Only a tile URL that the caller gives takes `api_key`: a base map of roadstyle needs no key.
fn basemap(v: &Value, api_key: Option<&str>, resolved: &[Value]) -> Result<Value, crate::Error> {
    if v.is_object() {
        return Ok(v.clone());
    }
    let k = v.as_str().ok_or_else(|| crate::error::options(format!("basemap must be a key or a base map entry, got {v}")))?;
    if let Some(b) = resolved.iter().find(|b| b["key"] == k) {
        return Ok(b.clone());
    }
    let all: Value = serde_json::from_str(BASEMAPS).expect("data/basemaps.json is JSON");
    Ok(match all["basemaps"].as_array().and_then(|l| l.iter().find(|b| b["key"] == k)) {
        Some(b) => b.clone(),
        None if ["{z}", "{x}", "{y}"].iter().all(|p| k.contains(p)) => {
            let url = api_key.filter(|t| !t.is_empty()).map_or(k.to_string(), |t| inject_token(k, t));
            json!({"key": "custom", "label": "Custom Basemap", "url": url, "attr": ""})
        }
        None => {
            let keys: Vec<Value> = all["basemaps"].as_array().into_iter().flatten().map(|b| b["key"].clone()).collect();
            return Err(crate::error::options(format!("unknown basemap '{k}'; choose from {}", repr(&Value::Array(keys)))));
        }
    })
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

/// The layers on top of a base map (data/basemaps.json `ontop`): only a page with the base-map box has them (the box turns them on).
fn ontop_layers() -> Value {
    let all: Value = serde_json::from_str(BASEMAPS).expect("data/basemaps.json is JSON");
    all["ontop"].clone()
}

/// the active base map, the switcher's list (the active one first) and the style that draws it.
fn basemaps(k: &PageKeys, look: &Look, warnings: &mut Vec<String>) -> Result<(Value, Vec<Value>, Value), crate::Error> {
    let api = k.api_key.as_deref();
    let resolved = k.resolved_basemaps.clone();
    let active = Some(&k.basemap).filter(|v| present(v)).cloned().unwrap_or_else(|| json!(look.sections.page.basemap));
    let active = current_key(&active, warnings);
    let active_bm = basemap(&active, api, &resolved)?;
    let all: Value = serde_json::from_str(BASEMAPS).expect("data/basemaps.json is JSON");
    let key_of = |v: &Value| if v.is_object() { v["key"].clone() } else { v.clone() };
    let mut keys: Vec<Value> = k.basemaps.clone().filter(|l| !l.is_empty()).unwrap_or_else(|| all["switcher"].as_array().cloned().unwrap_or_default())
        .iter().map(|v| current_key(v, warnings)).collect();
    let mut seen = Vec::new();          // two removed keys are one fallback: it is in the list one time
    keys.retain(|v| { let k = key_of(v); let new = !seen.contains(&k); seen.push(k); new });
    let mut list = vec![active_bm.clone()];
    for b in keys.iter().filter(|b| key_of(b) != active_bm["key"] && key_of(b) != key_of(&active)) {
        list.push(basemap(b, api, &resolved)?);
    }
    // a map with a dark twin (`dark`) brings its twin: the box lists the pair as one row, and the theme switches between them
    let mut i = 0;
    while i < list.len() {
        if let Some(t) = list[i]["dark"].as_str().filter(|t| !list.iter().any(|b| b["key"] == *t)) {
            let twin = basemap(&json!(t), api, &resolved)?;
            list.push(twin);
        }
        i += 1;
    }
    let order = |b: &Value| keys.iter().position(|k| key_of(k) == b["key"]).map_or(99, |p| p as i64);
    let mut bms: Vec<Value> = list.iter().map(|b| json!({"key": b["key"], "label": b["label"], "tiles": tiles_of(b), "bg": bg_color(b, look),
                                                         "title": b.get("title").cloned().unwrap_or_else(|| b["label"].clone()), "group": b.get("group").cloned().unwrap_or(json!("")),
                                                         "swatch": b.get("swatch").cloned().unwrap_or(Value::Null), "order": order(b),
                                                         "maxzoom": b.get("maxzoom").cloned().unwrap_or(json!(19)), "attr": b["attr"],
                                                         "is_dark": b["is_dark"], "style_url": b.get("style_url").cloned().unwrap_or(Value::Null),
                                                         "dark": b.get("dark").cloned().unwrap_or(Value::Null),
                                                         "building_3d": b.get("building_3d").cloned().unwrap_or(Value::Null)})).collect();
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

/// The options of a host page that writes its own HTML and calls `rsDashboard` itself (a JavaScript page, such as the duckOSM page): the typed
/// `dashboard` of the template `dashboard` (with the layout and the `dashboard` keys of `given`, as `page_from` merges them), its first paint, and the
/// base maps (`basemaps`, `ontop`, the active key and `style`, the page's base style: its background and the hidden raster layer, as `page_from` gives them to the page). `given` has the keys of a call: `layout`, `dashboard`,
/// `basemap`, `basemaps`, `api_key`, `basemap_switcher`. The same rules as a page that roadstyle writes, so the host has no copy of them.
/// `data/host_options.json` is its answer for the default look and no keys (a test keeps it current): a host page fetches the file, changes what it needs
/// (the panel's width and sections, the order of the base maps) and loads no WebAssembly module on its main thread for it.
pub fn host_options(look: &Look, given: &Map<String, Value>) -> Result<(Value, Vec<String>), crate::Error> {
    let mut given = given.clone();
    given.entry("template").or_insert_with(|| "dashboard".into());
    let (template, layout) = form_of(&given)?;
    if template != Template::Dashboard {
        return Err(crate::error::options("host_options is for template=\"dashboard\": a host page has a panel and a bar"));
    }
    let mut dashboard = template.dashboard(layout);
    let (a, owned) = page_args(look, &given, template)?;
    let look = owned.as_ref().unwrap_or(look);
    let k: PageKeys = serde_json::from_value(Value::Object(a)).map_err(|e| crate::error::options(format!("a page key: {e}")))?;
    let mut warnings = Vec::new();
    let (active, bms, style) = basemaps(&k, look, &mut warnings)?;
    dashboard.google_3d.layers = k.google_3d_layers.clone();
    dashboard.google_3d.selected = k.google_3d_selected;
    dashboard.boundary.dim = k.boundary_dim;
    (dashboard.boundary.limit, dashboard.boundary.bounds) = limit_area(&k.boundary_limit, look)?;
    if let Some(over) = k.dashboard.as_ref().filter(|v| !v.is_null()) {
        dashboard = crate::dashboard::merge(&dashboard, over)?;
    }
    let first = dashboard.first_paint_parts();
    let ontop = if bms.len() > 1 { ontop_layers() } else { Value::Null };
    Ok((json!({"dashboard": dashboard, "first_paint": first, "basemaps": bms, "ontop": ontop, "basemap": active["key"], "style": style}), warnings))
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
    let mut named = k.views.clone();        // a view that names a removed base map gets the fallback, as the page's list did
    for set in named.as_object_mut().into_iter().flat_map(|m| m.values_mut()) {
        if let Some(b) = set.get_mut("basemap") {
            *b = current_key(b, &mut src.warnings);
        }
    }
    let views = check_views(&named, [("color", colors), ("overlays", overlays), ("classes", classes), ("basemap", basemaps.to_vec()),
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

/// The overlays of the page with the rows of each one that has some (`props`: the URL of its rows, from `tiled_page`'s `base_props`).
fn overlays_with_rows(overlays: &Value, rows: &Value) -> Value {
    let mut out = overlays.clone();
    for o in out.as_array_mut().into_iter().flatten() {
        if let Some(url) = o["source"].as_str().and_then(|s| rows.get(s)) {
            o["props"] = url.clone();
        }
    }
    out
}

/// The sources that a tiled page keeps as GeoJSON: the dashboard reads all the features of the 3D bridge decks and their shadows at one time
/// (`filter.js`, `_deckIdsForRoad`), so they cannot be tiles before step 5 of docs/design/memory_budget.md (3D pieces by tile).
const WHOLE_SOURCES: [&str; 2] = ["decks", "shadows"];

/// _engine._tiled_page: the tiled page's style and its PMTiles archive, from stage 2 of the same stage 1 (no second build). The style
/// has one vector source `roads` (the embedded archive) with a tile layer for each source (the roads, the base map, the boundary and the
/// overlays), as the map worker and the server tiles have; only `WHOLE_SOURCES` stay inline. An overlay's tiles have only the keys that the
/// style reads: all its rows (its properties and its box, `crate::rows_file`) go into the style as a gzip data URL (`roadstyle:interaction.base_props`), which the page reads by row.
/// The PMTiles archives of a tiled page by source: `roads` first, then each hidden overlay's own.
type Archives = Vec<(String, Vec<u8>)>;

/// The folder of a page's files (`lazy_overlays=True`), next to the page.
pub const FILES_DIR: &str = "rs-files";

#[derive(PartialEq)]
enum FileKind {
    Tiles,
    Rows,
}

/// A file of a page with `lazy_overlays=True`: the archive (its tiles gzipped) or the gzipped rows of an overlay, at `path` (relative to the page).
struct PageFile {
    source: String,
    kind: FileKind,
    path: String,
    bytes: Vec<u8>,
}

/// `bytes` as a page file of `source` (the rows gzipped already). The name has a hash of the bytes: two pages in one folder do not overwrite the file of the
/// other, and a browser can keep a file in its cache.
fn page_file(source: &str, kind: FileKind, bytes: Vec<u8>, salt: &str) -> PageFile {
    use std::hash::{Hash, Hasher};
    let mut h = std::collections::hash_map::DefaultHasher::new();
    bytes.hash(&mut h);
    salt.hash(&mut h);          // files_salt: a caller that puts other bytes under the name (the overlays of overlay_files) gives each build its own
    let ext = if kind == FileKind::Tiles { "pmtiles" } else { "json.gz" };
    PageFile { path: format!("{FILES_DIR}/{source}-{:016x}.{ext}", h.finish()), source: source.into(), kind, bytes }
}

/// `lazy`: the archive and the rows of each overlay with its own source (each hidden overlay) go into files next to the page (docs/design/tiling.md,
/// "Overlays in files"): the page reads the tiles of the view from the archive while the overlay shows, and the rows when it first shows.
fn tiled_page(s: &Styled, look: &Look, a: &Map<String, Value>, lazy: bool, salt: &str) -> Result<(Value, Archives, Vec<PageFile>), crate::Error> {
    let o = page_tile_options(s, look, a.get("tile_format").and_then(Value::as_str))?;
    let (mut style, t) = crate::tile_stage(s, &o, &json!({"url": "pmtiles://roads"}), crate::sources::SourceMode::inline_of(a))?;
    thin_arrows(&mut style, look);
    // the page gzips each archive as one stream (page.rs), so its tiles are not gzipped one by one
    let bounds = t.bounds().ok_or(crate::tiles::Error::Empty)?;
    let names = t.layer_names();
    // an overlay whose layers make no tile at any zoom (its style hides it at every tile zoom) has no archive: it stays in `roads`
    let mut archives = Vec::new();
    for k in overlay_sources(&style).into_iter().filter(|k| names.contains(k)) {
        // a file (lazy): its tiles gzipped one by one, for a read of one tile; in the page: plain, as the page gzips the whole archive
        match t.archive_of(bounds, std::slice::from_ref(&k), !lazy) {
            Ok(a) => archives.push((k, a)),
            Err(crate::tiles::Error::Empty) => {}
            Err(e) => return Err(e.into()),
        }
    }
    let own: Vec<String> = archives.iter().map(|(k, _)| k.clone()).collect();
    let rest: Vec<String> = names.iter().filter(|n| !own.contains(n)).cloned().collect();
    let roads = match t.archive_of(bounds, &rest, true) {
        Ok(a) => {
            own_sources(&mut style, &own);
            lazy_layers(&mut style, &own);
            a
        }
        // no road, base map or boundary has a tile (a page of overlays alone): the overlays stay in `roads`, which then has tiles
        Err(crate::tiles::Error::Empty) if !own.is_empty() => {
            archives.clear();
            t.archive_in(bounds, &names, true)?
        }
        Err(e) => return Err(e.into()),
    };
    let mut files: Vec<PageFile> = Vec::new();
    if lazy {
        // the archives that are left here are the hidden overlays' own (own_sources): roads goes in below
        files.extend(archives.drain(..).map(|(k, a)| page_file(&k, FileKind::Tiles, a, salt)));
    }
    archives.insert(0, (crate::tiles::SOURCE.to_string(), roads));
    // the rows of each overlay (all its properties and its box): the tiles have only the keys that the style reads
    let mut rows = Vec::new();
    let urls: Map<String, Value> = s.shown().filter(|(k, _)| o.wants(k) && !["simple", "slots"].contains(k)).filter_map(|(k, src)| {
        use base64::Engine;
        let gz = crate::tiles::pmtiles::gzip_at(crate::rows_file(src)?.as_bytes(), 9);
        if files.iter().any(|f| f.source == k) {          // an overlay in files: its rows too
            let f = page_file(k, FileKind::Rows, gz, salt);
            let path = f.path.clone().into();
            rows.push(f);
            return Some((k.to_string(), path));
        }
        Some((k.to_string(), format!("data:application/gzip;base64,{}", base64::engine::general_purpose::STANDARD.encode(gz)).into()))
    }).collect();
    files.extend(rows);
    if !urls.is_empty() {
        style["metadata"]["roadstyle:interaction"]["base_props"] = Value::Object(urls);
    }
    // the boundary's GeoJSON for the dashboard (boundary.js: the shade and the camera limits): in tiles, the page has no GeoJSON source of it
    if let Some((_, crate::sources::Source::Json(b))) = s.shown().find(|(k, _)| *k == "boundary") {
        style["metadata"]["roadstyle:boundary_shape"] = b["data"].clone();
    }
    Ok((style, archives, files))
}

/// The tile rules of a tiled page (and of an overlay's own file, `overlay_files`): the keys that the page filters read stay, every source but
/// `WHOLE_SOURCES` is tiled, in `tile_format` (the one default is MLT, docs/design/tiling.md).
fn page_tile_options(s: &Styled, look: &Look, tile_format: Option<&str>) -> Result<TileOptions, crate::Error> {
    let c = &look.map.columns;
    let hw = Some(c.class.as_str()).filter(|h| !h.is_empty()).unwrap_or("highway");
    fn col(v: &Option<String>) -> Option<&str> {
        v.as_deref().filter(|c| !c.is_empty())
    }
    let keep = [Some(hw), Some(col(&c.filter).unwrap_or(hw)), Some(roadstyle_model::mark::Mark::Twoway.name()), Some(roadstyle_model::mark::Mark::Edge.name()), Some("lvl"), col(&c.width_m)];
    let mut o = TileOptions::new(&s.layers, &s.metadata, &s.saved[TILES], &s.saved[COLUMNS], &[])?;
    o.exact = Some(keep.into_iter().flatten().map(String::from).collect());
    o.only = Some(s.shown().map(|(k, _)| k.to_string()).filter(|k| !WHOLE_SOURCES.contains(&k.as_str())).collect());
    if let Some(f) = tile_format {
        o.format = crate::tiles::TileFormat::parse(f)?;
    }
    Ok(o)
}

/// The files of one hidden overlay of a page with `lazy_overlays=True`, made apart from the page, so that a caller reads, tiles and frees one
/// overlay at a time (rs.Overlay(data=<a function>), docs/design/tiling.md "Overlays in files"): its PMTiles archive (tiles gzipped one by one) and
/// its rows (gzipped JSON), as the page makes them, with its tile layer named `source` (the page's name of it, `Page::overlay_sources`). `look`:
/// the page's look with this overlay as its one overlay (MapOptions::with_overlays).
pub fn overlay_files(look: &Look, source: &str, tile_format: Option<&str>) -> Result<(Vec<u8>, Vec<u8>), crate::Error> {
    // a page of no roads: the roads' drawing positions are not read (a duckOSM page's stored levels would not match its 0 edges)
    let mut m = look.map.clone();
    m.levels = roadstyle_look::options::Levels::Auto;
    m.columns.levels = None;
    let look = &look.clone().with_map(m)?;
    let mut s = crate::sources_of(RoadTable::empty(), look, None, None, None)?;
    // the look has no base map and one overlay: its source is the one of `look.map.overlays`, named by its place (ov0); it takes the page's name
    let own = s.sources.iter().map(|(k, _)| k.clone()).find(|k| k.starts_with("ov"))
        .ok_or_else(|| crate::error::options("overlay_files: the look has no overlay with a source of its own"))?;
    for (k, _) in s.sources.iter_mut().filter(|(k, _)| *k == own) {
        *k = source.to_string();
    }
    for l in s.layers.iter_mut().filter(|l| l["source"] == own.as_str()) {
        l["source"] = source.into();
    }
    let o = page_tile_options(&s, look, tile_format)?;
    let (_, t) = crate::tile_stage(&s, &o, &json!({"url": "pmtiles://roads"}), crate::sources::SourceMode::inline_of(&Map::new()))?;
    let archive = t.archive_of(t.bounds().ok_or(crate::tiles::Error::Empty)?, &[source.to_string()], false)?;
    let src = s.source(source).ok_or_else(|| crate::error::options(format!("overlay_files: no source {source}")))?;
    let rows = crate::rows_file(src).ok_or_else(|| crate::error::options(format!("overlay_files: the overlay {source} has no rows")))?;
    Ok((archive, crate::tiles::pmtiles::gzip_at(rows.as_bytes(), 9)))
}

/// One source for each hidden overlay (docs/design/tiling.md): the layers of each overlay in `own` move from the source `roads` to a vector source
/// of the overlay's own name, whose tiles are its own archive (`pmtiles://<source>/{z}/{x}/{y}`). MapLibre asks for a source's tiles only while one of
/// its layers shows, and MapLibre's MLT reader decodes every layer of a tile: a hidden overlay in `roads` cost every map move its decoding
/// (noise-map, 63 hidden overlays: 67 % more worker time, 2026-11-24). The source has `tiles`, not `url`: a `url` asks for the archive's header
/// when the style loads, which inflates every archive. `own`: the overlay sources that have an archive.
fn own_sources(style: &mut Value, own: &[String]) {
    let roads = style["sources"][crate::tiles::SOURCE].clone();
    for k in own {
        let mut v = json!({"type": "vector", "tiles": [format!("pmtiles://{k}/{{z}}/{{x}}/{{y}}")]});
        for key in ["minzoom", "maxzoom", "encoding"] {
            if !roads[key].is_null() {
                v[key] = roads[key].clone();
            }
        }
        style["sources"][k] = v;
    }
    for l in style["layers"].as_array_mut().into_iter().flatten() {
        if let Some(k) = l["source-layer"].as_str().filter(|k| own.iter().any(|o| o == k)).map(String::from) {
            l["source"] = k.into();
        }
    }
}

/// The caller's hidden overlays (rs.Overlay, not the base map's) with a source of their own are not in the page's starting style: their source and
/// layers go into `roadstyle:overlay_layers` (`{order, sources: {source: {source, layers}}}`, `order` the ids of every layer of the style), and the
/// dashboard adds them when the overlay shows and takes them away when it hides (overlays.js). MapLibre walks every layer of the style at each frame:
/// noise-map's page, 1,215 hidden overlays (2,449 layers, 9 shown), could not pan or zoom (2026-11-25).
fn lazy_layers(style: &mut Value, own: &[String]) {
    let users: Vec<String> = style["metadata"]["roadstyle:controls"]["overlays"].as_array().into_iter().flatten().filter(|o| o["base_map"] != true)
        .filter_map(|o| o["source"].as_str()).filter(|s| own.iter().any(|o| o == s)).map(String::from).collect();
    if users.is_empty() {
        return;
    }
    let Some(layers) = style["layers"].as_array_mut() else { return };
    let order: Vec<Value> = layers.iter().map(|l| l["id"].clone()).collect();
    let mut out = Map::new();
    let mut keep = Vec::with_capacity(layers.len());
    for mut l in layers.drain(..) {
        match l["source"].as_str().filter(|s| users.iter().any(|u| u == s)).map(String::from) {
            Some(s) => {
                if let Some(o) = l.as_object_mut() {
                    o.shift_remove("metadata");      // as the page's own layers (page_style)
                }
                let e = out.entry(s).or_insert_with(|| json!({"layers": []}));
                e["layers"].as_array_mut().expect("a list").push(l);
            }
            None => keep.push(l),
        }
    }
    *layers = keep;
    for s in &users {
        if let Some(def) = style["sources"].as_object_mut().and_then(|m| m.shift_remove(s)) {
            out.entry(s.clone()).or_insert_with(|| json!({"layers": []}))["source"] = def;
        }
    }
    style["metadata"]["roadstyle:overlay_layers"] = json!({"order": order, "sources": out});
}

/// The sources of the page's overlays (`roadstyle:controls.overlays`) that start hidden: every layer on the source has the visibility `none`. An overlay
/// that shows at the start stays in `roads`: in a source of its own, each tile is one more worker task, and the 6 shown overlays of noise-map's page
/// (the base map's) cost the tile worker 1.6 s more on the tour of `docs/design/tiling.md` (4.30 s against 2.65 s).
fn overlay_sources(style: &Value) -> Vec<String> {
    let layers = style["layers"].as_array().map(Vec::as_slice).unwrap_or_default();
    let hidden = |k: &str| {
        let mut on = layers.iter().filter(|l| l["source-layer"] == k || l["source"] == k).peekable();
        on.peek().is_some() && on.all(|l| l["layout"]["visibility"] == "none")
    };
    style["metadata"]["roadstyle:controls"]["overlays"].as_array().into_iter().flatten().filter_map(|o| o["source"].as_str()).filter(|k| hidden(k))
        .map(String::from).collect()
}

/// The arrows of a tiled page repeat along the slots (the page has no road to put one arrow on), one for each piece. They are thinned as the
/// export's are: below `main_below` only the main classes; only the odd slots (the names are on the even ones, and an arrow under a name is
/// dropped), every 4th slot of them below zoom 17. An unnamed road keeps the arrow of its first slot, so a short one-way road has one.
fn thin_arrows(style: &mut Value, look: &Look) {
    let arw = &look.sections.arrows;
    // the tiles have the class as its index (`__rs_ci`), not its name
    let main: Vec<usize> = look.model.classes.iter().enumerate()
        .filter(|(_, c)| arw.main.iter().any(|h| c.as_str() == h.as_str() || c.strip_suffix("_link") == Some(h.as_str()))).map(|(i, _)| i).collect();
    let slot = json!(["get", "slot"]);
    for l in style["layers"].as_array_mut().into_iter().flatten() {
        if l["id"].as_str().is_some_and(|i| i.starts_with("roads-arrows")) {
            l["filter"] = json!(["all", l["filter"], ["any", ["match", ["coalesce", ["get", roadstyle_engine::layers::CLASS_INDEX], -1], main, true, false], [">=", ["zoom"], arw.main_below]],
                                 ["any", ["==", ["%", slot, ["step", ["zoom"], 4, 17, 2]], 1],
                                  ["all", ["==", slot, 0], ["!", ["to-boolean", ["get", "name"]]]]]]);
        }
    }
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
    fn each_hidden_overlay_with_tiles_has_its_own_source() {
        let mut style = json!({"metadata": {"roadstyle:controls": {"overlays": [{"source": "ov0"}, {"source": "ov1"}]}},
            "sources": {"roads": {"type": "vector", "url": "pmtiles://roads", "minzoom": 6, "maxzoom": 16, "encoding": "mlt"}},
            "layers": [{"id": "r", "source": "roads", "source-layer": "simple"}, {"id": "a", "source": "roads", "source-layer": "ov0", "layout": {"visibility": "none"}},
                       {"id": "b", "source": "roads", "source-layer": "ov1", "layout": {"visibility": "none"}},
                       {"id": "c", "source": "roads", "source-layer": "ov2", "layout": {"visibility": "visible"}}]});
        style["metadata"]["roadstyle:controls"]["overlays"].as_array_mut().unwrap().push(json!({"source": "ov2"}));
        assert_eq!(overlay_sources(&style), ["ov0", "ov1"]);           // ov2 shows at the start: it stays in `roads`
        // ov1 has no archive (no tile at any zoom): it stays in `roads`
        own_sources(&mut style, &["ov0".into()]);
        assert_eq!(style["sources"]["ov0"], json!({"type": "vector", "tiles": ["pmtiles://ov0/{z}/{x}/{y}"], "minzoom": 6, "maxzoom": 16, "encoding": "mlt"}));
        let src: Vec<&str> = style["layers"].as_array().unwrap().iter().map(|l| l["source"].as_str().unwrap()).collect();
        assert_eq!(src, ["roads", "ov0", "roads", "roads"]);
    }

    #[test]
    fn a_key_goes_into_a_tile_url_as_basemaps_puts_it() {
        assert_eq!(inject_token("https://t.example/{z}/{x}/{y}?s=1", "T"), "https://t.example/{z}/{x}/{y}?s=1&api_key=T");
        assert_eq!(inject_token("https://t.example/{z}/{x}/{y}?token={token}", "T"), "https://t.example/{z}/{x}/{y}?token=T");
        assert_eq!(inject_token("", "T"), "");
    }

    #[test]
    fn a_host_page_gets_the_dashboard_its_first_paint_and_the_base_maps_of_a_page_that_roadstyle_writes() {
        let look = Look::resolve(&Options::from_value(&json!({"args": {"state": "live"}})).unwrap()).unwrap();
        let given = json!({"basemap": "blank", "basemaps": ["blank", "osm"], "dashboard": {"panel": {"width_px": 370}}});
        let (o, warnings) = host_options(&look, given.as_object().unwrap()).unwrap();
        assert!(warnings.is_empty(), "{warnings:?}");
        // the dashboard of the template with the call's change, and its first paint from the same value
        assert_eq!(o["dashboard"]["template"], "dashboard");
        assert_eq!(o["dashboard"]["panel"]["width_px"], 370);
        assert_eq!(o["first_paint"]["panel_width_px"], 370);
        assert_eq!(o["first_paint"]["phone_max_width_px"], 700);
        assert_eq!(o["first_paint"]["classes"], json!(["rs-tpl-dashboard", "rs-overlay", "rs-has-toolbar", "rs-tb-right", "rs-panel-left", "rs-panel-card", "rs-hide-scale"]));
        // the base maps: the active one first, its dark twin with it, the tiles as MapLibre's `tiles`
        let keys: Vec<&Value> = o["basemaps"].as_array().unwrap().iter().map(|b| &b["key"]).collect();
        assert_eq!(keys, ["blank", "osm", "blank_dark"]);
        assert_eq!(o["basemap"], "blank");
        assert_eq!(o["basemaps"][1]["tiles"], json!(["https://a.tile.openstreetmap.org/{z}/{x}/{y}.png", "https://b.tile.openstreetmap.org/{z}/{x}/{y}.png", "https://c.tile.openstreetmap.org/{z}/{x}/{y}.png"]));
        assert_eq!(o["basemaps"][0]["bg"], "#efede8");
        assert_eq!(o["style"]["layers"][0]["id"], "bg");
        assert!(o["ontop"]["hillshade"].is_object());
        // a form that is not the dashboard is an error here, as for a page
        assert!(host_options(&look, json!({"template": "map"}).as_object().unwrap()).is_err());
    }

    /// A host that adds its roads later (duckOSM Studio, `duckosm studio`) has a page with no roads: its first view is the world (not a center
    /// that is not a number, which MapLibre opens at 0, 0), and the page knows that it is empty, so the banner for a map with no road features is not for it.
    /// A page with roads has the box of the roads and no `empty`.
    #[test]
    fn a_page_with_no_roads_opens_on_the_world_and_says_that_it_is_empty() {
        let o = Options::from_value(&json!({"args": {"template": "dashboard", "state": "live", "tiles": false}})).unwrap();
        let look = Look::resolve(&o).unwrap();
        let given = given_of(&look, &o.args);
        let camera = |html: &str| -> Value {
            let at = html.find("const RS_OPTIONS = ").expect("the page has its options") + "const RS_OPTIONS = ".len();
            let mut it = serde_json::Deserializer::from_str(&html[at..]).into_iter::<Value>();
            it.next().unwrap().unwrap()["camera"].clone()
        };
        let page = page_from(RoadTable::empty(), None, &look, &o, &given).unwrap();
        let c = camera(&page.html);
        assert_eq!(c["empty"], true);
        assert_eq!(c["bounds"], json!([[-180.0, -60.0], [180.0, 75.0]]));
        assert!(c["center"][0].is_number() && c["center"][1].is_number(), "{c}");
    }

    /// A removed base map (the CARTO maps, OpenFreeMap Bright) becomes `ofm_positron` with one warning, in the active key, the list and the views;
    /// the fallback is in the list one time.
    #[test]
    fn a_removed_base_map_gets_the_fallback_and_a_warning() {
        let look = Look::resolve(&Options::from_value(&json!({"args": {"state": "live"}})).unwrap()).unwrap();
        let all: Value = serde_json::from_str(BASEMAPS).unwrap();
        let removed = all["removed"].as_array().unwrap();
        assert_eq!(removed.len(), 5);
        let given = json!({"basemap": removed[0], "basemaps": [removed[0], removed[1], removed[2], removed[3], removed[4], "osm"]});
        let (o, warnings) = host_options(&look, given.as_object().unwrap()).unwrap();
        let keys: Vec<&Value> = o["basemaps"].as_array().unwrap().iter().map(|b| &b["key"]).collect();
        assert_eq!(keys, ["ofm_positron", "osm", "ofm_dark"]);
        assert_eq!(o["basemap"], "ofm_positron");
        assert_eq!(warnings.len(), 5, "{warnings:?}");
        assert!(warnings[0].contains(&format!("'{}' was removed", removed[0].as_str().unwrap())) && warnings[0].contains("'ofm_positron'"), "{warnings:?}");
        let mut w = Vec::new();
        assert_eq!(current_key(&json!("osm"), &mut w), "osm");
        assert!(w.is_empty());
    }

    /// data/host_options.json is what a JavaScript host page fetches (the typed dashboard, its first paint and the base maps), so that the page
    /// has no copy and loads no wasm module for it. `ROADSTYLE_BLESS=1 cargo test host_options` writes it again.
    #[test]
    fn the_host_options_file_is_what_host_options_gives() {
        let look = Look::resolve(&Options::from_value(&json!({"args": {"state": "live"}})).unwrap()).unwrap();
        let (o, warnings) = host_options(&look, &Map::new()).unwrap();
        assert!(warnings.is_empty(), "{warnings:?}");
        let want = serde_json::to_string_pretty(&o).unwrap() + "\n";
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../roadstyle-assets/files/data/host_options.json");
        if std::env::var_os("ROADSTYLE_BLESS").is_some() {
            std::fs::write(&path, &want).unwrap();
        }
        assert!(std::fs::read_to_string(&path).is_ok_and(|have| have == want), "data/host_options.json is not what host_options gives; ROADSTYLE_BLESS=1 writes it again");
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
        let o = Options::from_value(&json!({"args": {"state": "live", "template": "dashboard", "popup_mode": "panel", "name": "N",
                                                     "road_popup": ["highway"], "color_by": "lanes"}})).unwrap();
        let g = given_of(&Look::resolve(&o).unwrap(), &o.args);
        assert_eq!(g["template"], "dashboard");
        assert_eq!(g["popup_mode"], "panel");
        assert_eq!((&g["name"], &g["road_popup"]), (&json!("N"), &json!(["highway"])));   // a template's defaults give way to them
        assert!(!g.contains_key("color_by") && !g.contains_key("state"), "map options are the look's: {g:?}");
    }
}
