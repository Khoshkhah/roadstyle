//! The level editor's page files in the program (src/lib.rs, `EMBEDDED`): src/roadstyle/static/level_editor/ (the page, and its wasm
//! package pkg/ when rust/roadstyle-wasm/build_editor.sh made it before this build), level_editor.html (the panel), the dashboard's
//! modules and popup.css and popup.js (which they import). Each file by its path under static/.
use std::path::{Path, PathBuf};

fn main() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../src/roadstyle/static");
    let mut files: Vec<(String, PathBuf)> = Vec::new();
    for single in ["level_editor.html", "popup.css", "popup.js"] {
        files.push((single.into(), root.join(single)));
    }
    for (dir, exts) in [("level_editor", &["html", "js"][..]), ("level_editor/pkg", &["js", "wasm"][..]), ("dashboard", &["js", "css"][..]), ("dashboard/editor", &["js"][..]), ("dashboard/worker", &["js"][..])] {
        let d = root.join(dir);
        println!("cargo:rerun-if-changed={}", d.display());
        let Ok(list) = std::fs::read_dir(&d) else { continue };   // pkg/: only when it was built
        let mut names: Vec<PathBuf> = list.flatten().map(|e| e.path())
            .filter(|p| p.is_file() && p.extension().and_then(|e| e.to_str()).is_some_and(|e| exts.contains(&e))).collect();
        names.sort();
        for p in names {
            files.push((format!("{dir}/{}", p.file_name().unwrap().to_string_lossy()), p));
        }
    }
    let items: Vec<String> = files.iter().map(|(name, p)| {
        println!("cargo:rerun-if-changed={}", p.display());
        let abs = p.canonicalize().unwrap_or_else(|e| panic!("{}: {e}", p.display()));
        format!("({name:?}, include_bytes!({:?}))", abs.display().to_string())
    }).collect();
    let out = Path::new(&std::env::var("OUT_DIR").unwrap()).join("embedded.rs");
    std::fs::write(&out, format!("/// The level editor's page files, by their path under src/roadstyle/static/\npub const EMBEDDED: &[(&str, &[u8])] = &[{}];\n",
                                 items.join(", "))).unwrap();
}
