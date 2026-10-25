//! Writes the lookup of files/ (src/lib.rs includes it): `get`, one name test for each file, and `NAMES`; and `DASHBOARD_JS`, the
//! dashboard's modules in the order of files/static/dashboard/files.txt. A new file needs no change here.
use std::path::{Path, PathBuf};

fn walk(dir: &Path, out: &mut Vec<PathBuf>) {
    let mut entries: Vec<PathBuf> = std::fs::read_dir(dir).unwrap_or_else(|e| panic!("{}: {e}", dir.display())).flatten().map(|e| e.path()).collect();
    entries.sort();
    for p in entries {
        if p.is_dir() {
            walk(&p, out);
        } else {
            out.push(p);
        }
    }
}

fn main() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("files");
    println!("cargo:rerun-if-changed={}", root.display());
    let mut files = Vec::new();
    walk(&root, &mut files);
    let name = |p: &Path| p.strip_prefix(&root).unwrap().to_string_lossy().replace('\\', "/");
    let mut code = String::from("/// The file of `name` (its path under files/), or None. A `const fn`: in a const, a wrong name is a compile error.\n\
                                 pub const fn get(name: &str) -> Option<&'static [u8]> {\n");
    for p in &files {
        println!("cargo:rerun-if-changed={}", p.display());
        code += &format!("    if eq(name, {:?}) {{ return Some(include_bytes!({:?})); }}\n", name(p), p.display().to_string());
    }
    code += "    None\n}\n\n/// The names of every file, sorted.\npub const NAMES: &[&str] = &[";
    code += &files.iter().map(|p| format!("{:?}", name(p))).collect::<Vec<_>>().join(", ");
    code += "];\n\n";
    let list = root.join("static/dashboard/files.txt");
    let text = std::fs::read_to_string(&list).unwrap_or_else(|e| panic!("{}: {e}", list.display()));
    let modules: Vec<String> = text.lines().map(str::trim).filter(|l| !l.is_empty() && !l.starts_with('#'))
        .map(|n| format!("text!({:?})", format!("static/dashboard/{n}.js"))).collect();
    code += &format!("/// The dashboard's modules, in the order of static/dashboard/files.txt (the page writer puts them in one script).\n\
                      pub const DASHBOARD_JS: [&str; {}] = [{}];\n", modules.len(), modules.join(", "));
    std::fs::write(Path::new(&std::env::var("OUT_DIR").unwrap()).join("files.rs"), code).unwrap();
}
