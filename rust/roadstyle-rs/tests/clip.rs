//! The base map clipped to its area's boundary (roadstyle-io duckosm::clip_to_boundary, 2026-10-25): on a real base map (the duckOSM
//! reader's features.parquet: Monaco in tests/data; more files with ROADSTYLE_CLIP=<a folder of *.parquet>, for the measurement), no
//! kept feature reaches past the boundary's box; the counts by layer before and after and the time are printed.

use roadstyle_rs::read::read_feature_table;
use std::path::PathBuf;

fn measure(name: &str, bytes: Vec<u8>) {
    let t = read_feature_table(bytes, "geometry").unwrap();
    let count = |t: &roadstyle_rs::FeatureTable| {
        let mut c = std::collections::BTreeMap::<String, usize>::new();
        (0..t.len()).for_each(|r| *c.entry(t.get(r, "layer").and_then(|v| v.as_str().map(String::from)).unwrap_or_default()).or_default() += 1);
        c
    };
    let before = count(&t);
    let g = t.geometries_of();
    let Some(b) = (0..t.len()).find(|&r| t.get(r, "kind").and_then(|v| v.as_str().map(String::from)).as_deref() == Some("background")) else {
        println!("{name}: no boundary in the file: nothing is clipped");
        assert_eq!(roadstyle_rs::duckosm::clip_to_boundary(t).unwrap().len(), before.values().sum::<usize>());
        return;
    };
    let bpts: Vec<[f64; 2]> = g.parts(b).flatten().flatten().copied().collect();
    let (lo, hi) = bpts.iter().fold(([f64::MAX; 2], [f64::MIN; 2]), |(lo, hi), p| ([lo[0].min(p[0]), lo[1].min(p[1])], [hi[0].max(p[0]), hi[1].max(p[1])]));
    let start = std::time::Instant::now();
    let t = roadstyle_rs::duckosm::clip_to_boundary(t).unwrap();
    let ms = start.elapsed().as_secs_f64() * 1000.0;
    let after = count(&t);
    let g = t.geometries_of();
    let eps = 1e-7;
    let outside = (0..t.len()).filter(|&r| g.parts(r).flatten().flatten().any(|p| p[0] < lo[0] - eps || p[0] > hi[0] + eps || p[1] < lo[1] - eps || p[1] > hi[1] + eps)).count();
    println!("{name}: {} -> {} features in {ms:.0} ms; outside the boundary's box: {outside}", before.values().sum::<usize>(), t.len());
    for (layer, n) in &before {
        let m = after.get(layer).copied().unwrap_or(0);
        if m != *n {
            println!("  {layer}: {n} -> {m}");
        }
    }
    assert_eq!(outside, 0, "{name}: a feature past the boundary's box");
}

#[test]
fn monaco_is_clipped_to_its_boundary() {
    measure("monaco", std::fs::read(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data/monaco/features.parquet")).unwrap());
}

/// ROADSTYLE_CLIP=<folder> cargo test -p roadstyle-rs --release --test clip -- --ignored --nocapture
#[test]
#[ignore]
fn the_files_of_a_folder_are_clipped() {
    let dir = PathBuf::from(std::env::var("ROADSTYLE_CLIP").expect("ROADSTYLE_CLIP: a folder of features.parquet files"));
    let mut files: Vec<PathBuf> = std::fs::read_dir(&dir).unwrap().filter_map(|e| Some(e.ok()?.path())).filter(|p| p.extension().is_some_and(|e| e == "parquet")).collect();
    files.sort();
    for f in files {
        measure(f.file_stem().unwrap().to_str().unwrap(), std::fs::read(&f).unwrap());
    }
}
