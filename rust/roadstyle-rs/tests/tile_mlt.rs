//! MLT is a second format of the same tiles (roadstyle-tiles, mlt.rs): a tile in MLT decodes to the features of the tile in MVT, with the same
//! layers, ids, order, properties and geometry. Monaco's roads and base map at three zooms.

mod common;

use mlt_core::geo_types::{Geometry, LineString};
use mlt_core::{Decoder, Layer, Parser, PropValue};
use serde_json::{json, Map, Value};
use std::path::PathBuf;

/// A feature as both formats give it: its id, its properties (a number as f64: MLT widens a column of integers and floats), its vertices.
type Plain = (Option<u64>, Map<String, Value>, Vec<[i64; 2]>);

fn value(v: &PropValue) -> Option<Value> {
    Some(match v {
        PropValue::Bool(b) => json!((*b)?),
        PropValue::I8(n) => json!((*n)? as f64),
        PropValue::U8(n) => json!((*n)? as f64),
        PropValue::I32(n) => json!((*n)? as f64),
        PropValue::U32(n) => json!((*n)? as f64),
        PropValue::I64(n) => json!((*n)? as f64),
        PropValue::U64(n) => json!((*n)? as f64),
        PropValue::F32(n) => json!((*n)? as f64),
        PropValue::F64(n) => json!((*n)?),
        PropValue::Str(s) => json!(s.as_ref()?.as_str()),
    })
}

/// The vertices of a geometry in order; a polygon's ring has no closing vertex (the MVT command ClosePath adds none).
fn vertices(g: &Geometry<i32>) -> Vec<[i64; 2]> {
    let line = |l: &LineString<i32>, closed: bool| -> Vec<[i64; 2]> {
        let n = l.0.len() - usize::from(closed);
        l.0[..n].iter().map(|c| [c.x as i64, c.y as i64]).collect()
    };
    match g {
        Geometry::Point(p) => vec![[p.x() as i64, p.y() as i64]],
        Geometry::MultiPoint(ps) => ps.0.iter().map(|p| [p.x() as i64, p.y() as i64]).collect(),
        Geometry::LineString(l) => line(l, false),
        Geometry::MultiLineString(ls) => ls.0.iter().flat_map(|l| line(l, false)).collect(),
        Geometry::Polygon(p) => std::iter::once(p.exterior()).chain(p.interiors()).flat_map(|r| line(r, true)).collect(),
        Geometry::MultiPolygon(ps) => ps.0.iter().flat_map(|p| std::iter::once(p.exterior()).chain(p.interiors()).flat_map(|r| line(r, true))).collect(),
        other => panic!("geometry {other:?}"),
    }
}

fn from_mlt(tile: &[u8]) -> Vec<(String, Vec<Plain>)> {
    let mut dec = Decoder::default();
    Parser::default().parse_layers(tile).unwrap().into_iter().map(|l| {
        let Layer::Tag01(_) = &l else { panic!("a layer of the first MLT version") };
        let layer = l.into_tile(&mut dec).unwrap().expect("a known layer");
        let names = layer.property_names().to_vec();
        let feats = layer.features().iter().map(|f| {
            let props = names.iter().zip(f.properties()).filter_map(|(k, v)| Some((k.clone(), value(v)?))).collect();
            (f.id(), props, vertices(f.geometry()))
        }).collect();
        (layer.name().to_string(), feats)
    }).collect()
}

/// The MVT tile as MLT will have it: a column is typed in MLT, so a key whose values in a layer are of two kinds (`__rs_cap` is `true` on one piece
/// and "square" on another) is text there: `true` is "true". `mixed` collects those keys.
fn from_mvt(tile: &[u8], mixed: &mut std::collections::BTreeSet<String>) -> Vec<(String, Vec<Plain>)> {
    let kind = |v: &Value| match v { Value::Bool(_) => 0, Value::String(_) => 1, _ => 2 };
    common::decode_tile(tile).into_iter().map(|(name, feats)| {
        let mut kinds: std::collections::HashMap<&str, std::collections::HashSet<u8>> = Default::default();
        feats.iter().flat_map(|f| &f.1).for_each(|(k, v)| { kinds.entry(k).or_default().insert(kind(v)); });
        let text: std::collections::HashSet<String> = kinds.into_iter().filter(|(_, v)| v.len() > 1).map(|(k, _)| k.to_string()).collect();
        mixed.extend(text.iter().map(|k| format!("{name}.{k}")));
        let feats = feats.into_iter().map(|(id, props, _, parts)| {
            let props = props.into_iter().map(|(k, v)| {
                let v = match &v {
                    _ if !text.contains(&k) => v.as_f64().map_or(v.clone(), |n| json!(n)),
                    Value::Bool(b) => json!(b.to_string()),
                    Value::String(_) => v,
                    other => panic!("{name}.{k}: {other} in a column of two kinds: MLT text is not tested for it"),
                };
                (k, v)
            }).collect();
            (id, props, parts.into_iter().flatten().collect())
        }).collect();
        (name, feats)
    }).collect()
}

#[test]
fn a_monaco_tile_in_mlt_has_the_features_of_the_tile_in_mvt() {
    let data = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data");
    let read = |p: &str| std::fs::read(data.join(p)).unwrap();
    let look = roadstyle_rs::Look::from_value(serde_json::from_slice(&read("look.json")).unwrap()).unwrap();
    let (_, tiles, _) = roadstyle_rs::tiled_from_parquet(read("monaco/roads.parquet"), &look, Some(read("monaco/features.parquet")), None, "rs://", &[]).unwrap();
    let (mut checked, mut layers, mut mixed) = (0, std::collections::BTreeSet::new(), std::collections::BTreeSet::new());
    for (z, x0, y0) in [(12u32, 2132u32, 1493u32), (14, 8528, 5973), (15, 17057, 11947)] {
        for (x, y) in (0..2).flat_map(|dx| (0..2).map(move |dy| (x0 + dx, y0 + dy))) {
            let mvt = tiles.tile(z, x, y);
            let mlt = tiles.tile_in(roadstyle_rs::tiles::TileFormat::Mlt, z, x, y).unwrap();
            assert_eq!(mvt.is_empty(), mlt.is_empty(), "{z}/{x}/{y}");
            if mvt.is_empty() {
                continue;
            }
            let (a, b) = (from_mvt(&mvt, &mut mixed), from_mlt(&mlt));
            assert_eq!(a.len(), b.len(), "{z}/{x}/{y}: the layers");
            for ((na, fa), (nb, fb)) in a.iter().zip(&b) {
                assert_eq!(na, nb, "{z}/{x}/{y}: the layer order");
                assert_eq!(fa.len(), fb.len(), "{z}/{x}/{y} {na}: the features");
                if let Some(i) = fa.iter().zip(fb).position(|(p, q)| p != q) {
                    panic!("{z}/{x}/{y} {na} feature {i}:\n MVT {:?}\n MLT {:?}", fa[i], fb[i]);
                }
                layers.insert(na.clone());
            }
            checked += 1;
        }
    }
    assert!(checked >= 6, "tiles with data: {checked}");
    println!("columns of two kinds, text in MLT: {mixed:?}");
    assert!(layers.contains("simple") && layers.len() > 1, "roads and base-map layers: {layers:?}");
}
