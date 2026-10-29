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
/// and the boxes. `Frame`: full height, with a translucent frame around the card and the corners on the map side curved.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PanelLook {
    Card,
    Frame,
}

/// The side panel: its edge, its width and its look. The panel's HTML is the template's.
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Panel {
    pub side: Edge,
    pub width_px: u32,
    pub look: PanelLook,
}

/// The toolbar: one bar of the map's tools at an edge.
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Toolbar {
    pub position: Edge,
    /// the tool `settings`: the person's choices (the place of the bar and the panel, the transparency, the keys), kept in the browser
    pub settings: bool,
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
    pub selection_style: SelectionStyle,
    /// the page's layers (the page keyword `google_3d_layers`); none in a template
    pub layers: Vec<Layer3d>,
}

impl Google3d {
    fn new() -> Google3d {
        Google3d { fov_deg: None, follow: true, min_alt_m: 80.0, min_zoom_drawn: 17.0,
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
    pub phone: Phone,
}

impl Template {
    /// The sidebar's HTML, and the keywords that it changes when the call gives none (pages.py's defaults; tests/test_pages.py checks them).
    /// `map` has no sidebar.
    pub(crate) fn sidebar(self) -> Option<(&'static str, &'static str)> {
        match self {
            Template::Map => None,
            Template::Dashboard => Some((roadstyle_assets::text!("templates/dashboard.html"),
                r#"{"name": "Roads dashboard", "basemap_switcher": false, "filter_control": false, "road_popup": false}"#)),
        }
    }

    /// The defaults of the template with a layout (`Map` has no panel, so the layout does not change it).
    pub fn dashboard(self, layout: Layout) -> Dashboard {
        let right = Some(Panel { side: Edge::Right, width_px: 340, look: PanelLook::Card });
        let free = WindowRules { clamp: false, recenter_map: true, restore_open: true, remember: true };
        let phone = Phone { max_width_px: 700, toolbar: Edge::Top };
        let (layout, panel, toolbar, windows) = match (self, layout) {
            (Template::Map, _) => (Layout::Dock, None, None, free),
            (Template::Dashboard, Layout::Dock) => (Layout::Dock, right, None, free),
            (Template::Dashboard, Layout::Overlay) => (Layout::Overlay, right, Some(Toolbar { position: Edge::Right, settings: true }),
                                                       WindowRules { clamp: true, recenter_map: false, ..free }),
        };
        Dashboard { template: self, layout, panel, toolbar, windows, boundary: BoundaryRules::new(), google_3d: Google3d::new(), phone }
    }
}

impl Layout {
    /// The layout of a keyword (`layout=`).
    pub fn parse(name: &str) -> Result<Layout, crate::Error> {
        serde_json::from_value(Value::from(name))
            .map_err(|_| crate::error::options(format!("layout must be \"overlay\" or \"dock\", got '{name}'")))
    }
}

impl Dashboard {
    /// The script that is the first thing of the body: the classes of <html> that the first paint needs (the template, the layout, the
    /// toolbar, the phone form), so that no frame shows the page in another form. The dashboard's script keeps them current.
    pub fn first_paint(&self) -> String {
        fn word<T: Serialize>(v: &T) -> String {
            serde_json::to_value(v).ok().and_then(|v| v.as_str().map(String::from)).expect("a name")
        }
        let mut classes = vec![format!("rs-tpl-{}", word(&self.template)), format!("rs-{}", word(&self.layout))];
        if let Some(t) = &self.toolbar {
            classes.push("rs-has-toolbar".into());
            classes.push(format!("rs-tb-{}", word(&t.position)));
        }
        let list = classes.iter().map(|c| format!("\"{c}\"")).collect::<Vec<_>>().join(",");
        format!("<script>(function(){{var c=document.documentElement.classList;c.add({list});\
                 if(matchMedia(\"(max-width:{}px)\").matches)c.add(\"rs-phone\")}})()</script>", self.phone.max_width_px)
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
        assert_eq!((d.layout, d.panel, d.toolbar), (Dock, Some(Panel { side: Edge::Right, width_px: 340, look: PanelLook::Card }), None));
        let r = Template::Dashboard.dashboard(Overlay);
        assert_eq!((r.layout, r.toolbar), (Overlay, Some(Toolbar { position: Edge::Right, settings: true })));
        assert!(r.windows.clamp && !r.windows.recenter_map);
        for layout in [Dock, Overlay] {         // the map has no panel, whatever the layout is
            let free = Template::Map.dashboard(layout);
            assert!((free.layout, free.panel, free.toolbar) == (Dock, None, None) && !free.windows.clamp && free.windows.recenter_map);
        }
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
        assert!(r.contains(r#"c.add("rs-tpl-dashboard","rs-overlay","rs-has-toolbar","rs-tb-right")"#) && r.contains("(max-width:700px)"), "{r}");
        assert!(Template::Dashboard.dashboard(Dock).first_paint().contains(r#"c.add("rs-tpl-dashboard","rs-dock")"#));
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
        assert_eq!((g.min_alt_m, g.min_zoom_drawn, g.selection_style.color.as_str(), g.selection_style.width), (80.0, 17.0, "#22d3ee", 8.0));
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
        assert_eq!(v["toolbar"], serde_json::json!({"position": "right", "settings": true}));
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
