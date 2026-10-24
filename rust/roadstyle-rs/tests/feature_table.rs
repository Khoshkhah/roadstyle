//! R10 step 1 (docs/design/r10_feature_table.md): the typed FeatureTable that read::read_feature_table makes from a GeoParquet file has
//! every row of read::features (the JSON form of the same file): its properties (a null is left out) and its geometry, on Monaco's base
//! map (2,571 features: points, lines, polygons).

use std::path::PathBuf;

#[test]
fn the_feature_table_has_every_feature_of_the_file() {
    let bytes = std::fs::read(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data/monaco/features.parquet")).unwrap();
    let want = roadstyle_rs::read::features(bytes.clone()).unwrap();
    let want = want["features"].as_array().unwrap();
    let t = roadstyle_rs::read::read_feature_table(bytes, "geometry").unwrap();
    assert_eq!(t.len(), want.len());
    assert!(t.len() > 2000);
    for (row, w) in want.iter().enumerate() {
        let got = t.to_geojson(row);
        assert_eq!(got["geometry"], w["geometry"], "row {row}: the geometry");
        assert_eq!(got["properties"], w["properties"], "row {row}: the properties");
    }
    let kinds: std::collections::HashSet<_> = (0..t.len()).filter_map(|r| t.geometries_of().kind(r)).collect();
    assert!(kinds.len() >= 3, "points, lines and polygons: {kinds:?}");
}
