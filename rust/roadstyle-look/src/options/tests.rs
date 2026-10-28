use super::*;
use crate::color::Color;
use serde_json::{json, Value};

#[test]
fn a_misspelt_key_is_an_error_with_its_path_and_the_nearest_key() {
    let e = MapOptions::from_json(r#"{"color": {"by_column": "speed"}}"#).unwrap_err().to_string();
    assert_eq!(e, r#""color.by_column": unknown key; did you mean "by"?"#);
    let e = MapOptions::from_json(r#"{"roads": {"fill": false, "casing_minpx": 1}}"#).unwrap_err().to_string();
    assert_eq!(e, r#""roads.casing_minpx": unknown key; did you mean "casing_min_px"?"#);
    let e = MapOptions::from_json(r#"{"overlays": [{"label": "a"}, {"lable": "b"}]}"#).unwrap_err().to_string();
    assert_eq!(e, r#""overlays[1].lable": unknown key; did you mean "label"?"#);
    let e = MapOptions::from_json(r#"{"levels": "solved"}"#).unwrap_err().to_string();
    assert_eq!(e, r#""levels": unknown key; did you mean "solve"?"#);
    let e = MapOptions::from_json(r#"{"colour": {}}"#).unwrap_err().to_string();
    assert_eq!(e, r#""colour": unknown key; did you mean "color"?"#);
}

#[test]
fn the_defaults() {
    let m = MapOptions::from_json("{}").unwrap();
    assert_eq!(m, MapOptions::default());
    assert_eq!((m.columns.class.as_str(), m.roads.fill, m.labels.on, m.arrows.on), ("highway", true, true, true));
    assert_eq!((&m.levels, &m.roads.minzoom, &m.interaction.popup, m.output.state), (&Levels::Auto, &ClassMinzoom::Profile, &Popup::Default, State::Static));
    // the JSON form reads back as the same options
    assert_eq!(MapOptions::from_json(&serde_json::to_string(&m).unwrap()).unwrap(), m);
}

#[test]
fn the_flat_keywords() {
    let (m, rest) = MapOptions::from_args(&json!({
        "highway_col": "klass", "casing_level_col": "cl", "fill_level_col": "fl", "color_by": "speed", "cmap": ["#000", "red"],
        "width_by": [1, 4], "road_popup": "panel", "road_tooltip": false, "tooltip": ["name"], "minzoom": {"service": 16},
        "color_table": {"1": "#ff0000"}, "color_key": "id", "view_3d": true, "state": "live", "basemap": "blank", "sidebar": null,
        "levels": {"edge_hash": "ab", "n_edges": 2}, "modes": ["driving"], "interaction": {"landcover": {"clickable": true}},
        "color_options": {"Speed": {"color_by": "speed", "missing": "self"}, "Class": {}},
        "overlays": [{"fc": {"type": "FeatureCollection", "features": []}, "kind": "line", "edge_col": "eid", "text_col": null,
                      "popup_window": true, "visible": false}]})).unwrap();
    assert_eq!(rest, ["basemap"]);
    assert_eq!(m.columns.class, "klass");
    assert_eq!(m.columns.levels.as_ref().unwrap().casing_level.as_deref(), Some("cl"));
    assert_eq!(m.levels, Levels::Stored { edge_hash: "ab".into(), n_edges: 2 });
    assert_eq!(m.color.by.as_deref(), Some("speed"));
    assert_eq!(m.color.cmap, Some(Cmap::Colors(vec![Color::parse("#000000").unwrap(), Color::parse("#ff0000").unwrap()])));
    assert_eq!(m.width.range, Some((1.0, 4.0)));
    assert_eq!(m.interaction.popup, Popup::Panel);
    assert_eq!(m.interaction.tooltip, Some(Tooltip::Fields(vec!["name".into()])));
    assert_eq!(m.roads.minzoom, ClassMinzoom::Table(json!({"service": 16}).as_object().unwrap().clone()));
    assert_eq!(m.color.table.as_ref().unwrap().key, "id");
    assert_eq!(m.color.options.iter().map(|o| (o.name.as_str(), o.by.as_deref(), o.missing)).collect::<Vec<_>>(),
               [("Speed", Some("speed"), Missing::Itself), ("Class", None, Missing::Base)]);
    assert!(m.bridges.decks_3d && m.output.state == State::Live);
    let ov = &m.overlays[0];
    assert_eq!((ov.kind, ov.edge.as_ref().map(|e| e.column.as_str()), ov.visible, ov.popup_window), (Some(OverlayKind::Line), Some("eid"), false, true));
    assert_eq!(m.base_map.as_ref().unwrap().modes, ["driving"]);
    // no level columns and no `levels`: solved; the columns alone: given; minzoom False: off
    assert_eq!(MapOptions::from_args(&json!({})).unwrap().0.levels, Levels::Auto);
    assert_eq!(MapOptions::from_args(&json!({"levels": "solve"})).unwrap().0.levels, Levels::Solve);
    assert_eq!(MapOptions::from_args(&json!({"fill_level_col": "f"})).unwrap().0.levels, Levels::Given);
    assert_eq!(MapOptions::from_args(&json!({"minzoom": false})).unwrap().0.roads.minzoom, ClassMinzoom::Off);
    assert_eq!(MapOptions::from_args(&json!({"levels": "tags"})).unwrap().0.levels, Levels::Tags);
}

#[test]
fn a_flat_keyword_of_the_wrong_kind_is_an_error_that_names_it() {
    let e = |a: Value| MapOptions::from_args(&a).unwrap_err().to_string();
    assert_eq!(e(json!({"road_popup": 3})), "road_popup: True, False, a list of columns, \"all\" or \"panel\", not 3");
    assert_eq!(e(json!({"minzoom": "yes"})), "minzoom: True, False, None or a {class: zoom} mapping, not \"yes\"");
    assert_eq!(e(json!({"overlays": [{"fc": {}, "lable": "x"}]})), "overlays: unknown field \"lable\"; did you mean \"label\"?");
    assert!(e(json!({"hover_color": "#zzz"})).contains("\"#zzz\" is not a colour"), "{}", e(json!({"hover_color": "#zzz"})));
    assert!(e(json!({"road_fill": "no"})).starts_with("map options: invalid type"), "{}", e(json!({"road_fill": "no"})));
}
