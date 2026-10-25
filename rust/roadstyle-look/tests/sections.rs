//! The typed sections (T3 step 2, docs/design/t3_map_options_and_look.md): each golden look written as version 2 and read again is the
//! same look, and a look of version 1 gives the same sections as the resolution; a bad colour of a section is an error that names it;
//! look.schema.json is the schema of the types (`ROADSTYLE_BLESS=1 cargo test -p roadstyle-look --test sections` writes it).

use roadstyle_look::{basemap::BaseMap, Look, Options};
use serde_json::{json, Value};
use std::io::Read;
use std::path::PathBuf;

fn here(p: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(p)
}

/// The fixture: a look of version 0 (0.25.0's look.json), as its JSON value.
fn fixture() -> Value {
    serde_json::from_str(&std::fs::read_to_string(here("../roadstyle-rs/tests/data/look.json")).unwrap()).unwrap()
}

/// The golden looks: the fixture, each built-in profile x palette, and the 64 looks of mapstyle's choices; with the options of each
/// resolved one.
fn looks() -> Vec<(String, Look, Option<Options>)> {
    let mut out = vec![("the fixture".to_string(), Look::from_value(fixture()).unwrap(), None)];
    for pr in ["default", "highsat"] {
        for pa in ["amber", "carto", "highsat", "mono"] {
            let o = Options::from_value(&json!({"palette": pa, "profile": pr})).unwrap();
            out.push((format!("{pr} x {pa}"), Look::resolve(&o).unwrap(), Some(o)));
        }
    }
    let mut text = String::new();
    flate2::read::GzDecoder::new(std::fs::File::open(here("tests/data/mapstyle_looks.json.gz")).unwrap()).read_to_string(&mut text).unwrap();
    let g: Value = serde_json::from_str(&text).unwrap();
    for (choice, idx) in g["choices"].as_object().unwrap() {
        let [mode, theme, paths]: [&str; 3] = choice.split('|').collect::<Vec<_>>().try_into().unwrap();
        let args = g["parts"]["args"][idx["args"].as_u64().unwrap() as usize].clone();
        let o = Options { base_map: Some(BaseMap { mode: mode.into(), theme: theme.into(), paths: paths.into(), place: None }), args,
                          ..Default::default() };
        out.push((choice.clone(), Look::resolve(&o).unwrap(), Some(o)));
    }
    out
}

#[test]
fn version_2_is_the_same_look() {
    let all = looks();
    assert!(all.len() > 70);
    for (name, look, options) in &all {
        let file = look.to_json();
        let again = Look::from_json(&file).unwrap_or_else(|e| panic!("{name}: {e}"));
        assert_eq!(again.sections, look.sections, "{name}: the sections");
        assert_eq!(again.map, look.map, "{name}: the map options");
        assert_eq!(again.to_json(), file, "{name}: written again");
        // the resolution's look of version 1 gives the same look
        if let Some(o) = options {
            let v1 = Look::from_value(Look::resolution_value(o).unwrap()).unwrap_or_else(|e| panic!("{name}: {e}"));
            assert_eq!(v1.to_json(), file, "{name}: version 1");
        }
    }
}

#[test]
fn the_sections_are_the_views() {
    // a section's value is its theme section's (or config's) value of the look of version 0
    let (f, look) = (fixture(), Look::from_value(fixture()).unwrap());
    let (theme, config) = (&f["theme"], &f["config"]);
    assert_eq!(look.sections.labels.color.css(), theme["labels"]["color"].as_str().unwrap());
    assert_eq!(look.sections.bridges.decks.match_zoom.f(), config["bridge_decks"]["match_zoom"].as_f64().unwrap());
    assert_eq!(look.sections.labels.slot_m.f(), config["annotations"]["slot_m"].as_f64().unwrap());
    assert_eq!(look.sections.page.basemap, config["basemap"].as_str().unwrap());
    assert_eq!(look.sections.camera.pitch_3d.f(), config["camera"]["pitch_3d"].as_f64().unwrap());
    assert_eq!(serde_json::to_value(&look.sections.access).unwrap(), theme["access"]);
    assert_eq!(serde_json::to_value(&look.sections.roads.styles).unwrap(), f["styles"]);
    assert_eq!(serde_json::to_value(&look.sections.roads.model).unwrap(), f["roads_model"]);
    assert_eq!(serde_json::to_value(&look.sections.labels.slots).unwrap(), f["slots"]);
    assert_eq!(look.sections.arrows.image, f["oneway_image"]);
}

/// A look file has no page key and nothing of `other`: the keywords that are not map options stay in memory.
#[test]
fn a_look_file_has_no_page_key() {
    let o = Options::from_value(&json!({"args": {"name": "m", "basemap_switcher": false, "export": true, "color_by": "lanes"}})).unwrap();
    let look = Look::resolve(&o).unwrap();
    let keys: Vec<&String> = look.other.keys().collect();
    assert_eq!(keys, ["basemap_switcher"]);
    let v = look.to_value();
    assert!(v.get("args").is_none() && v["map"]["color"]["by"] == "lanes" && v["map"]["output"]["name"] == "m", "{}", v["map"]);
    let text = look.to_json();
    assert!(!text.contains("basemap_switcher"), "a page key in the look file");
    assert!(look.map.output.export, "export is a map option (it changes stage 1)");
    assert!(Look::from_json(&text).unwrap().other.is_empty());
    // with_arg: a map option changes the map options and keeps the others; another keyword goes to `other`
    let l = look.with_arg("arrows", json!(false)).unwrap().with_arg("legend", json!(false)).unwrap();
    assert!(!l.map.arrows.on && l.map.color.by.as_deref() == Some("lanes") && l.other["legend"] == false);
}

#[test]
fn a_bad_colour_of_a_section_names_it() {
    let look = Look::from_value(fixture()).unwrap();
    let mut v = look.to_value();
    v["labels"]["color"] = "#zzz".into();
    let e = Look::from_value(v).unwrap_err().to_string();
    assert!(e.contains("\"#zzz\" is not a colour"), "{e}");
    let mut v = fixture();
    v["theme"]["bridges"]["casing_color"] = "nocolour".into();
    let e = Look::from_value(v).unwrap_err().to_string();
    assert!(e.contains("\"nocolour\" is not a colour"), "{e}");
    let mut v = look.to_value();
    v["casing"]["extar"] = 1.into();
    let e = Look::from_value(v).unwrap_err().to_string();
    assert!(e.contains("unknown field `extar`"), "{e}");
}

#[test]
fn look_schema_json_is_the_schema_of_the_types() {
    let path = here("look.schema.json");
    let made = serde_json::to_string_pretty(&roadstyle_look::sections::schema()).unwrap() + "\n";
    if std::env::var_os("ROADSTYLE_BLESS").is_some() {
        std::fs::write(&path, &made).unwrap();
    }
    let saved = std::fs::read_to_string(&path).unwrap_or_default();
    assert!(saved == made, "look.schema.json is not the schema of the types: ROADSTYLE_BLESS=1 cargo test -p roadstyle-look --test sections");
}

/// No API key goes into a look (it is saved and published): not from the settings' config, not from the keywords. The written look and
/// its views have no field whose name has "key" with a value, and the schema has no such field.
#[test]
fn a_look_holds_no_api_key() {
    let o = Options::from_value(&json!({"settings": [{"config": {"api_key": "SECRET1", "api_keys": {"carto": "SECRET2"}, "basemap": "osm"}}],
                                        "args": {"api_key": "SECRET3", "street_view_key": "SECRET4", "name": "m"}})).unwrap();
    let look = Look::resolve(&o).unwrap();
    for text in [look.to_json(), Look::resolution_value(&o).unwrap().to_string(), Look::from_json(&look.to_json()).unwrap().to_json()] {
        assert!(!text.contains("SECRET"), "a key in the look: {}", &text[text.find("SECRET").unwrap().saturating_sub(80)..][..120]);
    }
    assert_eq!(look.sections.page.basemap, "osm", "the settings' other config keys stay");
    fn keys_with_values(v: &Value, at: &str, out: &mut Vec<String>) {
        match v {
            Value::Object(m) => m.iter().for_each(|(k, x)| {
                let empty = x.is_null() || x.as_object().is_some_and(|o| o.is_empty()) || x == "";
                if k.to_lowercase().contains("key") && !empty {
                    out.push(format!("{at}.{k}"));
                }
                keys_with_values(x, &format!("{at}.{k}"), out);
            }),
            Value::Array(l) => l.iter().for_each(|x| keys_with_values(x, at, out)),
            _ => {}
        }
    }
    let mut found = Vec::new();
    keys_with_values(&look.to_value(), "", &mut found);
    keys_with_values(&Look::resolution_value(&o).unwrap(), "", &mut found);
    assert!(found.is_empty(), "{found:?}");
    // the map options' colour table has a `key` (its join column, "edge_id"), which is not an API key
    let schema = roadstyle_look::sections::schema().to_string().to_lowercase();
    for k in ["api_key", "api_keys", "street_view_key"] {
        assert!(!schema.contains(&format!("\"{k}\"")), "the field {k} in look.schema.json");
    }
}

/// The tunnel look's rule (render_web._tun_settings, the texts of Python's _check_tunnels): each colour of tunnel_towards a "#rrggbb",
/// tunnel_toward one of their names or a "#rrggbb"; a value of another type is the same error, not serde's.
#[test]
fn the_tunnel_look_is_checked() {
    let e = |c: Value| Look::resolve(&Options::from_value(&json!({"settings": {"config": c}})).unwrap()).unwrap_err().to_string();
    assert!(e(json!({"tunnel_toward": 7})).starts_with("tunnel_toward 7 is not a colour name in ['Slate', "), "{}", e(json!({"tunnel_toward": 7})));
    assert!(e(json!({"tunnel_toward": "Pink"})).starts_with("tunnel_toward 'Pink' is not a colour name in ["));
    assert!(e(json!({"tunnel_toward": "#12345"})).ends_with("or a '#rrggbb' colour"));
    assert_eq!(e(json!({"tunnel_towards": {"A": "red"}, "tunnel_toward": "A"})), "tunnel_towards 'A': 'red' is not a '#rrggbb' colour");
    assert!(Look::resolve(&Options::from_value(&json!({"settings": {"config": {"tunnel_toward": "#123456"}}})).unwrap()).is_ok());
}
