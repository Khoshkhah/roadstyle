//! The errors of the engine and the facade (target_architecture.md (e)): bad input gives an error of its kind, never a panic, and a
//! message names no binding.

use roadstyle_rs::{EngineError, Error, Limit, Unsupported};
use serde_json::{json, Value};
use std::path::PathBuf;

fn look(args: Value) -> roadstyle_rs::Look {
    let mut l: Value = serde_json::from_slice(&std::fs::read(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data/look.json")).unwrap()).unwrap();
    for (k, v) in args.as_object().unwrap() {
        l["args"][k] = v.clone();
    }
    roadstyle_rs::Look::from_value(l).unwrap()
}

/// Roads as GeoJSON: a good one, a line of one point, a line of two equal points and a road with no geometry.
fn roads() -> roadstyle_rs::RoadTable {
    let road = |id: i64, g: Value| json!({"type": "Feature", "properties": {"edge_id": id, "highway": "primary", "name": "A", "oneway": "yes"}, "geometry": g});
    let fc = json!({"type": "FeatureCollection", "features": [
        road(1, json!({"type": "LineString", "coordinates": [[7.42, 43.73], [7.421, 43.731], [7.422, 43.731]]})),
        road(2, json!({"type": "LineString", "coordinates": [[7.422, 43.731]]})),
        road(3, json!({"type": "LineString", "coordinates": [[7.423, 43.732], [7.423, 43.732]]})),
        road(4, Value::Null),
    ]});
    roadstyle_rs::geojson::read_roads(fc.to_string().as_bytes()).unwrap()
}

/// Stage 1 of `roads()` with `args`: the engine's error, which the facade wraps.
fn stage1(args: Value) -> EngineError {
    match roadstyle_rs::sources_of(roads(), &look(args), None, None, None) {
        Err(Error::Engine(e)) => e,
        Err(e) => panic!("not an engine error: {e:?}"),
        Ok(_) => panic!("no error"),
    }
}

#[test]
fn degenerate_lines_draw_and_tile_without_a_panic() {
    let l = look(json!({}));
    assert!(roadstyle_rs::sources_of(roads(), &l, None, None, None).is_ok());
    let (_, tiles, _) = roadstyle_rs::tiled_of(roads(), &l, None, None, "rs://", &[]).unwrap();
    for z in [6u32, 12, 18] {
        let n = (1u64 << z) as f64;
        let (x, y) = (((7.421 + 180.0) / 360.0 * n) as u32, ((1.0 - 43.731f64.to_radians().tan().asinh() / std::f64::consts::PI) / 2.0 * n) as u32);
        tiles.tile(z, x, y);
    }
}

#[test]
fn each_bad_option_has_its_kind() {
    let e = stage1(json!({"color_by": "speed"}));
    assert!(matches!(&e, EngineError::Column { column, .. } if column == "speed"), "{e}");
    let e = stage1(json!({"simple": false}));
    assert_eq!(e, EngineError::Unsupported(Unsupported::FullLook));
    // an overlay's keys are the look's to check (the typed look, T3): a key it does not know is a look error before the engine
    let mut l: Value = serde_json::from_slice(&std::fs::read(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data/look.json")).unwrap()).unwrap();
    l["args"]["overlays"] = json!([{"kind": "blob"}]);
    assert!(matches!(roadstyle_rs::Look::from_value(l), Err(roadstyle_rs::look::Error::Options(_))));
    let e = stage1(json!({"access_col": "who"}));
    assert!(matches!(&e, EngineError::Column { column, .. } if column == "who"), "{e}");
    // the facade wraps the engine's kind
    let e = roadstyle_rs::tiled_of(roads(), &look(json!({"simple": false})), None, None, "rs://", &[]).err();
    assert_eq!(e, Some(Error::Engine(EngineError::Unsupported(Unsupported::FullLook))));
}

#[test]
fn a_limit_names_what_it_counts() {
    let e = EngineError::Limit { what: Limit::Roads, found: 200_001, max: 200_000 };
    assert!(e.to_string().contains("200001 roads"), "{e}");
}

#[test]
fn no_message_names_a_binding() {
    let all = [EngineError::Unsupported(Unsupported::FullLook), EngineError::Unsupported(Unsupported::Styler),
               EngineError::Unsupported(Unsupported::Palette { palette: "p".into(), look: "q".into() }),
               EngineError::Unsupported(Unsupported::ItemPalette { palette: "p".into(), key: "k".into() }),
               EngineError::Unsupported(Unsupported::MultiLineItem { overlay: "o".into(), item: 0 }),
               EngineError::Unsupported(Unsupported::TableItems { overlay: "o".into() }),
               EngineError::Unsupported(Unsupported::TiledPalettes),
               EngineError::Limit { what: Limit::Roads, found: 1, max: 0 }, EngineError::Limit { what: Limit::Edges, found: 1, max: 0 },
               EngineError::Limit { what: Limit::Pieces { edge: 1 }, found: 1, max: 0 }, EngineError::Limit { what: Limit::Items { edge: 1 }, found: 1, max: 0 }];
    for e in all {
        let m = e.to_string().to_lowercase();
        assert!(!m.contains("python") && !m.contains("engine=") && !m.contains("plugin") && !m.contains("rust engine"), "{m}");
    }
}
