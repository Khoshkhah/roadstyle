//! The buffer round a tile at each zoom, from the style: the widest stroke's reach (half its width, its gap and its offset) at the map
//! zooms that draw the tile, in px of the tile. MapLibre draws each tile only inside its own edges, so a road out of a tile whose stroke
//! reaches into it must be in the tile (the casing gap on Burnaby, 2026-10-27). A tile of zoom z draws the map zooms z to z + 1, scaled
//! up by 2^(Z - z); a tile of the last zoom draws every zoom after it. Thin roads at low zooms then get a small buffer (fewer features
//! in a tile), wide ones near the last zoom a large one.

use serde_json::Value;

/// The live width's largest factor (a page's `rs.setData(rows, {widthBy, widthRange})`: the dashboard's widthRange default is [1, 3]):
/// a stroke whose width reads a feature state can be this many times wider.
pub const LIVE_WIDTH_MAX: f64 = 3.0;

/// The last zoom that MapLibre draws.
const MAP_MAX_ZOOM: f64 = 24.0;

/// The buffer of each tile zoom 0 to `max_zoom`, in px of the tile: the widest reach of a line or circle layer at the map zooms that
/// draw a tile of that zoom, plus 1 px (the line's smoothing). `live`: the factor of a width that reads a feature state (LIVE_WIDTH_MAX).
/// `fallback`: the buffer (px) of a zoom where a layer's reach cannot be bounded (an expression that this does not read).
pub fn buffers_px(layers: &[Value], max_zoom: u32, live: f64, fallback: f64) -> Vec<f64> {
    (0..=max_zoom).map(|z| {
        let top = if z < max_zoom { z as f64 + 1.0 } else { MAP_MAX_ZOOM };
        let steps = ((top - z as f64) * 16.0).ceil() as usize;
        let mut need = 0.0f64;
        for k in 0..=steps {
            let zz = z as f64 + (top - z as f64) * k as f64 / steps as f64;
            for l in layers {
                match reach(l, zz, live) {
                    Some(px) => need = need.max(px / 2f64.powf(zz - z as f64)),
                    None => return fallback,
                }
            }
        }
        need + 1.0
    }).collect()
}

/// The reach of a layer's stroke from its line or point at the map zoom `z`, in px: 0 for a layer with no stroke or that the zoom does
/// not draw (and for the labels and arrows: the `slots`, a source or a tiled style's source layer, go whole into the tiles, and a
/// symbol is placed by its anchor).
fn reach(l: &Value, z: f64, live: f64) -> Option<f64> {
    let drawn = l["minzoom"].as_f64().is_none_or(|m| z >= m) && l["maxzoom"].as_f64().is_none_or(|m| z < m);
    if !drawn || l["source"] == "slots" || l["source-layer"] == "slots" {
        return Some(0.0);
    }
    let p = &l["paint"];
    let ub = |k: &str, none: f64| if p[k].is_null() { Some(none) } else { bound(&p[k], z, live) };
    match l["type"].as_str() {
        Some("line") => {
            let (w, gap) = (ub("line-width", 1.0)?, ub("line-gap-width", 0.0)?);
            Some(if gap > 0.0 { gap / 2.0 + w } else { w / 2.0 } + ub("line-offset", 0.0)? + ub("line-blur", 0.0)? / 2.0)
        }
        Some("circle") => Some(ub("circle-radius", 5.0)? + ub("circle-stroke-width", 0.0)? + ub("circle-blur", 0.0)?),
        _ => Some(0.0),
    }
}

/// An upper bound of the absolute value of the expression `e` at the zoom `z` for every feature, or None when it cannot be bounded.
fn bound(e: &Value, z: f64, live: f64) -> Option<f64> {
    let a = match e {
        Value::Number(n) => return n.as_f64().map(f64::abs),
        Value::Array(a) => a,
        _ => return None,
    };
    let b = |e: &Value| bound(e, z, live);
    let max = |es: &mut dyn Iterator<Item = &Value>| es.map(b).try_fold(0.0f64, |m, x| x.map(|x| m.max(x)));
    match a.first()?.as_str()? {
        "literal" => match &a[1] {
            Value::Array(xs) => xs.iter().try_fold(0.0f64, |m, x| x.as_f64().map(|x| m.max(x.abs()))),
            x => bound(x, z, live),
        },
        "zoom" => Some(z),
        "feature-state" => Some(live),
        "at" => b(a.get(2)?),
        "let" => b(a.last()?),      // a variable is only read as the index of an `at`, which the bound does not use
        "abs" => b(a.get(1)?),
        "*" => a[1..].iter().try_fold(1.0, |m, x| b(x).map(|x| m * x)),
        "+" | "-" => a[1..].iter().try_fold(0.0, |m, x| b(x).map(|x| m + x)),
        "/" => {
            let d = a.get(2)?.as_f64().filter(|d| *d != 0.0)?;
            Some(b(a.get(1)?)? / d.abs())
        }
        "max" | "coalesce" => max(&mut a[1..].iter()),
        "min" => a[1..].iter().filter_map(b).reduce(f64::min),
        // the values of the branches (each condition's value, then the default)
        "case" => max(&mut a[2..].iter().step_by(2).chain(a.last())),
        "match" => max(&mut a[3..].iter().step_by(2).chain(a.last())),
        "step" => {
            let outs: Vec<&Value> = std::iter::once(a.get(2)?).chain(a[4..].iter().step_by(2)).collect();
            if a.get(1)? == &Value::from(vec!["zoom"]) {
                let at = a[3..].iter().step_by(2).take_while(|s| s.as_f64().is_some_and(|s| s <= z)).count();
                b(outs[at])
            } else {
                max(&mut outs.into_iter())
            }
        }
        "interpolate" => {
            let stops: Vec<(f64, &Value)> = a[3..].chunks(2).map(|c| Some((c[0].as_f64()?, c.get(1)?))).collect::<Option<_>>()?;
            if a.get(2)? != &Value::from(vec!["zoom"]) {
                return max(&mut stops.iter().map(|s| s.1));
            }
            let i = stops.iter().take_while(|s| s.0 <= z).count();
            if i == 0 {
                return b(stops.first()?.1);
            }
            if i == stops.len() {
                return b(stops[i - 1].1);      // after the last stop: MapLibre keeps its value
            }
            let ((z0, e0), (z1, e1)) = (stops[i - 1], stops[i]);
            let (v0, v1) = (b(e0)?, b(e1)?);
            // the interpolated value is (1 - t) v0 + t v1 with t in [0, 1] for every feature: the same of the bounds bounds it
            let t = match a[1][0].as_str() {
                Some("linear") => (z - z0) / (z1 - z0),
                Some("exponential") => {
                    let base = a[1][1].as_f64()?;
                    if base == 1.0 { (z - z0) / (z1 - z0) } else { (base.powf(z - z0) - 1.0) / (base.powf(z1 - z0) - 1.0) }
                }
                _ => return Some(v0.max(v1)),
            };
            Some(v0 + t.clamp(0.0, 1.0) * (v1 - v0))
        }
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn the_bound_of_a_width_table_is_its_largest_value() {
        let w = json!(["let", "row", ["get", "i"], ["interpolate", ["linear"], ["zoom"], 12, ["*", ["at", ["var", "row"], ["literal", [1, 4]]], 2], 18, ["at", ["var", "row"], ["literal", [3, 5]]]]]);
        assert_eq!(bound(&w, 12.0, 3.0), Some(8.0));
        assert_eq!(bound(&w, 18.0, 3.0), Some(5.0));
    }

    #[test]
    fn the_bound_of_a_road_width() {
        let w = json!(["*", ["interpolate", ["linear"], ["zoom"], 12, ["match", ["get", "highway"], "primary", 4, 2], 18, ["at", ["get", "i"], ["literal", [10, 20]]]],
                       ["coalesce", ["feature-state", "rs_w"], 1]]);
        assert_eq!(bound(&w, 12.0, 3.0), Some(12.0));
        assert_eq!(bound(&w, 15.0, 1.0), Some(12.0));      // halfway from 4 to 20
        assert_eq!(bound(&w, 20.0, 1.0), Some(20.0));      // after the last stop
        assert_eq!(bound(&json!(["get", "w"]), 15.0, 1.0), None);
    }

    #[test]
    fn a_tile_has_the_buffer_of_its_widest_stroke() {
        // a road 2 px wide to z13, then wider up to 40 px at z18 (and after it, MapLibre keeps the last stop)
        let layers = [json!({"type": "line", "source": "simple", "paint": {"line-width": ["interpolate", ["linear"], ["zoom"], 13, 2, 18, 40]}})];
        let b = buffers_px(&layers, 18, LIVE_WIDTH_MAX, 80.0);
        // the thin roads of zooms 11 to 12 (up to z13): far less than the old 10 px (80 units of 512 px tiles)
        assert!(b[11] <= 2.0 + 1e-9 && b[12] <= 2.0 + 1e-9, "{:?}", &b[11..13]);
        assert!(b[13] < 10.0, "z13 {}", b[13]);
        // the last zoom: half of 40 px at z18 (then the scale up halves it each zoom), plus 1 px
        assert!((b[18] - 21.0).abs() < 1e-9, "z18 {}", b[18]);
        // an expression that cannot be bounded: the look's buffer
        let unknown = [json!({"type": "line", "source": "simple", "paint": {"line-width": ["get", "w"]}})];
        assert_eq!(buffers_px(&unknown, 18, LIVE_WIDTH_MAX, 80.0), vec![80.0; 19]);
    }
}
