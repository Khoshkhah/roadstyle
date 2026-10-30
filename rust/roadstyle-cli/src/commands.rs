//! The commands of the roadstyle program (main.rs runs `run`): stage 1 (`sources`), stage 2 (`tiles`), a level area (`levels make`,
//! `levels solve`) and the level editor (`levels edit`, `serve`). The options have the names of the keywords of `render_edges` (`--color-by lanes` is
//! `color_by="lanes"`, `--no-arrows` is `arrows=False`); a value that is JSON (a number, true, a list) is read as JSON.

use crate::Error;
use roadstyle::level_area::{make_area, MakeOptions};
use roadstyle::level_editor::Editor;
use serde_json::{Map, Value};
use std::path::{Path, PathBuf};

pub const USAGE: &str = "roadstyle: road networks as styled maps (https://khoshkhah.github.io/roadstyle/)

usage:
  roadstyle sources <roads> <out dir> [--format geojson|geoparquet] [--keep COL,COL] [--name NAME]
                    [--palette P] [--profile P] [--settings FILE.json] [--<keyword> VALUE] [--no-<keyword>]
      stage 1: the style and one file for each source, and the road table (export_geojson). Any other option is a keyword of
      render (--color-by lanes, --no-arrows).
  roadstyle page <roads> <out.html> [--palette P] [--profile P] [--settings FILE.json] [--api-key KEY]
                 [--street-view-key KEY] [--<keyword> VALUE] [--no-<keyword>]
      the page in one file (render_edges(backend=\"web\")): the map, its dashboard and MapLibre, offline. The base map's key:
      --api-key, else $ROADSTYLE_API_KEY; the Google Maps key: --street-view-key, else $GOOGLE_MAPS_KEY. Any other option is a
      keyword of render (--tiles, --views '{\"plain\": {\"road_fill\": false}}').
  roadstyle tiles <stage 1 dir> <out> [--format pmtiles|xyz] [--tile-format mlt|mvt] [--keep COL,COL] [--base-url URL]
      stage 2: the vector tiles of stage 1's files (tile_geojson): one PMTiles file, or <out>/roads/{z}/{x}/{y} and style.json.
  roadstyle levels make <edges> <area folder> [--id-col edge_id] [--band-col C] [--order priority|class|none|C]
                    [--band-dist 10] [--head-m 5] [--near-rules] [--highway-col highway] [--layer-col layer] [--bridge-col bridge]
                    [--tunnel-col tunnel] [--junction-col junction]
      a level area's input: roads.parquet, pairs.csv and edits.csv (roadstyle-levels make).
  roadstyle levels solve <area folder>
      levels.csv and levels_info.json from the area's input and your edits.csv, heads.csv and caps.csv (roadstyle-levels solve).
  roadstyle levels edit <area folder> [--port 8780] [--page DIR]
      the level editor at http://127.0.0.1:<port>/level_editor/: the page, your area's files, and the saves of your changes
      (edits.csv, heads.csv, caps.csv, levels.csv). `roadstyle serve <area folder>` is the same without the check of the area.
  roadstyle snapshot <page.html> <out.png> [--center LON,LAT] [--zoom Z] [--pitch P] [--bearing B] [--width 1200] [--height 800]
                    [--scale 1] [--settle 2.5] [--timeout 40]
      a PNG of a saved page, drawn by Chromium (roadstyle-snapshot; Python's rs.snapshot).

<roads> and <edges>: a .parquet (GeoParquet, the line in the column geometry), .geojson, .shp (with its .dbf and .prj beside it)
or .gpkg file.";

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

/// The vendored MapLibre, so a page works offline.
const MAPLIBRE_JS: &str = roadstyle::assets::text!("vendor/maplibre-gl.js");
const MAPLIBRE_CSS: &str = roadstyle::assets::text!("vendor/maplibre-gl.css");

/// The look's options of the command's options: --palette, --profile, --settings FILE.json and every other option as a keyword
/// (`args`), which `defaults` can add to.
fn look_options(opts: &mut Vec<(String, Option<String>)>, defaults: impl FnOnce(&mut Map<String, Value>)) -> Result<roadstyle::look::Options, Error> {
    let mut look = Map::new();
    for k in ["palette", "profile"] {
        if let Some(v) = take(opts, k) {
            look.insert(k.into(), Value::String(v));
        }
    }
    if let Some(f) = take(opts, "settings") {
        let text = String::from_utf8(read(&f)?).map_err(|e| Error::File(format!("{f}: {e}")))?;
        look.insert("settings".into(), serde_json::from_str(&text).map_err(|e| Error::File(format!("{f}: not JSON: {e}")))?);
    }
    let mut kw: Map<String, Value> = opts.iter().map(keyword).collect();
    defaults(&mut kw);
    look.insert("args".into(), Value::Object(kw));
    Ok(roadstyle::look::Options::from_value(&Value::Object(look))?)
}

fn read(path: &str) -> Result<Vec<u8>, Error> {
    std::fs::read(path).map_err(|e| Error::File(format!("{path}: {e}")))
}

/// The roads of a file by its extension (roadstyle-io's readers): GeoParquet (.parquet, the line in `geometry`), GeoJSON (.geojson,
/// .json), a Shapefile (.shp, with its .dbf and .prj beside it) or a GeoPackage (.gpkg, its first feature table). The lines in
/// EPSG:4326 (a Shapefile or GeoPackage in another CRS is reprojected).
fn roads(path: &str) -> Result<roadstyle::RoadTable, Error> {
    let p = Path::new(path);
    let beside = |ext: &str| p.with_extension(ext).to_string_lossy().into_owned();
    match p.extension().and_then(|e| e.to_str()).map(str::to_ascii_lowercase).as_deref() {
        Some("parquet" | "geoparquet") => Ok(roadstyle::read::read_roads(read(path)?, "geometry").map_err(String::from)?),
        Some("geojson" | "json") => Ok(roadstyle::geojson::read_roads(&read(path)?).map_err(String::from)?),
        Some("shp") => {
            let prj = std::fs::read_to_string(beside("prj")).ok();
            Ok(roadstyle::shp::read_roads(&read(path)?, &read(&beside("dbf"))?, prj.as_deref(), path).map_err(String::from)?)
        }
        Some("gpkg") => {
            let (t, warning) = roadstyle::gpkg::read_roads(&read(path)?, path).map_err(String::from)?;
            if let Some(w) = warning {
                eprintln!("warning: {w}");
            }
            Ok(t)
        }
        _ => Err(Error::Usage(format!("{path}: the roads must be a .parquet, .geojson, .shp or .gpkg file"))),
    }
}

/// Runs one command (`args` without the program's name).
/// A comma-separated option as a list of names.
fn list(v: Option<String>) -> Vec<String> {
    v.map(|s| s.split(',').map(str::trim).filter(|c| !c.is_empty()).map(String::from).collect()).unwrap_or_default()
}

/// `sources <roads> <out>`: the style's sources as files.
fn sources_cmd(roads: &str, out: &str, opts: &mut Vec<(String, Option<String>)>) -> Result<(), Error> {
    let format = match take(opts, "format").as_deref().unwrap_or("geojson") {
        "geojson" => roadstyle::Format::GeoJson,
        "geoparquet" => roadstyle::Format::GeoParquet,
        f => return Err(Error::Usage(format!("--format must be geojson or geoparquet, not {f}"))),
    };
    let keep = list(take(opts, "keep"));
    let name = take(opts, "name");
    let o = look_options(opts, |kw| {
        kw.entry("view_3d").or_insert(Value::Bool(true)); // as export_inline and export_geojson
    })?;
    let look = roadstyle::Look::resolve(&o)?;
    let s = roadstyle::sources_of(self::roads(roads)?, &look, None, None, name)?;
    for (file, size) in roadstyle::write_sources(&s, Path::new(out), format, &keep)? {
        println!("{file} {size} bytes");
    }
    Ok(())
}

/// `page <roads> <out>`: one HTML file with the map.
fn page_cmd(roads: &str, out: &str, opts: &mut Vec<(String, Option<String>)>) -> Result<(), Error> {
    let env = |k: &str| std::env::var(k).ok().filter(|v| !v.is_empty()).map(Value::String);
    let mut given = Map::new();         // the page's keys: the call's keywords (a look has none), and the keys
    given.insert("api_key".into(), take(opts, "api_key").map(Value::String).or_else(|| env("ROADSTYLE_API_KEY")).unwrap_or_default());
    given.insert("street_view_key".into(), take(opts, "street_view_key").map(Value::String).or_else(|| env("GOOGLE_MAPS_KEY"))
        .unwrap_or_default());
    let o = look_options(opts, |kw| {
        kw.insert("state".into(), "live".into()); // a page's style: the state in the expressions, the interaction contract
    })?;
    let look = roadstyle::Look::resolve(&o)?;
    given.extend(o.args.as_object().into_iter().flatten().map(|(k, v)| (k.clone(), v.clone())));
    let page = roadstyle::page_options::page_from(self::roads(roads)?, None, &look, &o, &given)?;
    for w in &page.warnings {
        eprintln!("warning: {w}");
    }
    let html = page.html.replacen("__MAPLIBRE_CSS__", MAPLIBRE_CSS, 1)
        .replacen("__MAPLIBRE_JS__", &MAPLIBRE_JS.replace("</script>", "<\\/script>"), 1);
    std::fs::write(out, &html).map_err(|e| Error::File(format!("{out}: {e}")))?;
    println!("{out} {} bytes", html.len());
    Ok(())
}

/// `tiles <src> <out>`: the tiles of a folder of sources, as a PMTiles file or a folder of xyz tiles.
fn tiles_cmd(src: &str, out: &str, opts: &mut Vec<(String, Option<String>)>) -> Result<(), Error> {
    let format = take(opts, "format").unwrap_or_else(|| "pmtiles".into());
    let keep = list(take(opts, "keep"));
    let base = take(opts, "base_url").map(|b| format!("{}/", b.trim_end_matches('/'))).unwrap_or_default();
    let tile_format = roadstyle::tiles::TileFormat::parse(&take(opts, "tile_format").unwrap_or_else(|| "mlt".into())).map_err(|e| Error::Usage(e.to_string()))?;
    no_more(opts)?;
    let (mut style, mut tiles) = roadstyle::tiles_of_files(Path::new(src), &keep, None, &roadstyle::xyz_at(&base))?;
    tiles.format = tile_format;
    tile_format.set_encoding(&mut style["sources"][roadstyle::tiles::SOURCE]);
    let bounds = tiles.bounds().ok_or(Error::Engine(format!("tiles: no feature in the files of {src}")))?;
    let out = PathBuf::from(out);
    match format.as_str() {
        "pmtiles" => {
            let bytes = tiles.archive(bounds, &tiles.layer_names()).map_err(|e| Error::Engine(format!("tiles: {e}")))?;
            if let Some(d) = out.parent().filter(|d| !d.as_os_str().is_empty()) {
                std::fs::create_dir_all(d).map_err(|e| Error::File(format!("{}: {e}", d.display())))?;
            }
            std::fs::write(&out, &bytes).map_err(|e| Error::File(format!("{}: {e}", out.display())))?;
            println!("{} {} bytes", out.display(), bytes.len());
        }
        "xyz" => {
            let (z0, z1) = tiles.zooms();
            let mut n = 0;
            for z in z0..=z1 {
                let ([x0, y0], [x1, y1]) = (tile_of(bounds[0], bounds[3], z), tile_of(bounds[2], bounds[1], z));
                for x in x0..=x1 {
                    for y in y0..=y1 {
                        let b = tiles.build_in(tile_format, z, x, y).map_err(|e| Error::Engine(format!("tiles: {e}")))?;        // each tile once: no cache (review 4, D9)
                        if !b.is_empty() {
                            let p = out.join("roads").join(z.to_string()).join(x.to_string());
                            std::fs::create_dir_all(&p).map_err(|e| Error::File(format!("{}: {e}", p.display())))?;
                            std::fs::write(p.join(y.to_string()), &b).map_err(|e| Error::File(e.to_string()))?;
                            n += 1;
                        }
                    }
                }
            }
            std::fs::write(out.join("style.json"), style.to_string()).map_err(|e| Error::File(e.to_string()))?;
            println!("{} tiles and style.json in {}", n, out.display());
        }
        f => return Err(Error::Usage(format!("--format must be pmtiles or xyz, not {f}"))),
    }
    Ok(())
}

pub fn run(args: &[String]) -> Result<(), Error> {
    let (cmd, rest) = args.split_first().ok_or(Error::Usage(USAGE.into()))?;
    let (pos, mut opts) = split(rest);
    match (cmd.as_str(), pos.as_slice()) {
        ("sources", [roads, out]) => sources_cmd(roads, out, &mut opts),
        ("page", [roads, out]) => page_cmd(roads, out, &mut opts),
        ("tiles", [src, out]) => tiles_cmd(src, out, &mut opts),
        ("levels", [sub, rest @ ..]) => levels(sub, rest, opts),
        ("serve", [area]) => serve(area, &mut opts),
        ("snapshot", [page, out]) => snapshot(page, out, opts),
        ("help" | "-h", _) => {
            println!("{USAGE}");
            Ok(())
        }
        _ => Err(Error::Usage(USAGE.into())),
    }
}

fn levels(sub: &str, pos: &[String], mut opts: Vec<(String, Option<String>)>) -> Result<(), Error> {
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
            let num = |v: Option<String>, d: f64, k: &str| v.map_or(Ok(d), |v| v.parse().map_err(|_| Error::Usage(format!("--{k} needs a number"))));
            o.band_dist = num(take(&mut opts, "band_dist"), o.band_dist, "band-dist")?;
            o.head_m = num(take(&mut opts, "head_m"), o.head_m, "head-m")?;
            if let Some(i) = opts.iter().position(|(n, v)| n == "near_rules" && v.is_none()) {
                opts.remove(i);
                o.near_rules = true;
            }
            no_more(&opts)?;
            let table = roads(edges)?;
            let made = make_area(&table, Path::new(folder), &o)?.made;
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
            let answer = ed.solve(&text("edits.csv"))?;
            let levels: Vec<i64> = answer.levels.iter().flatten().copied().collect();
            let csv = ed.levels_csv(&levels, &text("heads.csv"), &text("caps.csv"))?;
            std::fs::write(dir.join("levels.csv"), csv).map_err(|e| Error::File(e.to_string()))?;
            // levels_info.json: the counts with the rules not kept (the page's answer without the numbers)
            let json = answer.to_json();
            let mut info = json["info"].clone();
            for k in ["given_up", "given_up_parts", "near", "orders_not_kept"] {
                info[k] = json[k].clone();
            }
            let bytes = |f: &str| std::fs::read(dir.join(f)).unwrap_or_default();
            info["inputs"] = roadstyle::levels::inputs_key(&bytes("roads.parquet"), &bytes("pairs.csv"), &bytes("edits.csv")).into();
            std::fs::write(dir.join("levels_info.json"), info.to_string()).map_err(|e| Error::File(e.to_string()))?;
            println!("{} roads -> {}: {} stack pair(s) given up, {} order wish(es) not kept", answer.levels.len(),
                     dir.join("levels.csv").display(), answer.given_up.len(), answer.orders_not_kept.len());
            Ok(())
        }
        ("edit", [folder]) => {
            if !Path::new(folder).join("roads.parquet").exists() {
                return Err(Error::File(format!("{folder}: no roads.parquet: make the area first (roadstyle levels make)")));
            }
            serve(folder, &mut opts)
        }
        _ => Err(Error::Usage(USAGE.into())),
    }
}

/// `serve` and `levels edit`: the level editor of an area folder, until Ctrl+C.
fn serve(area: &str, opts: &mut Vec<(String, Option<String>)>) -> Result<(), Error> {
    let port: u16 = take(opts, "port").map_or(Ok(8780), |p| p.parse().map_err(|_| Error::Usage("--port needs a number".into())))?;
    let page = take(opts, "page").map_or(roadstyle_serve::Page::Embedded, |p| roadstyle_serve::Page::Dir(p.into()));
    no_more(opts)?;
    println!("level editor: http://127.0.0.1:{port}/level_editor/  ({area}; Ctrl+C to stop)");
    Ok(roadstyle_serve::serve(Path::new(area), page, port)?)
}

/// An error for an option the command does not take.
fn no_more(opts: &[(String, Option<String>)]) -> Result<(), Error> {
    match opts.first() {
        Some((n, _)) => Err(Error::Usage(format!("unknown option --{}\n\n{USAGE}", n.replace('_', "-")))),
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

/// `snapshot` in a build without the feature "snapshot": an error.
#[cfg(not(feature = "snapshot"))]
fn snapshot(_: &str, _: &str, _: Vec<(String, Option<String>)>) -> Result<(), Error> {
    Err(Error::Usage("snapshot: this roadstyle is built without the feature \"snapshot\"".into()))
}

/// `snapshot`: the PNG of a saved page; a map that did not load in the time is taken with a warning (on stderr).
#[cfg(feature = "snapshot")]
fn snapshot(page: &str, out: &str, mut opts: Vec<(String, Option<String>)>) -> Result<(), Error> {
    use roadstyle_snapshot::{Camera, Shot};
    let num = |k: &str, v: Option<String>| -> Result<Option<f64>, Error> {
        v.map(|v| v.parse::<f64>().map_err(|_| Error::Usage(format!("--{k} needs a number, not {v:?}")))).transpose()
    };
    let center = match take(&mut opts, "center") {
        Some(c) => {
            let ll: Vec<f64> = c.split(',').map(|v| v.trim().parse::<f64>()).collect::<Result<_, _>>().map_err(|_| Error::Usage("--center needs LON,LAT".into()))?;
            Some(<[f64; 2]>::try_from(ll).map_err(|_| Error::Usage("--center needs LON,LAT".into()))?)
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
        return Err(Error::Usage(format!("snapshot: unknown option --{k}\n{USAGE}")));
    }
    let pic = roadstyle_snapshot::snapshot(page.as_ref(), out.as_ref(), &cam, &shot).map_err(|e| Error::Engine(e.to_string()))?;
    if let Some(w) = pic.warning {
        eprintln!("roadstyle: warning: {w}");
    }
    println!("{out}");
    Ok(())
}
