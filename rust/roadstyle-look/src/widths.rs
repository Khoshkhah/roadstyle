//! The road width model: the width of each class
//! by zoom, its draw order and its two-way split. The engine builds the MapLibre expressions from it (roadstyle-engine `layers::Exprs`).

use crate::options::MapOptions;
use crate::sections::{Links, Num, RoadsModel, Split};
use crate::Error;
use serde_json::{Map, Value};
use std::collections::HashMap;

/// Round x to n decimals: the nearest double to the correctly rounded decimal.
pub fn round_to(x: f64, n: usize) -> f64 {
    let v: f64 = format!("{x:.n$}").parse().unwrap();
    if v == 0.0 { 0.0 } else { v }
}

/// The road tables of the look and the theme values that the width curves read.
#[derive(Clone, Debug)]
pub struct RoadModel {
    pub width: HashMap<String, Vec<(f64, f64)>>, // group -> (zoom, px), by zoom
    pub hi_rate: HashMap<String, f64>,
    pub casing_ratio: HashMap<String, f64>,
    pub group: Vec<(String, String)>, // class -> width group, in the table's order
    pub classes: Vec<String>,         // the groups' classes, then the links (_CLASSES)
    pub zstops: Vec<Value>,
    pub z_order: Map<String, Value>,
    pub link_w: f64,
    pub offset_frac: f64,
    pub width_frac: f64,
    pub offset_zoom: f64,
    pub ramp_zooms: f64,
    pub fb_group: String,
    pub fb_order: Value,
    pub fb_link_order: f64,
}

impl RoadModel {
    /// From the look's road tables (`roads.model`), the theme's links, two-way split and fallback, and the map options (render's
    /// offset_frac, width_frac and offset_zoom over the split).
    pub fn new(m: &RoadsModel, links: &Links, split: &Split, fallback: &Map<String, Value>, map: &MapOptions) -> Result<RoadModel, Error> {
        let mut width = HashMap::new();
        for (g, t) in &m.width {
            let mut stops: Vec<(f64, f64)> = t.iter()
                .map(|(z, w)| Ok((z.parse::<f64>().map_err(|e| Error::Look(format!("look: roads.model.width.{g}: zoom {z:?}: {e}")))?, w.f())))
                .collect::<Result<_, Error>>()?;
            stops.sort_by(|a, b| a.0.total_cmp(&b.0));
            width.insert(g.clone(), stops);
        }
        let floats = |t: &indexmap::IndexMap<String, Num>| t.iter().map(|(k, x)| (k.clone(), x.f())).collect::<HashMap<_, _>>();
        let group: Vec<(String, String)> = m.group.iter().map(|(c, g)| (c.clone(), g.clone())).collect();
        let classes = group.iter().map(|(c, _)| c.clone()).chain(m.links.iter().cloned()).collect();
        let r = &map.roads;
        Ok(RoadModel {
            width,
            hi_rate: floats(&m.width_zoom_rate),
            casing_ratio: floats(&m.casing_ratio),
            group,
            classes,
            zstops: m.zoom_stops.iter().map(|z| Value::Number(z.0.clone())).collect(),
            z_order: m.z_order.clone(),
            link_w: links.width.f(),
            // render(offset_frac=, width_frac=) over the theme's split: mapstyle passes 0 and 1 for a mode without lanes (one centred line per road)
            offset_frac: r.offset_frac.unwrap_or_else(|| split.offset_frac.f()),
            width_frac: r.width_frac.unwrap_or_else(|| split.width_frac.f()),
            offset_zoom: r.offset_zoom.unwrap_or_else(|| split.offset_zoom.f()),
            ramp_zooms: split.ramp_zooms.f(),
            fb_group: fallback.get("group").and_then(Value::as_str).ok_or_else(|| Error::Look("look: no roads.fallback.group".into()))?.to_string(),
            fb_order: fallback.get("order").cloned().unwrap_or(Value::Null),
            fb_link_order: fallback.get("link_order").and_then(Value::as_f64)
                .ok_or_else(|| Error::Look("look: roads.fallback.link_order is not a number".into()))?,
        })
    }

    /// _base: a link's main class.
    pub fn base(c: &str) -> (&str, bool) {
        match c.strip_suffix("_link") { Some(b) => (b, true), None => (c, false) }
    }

    /// ROAD_Z of a class's main class (its draw order), else the fallback order.
    pub fn z_of(&self, c: &str) -> f64 {
        self.z_order.get(Self::base(c).0).unwrap_or(&self.fb_order).as_f64().unwrap_or(0.0)
    }

    pub fn group_of(&self, base: &str) -> &str {
        self.group.iter().find(|(c, _)| c == base).map_or(self.fb_group.as_str(), |(_, g)| g.as_str())
    }

    /// _gwidth: a group's width at zoom z (linear between its stops, growing by its rate past the last).
    pub fn gwidth(&self, g: &str, z: f64) -> f64 {
        let t = &self.width[g];
        let (first, last) = (t[0], t[t.len() - 1]);
        if z <= first.0 {
            return first.1;
        }
        if z >= last.0 {
            return last.1 * self.hi_rate[g].powf(z - last.0);
        }
        for w in t.windows(2) {
            if z <= w[1].0 {
                let f = (z - w[0].0) / (w[1].0 - w[0].0);
                return w[0].1 + (w[1].1 - w[0].1) * f;
            }
        }
        last.1
    }

    /// The zoom stops, each as a number and as its JSON value (an integer stays an integer in the style).
    pub fn stops(&self) -> impl Iterator<Item = (f64, &Value)> {
        self.zstops.iter().map(|z| (z.as_f64().unwrap(), z))
    }

    /// The width in px of a width group at the zoom stop `z` (a link: times the links' width; casing: times the group's casing ratio),
    /// as _width_expr writes it for each class.
    pub fn group_px(&self, g: &str, link: bool, z: f64, casing: bool, scale: f64) -> f64 {
        let mut w = self.gwidth(g, z) * if casing { self.casing_ratio[g] } else { 1.0 } * scale;
        if link {
            w *= self.link_w;
        }
        round_to(w, 2)
    }

    /// The width in px of a class (none or not in the tables: the fallback group) at the zoom stop `z`.
    pub fn class_px(&self, cls: Option<&str>, z: f64, casing: bool, scale: f64) -> f64 {
        match cls.filter(|c| self.classes.iter().any(|x| x == c)) {
            Some(c) => {
                let (b, lk) = Self::base(c);
                self.group_px(self.group_of(b), lk, z, casing, scale)
            }
            None => self.group_px(&self.fb_group, false, z, casing, scale),
        }
    }

    /// class_width_px (casing as given): the class's width at `zoom` read off the width curve (linear between its stops, the ends outside).
    pub fn class_width_px(&self, cls: Option<&str>, zoom: f64, casing: bool) -> f64 {
        let zs: Vec<f64> = self.stops().map(|(z, _)| z).collect();
        let at = |i: usize| self.class_px(cls, zs[i], casing, 1.0);
        if zoom <= zs[0] {
            return at(0);
        }
        if zoom >= zs[zs.len() - 1] {
            return at(zs.len() - 1);
        }
        let i = (0..zs.len()).filter(|&k| zs[k] <= zoom).max().unwrap();
        let f = (zoom - zs[i]) / (zs[i + 1] - zs[i]);
        at(i) + (at(i + 1) - at(i)) * f
    }

    /// class_order: the table's order, else a link just under its main class.
    pub fn class_order(&self, c: &str) -> Value {
        if let Some(v) = self.z_order.get(c) {
            return v.clone();
        }
        let (b, lk) = Self::base(c);
        let base = self.z_order.get(b).unwrap_or(&self.fb_order);
        if lk { serde_json::json!(base.as_f64().unwrap() + self.fb_link_order) } else { base.clone() }
    }

    /// The stops of the metre-width curves: the zoom stops, width_m_zoom and 22 (MapLibre's last zoom), in order, each once.
    pub fn metre_stops(&self, wmz: &Value) -> Vec<(f64, Value)> {
        let mut zs: Vec<(f64, Value)> = Vec::new();
        for v in self.zstops.iter().chain([wmz, &serde_json::json!(22)]) {
            let z = v.as_f64().unwrap_or(22.0);
            if !zs.iter().any(|(x, _)| *x == z) {
                zs.push((z, v.clone()));
            }
        }
        zs.sort_by(|a, b| a.0.total_cmp(&b.0));
        zs
    }

    /// A zoom inside the zoom stops.
    pub fn clamp_stop(&self, z: f64) -> f64 {
        z.clamp(self.zstops[0].as_f64().unwrap(), self.zstops[self.zstops.len() - 1].as_f64().unwrap())
    }
}
