//! The dashboard templates: the named forms of a page (docs/design/dashboard_templates.md). A template gives the defaults of
//! `Dashboard`, the typed option that the page's script reads (`RS_OPTIONS.dashboard`). A page can change each field, except the HTML of
//! the panel: the template is that HTML.

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

/// The named form of a page. `Map`: the map and its control column. `Dashboard`: the map and a docked query sidebar. `Review`: the same
/// sidebar floats over a full map, with a toolbar. `Report`: the map and a docked stats sidebar.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Template {
    Map,
    Dashboard,
    Review,
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

/// The side panel: its edge and its width. The panel's HTML is the template's.
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Panel {
    pub side: Edge,
    pub width_px: u32,
}

/// The toolbar: one bar of the map's tools at an edge.
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Toolbar {
    pub position: Edge,
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
    pub phone: Phone,
}

impl Template {
    /// The template of a keyword (`template=`).
    pub fn parse(name: &str) -> Result<Template, crate::Error> {
        serde_json::from_value(Value::from(name))
            .map_err(|_| crate::error::options(format!("template must be \"map\", \"dashboard\", \"review\" or \"report\", got '{name}'")))
    }

    /// The sidebar's HTML, and the keywords that it changes when the call gives none (pages.py's defaults; tests/test_pages.py checks them).
    /// `map` has no sidebar.
    pub(crate) fn sidebar(self) -> Option<(&'static str, &'static str)> {
        match self {
            Template::Map => None,
            Template::Dashboard => Some((roadstyle_assets::text!("templates/dashboard.html"),
                r#"{"name": "Roads dashboard", "basemap_switcher": false, "filter_control": false, "road_popup": false}"#)),
            Template::Review => Some((roadstyle_assets::text!("templates/dashboard.html"),
                r#"{"name": "Roads review", "basemap_switcher": false, "filter_control": false, "road_popup": false}"#)),
            Template::Report => Some((roadstyle_assets::text!("templates/report.html"),
                r#"{"name": "Roads report", "basemap_switcher": true, "filter_control": false, "road_popup": false}"#)),
        }
    }

    /// The defaults of the template.
    pub fn dashboard(self) -> Dashboard {
        let right = |width_px| Some(Panel { side: Edge::Right, width_px });
        let free = WindowRules { clamp: false, recenter_map: true, restore_open: true, remember: true };
        let phone = |panel| Phone { max_width_px: 700, toolbar: Edge::Top, panel };
        let (layout, panel, toolbar, windows, phone) = match self {
            Template::Map => (Layout::Dock, None, None, free, phone(PhonePanel::Sheet)),
            Template::Dashboard => (Layout::Dock, right(340), None, free, phone(PhonePanel::Sheet)),
            Template::Review => (Layout::Overlay, right(340), Some(Toolbar { position: Edge::Right }),
                                 WindowRules { clamp: true, recenter_map: false, ..free }, phone(PhonePanel::Sheet)),
            Template::Report => (Layout::Dock, right(340), None, free, phone(PhonePanel::Below)),
        };
        Dashboard { template: self, layout, panel, toolbar, windows, phone }
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
    [Template::Dashboard, Template::Review, Template::Report].into_iter()
        .map(|t| (serde_json::to_value(t).expect("a name").as_str().expect("a name").to_string(),
                  serde_json::from_str(t.sidebar().expect("a sidebar").1).expect("a template's defaults are JSON")))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn each_template_has_its_defaults() {
        let d = Template::Dashboard.dashboard();
        assert_eq!((d.layout, d.panel, d.toolbar), (Layout::Dock, Some(Panel { side: Edge::Right, width_px: 340 }), None));
        let r = Template::Review.dashboard();
        assert_eq!((r.layout, r.toolbar), (Layout::Overlay, Some(Toolbar { position: Edge::Right })));
        assert!(r.windows.clamp && !r.windows.recenter_map);
        let free = Template::Map.dashboard();
        assert!((free.layout, free.panel, free.toolbar) == (Layout::Dock, None, None) && !free.windows.clamp && free.windows.recenter_map);
        assert_eq!(Template::Report.dashboard().phone.panel, PhonePanel::Below);
    }

    #[test]
    fn only_review_clamps_the_windows() {
        let clamp: Vec<Template> = [Template::Map, Template::Dashboard, Template::Review, Template::Report].into_iter()
            .filter(|t| t.dashboard().windows.clamp).collect();
        assert_eq!(clamp, [Template::Review]);
    }

    #[test]
    fn every_template_has_one_phone_width_and_the_bar_at_the_top() {
        for t in [Template::Map, Template::Dashboard, Template::Review, Template::Report] {
            let p = t.dashboard().phone;
            assert_eq!((p.max_width_px, p.toolbar), (700, Edge::Top), "{t:?}");
        }
    }

    #[test]
    fn the_first_paint_script_names_the_classes_of_the_form() {
        let r = Template::Review.dashboard().first_paint();
        assert!(r.contains(r#"c.add("rs-tpl-review","rs-overlay","rs-has-toolbar","rs-tb-right")"#) && r.contains("(max-width:700px)"), "{r}");
        assert!(Template::Report.dashboard().first_paint().contains(r#"c.add("rs-tpl-report","rs-dock")"#));
    }

    #[test]
    fn a_template_name_is_parsed_or_refused() {
        assert_eq!(Template::parse("review").unwrap(), Template::Review);
        assert!(Template::parse("sidebar").unwrap_err().to_string().contains("template must be"));
    }

    #[test]
    fn the_defaults_are_the_json_that_the_page_reads() {
        let v = serde_json::to_value(Template::Review.dashboard()).unwrap();
        assert_eq!(v["template"], "review");
        assert_eq!(v["toolbar"]["position"], "right");
        assert_eq!(v["phone"], serde_json::json!({"max_width_px": 700, "toolbar": "top", "panel": "sheet"}));
        assert!(serde_json::from_value::<Dashboard>(serde_json::json!({"template": "map", "layout": "dock", "panel": null, "toolbar": null,
            "windows": {"clamp": false, "recenter_map": true, "restore_open": true, "remember": true}, "phone": v["phone"], "extra": 1})).is_err());
    }

    #[test]
    fn the_sidebar_templates_change_the_keywords_of_their_page() {
        let k = template_keys();
        assert_eq!(k.len(), 3);
        assert_eq!(k["report"]["basemap_switcher"], true);
        assert_eq!(k["review"]["name"], "Roads review");
    }
}
