//! A look as `Look::to_json` writes it after a read (the text that the stage-1 key hashes).
//!
//!     cargo run --release -p roadstyle --example look_json -- <look.json> <out.json>
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let l = roadstyle::Look::from_json(&std::fs::read_to_string(&a[0]).unwrap()).unwrap();
    std::fs::write(&a[1], l.to_json()).unwrap();
}
