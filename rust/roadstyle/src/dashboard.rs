//! The dashboard templates: the named forms of a page (docs/design/dashboard_templates.md). A template gives the defaults of
//! `Dashboard`, the typed option that the page's script reads (`RS_OPTIONS.dashboard`). A page can change each field, except the HTML of
//! the panel: the template is that HTML.

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

/// The named form of a page. `Map`: the map and its control column. `Classic`: the map and a docked query sidebar, with no toolbar. `Dashboard`: the
/// same sidebar floats over a full map, with the toolbar, the settings and the window rules (the default of `render_dashboard`, decided
/// 2026-10-29). `Report`: the map and a docked stats sidebar.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Template {
    Map,
    Classic,
    Dashboard,
    Report,
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

/// What a panel is on a phone.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PhonePanel {
    /// a bottom sheet with three heights: closed, 40 % and full
    Sheet,
    /// under the map: the map takes 55 % of the height and the panel scrolls
    Below,
}

/// The phone form: the same page at a width of `max_width_px` or less.
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Phone {
    pub max_width_px: u32,
    pub toolbar: Edge,
    pub panel: PhonePanel,
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
}

impl Google3d {
    fn new() -> Google3d {
        Google3d { fov_deg: None, follow: true, min_alt_m: 80.0, min_zoom_drawn: 17.0,
                   selection_style: SelectionStyle { color: "#22d3ee".into(), width: 8.0, outline: "#0b1020".into(), outline_width: 2.0,
                                                     arrow_color: "#ffffff".into(), arrow_width: 5.0, arrow_every: 25.0, fill: "rgba(34,211,238,0.35)".into() } }
    }
}

/// The area boundary (docs/design/dashboard_templates.md, 3.3; decided 2026-10-29, level 3). The outline is the map option `boundary` (a dashed
/// line, whose look is in the config files; a duckOSM file's `main.boundary` is its geometry). This adds what the dashboard does with it: the
/// outside is shaded, and the camera is limited. A page that has no `boundary` has neither.
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
    fn new(on: bool) -> BoundaryRules {
        BoundaryRules { dim: on, limit: on, dim_light: 0.16, dim_dark: 0.4, limit_pad: 2.0, zoom_out: 3.0 }
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
    /// The template of a keyword (`template=`).
    pub fn parse(name: &str) -> Result<Template, crate::Error> {
        serde_json::from_value(Value::from(name))
            .map_err(|_| crate::error::options(format!("template must be \"map\", \"dashboard\", \"classic\" or \"report\", got '{name}'")))
    }

    /// The sidebar's HTML, and the keywords that it changes when the call gives none (pages.py's defaults; tests/test_pages.py checks them).
    /// `map` has no sidebar.
    pub(crate) fn sidebar(self) -> Option<(&'static str, &'static str)> {
        match self {
            Template::Map => None,
            Template::Classic => Some((roadstyle_assets::text!("templates/dashboard.html"),
                r#"{"name": "Roads dashboard", "basemap_switcher": false, "filter_control": false, "road_popup": false}"#)),
            Template::Dashboard => Some((roadstyle_assets::text!("templates/dashboard.html"),
                r#"{"name": "Roads dashboard", "basemap_switcher": false, "filter_control": false, "road_popup": false}"#)),
            Template::Report => Some((roadstyle_assets::text!("templates/report.html"),
                r#"{"name": "Roads report", "basemap_switcher": true, "filter_control": false, "road_popup": false}"#)),
        }
    }

    /// The defaults of the template.
    pub fn dashboard(self) -> Dashboard {
        let right = |width_px| Some(Panel { side: Edge::Right, width_px, look: PanelLook::Card });
        let free = WindowRules { clamp: false, recenter_map: true, restore_open: true, remember: true };
        let phone = |panel| Phone { max_width_px: 700, toolbar: Edge::Top, panel };
        let (layout, panel, toolbar, windows, phone) = match self {
            Template::Map => (Layout::Dock, None, None, free, phone(PhonePanel::Sheet)),
            Template::Classic => (Layout::Dock, right(340), None, free, phone(PhonePanel::Sheet)),
            Template::Dashboard => (Layout::Overlay, right(340), Some(Toolbar { position: Edge::Right, settings: true }),
                                 WindowRules { clamp: true, recenter_map: false, ..free }, phone(PhonePanel::Sheet)),
            Template::Report => (Layout::Dock, right(340), None, free, phone(PhonePanel::Below)),
        };
        // the area's boundary is for the two forms that work on one area
        let boundary = BoundaryRules::new(matches!(self, Template::Classic | Template::Dashboard));
        Dashboard { template: self, layout, panel, toolbar, windows, boundary, google_3d: Google3d::new(), phone }
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

/// The keywords that each template with a sidebar changes, and their values (`page_options`' `template_keys`).
pub fn template_keys() -> Map<String, Value> {
    [Template::Classic, Template::Dashboard, Template::Report].into_iter()
        .map(|t| (serde_json::to_value(t).expect("a name").as_str().expect("a name").to_string(),
                  serde_json::from_str(t.sidebar().expect("a sidebar").1).expect("a template's defaults are JSON")))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn each_template_has_its_defaults() {
        let d = Template::Classic.dashboard();
        assert_eq!((d.layout, d.panel, d.toolbar), (Layout::Dock, Some(Panel { side: Edge::Right, width_px: 340, look: PanelLook::Card }), None));
        let r = Template::Dashboard.dashboard();
        assert_eq!((r.layout, r.toolbar), (Layout::Overlay, Some(Toolbar { position: Edge::Right, settings: true })));
        assert!(r.windows.clamp && !r.windows.recenter_map);
        let free = Template::Map.dashboard();
        assert!((free.layout, free.panel, free.toolbar) == (Layout::Dock, None, None) && !free.windows.clamp && free.windows.recenter_map);
        assert_eq!(Template::Report.dashboard().phone.panel, PhonePanel::Below);
    }

    #[test]
    fn only_the_dashboard_clamps_the_windows() {
        let clamp: Vec<Template> = [Template::Map, Template::Classic, Template::Dashboard, Template::Report].into_iter()
            .filter(|t| t.dashboard().windows.clamp).collect();
        assert_eq!(clamp, [Template::Dashboard]);
    }

    #[test]
    fn every_template_has_one_phone_width_and_the_bar_at_the_top() {
        for t in [Template::Map, Template::Classic, Template::Dashboard, Template::Report] {
            let p = t.dashboard().phone;
            assert_eq!((p.max_width_px, p.toolbar), (700, Edge::Top), "{t:?}");
        }
    }

    #[test]
    fn the_first_paint_script_names_the_classes_of_the_form() {
        let r = Template::Dashboard.dashboard().first_paint();
        assert!(r.contains(r#"c.add("rs-tpl-dashboard","rs-overlay","rs-has-toolbar","rs-tb-right")"#) && r.contains("(max-width:700px)"), "{r}");
        assert!(Template::Report.dashboard().first_paint().contains(r#"c.add("rs-tpl-report","rs-dock")"#));
    }

    #[test]
    fn only_the_forms_of_one_area_have_the_boundary() {
        let on: Vec<Template> = [Template::Map, Template::Classic, Template::Dashboard, Template::Report].into_iter()
            .filter(|t| t.dashboard().boundary.dim).collect();
        assert_eq!(on, [Template::Classic, Template::Dashboard]);
        let b = Template::Dashboard.dashboard().boundary;
        assert!(b.dim && b.limit && b.limit_pad > 0.0 && b.zoom_out > 0.0);
    }

    #[test]
    fn the_google_3d_window_starts_with_follow_on_and_the_selection_in_cyan() {
        let g = Template::Dashboard.dashboard().google_3d;
        assert!(g.follow && g.fov_deg.is_none());
        assert_eq!((g.min_alt_m, g.min_zoom_drawn, g.selection_style.color.as_str(), g.selection_style.width), (80.0, 17.0, "#22d3ee", 8.0));
    }

    #[test]
    fn a_template_name_is_parsed_or_refused() {
        assert_eq!(Template::parse("dashboard").unwrap(), Template::Dashboard);
        assert!(Template::parse("sidebar").unwrap_err().to_string().contains("template must be"));
    }

    #[test]
    fn the_defaults_are_the_json_that_the_page_reads() {
        let v = serde_json::to_value(Template::Dashboard.dashboard()).unwrap();
        assert_eq!(v["template"], "dashboard");
        assert_eq!(v["toolbar"], serde_json::json!({"position": "right", "settings": true}));
        assert_eq!(v["phone"], serde_json::json!({"max_width_px": 700, "toolbar": "top", "panel": "sheet"}));
        assert!(serde_json::from_value::<Dashboard>(serde_json::json!({"template": "map", "layout": "dock", "panel": null, "toolbar": null,
            "windows": {"clamp": false, "recenter_map": true, "restore_open": true, "remember": true}, "boundary": v["boundary"],
            "google_3d": v["google_3d"], "phone": v["phone"], "extra": 1})).is_err());
    }

    #[test]
    fn the_sidebar_templates_change_the_keywords_of_their_page() {
        let k = template_keys();
        assert_eq!(k.len(), 3);
        assert_eq!(k["report"]["basemap_switcher"], true);
        assert_eq!((&k["classic"]["name"], &k["dashboard"]["name"]), (&serde_json::json!("Roads dashboard"), &serde_json::json!("Roads dashboard")));
    }
}
