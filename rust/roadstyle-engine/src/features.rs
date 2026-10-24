//! The base-map layers' features (full port step 3): mapstyle.map.load_layers from the rows the worker's SQL writes (features.parquet: one row
//! per feature with its layer, osm_id, kind, name, bearing, the height tags and the WKB), as one typed table for each layer in draw order
//! (audit R10), and the typed source that writes a layer's table as GeoJSON.

use crate::Cell;
use indexmap::IndexMap;
use roadstyle_model::feature_table::{FeatureTable, GeomType};
use serde_json::{json, Value};

/// _number: the number at the start of a tag value ("12 m" -> 12.0, "12,5" -> 12.5) and the rest of the text.
fn number(text: Option<&str>) -> Option<(f64, &str)> {
    let t = text?.trim_start_matches(|c: char| c.is_whitespace());
    let int = t.bytes().take_while(u8::is_ascii_digit).count();
    if int == 0 {
        return None;
    }
    let mut end = int;
    if matches!(t.as_bytes().get(int), Some(b'.' | b',')) {
        let frac = t[int + 1..].bytes().take_while(u8::is_ascii_digit).count();
        if frac > 0 {
            end = int + 1 + frac;
        }
    }
    Some((t[..end].replace(',', ".").parse().ok()?, &t[end..]))
}

/// _metres: a height tag in metres: the number, times 0.3048 when its unit is feet ("40 ft", "40'").
fn metres(text: Option<&str>) -> Option<f64> {
    let (h, rest) = number(text)?;
    let unit = rest.trim_start().to_lowercase();
    let feet = unit.starts_with("ft") || unit.starts_with("feet") || unit.starts_with("foot") || unit.starts_with('\'');
    Some(if feet { h * 0.3048 } else { h })
}

/// building_height: the higher of the height tag (from min_height) and (building:levels + roof:levels) x m_per_level, else the one of
/// them that is given, else the height of the kind; at most max_height. Not the order of OpenMapTiles (height first): in Tartu the
/// height tag is often an ETAK code (0 to 9), and levels first makes Monaco's buildings lower than OpenFreeMap's.
fn building_height(height: Option<&str>, levels: Option<&str>, roof_levels: Option<&str>, kind: Option<&str>, cfg: &Value) -> Value {
    let top = cfg.get("max_height").and_then(Value::as_f64).unwrap_or(200.0);
    let cap = |v: f64| if v <= top { json!(v) } else { cfg.get("max_height").cloned().unwrap_or(json!(200)) };
    let tag = metres(height).filter(|h| *h >= cfg["min_height"].as_f64().unwrap());
    let floors = number(levels)
        .map(|n| n.0)
        .filter(|l| *l != 0.0)
        .map(|l| (l + number(roof_levels).map_or(0.0, |n| n.0)) * cfg["m_per_level"].as_f64().unwrap());
    match (tag, floors) {
        (Some(h), Some(f)) => cap(h.max(f)),
        (Some(v), None) | (None, Some(v)) => cap(v),
        (None, None) => {
            let hs = &cfg["heights"];
            kind.and_then(|k| hs.get(k)).unwrap_or(&hs["default"]).clone()
        }
    }
}

/// building_base: the bottom of a building (part) for fill-extrusion-base: the min_height tag, else building:min_level x m_per_level, else 0.
fn building_base(min_height: Option<&str>, min_level: Option<&str>, cfg: &Value) -> Value {
    match metres(min_height).or_else(|| number(min_level).map(|n| n.0 * cfg["m_per_level"].as_f64().unwrap())) {
        Some(b) if b > 0.0 => json!(b.min(cfg.get("max_height").and_then(Value::as_f64).unwrap_or(200.0))),
        _ => json!(0),
    }
}

/// load_layers: one table for each layer (osm_id, kind, name, bearing, and a building's height and base), in the order of the first row
/// of each layer; a polygon layer's features largest first. `t`: the rows of features.parquet.
pub fn feature_tables(t: &FeatureTable, look: &crate::Look) -> Result<Vec<(String, FeatureTable)>, String> {
    let specs = look.features["layers_yaml"]["layers"].as_array().ok_or("look.json: no features.layers_yaml.layers")?;
    let kind_of = |name: &str| specs.iter().find(|s| s["name"] == name).and_then(|s| s["kind"].as_str()).unwrap_or("");
    let b3d = &look.features["buildings_3d"];
    let cell = |row: usize, col: &str| t.get(row, col).unwrap_or(Cell::Null);
    let text = |row: usize, col: &str| cell(row, col).as_str();
    let mut layers: IndexMap<String, Vec<usize>> = IndexMap::new();
    for row in 0..t.len() {
        layers.entry(text(row, "layer").unwrap_or_default().to_string()).or_default().push(row);
    }
    let g = t.geometries_of();
    let mut out = Vec::new();
    for (name, rows) in layers {
        // a layer can have rows of more than one spec (landcover: one for each table)
        let mut order = Vec::with_capacity(rows.len());
        for &row in &rows {
            let spec = &specs[cell(row, "spec").as_u64().ok_or("features.parquet: no spec")? as usize];
            let geom = g.geom(row).ok_or_else(|| format!("features.parquet: a geometry of {name} is not read"))?;
            let centroid = (spec["centroid"] == true).then(|| geom.centroid());
            order.push((geom.area(), row, centroid, spec["height"] == true));
        }
        if kind_of(&name) == "polygon" {
            order.sort_by(|a, b| b.0.total_cmp(&a.0)); // stable: largest first, ties in reading order
        }
        let mut geoms = FeatureTable::geometries();
        for (_, row, centroid, _) in &order {
            match centroid {
                Some(p) => geoms.push(GeomType::Point, &[vec![vec![*p]]]),
                None => geoms.push_copy(g, *row),
            }
        }
        let mut table = FeatureTable::new(Vec::new(), Vec::new(), geoms)?;
        let col = |c: &str| order.iter().map(|(_, r, _, _)| cell(*r, c)).collect::<Vec<_>>();
        for c in ["osm_id", "kind", "name"] {
            table.set_column(c, &col(c), true)?;
        }
        table.set_column("bearing", &col("bearing"), false)?;         // only a feature with a bearing has the key
        // a building's height and base: the keys of the rows whose spec has heights
        let tall: Vec<bool> = order.iter().map(|o| o.3).collect();
        if tall.iter().any(|t| *t) {
            let heights: Vec<Value> = order.iter().map(|(_, r, _, t)| if *t { building_height(text(*r, "height"), text(*r, "levels"),
                                                                                              text(*r, "roof_levels"), text(*r, "kind"), b3d) } else { Value::Null }).collect();
            let bases: Vec<Value> = order.iter().map(|(_, r, _, t)| if *t { building_base(text(*r, "min_height"), text(*r, "min_level"), b3d) }
                                                                    else { Value::Null }).collect();
            let every = tall.iter().all(|t| *t);
            if !every && heights.iter().zip(&tall).any(|(h, t)| *t && h.is_null()) {
                return Err(format!("the layer {name}: a building with no height, beside rows with no height key (buildings_3d.heights has no default)"));
            }
            table.set_column("height", &heights.iter().map(Cell::from).collect::<Vec<_>>(), every)?;
            table.set_column("base", &bases.iter().map(Cell::from).collect::<Vec<_>>(), every)?;
        }
        out.push((name, table));
    }
    Ok(out)
}

/// A base-map layer's source (`Src::Features`): its table, written as GeoJSON a feature at a time, and render's data_maxzoom.
pub struct FeatureSource {
    pub table: FeatureTable,
    pub maxzoom: Option<i64>,
}

impl FeatureSource {
    /// The source's FeatureCollection as GeoJSON text.
    pub fn write_data<W: std::io::Write>(&self, w: &mut W) -> std::io::Result<()> {
        self.table.write_geojson(w)
    }

    /// The source as the style's JSON text, with its data.
    pub fn write_json<W: std::io::Write>(&self, w: &mut W) -> std::io::Result<()> {
        w.write_all(br#"{"type":"geojson","data":"#)?;
        self.write_data(w)?;
        w.write_all(br#","generateId":true"#)?;
        if let Some(z) = self.maxzoom {
            write!(w, r#","maxzoom":{z}"#)?;
        }
        w.write_all(b"}")
    }

    /// The source with `data` (its data, or a URL of it), as JSON.
    pub fn spec(&self, data: Value) -> Value {
        let mut s = serde_json::Map::new();
        s.insert("type".into(), "geojson".into());
        s.insert("data".into(), data);
        s.insert("generateId".into(), true.into());
        if let Some(z) = self.maxzoom {
            s.insert("maxzoom".into(), z.into());
        }
        Value::Object(s)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_higher_of_the_height_tag_and_the_levels() {
        let cfg = json!({"m_per_level": 3.66, "min_height": 2, "max_height": 200, "heights": {"house": 6, "default": 8}});
        let h = |height, levels| building_height(height, levels, None, Some("house"), &cfg).as_f64().unwrap();
        assert!((h(Some("3"), Some("3")) - 10.98).abs() < 1e-9, "Tartu: an ETAK code 3 and 3 levels");
        assert_eq!(h(Some("9"), Some("2")), 9.0, "Monaco: 9 m and 2 levels (7.32 m)");
        assert_eq!(h(Some("12 m"), None), 12.0, "the height tag only");
        assert_eq!(h(None, None), 6.0, "the height of the kind");
    }
}
