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
            assert!(a[k].to_string() == v.to_string(), "{name}: the view {k}: {:.300} against {:.300}", a[k].to_string(), v.to_string());
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
    assert_eq!(look.sections.roads.styles, look.styles);
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
