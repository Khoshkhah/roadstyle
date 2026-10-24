//! The commands of the roadstyle program (main.rs runs `run`): stage 1 (`sources`), stage 2 (`tiles`), a level area (`levels make`,
//! `levels solve`) and the level editor (`serve`). The options have the names of roadstyle's Python keywords (`--color-by lanes` is
//! `color_by="lanes"`, `--no-arrows` is `arrows=False`); a value that is JSON (a number, true, a list) is read as JSON.

use roadstyle::level_area::{make_area, MakeOptions};
use roadstyle::level_editor::Editor;
use serde_json::{Map, Value};
use std::path::{Path, PathBuf};

pub const USAGE: &str = "roadstyle: road networks as styled maps (https://khoshkhah.github.io/roadstyle/)

usage:
  roadstyle sources <roads.parquet> <out dir> [--format geojson|geoparquet] [--keep COL,COL] [--name NAME]
                    [--palette P] [--profile P] [--settings FILE.json] [--<keyword> VALUE] [--no-<keyword>]
      stage 1: the style and one file for each source, and the road table (export_geojson). The roads: GeoParquet, the line in
      the column geometry, longitude and latitude. Any other option is a keyword of render (--color-by lanes, --no-arrows).
  roadstyle tiles <stage 1 dir> <out> [--format pmtiles|xyz] [--keep COL,COL] [--base-url URL]
      stage 2: the vector tiles of stage 1's files (tile_geojson): one PMTiles file, or <out>/roads/{z}/{x}/{y} and style.json.
  roadstyle levels make <edges.parquet> <area folder> [--id-col edge_id] [--band-col C] [--order priority|class|none|C]
                    [--band-dist 10] [--head-m 5] [--near-rules] [--highway-col highway] [--layer-col layer] [--bridge-col bridge]
                    [--tunnel-col tunnel] [--junction-col junction]
      a level area's input: roads.parquet, pairs.csv and edits.csv (roadstyle-levels make).
  roadstyle levels solve <area folder>
      levels.csv and levels_info.json from the area's input and your edits.csv, heads.csv and caps.csv (roadstyle-levels solve).
  roadstyle serve <area folder> [--port 8780] [--page DIR]
      the level editor at http://127.0.0.1:<port>/level_editor/ (roadstyle-levels edit).
  roadstyle snapshot <page.html> <out.png> [--center LON,LAT] [--zoom Z] [--pitch P] [--bearing B] [--width 1200] [--height 800]
                    [--scale 1] [--settle 2.5] [--timeout 40]
      a PNG of a saved page, drawn by Chromium (roadstyle-snapshot; Python's rs.snapshot).";

/// The positional arguments and the options (`--name value`, or a flag with no value), the names with `_` for `-`.
fn split(args: &[String]) -> (Vec<String>, Vec<(String, Option<String>)>) {
    let (mut pos, mut opts) = (Vec::new(), Vec::new());
    let mut it = args.iter().peekable();
    while let Some(a) = it.next() {
        match a.strip_prefix("--") {
            Some(name) => {
                let value = it.next_if(|v| !v.starts_with("--")).cloned();
                opts.push((name.replace('-', "_"), value));
            }
            None => pos.push(a.clone()),
        }
    }
    (pos, opts)
}

/// An option's value as JSON: a flag is true, `--no-x` is x false, a JSON text is JSON, any other text is text.
fn keyword((name, value): &(String, Option<String>)) -> (String, Value) {
    match (name.strip_prefix("no_"), value) {
        (Some(k), None) => (k.to_string(), Value::Bool(false)),
        (_, None) => (name.clone(), Value::Bool(true)),
        (_, Some(v)) => (name.clone(), serde_json::from_str(v).unwrap_or_else(|_| Value::String(v.clone()))),
    }
}

fn take(opts: &mut Vec<(String, Option<String>)>, name: &str) -> Option<String> {
    let i = opts.iter().position(|(n, _)| n == name)?;
    opts.remove(i).1
}

fn read(path: &str) -> Result<Vec<u8>, String> {
    std::fs::read(path).map_err(|e| format!("{path}: {e}"))
}

/// Runs one command (`args` without the program's name).
pub fn run(args: &[String]) -> Result<(), String> {
    let (cmd, rest) = args.split_first().ok_or(USAGE)?;
    let (pos, mut opts) = split(rest);
    let list = |v: Option<String>| v.map(|s| s.split(',').map(str::trim).filter(|c| !c.is_empty()).map(String::from).collect::<Vec<_>>()).unwrap_or_default();
    match (cmd.as_str(), pos.as_slice()) {
        ("sources", [roads, out]) => {
            let format = match take(&mut opts, "format").as_deref().unwrap_or("geojson") {
                "geojson" => roadstyle::Format::GeoJson,
                "geoparquet" => roadstyle::Format::GeoParquet,
                f => return Err(format!("--format must be geojson or geoparquet, not {f}")),
            };
            let keep = list(take(&mut opts, "keep"));
            let name = take(&mut opts, "name");
            let mut look = Map::new();
            for k in ["palette", "profile"] {
                if let Some(v) = take(&mut opts, k) {
                    look.insert(k.into(), Value::String(v));
                }
            }
            if let Some(f) = take(&mut opts, "settings") {
                let text = String::from_utf8(read(&f)?).map_err(|e| format!("{f}: {e}"))?;
                look.insert("settings".into(), serde_json::from_str(&text).map_err(|e| format!("{f}: not JSON: {e}"))?);
            }
            let mut kw: Map<String, Value> = opts.iter().map(keyword).collect();
            kw.entry("view_3d").or_insert(Value::Bool(true)); // as export_inline and export_geojson
            look.insert("args".into(), Value::Object(kw));
            let look = roadstyle::Look::resolve(&roadstyle::look::Options::from_value(&Value::Object(look))?)?;
            let s = roadstyle::make_sources(read(roads)?, &look, None, None, name)?;
            for (file, size) in roadstyle::save_sources(&s, Path::new(out), format, &keep)? {
                println!("{file} {size} bytes");
            }
            Ok(())
        }
        ("tiles", [src, out]) => {
            let format = take(&mut opts, "format").unwrap_or_else(|| "pmtiles".into());
            let keep = list(take(&mut opts, "keep"));
            let base = take(&mut opts, "base_url").map(|b| format!("{}/", b.trim_end_matches('/'))).unwrap_or_default();
            no_more(&opts)?;
            let (style, tiles) = roadstyle::tile_files(Path::new(src), &keep, None, &roadstyle::xyz_at(&base))?;
            let bounds = tiles.bounds().ok_or(format!("tiles: no feature in the files of {src}"))?;
            let out = PathBuf::from(out);
            match format.as_str() {
                "pmtiles" => {
                    let bytes = tiles.archive(bounds, &tiles.layer_names()).ok_or("tiles: no tile")?;
                    if let Some(d) = out.parent().filter(|d| !d.as_os_str().is_empty()) {
                        std::fs::create_dir_all(d).map_err(|e| format!("{}: {e}", d.display()))?;
                    }
                    std::fs::write(&out, &bytes).map_err(|e| format!("{}: {e}", out.display()))?;
                    println!("{} {} bytes", out.display(), bytes.len());
                }
                "xyz" => {
                    let (z0, z1) = tiles.zooms();
                    let mut n = 0;
                    for z in z0..=z1 {
                        let ([x0, y0], [x1, y1]) = (tile_of(bounds[0], bounds[3], z), tile_of(bounds[2], bounds[1], z));
                        for x in x0..=x1 {
                            for y in y0..=y1 {
                                let b = tiles.tile(z, x, y);
                                if !b.is_empty() {
                                    let p = out.join("roads").join(z.to_string()).join(x.to_string());
                                    std::fs::create_dir_all(&p).map_err(|e| format!("{}: {e}", p.display()))?;
                                    std::fs::write(p.join(y.to_string()), &b).map_err(|e| e.to_string())?;
                                    n += 1;
                                }
                            }
                        }
                    }
                    std::fs::write(out.join("style.json"), style.to_string()).map_err(|e| e.to_string())?;
                    println!("{} tiles and style.json in {}", n, out.display());
                }
                f => return Err(format!("--format must be pmtiles or xyz, not {f}")),
            }
            Ok(())
        }
        ("levels", [sub, rest @ ..]) => levels(sub, rest, opts),
        ("serve", [area]) => {
            let port: u16 = take(&mut opts, "port").map_or(Ok(8780), |p| p.parse().map_err(|_| "--port needs a number"))?;
            let page = take(&mut opts, "page").map_or(crate::Page::Embedded, |p| crate::Page::Dir(p.into()));
            no_more(&opts)?;
            println!("level editor: http://127.0.0.1:{port}/level_editor/  ({area}; Ctrl+C to stop)");
            crate::serve(Path::new(area), page, port)
        }
        ("snapshot", [page, out]) => snapshot(page, out, opts),
        ("help" | "-h", _) => {
            println!("{USAGE}");
            Ok(())
        }
        _ => Err(USAGE.into()),
    }
}

fn levels(sub: &str, pos: &[String], mut opts: Vec<(String, Option<String>)>) -> Result<(), String> {
    match (sub, pos) {
        ("make", [edges, folder]) => {
            let d = MakeOptions::default();
            let mut s = |k: &str, v: String| take(&mut opts, k).unwrap_or(v);
            let mut o = MakeOptions { id_col: s("id_col", d.id_col), highway_col: s("highway_col", d.highway_col), layer_col: s("layer_col", d.layer_col),
                                      bridge_col: s("bridge_col", d.bridge_col), tunnel_col: s("tunnel_col", d.tunnel_col),
                                      junction_col: s("junction_col", d.junction_col), ..d };
            o.band_col = take(&mut opts, "band_col");
            if let Some(order) = take(&mut opts, "order") {
                o.order = (order != "none").then_some(order);
            }
            let num = |v: Option<String>, d: f64, k: &str| v.map_or(Ok(d), |v| v.parse().map_err(|_| format!("--{k} needs a number")));
            o.band_dist = num(take(&mut opts, "band_dist"), o.band_dist, "band-dist")?;
            o.head_m = num(take(&mut opts, "head_m"), o.head_m, "head-m")?;
            if let Some(i) = opts.iter().position(|(n, v)| n == "near_rules" && v.is_none()) {
                opts.remove(i);
                o.near_rules = true;
            }
            no_more(&opts)?;
            let table = roadstyle::read::read_roads(read(edges)?, "geometry")?;
            let made = make_area(&table, Path::new(folder), &o)?;
            for w in &made.warnings {
                eprintln!("warning: {w}");
            }
            println!("{} edges -> {} roads, {} pairs -> {folder}", table.len(), made.roads, made.pairs);
            Ok(())
        }
        ("solve", [folder]) => {
            no_more(&opts)?;
            let dir = Path::new(folder);
            let text = |f: &str| std::fs::read_to_string(dir.join(f)).unwrap_or_default();
            let mut ed = Editor::new(read(&dir.join("roads.parquet").to_string_lossy())?, &text("pairs.csv"))?;
            let answer: Value = serde_json::from_str(&ed.solve(&text("edits.csv"))?).map_err(|e| e.to_string())?;
            let levels: Vec<i64> = answer["levels"].as_array().into_iter().flatten().flat_map(|v| v.as_array().cloned().unwrap_or_default())
                .filter_map(|x| x.as_i64()).collect();
            let csv = ed.levels_csv(&levels, &text("heads.csv"), &text("caps.csv"))?;
            std::fs::write(dir.join("levels.csv"), csv).map_err(|e| e.to_string())?;
            let mut info = answer["info"].clone();
            for k in ["given_up", "given_up_parts", "near", "orders_not_kept"] {
                info[k] = answer[k].clone();
            }
            std::fs::write(dir.join("levels_info.json"), info.to_string()).map_err(|e| e.to_string())?;
            println!("{} roads -> {}: {} stack pair(s) given up, {} order wish(es) not kept", answer["levels"].as_array().map_or(0, Vec::len),
                     dir.join("levels.csv").display(), answer["given_up"].as_array().map_or(0, Vec::len), info["order_violations"]);
            Ok(())
        }
        _ => Err(USAGE.into()),
    }
}

/// An error for an option the command does not take.
fn no_more(opts: &[(String, Option<String>)]) -> Result<(), String> {
    match opts.first() {
        Some((n, _)) => Err(format!("unknown option --{}\n\n{USAGE}", n.replace('_', "-"))),
        None => Ok(()),
    }
}

/// The tile (x, y) at zoom `z` of a point (lon, lat): the web Mercator tiles.
fn tile_of(lon: f64, lat: f64, z: u32) -> [u32; 2] {
    let n = (1u64 << z) as f64;
    let lat = lat.clamp(-85.051_128_78, 85.051_128_78).to_radians();
    let x = ((lon + 180.0) / 360.0 * n).floor().clamp(0.0, n - 1.0);
    let y = ((1.0 - lat.tan().asinh() / std::f64::consts::PI) / 2.0 * n).floor().clamp(0.0, n - 1.0);
    [x as u32, y as u32]
}

/// `snapshot`: the PNG of a saved page; a map that did not load in the time is taken with a warning (on stderr), as in Python.
fn snapshot(page: &str, out: &str, mut opts: Vec<(String, Option<String>)>) -> Result<(), String> {
    use roadstyle_snapshot::{Camera, Shot};
    let num = |k: &str, v: Option<String>| -> Result<Option<f64>, String> {
        v.map(|v| v.parse::<f64>().map_err(|_| format!("--{k} needs a number, not {v:?}"))).transpose()
    };
    let center = match take(&mut opts, "center") {
        Some(c) => {
            let ll: Vec<f64> = c.split(',').map(|v| v.trim().parse::<f64>()).collect::<Result<_, _>>().map_err(|_| "--center needs LON,LAT")?;
            Some(<[f64; 2]>::try_from(ll).map_err(|_| "--center needs LON,LAT")?)
        }
        None => None,
    };
    let cam = Camera { center, zoom: num("zoom", take(&mut opts, "zoom"))?, pitch: num("pitch", take(&mut opts, "pitch"))?,
                       bearing: num("bearing", take(&mut opts, "bearing"))? };
    let d = Shot::default();
    let secs = |k: &str, v: Option<String>, d: std::time::Duration| num(k, v).map(|x| x.map_or(d, std::time::Duration::from_secs_f64));
    let shot = Shot { width: num("width", take(&mut opts, "width"))?.map_or(d.width, |x| x as u32),
                      height: num("height", take(&mut opts, "height"))?.map_or(d.height, |x| x as u32),
                      scale: num("scale", take(&mut opts, "scale"))?.unwrap_or(d.scale),
                      settle: secs("settle", take(&mut opts, "settle"), d.settle)?, timeout: secs("timeout", take(&mut opts, "timeout"), d.timeout)? };
    if let Some((k, _)) = opts.first() {
        return Err(format!("snapshot: unknown option --{k}\n{USAGE}"));
    }
    let pic = roadstyle_snapshot::snapshot(page.as_ref(), out.as_ref(), &cam, &shot).map_err(|e| e.to_string())?;
    if let Some(w) = pic.warning {
        eprintln!("roadstyle: warning: {w}");
    }
    println!("{out}");
    Ok(())
}
