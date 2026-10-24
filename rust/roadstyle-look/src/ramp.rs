//! The colour ramps of data colours (render_edges' cmap): ports of roadstyle's colors.py ColorRamp over branca's LinearColormap. The ramps
//! are data (cmaps.json: branca's schemes and colour names, each matplotlib colormap at 9 stops; made by roadstyle-rs's
//! tests/make_goldens.py from branca and matplotlib).

use crate::Error;
use serde_json::{Map, Value};
use std::sync::OnceLock;

struct Cmaps {
    branca: Map<String, Value>,
    css: Map<String, Value>,
    matplotlib: Map<String, Value>,
}

fn cmaps() -> &'static Cmaps {
    static C: OnceLock<Cmaps> = OnceLock::new();
    C.get_or_init(|| {
        let v: Value = serde_json::from_str(include_str!("cmaps.json")).expect("cmaps.json");
        let m = |k: &str| v[k].as_object().cloned().unwrap_or_default();
        Cmaps { branca: m("branca"), css: m("css"), matplotlib: m("matplotlib") }
    })
}

/// A LinearColormap over [0, 1]: the colours (RGBA, 0 to 1) and their index.
pub struct Ramp {
    colors: Vec<[f64; 4]>,
    index: Vec<f64>,
}

impl Ramp {
    /// _branca_linear: a branca scheme (exact, then the first of the names in order that is the same ignoring case or starts with
    /// "<name>_"), else a matplotlib colormap (9 stops); or a list of colours (hex or a colour name).
    pub fn new(cmap: &Value) -> Result<Ramp, Error> {
        let c = cmaps();
        let list: Vec<String> = match cmap {
            Value::Array(a) => a.iter().map(|x| x.as_str().map(String::from).ok_or_else(|| Error::Options(format!("cmap: not a colour: {x}")))).collect::<Result<_, _>>()?,
            Value::String(name) => {
                let lower = name.to_lowercase();
                let mut names: Vec<&String> = c.branca.keys().collect();
                names.sort();
                let found = c.branca.get(name).or_else(|| {
                    names.into_iter().find(|n| n.to_lowercase() == lower || n.to_lowercase().starts_with(&format!("{lower}_"))).map(|n| &c.branca[n])
                }).or_else(|| c.matplotlib.get(name));
                let found = found.ok_or_else(|| Error::Unknown(format!("unknown cmap {name:?}; use a branca scheme name (e.g. 'viridis', 'YlOrRd'), a list of hex \
                                                          colour stops, or a matplotlib colormap name")))?;
                found.as_array().unwrap().iter().map(|x| x.as_str().unwrap().to_string()).collect()
            }
            other => return Err(Error::Options(format!("cmap: a name or a list of colours, not {other}"))),
        };
        if list.len() < 2 {
            return Err(Error::Options("You must provide at least 2 colors.".into()));
        }
        let n = list.len();
        let colors = list.iter().map(|x| parse_color(x)).collect::<Result<Vec<_>, _>>()?;
        Ok(Ramp { colors, index: (0..n).map(|i| i as f64 * 1.0 / (n - 1) as f64).collect() })
    }

    fn rgba(&self, x: f64) -> [f64; 4] {
        let (ix, cs) = (&self.index, &self.colors);
        if x <= ix[0] {
            return cs[0];
        }
        if x >= ix[ix.len() - 1] {
            return cs[cs.len() - 1];
        }
        let i = ix.iter().filter(|&&u| u < x).count();
        let p = if ix[i - 1] < ix[i] { (x - ix[i - 1]) * 1.0 / (ix[i] - ix[i - 1]) } else { 1.0 };
        std::array::from_fn(|j| (1.0 - p) * cs[i - 1][j] + p * cs[i][j])
    }

    /// ColorRamp.stops: `n` colours at even steps from the first to the last (at least 2).
    pub fn stops(&self, n: usize) -> Vec<String> {
        let n = n.max(2);
        (0..n).map(|i| self.hex(i as f64 / (n - 1) as f64)).collect()
    }

    /// rgb_hex_str: "#rrggbb", each channel int(u * 255.9999).
    pub fn hex(&self, x: f64) -> String {
        let c = self.rgba(x);
        format!("#{:02x}{:02x}{:02x}", (c[0] * 255.9999) as i64, (c[1] * 255.9999) as i64, (c[2] * 255.9999) as i64)
    }
}

/// _parse_color: "#rrggbb" or a colour name.
fn parse_color(x: &str) -> Result<[f64; 4], Error> {
    let hex = if x.starts_with('#') && x.len() == 7 {
        x.to_string()
    } else {
        cmaps().css.get(&x.to_lowercase()).and_then(Value::as_str).map(String::from).ok_or_else(|| Error::Unknown(format!("Unknown color {x:?}.")))?
    };
    let ch = |a: usize| u8::from_str_radix(&hex[a..a + 2], 16).map(|v| v as f64 / 255.0).map_err(|_| Error::Unknown(format!("Unknown color {x:?}.")));
    Ok([ch(1)?, ch(3)?, ch(5)?, 1.0])
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn a_ramp_as_branca() {
        // roadstyle's ColorRamp: "YlOrRd" is branca's first name with that prefix (YlOrRd_03); a list of two colours at a quarter
        let r = Ramp::new(&json!("YlOrRd")).unwrap();
        assert_eq!((r.hex(0.0), r.hex(0.5), r.hex(1.0)), ("#ffeda0".into(), "#feb24c".into(), "#f03b20".into()));
        let two = Ramp::new(&json!(["#000000", "white"])).unwrap();
        assert_eq!(two.hex(0.25), "#3f3f3f", "int(0.25 * 255.9999) = 63");
        assert!(Ramp::new(&json!("no such ramp")).is_err());
    }

    #[test]
    fn the_steps_of_a_ramp() {
        // roadstyle's ColorRamp(...).stops(n)
        let s = |c: Value, n| Ramp::new(&c).unwrap().stops(n);
        assert_eq!(s(json!("viridis"), 5), ["#440154", "#3a528b", "#21908c", "#5cc962", "#fde725"]);
        assert_eq!(s(json!("YlOrRd"), 1), ["#ffeda0", "#f03b20"]);
        assert_eq!(s(json!(["#000000", "white"]), 3), ["#000000", "#7f7f7f", "#ffffff"]);
    }
}
