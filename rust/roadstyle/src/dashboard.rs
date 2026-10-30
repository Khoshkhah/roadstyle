//! The dashboard templates: the named forms of a page (docs/design/dashboard_templates.md). A template gives the defaults of
//! `Dashboard`, the typed option that the page's script reads (`RS_OPTIONS.dashboard`). A page can change each field, except the HTML of
//! the panel: the template is that HTML.

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

/// The named form of a page. `Map`: the map and its control column. `Dashboard`: the map and the query sidebar (decided 2026-10-29: this is the one
/// template with a panel; a later template follows its style). The sidebar floats over a full map with the toolbar (`Layout::Overlay`, the
/// default of `render_dashboard`), or it is docked at the right with no toolbar (`Layout::Dock`).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Template {
    Map,
    Dashboard,
}

/// `Dock`: the panel takes its own space and the map is the rest. `Overlay`: the map fills the window and the panel floats over it.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Layout {
    Dock,
    Overlay,
}

/// An edge of the window.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Edge {
    Right,
    Left,
    Top,
    Bottom,
}

/// How the panel looks in the overlay layout (decided 2026-10-29). `Card`: a floating card with a margin and rounded corners all round, like the bar
/// and the boxes. `Frame`: full height, with a translucent frame around the card and the corners on the map side curved. The frame is the default
/// (decided 2026-10-29).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PanelLook {
    Card,
    Frame,
}

/// The ids of the panel's own sections, in their order: a section of the page goes `after` or `before` one of them, and `hide` can name them.
pub const PANEL_SECTIONS: [&str; 5] = ["base_map", "colour_by", "legend", "query", "selected_road"];

/// A section that the page adds to the panel: a block of HTML, with an optional heading (a `<label>`), at the end of the panel or beside another
/// section. The HTML is the page's own: it is written into the page as it is.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Section {
    pub id: String,
    pub html: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub label: Option<String>,
    /// the id of a section (the panel's or an earlier one of the page): this one goes after it
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub after: Option<String>,
    /// the same, before it
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub before: Option<String>,
    /// the section folds: its label is a button, its body hides, and the panel's title row has one button for all the sections that fold (needs a `label`)
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub fold: bool,
}

/// The side panel: its edge, its width, its look, the sections that the page adds, and the panel's own sections that it hides. The panel's HTML is
/// the template's.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Panel {
    pub side: Edge,
    pub width_px: u32,
    pub look: PanelLook,
    #[serde(default)]
    pub sections: Vec<Section>,
    #[serde(default)]
    pub hide: Vec<String>,
}

/// The mark of a legend row: what the page draws in this colour (a road is a line, a sensor a circle).
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum LegendShape {
    #[default]
    Square,
    Circle,
    Line,
}

/// A row that the page adds to the legend (the legend box of the bar, and the panel's legend): a colour mark and a text.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LegendRow {
    pub color: String,
    pub label: String,
    #[serde(default)]
    pub shape: LegendShape,
}

/// The legend: the rows that the page adds after the colour option's own.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LegendOptions {
    #[serde(default)]
    pub rows: Vec<LegendRow>,
}

/// The toolbar: one bar of the map's tools at an edge.
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Toolbar {
    pub position: Edge,
    /// the tool `settings`: the person's choices (the place of the bar and the panel, the transparency, the keys), kept in the browser
    pub settings: bool,
    /// the bar stays hidden until the page calls `rs.tools.ready()` (6 s at the latest): a page that adds tools of its own sets this, so that no bar
    /// without them flashes at the load
    #[serde(default)]
    pub hold: bool,
    /// how the map is navigated: `box` (the default: one button, with the compass needle, that opens a box with a zoom, a turn and a tilt slider; Ctrl + drag on the map
    /// turns and tilts it) or `buttons` (the buttons zoom in, zoom out, compass and 2D/3D)
    #[serde(default)]
    pub navigation: Navigation,
}

/// The way the map is navigated from the bar.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Navigation {
    Buttons,
    #[default]
    Box,
}

/// The rules of the floating windows (Street View, Google 3D).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WindowRules {
    /// a window stays inside the free part of the map at each drag, resize and panel change
    pub clamp: bool,
    /// a window can move the map's center (a window that opens over the map's middle)
    pub recenter_map: bool,
    /// a window that was open at the last visit opens again
    pub restore_open: bool,
    /// a window keeps its place and size
    pub remember: bool,
}

/// The phone form: the same page at a width of `max_width_px` or less. The panel is a bottom sheet with three heights: closed, 40 % and full.
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Phone {
    pub max_width_px: u32,
    pub toolbar: Edge,
}

/// The style of the selection in the Google 3D window: a line, its outline and its arrows, one style for every layer that draws the selection.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SelectionStyle {
    pub color: String,
    pub width: f64,
    pub outline: String,
    pub outline_width: f64,
    pub arrow_color: String,
    pub arrow_width: f64,
    /// metres between two arrows
    pub arrow_every: f64,
    pub fill: String,
}

/// What a 3D layer draws.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum LayerKind {
    /// a polyline (`LayerStyle`: color, width, dash)
    Line,
    /// a band around a line (`width_m`, or the feature's property `width_prop`)
    Ribbon,
    /// a filled area with an outline
    Polygon,
    /// an octagon of `radius` metres at each point
    Points,
}

/// Which features of the source a 3D layer draws.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum LayerScope {
    /// the features tied to the selected road (see `Layer3d::match_prop`)
    #[default]
    Selection,
    /// the features in the visible area, at most `Layer3d::max`
    View,
}

/// The look of a 3D layer. A key that does not fit the layer's kind is ignored by the drawing; the colors are CSS colors.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LayerStyle {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub color: Option<String>,
    /// line width in pixels
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub width: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub outline: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub outline_width: Option<f64>,
    /// [metres on, metres off]
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub dash: Option<[f64; 2]>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub fill: Option<String>,
    /// ribbon width in metres
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub width_m: Option<f64>,
    /// the feature property that holds the ribbon width in metres
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub width_prop: Option<String>,
    /// points: radius in metres
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub radius: Option<f64>,
}

/// A layer of the Google 3D window: the features of a GeoJSON source of the page, drawn on Google's mesh. The "Show" menu of the window has
/// one checkbox for each layer (it shows when there are two or more).
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Layer3d {
    pub id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub label: Option<String>,
    pub kind: LayerKind,
    /// the id of a GeoJSON source of the page
    pub source: String,
    /// scope `selection`: the feature property that is equal to the same property of the selected road
    #[serde(rename = "match", default, skip_serializing_if = "Option::is_none")]
    pub match_prop: Option<String>,
    #[serde(default)]
    pub scope: LayerScope,
    /// scope `view`: the most features drawn
    #[serde(default = "Layer3d::max_default")]
    pub max: u32,
    /// the layer starts shown
    #[serde(default = "Layer3d::on_default")]
    pub on: bool,
    /// kind `line`: direction arrows along the line
    #[serde(default)]
    pub arrows: bool,
    #[serde(default)]
    pub style: LayerStyle,
}

impl Layer3d {
    fn max_default() -> u32 { 500 }
    fn on_default() -> bool { true }
}

/// The checks of a list of layers: an id is used once, and a layer of scope `selection` says which property ties it to the road.
pub fn check_layers(layers: &[Layer3d]) -> Result<(), String> {
    for (i, l) in layers.iter().enumerate() {
        if l.id.is_empty() || l.source.is_empty() {
            return Err(format!("google_3d_layers[{i}]: a layer needs an id and a source"));
        }
        if layers[..i].iter().any(|o| o.id == l.id) {
            return Err(format!("google_3d_layers: the id '{}' is used twice", l.id));
        }
        if l.scope == LayerScope::Selection && l.match_prop.is_none() {
            return Err(format!("google_3d_layers: the layer '{}' has scope selection and needs `match` (or scope \"view\")", l.id));
        }
    }
    Ok(())
}

/// The Google 3D window (docs/design/dashboard_templates.md, 3.3). The map leads the camera, in one direction only.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Google3d {
    /// Google's vertical field of view in degrees: the range then makes the window's vertical extent on the ground equal to the map's.
    /// None: the range comes from the map's camera distance.
    pub fov_deg: Option<f64>,
    /// the window starts with Follow on
    pub follow: bool,
    /// the camera's height over the imagery under which the window shows a note, in metres
    pub min_alt_m: f64,
    /// the map's zoom over which the drawn map shows the note
    pub min_zoom_drawn: f64,
    /// metres above Google's mesh at which a line or a pin of the window lies over the imagery: at 0.5 m the mesh's bumps (cars, trees, kerbs) cut
    /// a line into pieces
    pub mesh_altitude_m: f64,
    pub selection_style: SelectionStyle,
    /// the page's layers (the page keyword `google_3d_layers`); none in a template
    pub layers: Vec<Layer3d>,
}

impl Google3d {
    fn new() -> Google3d {
        Google3d { fov_deg: None, follow: true, min_alt_m: 80.0, min_zoom_drawn: 17.0, mesh_altitude_m: 1.5,
                   selection_style: SelectionStyle { color: "#22d3ee".into(), width: 8.0, outline: "#0b1020".into(), outline_width: 2.0,
                                                     arrow_color: "#ffffff".into(), arrow_width: 5.0, arrow_every: 25.0, fill: "rgba(34,211,238,0.35)".into() },
                   layers: Vec::new() }
    }
}

/// The area boundary (docs/design/dashboard_templates.md, 3.3; decided 2026-10-29, level 3). The outline is the map option `boundary` (a dashed
/// line, whose look is in the config files). It is an input of the page: the caller says where it comes from. This adds what the dashboard can
/// do with it: the outside is shaded (`dim`), and the camera is limited (`limit`). Both are off until the page asks (`boundary_dim`,
/// `boundary_limit`): a fixed area is a choice of the page. A page that has no `boundary` has neither.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BoundaryRules {
    pub dim: bool,
    pub limit: bool,
    /// the opacity of the shade outside, in the light and in the dark theme
    pub dim_light: f64,
    pub dim_dark: f64,
    /// the camera's limit: the map's center stays inside the boundary's bounds, grown by this share of their size
    pub limit_pad: f64,
    /// and the lowest zoom is this many levels under the zoom at which the whole boundary fits the window
    pub zoom_out: f64,
}

impl BoundaryRules {
    fn new() -> BoundaryRules {
        BoundaryRules { dim: false, limit: false, dim_light: 0.16, dim_dark: 0.4, limit_pad: 2.0, zoom_out: 3.0 }
    }
}

/// A credit of the credits list (the tool `attribution`): a text and a link. The credits of the base map come from the map itself.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Credit {
    pub text: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub href: Option<String>,
}

/// The typed option of the dashboard (the page's `RS_OPTIONS.dashboard`).
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Dashboard {
    pub template: Template,
    pub layout: Layout,
    /// None: no panel (the template `map`)
    pub panel: Option<Panel>,
    /// None: the map's control column
    pub toolbar: Option<Toolbar>,
    pub windows: WindowRules,
    pub boundary: BoundaryRules,
    pub google_3d: Google3d,
    #[serde(default)]
    pub legend: LegendOptions,
    /// the credits of the page's own data, in the credits list before the base map's (the dashboard: OpenStreetMap, the source of its roads; `[]`: none)
    #[serde(default)]
    pub credits: Vec<Credit>,
    /// the scale bar and the zoom number: shown at the start. The dashboard hides them (the person can show them in the settings)
    #[serde(default)]
    pub scale_box: bool,
    pub phone: Phone,
}

impl Template {
    /// The sidebar's HTML, and the keywords that it changes when the call gives none (pages.py's defaults; tests/test_pages.py checks them).
    /// `map` has no sidebar.
    pub(crate) fn sidebar(self) -> Option<(&'static str, &'static str)> {
        match self {
            Template::Map => None,
            Template::Dashboard => Some((roadstyle_assets::text!("templates/dashboard.html"),
                r#"{"name": "Roads dashboard", "basemap": "blank", "basemap_switcher": true, "filter_control": false, "road_popup": false, "minzoom": {"*": 0, "service": 14, "living_street": 14, "steps": 15, "platform": 15, "corridor": 15, "road": 15, "@private": 15}}"#)),
        }
    }

    /// The defaults of the template with a layout (`Map` has no panel, so the layout does not change it).
    pub fn dashboard(self, layout: Layout) -> Dashboard {
        // the panel at the left, with the sections that the bar's boxes already have (the base map, the colour and the legend) hidden (decided 2026-10-29)
        let panel0 = Some(Panel { side: Edge::Left, width_px: 400, look: PanelLook::Frame, sections: Vec::new(),
                                  hide: ["base_map", "colour_by", "legend"].map(String::from).to_vec() });
        let free = WindowRules { clamp: false, recenter_map: true, restore_open: true, remember: true };
        let phone = Phone { max_width_px: 700, toolbar: Edge::Top };
        let (layout, panel, toolbar, windows) = match (self, layout) {
            (Template::Map, _) => (Layout::Dock, None, None, free),
            (Template::Dashboard, Layout::Dock) => (Layout::Dock, panel0.clone(), None, free),
            (Template::Dashboard, Layout::Overlay) => (Layout::Overlay, panel0.clone(), Some(Toolbar { position: Edge::Right, settings: true, hold: false, navigation: Navigation::Box }),
                                                       WindowRules { clamp: true, recenter_map: false, ..free }),
        };
        Dashboard { template: self, layout, panel, toolbar, windows, boundary: BoundaryRules::new(), google_3d: Google3d::new(), legend: LegendOptions::default(),
                    credits: if self == Template::Dashboard { vec![Credit { text: "\u{a9} OpenStreetMap contributors".into(), href: Some("https://www.openstreetmap.org/copyright".into()) }] } else { Vec::new() },
                    scale_box: self == Template::Map, phone }
    }
}

impl Layout {
    /// The layout of a keyword (`layout=`).
    pub fn parse(name: &str) -> Result<Layout, crate::Error> {
        serde_json::from_value(Value::from(name))
            .map_err(|_| crate::error::options(format!("layout must be \"overlay\" or \"dock\", got '{name}'")))
    }
}

/// What the first paint needs: the classes of <html>, the panel's width and the phone width. `Dashboard::first_paint` writes them as the script of a
/// page that roadstyle writes; a host page that writes its own HTML takes them as data (`page_options::host_options`, `rsFirstPaint` in template.js).
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct FirstPaint {
    pub classes: Vec<String>,
    pub panel_width_px: Option<u32>,
    pub phone_max_width_px: u32,
}

impl Dashboard {
    /// The classes of <html> that the first paint needs (the template, the layout, the toolbar, the phone form), so that no frame shows the page
    /// in another form. The dashboard's script keeps them current.
    pub fn first_paint_parts(&self) -> FirstPaint {
        fn word<T: Serialize>(v: &T) -> String {
            serde_json::to_value(v).ok().and_then(|v| v.as_str().map(String::from)).expect("a name")
        }
        let mut classes = vec![format!("rs-tpl-{}", word(&self.template)), format!("rs-{}", word(&self.layout))];
        if let Some(t) = &self.toolbar {
            classes.push("rs-has-toolbar".into());
            classes.push(format!("rs-tb-{}", word(&t.position)));
        }
        // the panel's side and look, and its width: the person's saved choice (placement.js) can change the side and the look after the load
        if let Some(p) = &self.panel {
            if p.side == Edge::Left {
                classes.push("rs-panel-left".into());
            }
            if p.look == PanelLook::Card {
                classes.push("rs-panel-card".into());
            }
        }
        if !self.scale_box {
            classes.push("rs-hide-scale".into());
        }
        FirstPaint { classes, panel_width_px: self.panel.as_ref().map(|p| p.width_px), phone_max_width_px: self.phone.max_width_px }
    }

    /// The script that is the first thing of the body (`first_paint_parts` as code).
    pub fn first_paint(&self) -> String {
        let f = self.first_paint_parts();
        let width = f.panel_width_px.map_or_else(String::new, |w| format!("document.documentElement.style.setProperty(\"--rs-panel-w\",\"{w}px\");"));
        let list = f.classes.iter().map(|c| format!("\"{c}\"")).collect::<Vec<_>>().join(",");
        format!("<script>(function(){{var c=document.documentElement.classList;c.add({list});{width}\
                 if(matchMedia(\"(max-width:{}px)\").matches)c.add(\"rs-phone\")}})()</script>", f.phone_max_width_px)
    }
}

/// A partial `Dashboard` (the page keyword `dashboard=`) over the dashboard of the template: mappings are merged field by field, any other
/// value replaces the field's. A wrong key or value is an error (the type refuses it), and the template cannot change.
pub fn merge(base: &Dashboard, over: &Value) -> Result<Dashboard, crate::Error> {
    fn deep(a: &mut Value, b: &Value) {
        match (a, b) {
            (Value::Object(a), Value::Object(b)) => b.iter().for_each(|(k, v)| deep(a.entry(k.clone()).or_insert(Value::Null), v)),
            (a, b) => *a = b.clone(),
        }
    }
    let Value::Object(o) = over else {
        return Err(crate::error::options("dashboard= must be a mapping of the dashboard's options"));
    };
    if o.contains_key("template") {
        return Err(crate::error::options("dashboard= cannot change the template: use template="));
    }
    let mut v = serde_json::to_value(base).expect("a Dashboard is JSON");
    deep(&mut v, over);
    let merged: Dashboard = serde_json::from_value(v).map_err(|e| crate::error::options(format!("dashboard=: {e}")))?;
    merged.check()?;
    Ok(merged)
}

impl Dashboard {
    /// The checks of the panel's sections: an id is used once and is not one of the panel's own; `after` and `before` name a section that is there
    /// (the panel's, or an earlier one of the page), and not both; `hide` names a section that is there.
    pub fn check(&self) -> Result<(), crate::Error> {
        let Some(p) = &self.panel else { return Ok(()) };
        let mut known: Vec<&str> = PANEL_SECTIONS.to_vec();
        let bad = |m: String| Err(crate::error::options(format!("dashboard=: panel.{m}")));
        for s in &p.sections {
            if s.id.is_empty() || PANEL_SECTIONS.contains(&s.id.as_str()) || known.contains(&s.id.as_str()) {
                return bad(format!("sections: the id '{}' is empty or used twice (the panel's own ids: {})", s.id, PANEL_SECTIONS.join(", ")));
            }
            if s.fold && s.label.is_none() {
                return bad(format!("sections: '{}' folds (`fold`) and has no `label`, which is its button", s.id));
            }
            if s.after.is_some() && s.before.is_some() {
                return bad(format!("sections: '{}' has `after` and `before`: use one", s.id));
            }
            for at in s.after.iter().chain(s.before.iter()) {
                if !known.contains(&at.as_str()) {
                    return bad(format!("sections: '{}' goes beside '{at}', which is not a section here (it is one of {}, or an earlier section)", s.id, PANEL_SECTIONS.join(", ")));
                }
            }
            known.push(&s.id);
        }
        match p.hide.iter().find(|h| !known.contains(&h.as_str())) {
            Some(h) => bad(format!("hide: '{h}' is not a section (the panel's own: {})", PANEL_SECTIONS.join(", "))),
            None => Ok(()),
        }
    }
}

/// The keywords that the template with a sidebar changes, and their values (`page_options`' `template_keys`).
pub fn template_keys() -> Map<String, Value> {
    [Template::Dashboard].into_iter()
        .map(|t| (serde_json::to_value(t).expect("a name").as_str().expect("a name").to_string(),
                  serde_json::from_str(t.sidebar().expect("a sidebar").1).expect("a template's defaults are JSON")))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    use Layout::{Dock, Overlay};

    #[test]
    fn each_form_has_its_defaults() {
        let d = Template::Dashboard.dashboard(Dock);
        assert_eq!((d.layout, d.panel.as_ref().map(|p| (p.side, p.width_px, p.look)), d.toolbar), (Dock, Some((Edge::Left, 400, PanelLook::Frame)), None));
        assert_eq!(d.panel.as_ref().unwrap().hide, ["base_map", "colour_by", "legend"]);
        let r = Template::Dashboard.dashboard(Overlay);
        assert_eq!((r.layout, r.toolbar), (Overlay, Some(Toolbar { position: Edge::Right, settings: true, hold: false, navigation: Navigation::Box })));
        assert!(r.windows.clamp && !r.windows.recenter_map);
        for layout in [Dock, Overlay] {         // the map has no panel, whatever the layout is
            let free = Template::Map.dashboard(layout);
            assert!((free.layout, free.panel, free.toolbar) == (Dock, None, None) && !free.windows.clamp && free.windows.recenter_map);
        }
    }

    #[test]
    fn a_section_that_folds_needs_a_label() {
        let d = Template::Dashboard.dashboard(Overlay);
        let with = |v: Value| merge(&d, &serde_json::json!({"panel": {"sections": [v]}}));
        assert!(with(serde_json::json!({"id": "a", "html": "<p>x</p>", "label": "A", "fold": true})).is_ok());
        let e = with(serde_json::json!({"id": "a", "html": "<p>x</p>", "fold": true})).unwrap_err().to_string();
        assert!(e.contains("folds") && e.contains("label"), "{e}");
        // a section that does not fold writes no `fold` key
        let s = serde_json::to_value(with(serde_json::json!({"id": "a", "html": "x"})).unwrap().panel.unwrap().sections).unwrap();
        assert!(s[0].get("fold").is_none(), "{s}");
    }

    #[test]
    fn only_the_overlay_dashboard_clamps_the_windows() {
        let clamp: Vec<(Template, Layout)> = [(Template::Map, Dock), (Template::Dashboard, Dock), (Template::Dashboard, Overlay)].into_iter()
            .filter(|(t, l)| t.dashboard(*l).windows.clamp).collect();
        assert_eq!(clamp, [(Template::Dashboard, Overlay)]);
    }

    #[test]
    fn every_form_has_one_phone_width_and_the_bar_at_the_top() {
        for (t, l) in [(Template::Map, Dock), (Template::Dashboard, Dock), (Template::Dashboard, Overlay)] {
            let p = t.dashboard(l).phone;
            assert_eq!((p.max_width_px, p.toolbar), (700, Edge::Top), "{t:?} {l:?}");
        }
    }

    #[test]
    fn the_first_paint_script_names_the_classes_of_the_form() {
        let r = Template::Dashboard.dashboard(Overlay).first_paint();
        assert!(r.contains(r#"c.add("rs-tpl-dashboard","rs-overlay","rs-has-toolbar","rs-tb-right","rs-panel-left","rs-hide-scale")"#) && r.contains("(max-width:700px)"), "{r}");
        assert!(Template::Dashboard.dashboard(Dock).first_paint().contains(r#"c.add("rs-tpl-dashboard","rs-dock","rs-panel-left","rs-hide-scale")"#));
        // the width of the panel, and a side and a look that are not the default
        let mut wide = Template::Dashboard.dashboard(Overlay);
        wide.panel = Some(Panel { side: Edge::Left, width_px: 420, look: PanelLook::Card, sections: Vec::new(), hide: Vec::new() });
        let w = wide.first_paint();
        assert!(w.contains(r#""rs-panel-left","rs-panel-card""#) && w.contains(r#"setProperty("--rs-panel-w","420px")"#), "{w}");
    }

    #[test]
    fn the_shade_and_the_limit_of_a_boundary_are_off_until_the_page_asks() {
        for (t, l) in [(Template::Map, Dock), (Template::Dashboard, Dock), (Template::Dashboard, Overlay)] {
            let b = t.dashboard(l).boundary;
            assert!(!b.dim && !b.limit && b.limit_pad > 0.0 && b.zoom_out > 0.0, "{t:?} {l:?}");
        }
    }

    #[test]
    fn the_google_3d_window_starts_with_follow_on_and_the_selection_in_cyan() {
        let g = Template::Dashboard.dashboard(Overlay).google_3d;
        assert!(g.follow && g.fov_deg.is_none());
        assert_eq!((g.min_alt_m, g.min_zoom_drawn, g.mesh_altitude_m, g.selection_style.color.as_str(), g.selection_style.width), (80.0, 17.0, 1.5, "#22d3ee", 8.0));
    }

    #[test]
    fn a_layout_name_is_parsed_or_refused() {
        assert_eq!((Layout::parse("overlay").unwrap(), Layout::parse("dock").unwrap()), (Overlay, Dock));
        assert!(Layout::parse("grid").unwrap_err().to_string().contains("layout must be"));
    }

    #[test]
    fn the_defaults_are_the_json_that_the_page_reads() {
        let v = serde_json::to_value(Template::Dashboard.dashboard(Overlay)).unwrap();
        assert_eq!(v["template"], "dashboard");
        assert_eq!(v["toolbar"], serde_json::json!({"position": "right", "settings": true, "hold": false, "navigation": "box"}));
        assert_eq!(v["scale_box"], false);
        assert_eq!(v["credits"][0]["text"].as_str().map(|t| t.contains("OpenStreetMap")), Some(true));        // the dashboard credits its roads
        assert_eq!(serde_json::to_value(Template::Map.dashboard(Overlay)).unwrap()["credits"], serde_json::json!([]));
        assert_eq!(v["phone"], serde_json::json!({"max_width_px": 700, "toolbar": "top"}));
        assert!(serde_json::from_value::<Dashboard>(serde_json::json!({"template": "map", "layout": "dock", "panel": null, "toolbar": null,
            "windows": {"clamp": false, "recenter_map": true, "restore_open": true, "remember": true}, "boundary": v["boundary"],
            "google_3d": v["google_3d"], "phone": v["phone"], "extra": 1})).is_err());
    }

    #[test]
    fn the_sidebar_template_changes_the_keywords_of_its_page() {
        let k = template_keys();
        assert_eq!(k.len(), 1);
        assert_eq!(k["dashboard"]["name"], "Roads dashboard");
    }

    #[test]
    fn a_partial_dashboard_is_merged_over_the_defaults() {
        let base = Template::Dashboard.dashboard(Overlay);
        let d = merge(&base, &serde_json::json!({"toolbar": {"position": "left", "hold": true}, "google_3d": {"selection_style": {"width": 12.0}, "mesh_altitude_m": 2.0}})).unwrap();
        assert_eq!(d.toolbar, Some(Toolbar { position: Edge::Left, settings: true, hold: true, navigation: Navigation::Box }));
        assert_eq!((d.google_3d.selection_style.width, d.google_3d.selection_style.color.as_str(), d.google_3d.mesh_altitude_m), (12.0, "#22d3ee", 2.0));
        assert_eq!(merge(&base, &serde_json::json!({"toolbar": null})).unwrap().toolbar, None);
        for (bad, said) in [(serde_json::json!({"toolbar": {"colour": 1}}), "colour"), (serde_json::json!({"template": "map"}), "cannot change the template"),
                            (serde_json::json!({"windows": {"clamp": "yes"}}), "invalid type"), (serde_json::json!([1]), "must be a mapping")] {
            assert!(merge(&base, &bad).unwrap_err().to_string().contains(said), "{bad}");
        }
    }

    #[test]
    fn the_sections_of_the_panel_are_checked() {
        let base = Template::Dashboard.dashboard(Overlay);
        let ok = merge(&base, &serde_json::json!({"panel": {"sections": [{"id": "notes", "html": "<p>x</p>", "label": "Notes", "after": "legend"},
            {"id": "more", "html": "<p>y</p>", "before": "notes"}], "hide": ["base_map", "notes"]}, "legend": {"rows": [{"color": "#f00", "label": "Events", "shape": "circle"}]}})).unwrap();
        assert_eq!((ok.panel.as_ref().unwrap().sections.len(), ok.legend.rows.len()), (2, 1));
        assert_eq!(ok.legend.rows[0].shape, LegendShape::Circle);
        for (bad, said) in [(serde_json::json!([{"id": "legend", "html": ""}]), "used twice"), (serde_json::json!([{"id": "a", "html": "", "after": "zzz"}]), "not a section here"),
                            (serde_json::json!([{"id": "a", "html": "", "after": "legend", "before": "query"}]), "use one"),
                            (serde_json::json!([{"id": "a", "html": ""}, {"id": "a", "html": ""}]), "used twice"),
                            (serde_json::json!([{"id": "a", "html": "", "colour": 1}]), "colour")] {
            let e = merge(&base, &serde_json::json!({"panel": {"sections": bad}})).unwrap_err().to_string();
            assert!(e.contains(said), "{e}");
        }
        assert!(merge(&base, &serde_json::json!({"panel": {"hide": ["nope"]}})).unwrap_err().to_string().contains("not a section"));
    }

    fn layer(v: serde_json::Value) -> Result<Layer3d, serde_json::Error> { serde_json::from_value(v) }

    #[test]
    fn a_layer_has_its_defaults_and_names_its_keys() {
        let l = layer(serde_json::json!({"id": "route", "kind": "line", "source": "bus", "match": "route_id",
                                         "style": {"color": "#f00", "width": 6, "dash": [8, 4]}})).unwrap();
        assert_eq!((l.scope, l.max, l.on, l.arrows), (LayerScope::Selection, 500, true, false));
        assert_eq!(l.style.dash, Some([8.0, 4.0]));
        // the page gets the keys back in snake_case, without the ones that are not set
        let v = serde_json::to_value(&l).unwrap();
        assert_eq!((v["match"].clone(), v["style"].as_object().unwrap().len()), ("route_id".into(), 3));
        for bad in [serde_json::json!({"id": "a", "kind": "tube", "source": "s"}), serde_json::json!({"id": "a", "kind": "line", "source": "s", "colour": 1}),
                    serde_json::json!({"id": "a", "kind": "line", "source": "s", "style": {"outlineWidth": 2}})] {
            assert!(layer(bad).is_err());
        }
    }

    #[test]
    fn the_layers_of_a_page_are_checked_together() {
        let mk = |id: &str, scope: &str, m: Option<&str>| layer(serde_json::json!({"id": id, "kind": "points", "source": "s", "scope": scope, "match": m})).unwrap();
        assert!(check_layers(&[mk("a", "view", None), mk("b", "selection", Some("k"))]).is_ok());
        assert!(check_layers(&[mk("a", "view", None), mk("a", "view", None)]).unwrap_err().contains("used twice"));
        assert!(check_layers(&[mk("a", "selection", None)]).unwrap_err().contains("needs `match`"));
    }
}
