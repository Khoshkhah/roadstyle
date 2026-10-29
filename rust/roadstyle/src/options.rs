//! The keywords of a call (render_edges' flat keywords) that no part of roadstyle reads: not a map option (roadstyle_look::options), not
//! a page key (page_options) and not a key of the style writer or of stage 2. A host (the Python binding, the MCP) warns or fails on them.

use serde_json::{Map, Value};

/// The keys of the style writer and of stage 2, which the look keeps in `other` until T4 moves them (SourceMode::Inline, TileOptions).
const WRITER: [&str; 5] = ["data_maxzoom", "data_tolerance", "tile_keep", "tile_layers", "tile_format"];

/// The page's keys that have no default in page_options' DEFAULTS: they come from the caller or from the base map's page defaults.
const PAGE: [&str; 4] = ["hover_delay_ms", "box_layout", "copy_field", "resolved_basemaps"];

/// The keywords of the old dashboard and where each one went (docs/guides/migrating-dashboard.md).
const MOVED: [(&str, &str); 4] = [
    ("toolbar", "the bar's place is now dashboard={\"toolbar\": {\"position\": \"right\"}}"),
    ("edit", "there is no edit hook: change the page text after the call (m.html); see the guide \"Move a dashboard to the new version\""),
    ("panel", "there is no report panel: use render_dashboard; the panel's width is dashboard={\"panel\": {\"width_px\": 400}}"),
    ("sidebar", "it is now template=\"dashboard\" or template=\"map\""),
];

/// Each keyword of `args` that no part of roadstyle reads, in order, with a hint (none when there is none): where a keyword of the old
/// dashboard went, or the known keyword nearest it ("did you mean 'x'?").
pub fn unknown(args: &Map<String, Value>) -> Vec<(String, Option<String>)> {
    let mut known: Vec<String> = crate::page_options::page_key_defaults().into_iter().map(|(k, _)| k).collect();
    known.extend(roadstyle_engine::look::options::keywords().chain(PAGE).chain(WRITER).map(String::from));
    args.keys().filter(|k| !known.contains(k))
        .map(|k| {
            let moved = MOVED.iter().find(|(m, _)| m == k).map(|(_, hint)| hint.to_string());
            let near = || roadstyle_engine::look::options::nearest_name(k, known.iter().map(String::as_str)).map(|n| format!("did you mean '{n}'?"));
            (k.clone(), moved.or_else(near))
        }).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn an_unknown_keyword_with_its_nearest() {
        let args = json!({"color_by": "lanes", "basemap_switcher": false, "export": true, "hover_delay_ms": 100, "colr_by": "x",
                          "filter_contrl": false, "zzz": 1});
        let got = unknown(args.as_object().unwrap());
        assert_eq!(got, [("colr_by".to_string(), Some("did you mean 'color_by'?".to_string())),
                         ("filter_contrl".into(), Some("did you mean 'filter_control'?".into())), ("zzz".into(), None)]);
    }

    #[test]
    fn a_keyword_of_the_old_dashboard_says_where_it_went() {
        let got = unknown(json!({"toolbar": "right", "edit": 1}).as_object().unwrap());
        assert!(got[0].1.as_deref().unwrap().contains("dashboard={\"toolbar\"") && got[1].1.as_deref().unwrap().contains("no edit hook"), "{got:?}");
    }
}
