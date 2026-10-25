//! The level editor's WebAssembly package in the program (src/lib.rs, `PKG`), when rust/roadstyle-wasm/build_editor.sh made it before
//! this build: `$CARGO_TARGET_DIR/editor-pkg/` (else rust/target/editor-pkg/), the folder that the script writes. It is a build output,
//! not a file of roadstyle-assets. The page's other files come from roadstyle-assets (src/lib.rs, `embedded`).
use std::path::{Path, PathBuf};

fn main() {
    println!("cargo:rerun-if-env-changed=CARGO_TARGET_DIR");
    let target = std::env::var_os("CARGO_TARGET_DIR").map(PathBuf::from)
        .unwrap_or_else(|| Path::new(env!("CARGO_MANIFEST_DIR")).join("../target"));
    let dir = target.join("editor-pkg");
    println!("cargo:rerun-if-changed={}", dir.display());
    let mut files: Vec<PathBuf> = std::fs::read_dir(&dir).map(|l| l.flatten().map(|e| e.path())
        .filter(|p| p.is_file() && p.extension().and_then(|e| e.to_str()).is_some_and(|e| e == "js" || e == "wasm")).collect())
        .unwrap_or_default();                  // not built: the program says so when it starts (serve)
    files.sort();
    let items: Vec<String> = files.iter().map(|p| {
        println!("cargo:rerun-if-changed={}", p.display());
        let abs = p.canonicalize().unwrap_or_else(|e| panic!("{}: {e}", p.display()));
        format!("(\"level_editor/pkg/{}\", include_bytes!({:?}))", p.file_name().unwrap().to_string_lossy(), abs.display().to_string())
    }).collect();
    std::fs::write(Path::new(&std::env::var("OUT_DIR").unwrap()).join("pkg.rs"),
                   format!("/// The editor's WebAssembly package, served at level_editor/pkg/<file>\nconst PKG: &[(&str, &[u8])] = &[{}];\n",
                           items.join(", "))).unwrap();
}
