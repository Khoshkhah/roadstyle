//! The page option `scene_3d`: 3D road tiles (a PMTiles archive of GLB files, SimReady's `<area>.page.pmtiles`) that the page draws in a map
//! layer (`dashboard/scene3d.js`, docs/design/scene_3d_tiles.md). The archive's path is read here, at render time: its header and metadata
//! give the parts (`kinds`), the CRS and the ground id, so the switch rows exist at the first paint and a ground that does not fit is an
//! error before the page is written. The page fetches the tiles from `url`.

use serde_json::{json, Map, Value};

const CRS: &str = roadstyle_assets::text!("data/crs.json");

fn err(m: impl Into<String>) -> crate::Error {
    crate::error::options(format!("scene_3d: {}", m.into()))
}

/// The projection of an EPSG code, from data/crs.json: {family, code, a, f, ...} (tmerc: lon0 k0 fe fn; lcc: lat0 lon0 lat1 lat2 fe fn; webmerc: none).
/// An unknown code is an error that lists the codes that the table has.
pub fn crs_of(code: &str) -> Result<Value, crate::Error> {
    let table: Value = serde_json::from_str(CRS).expect("data/crs.json is JSON");
    let n: u32 = code.strip_prefix("EPSG:").unwrap_or(code).parse().map_err(|_| err(format!("the CRS {code:?} is not an EPSG code (EPSG:<number>)")))?;
    let ell = |name: &str| -> Value {
        let e = &table["ellipsoids"][name];
        json!({"a": e["a"], "f": 1.0 / e["inv_f"].as_f64().expect("inv_f")})
    };
    let merge = |mut base: Value, from: &Value| -> Value {
        for (k, v) in from.as_object().expect("an object") {
            base[k] = v.clone();
        }
        base
    };
    for u in table["utm"].as_array().expect("utm") {
        let (first, last, base) = (u["first"].as_u64().unwrap() as u32, u["last"].as_u64().unwrap() as u32, u["zone_base"].as_u64().unwrap() as u32);
        if (first..=last).contains(&n) {
            let zone = (n - base) as f64;
            let south = u["south"].as_bool().unwrap();
            let e = ell(u["ellipsoid"].as_str().unwrap());
            return Ok(merge(e, &json!({"family": "tmerc", "code": format!("EPSG:{n}"), "lon0": zone * 6.0 - 183.0, "k0": 0.9996, "fe": 500000.0, "fn": if south { 10000000.0 } else { 0.0 }})));
        }
    }
    if let Some(c) = table["codes"].get(n.to_string()) {
        let e = c["ellipsoid"].as_str().map_or_else(|| json!({}), ell);
        let mut out = merge(e, c);
        out.as_object_mut().unwrap().remove("ellipsoid");
        out.as_object_mut().unwrap().remove("name");
        out["code"] = json!(format!("EPSG:{n}"));
        return Ok(out);
    }
    let mut known: Vec<String> = table["utm"].as_array().unwrap().iter().map(|u| format!("{}-{} ({})", u["first"], u["last"], u["name"].as_str().unwrap())).collect();
    known.extend(table["codes"].as_object().unwrap().iter().map(|(k, v)| format!("{k} ({})", v["name"].as_str().unwrap())));
    Err(err(format!("the archive's CRS EPSG:{n} is not in the projection table (rust/roadstyle-assets/files/data/crs.json). It has: {}. A code of a known family is one more row", known.join(", "))))
}

/// The option of the page from the keyword's value: a path (string), or `{"tiles": path, "url": address, "on", "popup", "min_zoom", "max_tiles", "cache_mb"}`.
/// `ground`: the page's own ground option (null: none). Null in, null out.
pub fn option(given: &Value, ground: &Value) -> Result<Value, crate::Error> {
    let o: Map<String, Value> = match given {
        Value::Null => return Ok(Value::Null),
        Value::String(p) => Map::from_iter([("tiles".to_string(), json!(p))]),
        Value::Object(m) => m.clone(),
        _ => return Err(err("give the path of the archive (a string) or a dict {\"tiles\": path, ...}")),
    };
    const KEYS: [&str; 7] = ["tiles", "url", "on", "popup", "min_zoom", "max_tiles", "cache_mb"];
    if let Some(k) = o.keys().find(|k| !KEYS.contains(&k.as_str())) {
        return Err(err(format!("unknown key {k:?}; the keys are {}", KEYS.join(", "))));
    }
    let path = o.get("tiles").and_then(Value::as_str).ok_or_else(|| err("the key \"tiles\" (the path of the archive) is missing"))?.to_string();
    let info = roadstyle_tiles::pmtiles::read_info(std::path::Path::new(&path)).map_err(err)?;
    let md = &info.metadata;
    if md["format"] != "glb" {
        return Err(err(format!("{path}: the metadata says format {} and not \"glb\"", md["format"])));
    }
    if info.min_zoom != info.max_zoom {
        return Err(err(format!("{path}: its tiles are at zooms {} to {}; the layer reads one zoom", info.min_zoom, info.max_zoom)));
    }
    let kinds: Vec<Value> = md["kinds"].as_array().filter(|k| !k.is_empty() && k.iter().all(Value::is_string)).cloned()
        .ok_or_else(|| err(format!("{path}: the metadata has no \"kinds\" (a list of the parts)")))?;
    let sr = &md["simready"];
    let crs = crs_of(sr["crs"].as_str().ok_or_else(|| err(format!("{path}: the metadata has no simready.crs")))?)?;
    let origin = sr["origin"].as_array().filter(|a| a.len() == 3 && a.iter().all(Value::is_number)).cloned().ok_or_else(|| err(format!("{path}: the metadata has no simready.origin [x, y, 0]")))?;
    let archive_ground = sr["ground"].as_str().ok_or_else(|| err(format!("{path}: the metadata names no ground (simready.ground): every product names the ground that its heights are above")))?;
    match ground.get("id").and_then(Value::as_str) {
        Some(id) if id == archive_ground => {}
        Some(id) => return Err(err(format!("its heights are above the ground {archive_ground}, and the page draws the ground {id}: two products of one area with different ground ids do not belong together"))),
        None => return Err(err(format!("its heights are above the ground {archive_ground}, and the page has no ground (ground=): the roads are drawn over the ground that they are measured in, never over another terrain such as the AWS Terrain Tiles"))),
    }
    let url = o.get("url").and_then(Value::as_str).map(str::to_string).unwrap_or_else(|| {
        std::path::Path::new(&path).file_name().map_or(path.clone(), |f| f.to_string_lossy().into_owned())
    });
    let num = |k: &str, d: f64, lo: f64| -> Result<f64, crate::Error> {
        match o.get(k) {
            None | Some(Value::Null) => Ok(d),
            Some(v) => v.as_f64().filter(|x| *x >= lo).ok_or_else(|| err(format!("{k} must be a number of {lo} or more, got {v}"))),
        }
    };
    let flag = |k: &str| -> Result<bool, crate::Error> {
        match o.get(k) { None | Some(Value::Null) => Ok(true), Some(Value::Bool(b)) => Ok(*b), Some(v) => Err(err(format!("{k} must be true or false, got {v}"))) }
    };
    Ok(json!({"url": url, "zoom": info.max_zoom, "kinds": kinds, "crs": crs, "origin": origin, "vertical_datum": sr["vertical_datum"], "ground_id": archive_ground,
              "on": flag("on")?, "popup": flag("popup")?, "min_zoom": num("min_zoom", 15.0, 0.0)?, "max_tiles": num("max_tiles", 49.0, 1.0)?, "cache_mb": num("cache_mb", 200.0, 1.0)?}))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_utm_zone_gives_its_central_meridian_and_a_southern_one_its_false_northing() {
        let n = crs_of("EPSG:32632").unwrap();
        assert_eq!((n["family"].as_str(), n["lon0"].as_f64(), n["fn"].as_f64()), (Some("tmerc"), Some(9.0), Some(0.0)));
        let s = crs_of("EPSG:32756").unwrap();
        assert_eq!((s["lon0"].as_f64(), s["fn"].as_f64()), (Some(153.0), Some(10000000.0)));
        assert_eq!(crs_of("EPSG:25833").unwrap()["lon0"], 15.0);
        assert_eq!(crs_of("3301").unwrap()["family"], "lcc");
        assert_eq!(crs_of("EPSG:3006").unwrap()["family"], "tmerc");
    }

    #[test]
    fn an_unknown_crs_is_an_error_that_lists_the_codes() {
        let e = crs_of("EPSG:2154").unwrap_err().to_string();
        assert!(e.contains("EPSG:2154") && e.contains("3301") && e.contains("32601-32660"), "{e}");
        assert!(crs_of("lambert").is_err());
    }

    #[test]
    fn no_value_is_no_option() {
        assert!(option(&Value::Null, &Value::Null).unwrap().is_null());
        assert!(option(&json!(5), &Value::Null).is_err());
        assert!(option(&json!({"tiles": "x.pmtiles", "tile": 1}), &Value::Null).unwrap_err().to_string().contains("unknown key"));
    }
}
