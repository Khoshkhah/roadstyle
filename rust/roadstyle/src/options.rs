//! The keywords of a call (render_edges' flat keywords) that no part of roadstyle reads: not a map option (roadstyle_look::options), not
//! a page key (page_options) and not a key of the style writer or of stage 2. A host (the Python binding, the MCP) warns or fails on them.

use serde_json::{Map, Value};

/// The keys of the style writer and of stage 2, which the look keeps in `other` until T4 moves them (SourceMode::Inline, TileOptions),
/// and `simple` (False: Unsupported::FullLook).
const WRITER: [&str; 5] = ["data_maxzoom", "data_tolerance", "tile_keep", "tile_layers", "simple"];

/// The page's keys that have no default in page_options' DEFAULTS: they come from the caller or from the base map's page defaults.
const PAGE: [&str; 4] = ["hover_delay_ms", "box_layout", "copy_field", "resolved_basemaps"];

/// Each keyword of `args` that no part of roadstyle reads, in order, with the known keyword nearest it (none when none is near).
pub fn unknown(args: &Map<String, Value>) -> Vec<(String, Option<String>)> {
    let mut known: Vec<String> = crate::page_options::page_defaults().into_iter().map(|(k, _)| k).collect();
    known.extend(roadstyle_engine::look::options::keywords().chain(PAGE).chain(WRITER).map(String::from));
    args.keys().filter(|k| !known.contains(k))
        .map(|k| (k.clone(), roadstyle_engine::look::options::nearest_name(k, known.iter().map(String::as_str)).map(String::from))).collect()
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
        assert_eq!(got, [("colr_by".to_string(), Some("color_by".to_string())), ("filter_contrl".into(), Some("filter_control".into())),
                         ("zzz".into(), None)]);
    }
}
