//! The GeoJSON reader (roadstyle-io geojson.rs) gives the roads that the GeoParquet reader gives: Monaco's part as GeoJSON (written from
//! its GeoParquet file by read::features) makes the same style as the GeoParquet file.

use std::path::PathBuf;

fn data(name: &str) -> Vec<u8> {
    std::fs::read(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data").join(name)).unwrap()
}

#[test]
fn a_geojson_file_makes_the_style_of_its_geoparquet_file() {
    let look = roadstyle_rs::Look::from_json(&String::from_utf8(data("look.json")).unwrap()).unwrap();
    let pq = data("monaco_part/roads.parquet");
    let fc = roadstyle_rs::read::features(pq.clone()).unwrap();
    let roads = roadstyle_rs::geojson::read_roads(fc.to_string().as_bytes()).unwrap();
    assert_eq!(roads.len(), fc["features"].as_array().unwrap().len());
    let style = |s: roadstyle_rs::sources::Styled| {
        let mut out = Vec::new();
        s.write_style(&mut out, roadstyle_rs::sources::SourceMode::INLINE).unwrap();
        serde_json::from_slice::<serde_json::Value>(&out).unwrap()
    };
    let want = style(roadstyle_rs::make_sources(pq, &look, None, None, None).unwrap());
    let got = style(roadstyle_rs::sources_of(roads, &look, None, None, None).unwrap());
    assert!(got == want, "the GeoJSON roads make another style");
}
