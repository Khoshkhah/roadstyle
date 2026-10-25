//! The typed sections (T3 step 2, docs/design/t3_map_options_and_look.md): each golden look written as version 2 and read again gives the
//! same views of version 1, byte for byte, and the same sections; a bad colour of a section is an error that names it; look.schema.json is
//! the schema of the types (`ROADSTYLE_BLESS=1 cargo test -p roadstyle-look --test sections` writes it).

use roadstyle_look::{basemap::BaseMap, Look, Options};
use serde_json::{json, Value};
use std::io::Read;
use std::path::PathBuf;

fn here(p: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(p)
}

/// The golden looks: the fixture (a look of version 0), each built-in profile x palette, and the 64 looks of mapstyle's choices.
fn looks() -> Vec<(String, Look)> {
    let fixture = std::fs::read_to_string(here("../roadstyle-rs/tests/data/look.json")).unwrap();
    let mut out = vec![("the fixture".to_string(), Look::from_json(&fixture).unwrap())];
    for pr in ["default", "highsat"] {
        for pa in ["amber", "carto", "highsat", "mono"] {
            let o = Options::from_value(&json!({"palette": pa, "profile": pr})).unwrap();
            out.push((format!("{pr} x {pa}"), Look::resolve(&o).unwrap()));
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
        out.push((choice.clone(), Look::resolve(&o).unwrap()));
    }
    out
}

#[test]
fn version_2_gives_the_same_views() {
    let all = looks();
    assert!(all.len() > 70);
    for (name, look) in &all {
        let file = look.to_json();
        let again = Look::from_json(&file).unwrap_or_else(|e| panic!("{name}: {e}"));
        let (a, b) = (again.views_value(), look.views_value());
        for (k, v) in b.as_object().unwrap() {
            let (x, y) = (a[k].to_string(), v.to_string());
            assert!(x == y, "{name}: the view {k}: {x:.300} against {y:.300}");
        }
        assert_eq!(a.to_string(), b.to_string(), "{name}: the views");
        assert_eq!(again.sections, look.sections, "{name}: the sections");
        assert_eq!(again.to_json(), file, "{name}: written again");
    }
}

#[test]
fn the_sections_are_the_views() {
    // a section's value is its theme section's (or config's) value
    let (_, look) = &looks()[0];
    assert_eq!(look.sections.labels.color.css(), look.theme["labels"]["color"].as_str().unwrap());
    assert_eq!(look.sections.bridges.decks.match_zoom.f(), look.config["bridge_decks"]["match_zoom"].as_f64().unwrap());
    assert_eq!(look.sections.labels.slot_m.f(), look.config["annotations"]["slot_m"].as_f64().unwrap());
    assert_eq!(look.sections.page.basemap, look.config["basemap"].as_str().unwrap());
    assert_eq!(look.sections.camera.pitch_3d.f(), look.config["camera"]["pitch_3d"].as_f64().unwrap());
    assert_eq!(serde_json::to_value(&look.sections.access).unwrap(), look.theme["access"]);
    assert_eq!(serde_json::to_value(&look.sections.roads.styles).unwrap(), look.styles);
    assert_eq!(serde_json::to_value(&look.sections.roads.model).unwrap(), look.roads_model);
    assert_eq!(serde_json::to_value(&look.sections.labels.slots).unwrap(), look.slots);
    assert_eq!(look.sections.arrows.image, look.oneway_image);
}

#[test]
fn a_bad_colour_of_a_section_names_it() {
    let (_, look) = &looks()[0];
    let mut v = look.to_value();
    v["labels"]["color"] = "#zzz".into();
    let e = Look::from_value(v).unwrap_err().to_string();
    assert!(e.contains("\"#zzz\" is not a colour"), "{e}");
    let mut v = look.views_value();
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
    for text in [look.to_json(), look.views_value().to_string(), Look::from_json(&look.to_json()).unwrap().to_json()] {
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
    keys_with_values(&look.views_value(), "", &mut found);
    assert!(found.is_empty(), "{found:?}");
    let schema = roadstyle_look::sections::schema().to_string();
    assert!(!schema.to_lowercase().contains("key\":"), "a field with \"key\" in its name in look.schema.json");
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
