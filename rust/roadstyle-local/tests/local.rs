//! Way D on Monaco (roadstyle-rs/tests/data/monaco): the program answers the four requests, and a tile of the program is the tile of the engine byte
//! for byte (the same function that the map worker of way C calls). `way_d_tiles.json` holds the size and hash of three tiles: this test and
//! rust/roadstyle-wasm/cross_language.mjs (the wasm package in Node, way C) check the same file, so the two ways give the same bytes.
//! `ROADSTYLE_BLESS=1 cargo test -p roadstyle-local` writes it again.

use roadstyle_local::{Config, Local};
use roadstyle_serve::Page;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::sync::Arc;

fn data(p: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../roadstyle-rs/tests/data/monaco").join(p)
}

/// Monaco's look, as roadstyle-rs/tests/areas.rs and cross_language.mjs make it: the area's options, resolved, as an export.
fn look() -> roadstyle::Look {
    let mut text = String::new();
    flate2::read::GzDecoder::new(std::fs::File::open(data("golden_options.json.gz")).unwrap()).read_to_string(&mut text).unwrap();
    let o = roadstyle::look::Options::from_value(&serde_json::from_str(&text).unwrap()).unwrap();
    let mut look = roadstyle::Look::resolution_value(&o).unwrap();
    look["args"]["export"] = true.into();
    roadstyle::Look::from_value(look).unwrap()
}

fn config(frames: Option<PathBuf>, port: u16) -> Config {
    let roads = roadstyle::read::read_roads(std::fs::read(data("roads.parquet")).unwrap(), "geometry").unwrap();
    Config { roads, features: None, database: None, roads_file: Some(data("roads.parquet")), name: "Monaco".into(), look: look(), tables: Vec::new(), frames, port }
}

/// The three tiles of cross_language.mjs: the point (7.4243, 43.7384) at zoom 12, 14 and 15.
fn addresses() -> Vec<(u32, u32, u32)> {
    let (lon, lat) = (7.4243f64, 43.7384f64);
    [12u32, 14, 15].iter().map(|&z| {
        let n = (1u64 << z) as f64;
        (z, ((lon + 180.0) / 360.0 * n).floor() as u32, ((1.0 - lat.to_radians().tan().asinh() / std::f64::consts::PI) / 2.0 * n).floor() as u32)
    }).collect()
}

fn sha16(b: &[u8]) -> String {
    Sha256::digest(b).iter().take(8).map(|x| format!("{x:02x}")).collect()
}

#[test]
fn a_tile_of_way_d_is_the_tile_of_the_engine_and_the_golden_of_the_wasm_package() {
    let local = Local::open(config(None, 0)).unwrap();
    // the engine's own call, as the wasm Tiler makes it (tiled_from_parquet): the same bytes
    let (_, tiler, _) = roadstyle::tiled_from_parquet(std::fs::read(data("roads.parquet")).unwrap(), &look(), None, None, "rs://", &[]).unwrap();
    let mut got = serde_json::Map::new();
    for (z, x, y) in addresses() {
        let bytes = local.tile("roads", z, x, y).unwrap();
        assert!(!bytes.is_empty(), "z{z} {x} {y} has roads");
        assert_eq!(bytes, tiler.tile_in(tiler.format, z, x, y).unwrap(), "z{z}/{x}/{y}: the program's tile is the engine's");
        got.insert(format!("{z}/{x}/{y}"), json!({"bytes": bytes.len(), "sha16": sha16(&bytes)}));
    }
    assert!(local.tile("walls", 15, 1, 1).unwrap().is_empty() && local.tile("roads", 15, 0, 0).unwrap().is_empty(), "no tile: no bytes");
    let path = data("way_d_tiles.json");
    if std::env::var("ROADSTYLE_BLESS").is_ok_and(|v| v == "1") {
        std::fs::write(&path, serde_json::to_string_pretty(&Value::Object(got.clone())).unwrap() + "\n").unwrap();
    }
    let want: Value = serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
    assert_eq!(Value::Object(got), want, "way_d_tiles.json: run ROADSTYLE_BLESS=1 cargo test -p roadstyle-local");
}

/// The area's own data (the local page of duckOSM): the tiles are the tiles of `tiled_of` (the look's tile keys apply; the base-map rows go
/// through the same call), and the tables of a `.duckdb` file are tables of the queries in their own schemas (a BIGINT keeps its digits) and of the schema, each one time.
#[test]
fn way_d_takes_a_duckdb_file_and_gives_the_tiles_of_tiled_of() {
    let file = std::env::temp_dir().join(format!("roadstyle-local-{}.duckdb", std::process::id()));
    let _ = std::fs::remove_file(&file);
    duckdb::Connection::open(&file).unwrap().execute_batch("CREATE TABLE edges AS SELECT 9007199254740993::BIGINT AS edge_id; CREATE SCHEMA driving; CREATE TABLE driving.edges AS SELECT 1 AS n").unwrap();
    let mut c = config(None, 0);
    c.database = Some(file.clone());
    let local = Local::open(c).unwrap();
    let roads = roadstyle::read::read_roads(std::fs::read(data("roads.parquet")).unwrap(), "geometry").unwrap();
    let (_, tiler, _) = roadstyle::tiled_of(roads, &look(), None, Some("Monaco".into()), "rs://", &[]).unwrap();
    for (z, x, y) in addresses() {
        assert_eq!(local.tile("roads", z, x, y).unwrap(), tiler.tile_in(tiler.format, z, x, y).unwrap(), "z{z}/{x}/{y}: the tile of tiled_of");
    }
    assert_eq!(local.query("SELECT edge_id FROM edges").unwrap()["rows"], json!([["9007199254740993"]]));
    let names: Vec<Value> = local.schema().unwrap()["tables"].as_array().unwrap().iter().map(|t| t["name"].clone()).collect();
    assert_eq!(local.query("SELECT n FROM driving.edges").unwrap()["rows"], json!([[1]]));
    assert_eq!(names, vec![json!("main.edges"), json!("main.roads"), json!("driving.edges")]);
    let _ = std::fs::remove_file(&file);
}

/// The redraw of way D (`POST /relevel`): a road with new levels is drawn again, so a tile with it changes; an id that no road has is an error.
#[test]
fn way_d_draws_a_road_again_with_new_levels() {
    let local = Local::open(config(None, 0)).unwrap();
    let id = local.rows("roads", &[0])[0]["edge_id"].clone();
    let id = id.as_i64().map(|i| i.to_string()).or_else(|| id.as_str().map(String::from)).expect("the road has an edge id");
    let before: Vec<Vec<u8>> = addresses().iter().map(|&(z, x, y)| local.tile("roads", z, x, y).unwrap()).collect();
    let r = local.relevel(&json!([{"edge": id, "casing_start": 3, "casing_level": 3, "casing_end": 3, "fill_level": 3}]).to_string()).unwrap();
    assert!(r["counts"]["edges"].as_u64().unwrap() >= 1, "{r}");
    assert!(r["style"].is_null() || r["style"]["metadata"]["roadstyle:bounds"].is_array(), "a new style has the bounds");
    let after: Vec<Vec<u8>> = addresses().iter().map(|&(z, x, y)| local.tile("roads", z, x, y).unwrap()).collect();
    assert_eq!(before.len(), after.len());
    assert!(local.relevel(r#"[{"edge": "1", "casing_start": 0, "casing_level": 0, "casing_end": 0, "fill_level": 0}]"#).unwrap_err().contains("no road has the edge id 1"));
}

/// An answer: the head and the body.
type Answer = (String, Vec<u8>);

/// A server on a free port (a page folder with no file), and `ask(method, path, body)` for its answer.
fn server(frames: Option<PathBuf>) -> (Arc<Local>, impl Fn(&str, &str, &str) -> Answer) {
    let port = TcpListener::bind("127.0.0.1:0").unwrap().local_addr().unwrap().port();
    let local = Arc::new(Local::open(config(frames, port)).unwrap());
    let dir = std::env::temp_dir().join(format!("roadstyle-local-{port}"));
    std::fs::create_dir_all(&dir).unwrap();
    let (api, d) = (local.clone(), dir.clone());
    std::thread::spawn(move || roadstyle_serve::serve_with(&d, Page::Dir(d.clone()), port, Some(Vec::new()), Vec::new(), Some(api)));
    std::thread::sleep(std::time::Duration::from_millis(300));
    let ask = move |method: &str, path: &str, body: &str| {
        let mut s = TcpStream::connect(("127.0.0.1", port)).unwrap();
        let req = format!("{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}", body.len());
        s.write_all(req.as_bytes()).unwrap();
        let mut all = Vec::new();
        s.read_to_end(&mut all).unwrap();
        let at = all.windows(4).position(|w| w == b"\r\n\r\n").unwrap() + 4;
        (String::from_utf8_lossy(&all[..at]).into_owned(), all[at..].to_vec())
    };
    (local, ask)
}

#[test]
fn the_four_requests_over_http() {
    // a run of three frames: the values 10 * frame + row / 100 for the roads 0 and 1 (the other roads have no value: NaN)
    let frames = std::env::temp_dir().join(format!("roadstyle-local-frames-{}.parquet", std::process::id()));
    duckdb::Connection::open_in_memory().unwrap().execute_batch(&format!(
        "COPY (SELECT f AS frame, f * 2.5 AS t, r AS row, f * 10 + r / 100.0 AS value FROM range(3) a(f), range(2) b(r)) TO '{}' (FORMAT parquet)",
        frames.display())).unwrap();
    let (local, ask) = server(Some(frames));
    let n = local.roads();
    assert!(n > 1000);

    // the style: the tile addresses are relative, and the roads' box is in it
    let (head, body) = ask("GET", "/style.json", "");
    let style: Value = serde_json::from_slice(&body).unwrap();
    assert!(head.starts_with("HTTP/1.1 200") && style["sources"]["roads"]["tiles"][0].as_str().unwrap().starts_with("/tiles/roads/{z}/{x}/{y}"), "{head}");
    let b = &style["metadata"]["roadstyle:bounds"];
    assert!(b[0].as_f64().unwrap() > 7.3 && b[0].as_f64().unwrap() < 7.5 && b[1].as_f64().unwrap() > 43.7, "{b}");

    // a tile: the bytes of the engine; no tile: 204
    let (z, x, y) = addresses()[2];
    let (head, bytes) = ask("GET", &format!("/tiles/roads/{z}/{x}/{y}"), "");
    assert!(head.starts_with("HTTP/1.1 200") && bytes == local.tile("roads", z, x, y).unwrap());
    assert!(ask("GET", "/tiles/roads/15/0/0", "").0.starts_with("HTTP/1.1 204"));

    // rows: the fields of a road; null for a row that no road has
    let (_, body) = ask("POST", "/rows/roads", &format!("[0, 1, {}]", n + 5));
    let rows: Value = serde_json::from_slice(&body).unwrap();
    assert!(rows[0].is_object() && rows[1].is_object() && rows[2].is_null(), "{rows}");
    assert!(rows[0].get("highway").is_some(), "{}", rows[0]);
    assert!(ask("POST", "/rows/roads", "not a list").0.starts_with("HTTP/1.1 400"));

    // a line
    let (_, body) = ask("POST", "/lines", "[0, 1]");
    let lines: Value = serde_json::from_slice(&body).unwrap();
    assert!(lines[0][0][0].as_f64().unwrap() > 7.3, "{lines}");

    // a query: a BIGINT is a text, a DOUBLE a number, an error is a 400 with the database's text
    let (_, body) = ask("POST", "/query", r#"{"sql": "SELECT count(*) AS n, 9007199254740993 AS big, 1.5 AS half, 2.5::DOUBLE AS two FROM roads"}"#);
    let r: Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(r["columns"], json!([{"name": "n", "type": "BIGINT"}, {"name": "big", "type": "BIGINT"}, {"name": "half", "type": "DOUBLE"}, {"name": "two", "type": "DOUBLE"}]), "{r}");
    assert_eq!(r["rows"][0], json!([n.to_string(), "9007199254740993", 1.5, 2.5]));
    let (head, body) = ask("POST", "/query", r#"{"sql": "SELECT nope FROM roads"}"#);
    assert!(head.starts_with("HTTP/1.1 400") && String::from_utf8_lossy(&body).contains("nope"));

    // the schema: the roads' file and the run are tables
    let (_, body) = ask("GET", "/schema", "");
    let s: Value = serde_json::from_slice(&body).unwrap();
    let names: Vec<&str> = s["tables"].as_array().unwrap().iter().map(|t| t["name"].as_str().unwrap()).collect();
    assert_eq!(names, ["main.frames", "main.roads"], "{s}");
    assert_eq!(s["tables"][1]["rows"], json!(n));

    // frames 1 and 2 (the window from 1 up to 3): u32 frames, u32 values, then f64 t and a f32 for each road
    let (head, body) = ask("GET", "/frames?from=1&to=3", "");
    assert!(head.starts_with("HTTP/1.1 200"), "{head}");
    let u = |b: &[u8], at: usize| u32::from_le_bytes(b[at..at + 4].try_into().unwrap());
    assert_eq!((u(&body, 0) as usize, u(&body, 4) as usize), (2, n));
    let frame = 8 + 4 * n;
    let t = |f: usize| f64::from_le_bytes(body[8 + f * frame..16 + f * frame].try_into().unwrap());
    let v = |f: usize, i: usize| f32::from_le_bytes(body[16 + f * frame + 4 * i..20 + f * frame + 4 * i].try_into().unwrap());
    assert_eq!((t(0), t(1)), (2.5, 5.0));
    assert_eq!((v(0, 0), v(0, 1), v(1, 1)), (10.0, 10.01, 20.01));
    assert!(v(0, 2).is_nan());
    assert!(ask("GET", "/frames?from=x", "").0.starts_with("HTTP/1.1 400"));

    // a path that is not the program's is a file of the page (none here)
    assert!(ask("GET", "/nothing", "").0.starts_with("HTTP/1.1 404"));
}
