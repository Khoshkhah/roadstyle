//! The bridge profile (docs/guides/bridge-profile.md, docs/reference/formats.md "The bridge profile"): the input of the engine's second part, the maker (`decks::make_pieces`).
//! It is a complete input profile: the groups of 3D bridges with their nodes (a height for each), their chains and the parameters. Every key that the maker needs is required here:
//! a missing one is an error that says "fill the profile first". The input profile that can be incomplete is read by the first part, the filler (`bridge_fill::fill`), which writes
//! a complete profile; the rules that it fills with are today's (`decks::today_profile`).
//!
//! The first build of the maker has one curve, `smooth`: the smoothstep ramps of today, made for the full height of the chain (`top_m`), from the heights at its two nodes. A chain with
//! interior control points and the curve `design` (straight grades and vertical curves) are in the format and are not built: they are errors that say so.

use crate::Error;
use serde::{Deserialize, Serialize};
use serde_json::Value;

/// The version of the format.
pub const FORMAT: &str = "roadstyle.bridge_profile/1";

/// A complete input profile.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BridgeProfile {
    pub format: String,
    pub parameters: Parameters,
    pub groups: Vec<Group>,
}

/// The design speed and the design grade (for the curve `design`), and the curve.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Parameters {
    pub design_speed_kmh: f64,
    pub design_grade: f64,
    /// `smooth` (today's ramps) when it is not there
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub curve: Option<Curve>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Curve {
    Smooth,
    Design,
}

/// A group of bridges: the bridge roads that touch each other.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Group {
    pub name: String,
    pub nodes: Vec<Node>,
    pub chains: Vec<Chain>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Kind {
    /// one chain ends here: the height is 0
    Ground,
    /// chains meet here
    Junction,
}

/// A node: the end of a chain, with its height above the ground.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Node {
    pub id: String,
    pub lonlat: [f64; 2],
    pub kind: Kind,
    pub chains: Vec<String>,
    pub z_m: f64,
    pub source: String,
    pub method: String,
}

/// A chain: a line of bridge roads between two nodes. `c<N>` is the chain number of the engine (`__rs_chain`): the order in which the roads give the chains.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Chain {
    pub id: String,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub osm_ways: Vec<i64>,
    pub length_m: f64,
    pub from: String,
    pub to: String,
    /// interior control points (the curve `design`): not built
    pub points: Vec<Point>,
    /// the full height of the chain: the height that its ramps are made for (the curve `smooth`). `__rs_full`
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub top_m: Option<f64>,
    /// the width of the deck: when it is not there, each road is drawn at the width of its class
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub width_m: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub width_source: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Point {
    pub s: f64,
    pub z_m: f64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub method: Option<String>,
}

impl BridgeProfile {
    /// The profile of a JSON value (a look option, a file). A key that is missing or not known, a wrong type and a wrong format are errors that say that the profile must be complete.
    pub fn from_value(v: &Value) -> Result<Self, Error> {
        let p: BridgeProfile = serde_json::from_value(v.clone())
            .map_err(|e| Error::Data(format!("bridge_profile: {e}. The maker needs a complete profile: fill it first (every key that a complete profile has: docs/reference/formats.md)")))?;
        p.check()?;
        Ok(p)
    }

    /// The profile as JSON.
    pub fn to_value(&self) -> Value {
        serde_json::to_value(self).expect("a profile is JSON")
    }

    /// The checks of the form that the type cannot make: the format, the numbers, the ids.
    fn check(&self) -> Result<(), Error> {
        let bad = |m: String| Err(Error::Data(format!("bridge_profile: {m}")));
        if self.format != FORMAT {
            return bad(format!("the format is {:?}; this engine reads {FORMAT:?}", self.format));
        }
        let p = &self.parameters;
        if !(p.design_speed_kmh.is_finite() && p.design_speed_kmh > 0.0 && p.design_speed_kmh <= 200.0) {
            return bad(format!("design_speed_kmh is {}; it is a number above 0 and at most 200", p.design_speed_kmh));
        }
        if !(p.design_grade.is_finite() && p.design_grade > 0.0 && p.design_grade <= 0.3) {
            return bad(format!("design_grade is {}; it is a number above 0 and at most 0.3", p.design_grade));
        }
        let mut ids = std::collections::HashSet::new();
        for g in &self.groups {
            for n in &g.nodes {
                if !ids.insert(n.id.as_str()) {
                    return bad(format!("two nodes have the id {:?}", n.id));
                }
                if !(n.z_m.is_finite() && n.z_m >= 0.0) {
                    return bad(format!("the node {} has z_m {}; a height is a number of metres, 0 or more", n.id, n.z_m));
                }
                if !(n.lonlat[0].is_finite() && n.lonlat[1].is_finite()) {
                    return bad(format!("the node {} has no position", n.id));
                }
            }
            for c in &g.chains {
                if !ids.insert(c.id.as_str()) {
                    return bad(format!("two chains have the id {:?}", c.id));
                }
                for (what, v) in [("length_m", Some(c.length_m)), ("top_m", c.top_m), ("width_m", c.width_m)] {
                    if v.is_some_and(|v| !(v.is_finite() && v > 0.0)) {
                        return bad(format!("the chain {} has {what} {}; it is a number of metres above 0", c.id, v.unwrap_or(f64::NAN)));
                    }
                }
            }
        }
        Ok(())
    }
}

/// How near a position of an input must be to a node of the roads (metres), and how far a node of a profile can be from the end of its chain.
pub const MATCH_M: f64 = 5.0;

/// The distance in metres between two `[lon, lat]` positions that are near each other.
pub fn metres_between(a: [f64; 2], b: [f64; 2]) -> f64 {
    ((a[0] - b[0]) * 111320.0 * a[1].to_radians().cos()).hypot((a[1] - b[1]) * 111320.0)
}

/// The ramp parameter `t` of the smoothstep `u = t² (3 − 2t)`: the inverse of the smoothstep, `t = 1/2 − sin(asin(1 − 2u) / 3)`. The two ends are exact (0 and 1: no sliver of a piece).
pub fn smoothstep_inverse(u: f64) -> f64 {
    if u <= 1e-12 {
        0.0
    } else if u >= 1.0 - 1e-12 {
        1.0
    } else {
        0.5 - ((1.0 - 2.0 * u).asin() / 3.0).sin()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn profile() -> Value {
        json!({"format": FORMAT, "parameters": {"design_speed_kmh": 50.0, "design_grade": 0.05},
               "groups": [{"name": "g", "nodes": [
                   {"id": "n1", "lonlat": [7.0, 43.0], "kind": "ground", "chains": ["c1"], "z_m": 0.0, "source": "data", "method": "mapped"},
                   {"id": "n2", "lonlat": [7.1, 43.0], "kind": "ground", "chains": ["c1"], "z_m": 0.0, "source": "data", "method": "mapped"}],
                           "chains": [{"id": "c1", "length_m": 100.0, "from": "n1", "to": "n2", "points": [], "top_m": 5.0}]}]})
    }

    #[test]
    fn a_complete_profile_is_read_and_written_as_it_is() {
        let p = BridgeProfile::from_value(&profile()).unwrap();
        assert_eq!(p.to_value(), profile());
        assert_eq!(BridgeProfile::from_value(&p.to_value()).unwrap(), p);
    }

    #[test]
    fn a_missing_or_wrong_value_says_to_fill_the_profile() {
        let mut v = profile();
        v["groups"][0]["nodes"][0].as_object_mut().unwrap().remove("z_m");
        let e = BridgeProfile::from_value(&v).unwrap_err().to_string();
        assert!(e.contains("missing field `z_m`") && e.contains("fill it first"), "{e}");
        let mut v = profile();
        v["groups"][0]["nodes"][0]["z_m"] = (-1.0).into();
        assert!(BridgeProfile::from_value(&v).unwrap_err().to_string().contains("0 or more"));
        let mut v = profile();
        v["format"] = "other".into();
        assert!(BridgeProfile::from_value(&v).unwrap_err().to_string().contains("this engine reads"));
        let mut v = profile();
        v["extra"] = 1.into();
        assert!(BridgeProfile::from_value(&v).unwrap_err().to_string().contains("unknown field `extra`"));
        let mut v = profile();
        v["parameters"]["design_grade"] = 0.0.into();
        assert!(BridgeProfile::from_value(&v).unwrap_err().to_string().contains("design_grade"));
    }

    #[test]
    fn the_smoothstep_inverse_is_the_inverse() {
        for k in 0..=100 {
            let t = k as f64 / 100.0;
            let u = t * t * (3.0 - 2.0 * t);
            assert!((smoothstep_inverse(u) - t).abs() < 1e-9, "{t}");
        }
        assert_eq!((smoothstep_inverse(0.0), smoothstep_inverse(1.0)), (0.0, 1.0));
    }
}
