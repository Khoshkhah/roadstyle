//! The dashboard's modules for the page writer (src/page.rs): their list is roadstyle's src/roadstyle/static/dashboard/files.txt (one
//! copy, which render_web.py reads too). This writes `DASH_JS`, each module's text in the list's order, so a new module needs no change here.
use std::path::Path;

fn main() {
    let dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../src/roadstyle/static/dashboard");
    let list = dir.join("files.txt");
    println!("cargo:rerun-if-changed={}", list.display());
    let text = std::fs::read_to_string(&list).unwrap_or_else(|e| panic!("{}: {e}", list.display()));
    let names: Vec<&str> = text.lines().map(str::trim).filter(|l| !l.is_empty() && !l.starts_with('#')).collect();
    let items: Vec<String> = names.iter().map(|n| {
        let f = dir.join(format!("{n}.js"));
        println!("cargo:rerun-if-changed={}", f.display());
        format!("include_str!({:?})", f.canonicalize().unwrap_or_else(|e| panic!("{}: {e}", f.display())).display().to_string())
    }).collect();
    let out = Path::new(&std::env::var("OUT_DIR").unwrap()).join("dash_files.rs");
    std::fs::write(&out, format!("/// render_web._DASH_FILES: static/dashboard/files.txt, in its order\nconst DASH_JS: [&str; {}] = [{}];\n",
                                 items.len(), items.join(", "))).unwrap();
}
