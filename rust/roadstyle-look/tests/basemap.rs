//! The base map's half of the look must be the one mapstyle makes (Python): the 64 looks of geolibre-roadstyle's build.py (`look_of`:
//! each mode x theme x path style, on Monaco), made with mapstyle at ebd6b12 and roadstyle's Python engine (tests/data/mapstyle_looks.json.gz:
//! each part once, and each choice's index of each part). Each look is resolved from its choice and the map options that render_map gives
//! (the golden's `args`). The keys are compared in sorted order: Python makes a mode's palette from a set, whose order changes with each
//! run. A texture is compared by its pixels (Python's PNG encoder writes other bytes for the same image); an icon by its text.

use base64::Engine;
use roadstyle_look::{basemap::BaseMap, Look, Options};
use serde_json::{json, Value};
use std::io::Read;

fn golden() -> Value {
    let p = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data/mapstyle_looks.json.gz");
    let mut text = String::new();
    flate2::read::GzDecoder::new(std::fs::File::open(p).unwrap()).read_to_string(&mut text).unwrap();
    serde_json::from_str(&text).unwrap()
}

/// `v` with the keys of each mapping in sorted order, and each image as its pixels.
fn canon(v: &Value) -> Value {
    match v {
        Value::Object(m) => {
            let mut keys: Vec<&String> = m.keys().collect();
            keys.sort();
            Value::Object(keys.into_iter().map(|k| (k.clone(), canon(&m[k]))).collect())
        }
        Value::Array(a) => Value::Array(a.iter().map(canon).collect()),
        Value::String(s) if s.starts_with("data:image/png;base64,") => {
            let png = base64::engine::general_purpose::STANDARD.decode(&s["data:image/png;base64,".len()..]).unwrap();
            let (w, h, ch, px) = roadstyle_look::png_pixels(&png).unwrap();
            let rgba: Vec<u8> = if ch == 4 { px } else { px.chunks(ch).flat_map(|p| [p[0], p[0], p[0], 255]).collect() };
            json!({"png": [w, h], "rgba": base64::engine::general_purpose::STANDARD.encode(rgba)})
        }
        v => v.clone(),
    }
}

/// Two hex colours that differ by at most 1 in each channel: the look rounds a mixed colour half up (roadstyle_look::color::mix, one rule
/// for the look and the export, review D4, 2026-10-24); mapstyle's _mix rounded half to even. The picture is the same.
fn near_colour(a: &Value, b: &Value) -> bool {
    match (a.as_str().and_then(roadstyle_look::color::hex_rgb), b.as_str().and_then(roadstyle_look::color::hex_rgb)) {
        (Some(x), Some(y)) => (0..3).all(|i| x[i].abs_diff(y[i]) <= 1),
        _ => false,
    }
}

fn first_differences(a: &Value, b: &Value, path: &str, out: &mut Vec<String>) {
    if out.len() >= 8 || a == b || near_colour(a, b) {
        return;
    }
    match (a, b) {
        (Value::Object(x), Value::Object(y)) if x.keys().eq(y.keys()) => {
            x.iter().for_each(|(k, v)| first_differences(v, &y[k], &format!("{path}.{k}"), out))
        }
        (Value::Array(x), Value::Array(y)) if x.len() == y.len() => {
            x.iter().zip(y).enumerate().for_each(|(i, (u, v))| first_differences(u, v, &format!("{path}[{i}]"), out))
        }
        _ => {
            let cut = |v: &Value| v.to_string().chars().take(200).collect::<String>();
            out.push(format!("{path}: {} != {}", cut(a), cut(b)));
        }
    }
}

#[test]
fn the_64_looks_of_mapstyle() {
    let g = golden();
    let mut bad = Vec::new();
    for (choice, idx) in g["choices"].as_object().unwrap() {
        let want: serde_json::Map<String, Value> = idx.as_object().unwrap().iter()
            .map(|(k, i)| (k.clone(), g["parts"][k][i.as_u64().unwrap() as usize].clone())).collect();
        let [mode, theme, paths]: [&str; 3] = choice.split('|').collect::<Vec<_>>().try_into().unwrap();
        let o = Options { base_map: Some(BaseMap { mode: mode.into(), theme: theme.into(), paths: paths.into(), place: None }), args: want["args"].clone(),
                          ..Default::default() };
        let mut got = Look::resolve(&o).unwrap_or_else(|e| panic!("{choice}: {e}")).to_value();
        got.as_object_mut().unwrap().shift_remove("schema_version");
        // added on 2026-10-24 for the dashboard's port of mapstyle's page scripts: the restricted roads' colour baked into the fills
        // (access_col), the Modes filter's columns and the page's box layout; mapstyle's look had them in its page script
        for k in ["access_col", "modes", "box_layout"] {
            got["args"].as_object_mut().unwrap().shift_remove(k);
        }
        let mut out = Vec::new();
        first_differences(&canon(&got), &canon(&Value::Object(want)), choice, &mut out);
        bad.extend(out);
    }
    assert!(bad.is_empty(), "the first differences:\n{}", bad.join("\n"));
}

#[test]
fn a_wrong_choice_names_the_choices() {
    // an unknown name, with the text that Python and JavaScript show
    let err = |b: BaseMap| match Look::resolve(&Options { base_map: Some(b), ..Default::default() }).unwrap_err() {
        roadstyle_look::Error::Unknown(m) => m,
        e => panic!("not an unknown name: {e:?}"),
    };
    assert!(err(BaseMap { mode: "boat".into(), ..Default::default() }).contains("choose from ('all', 'driving', 'walking', 'cycling')"));
    assert!(err(BaseMap { theme: "dark".into(), ..Default::default() }).contains("choose from ('osm', 'google', 'grey', 'roadstyle')"));
    assert!(err(BaseMap { paths: "x".into(), ..Default::default() }).contains("unknown path style 'x'"));
}
