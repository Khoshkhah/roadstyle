//! The text that the stage-1 key of a look hashes (relevel::stage1_text), with the look's keyword levels.
//!
//!     cargo run --release -p roadstyle --example stage1_text -- <look.json> <levels.json> <out.txt>
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let levels: serde_json::Value = serde_json::from_slice(&std::fs::read(&a[1]).unwrap()).unwrap();
    let l = roadstyle::Look::from_json(&std::fs::read_to_string(&a[0]).unwrap()).unwrap().with_arg("levels", levels).unwrap();
    std::fs::write(&a[2], roadstyle::relevel::stage1_text(&l)).unwrap();
}
