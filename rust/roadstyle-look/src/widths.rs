//! The road width model (render_web's _load_road_model: the look's "roads_model" and the theme's roads): the width of each class
//! by zoom, its draw order and its two-way split. The engine builds the MapLibre expressions from it (roadstyle-engine `layers::Exprs`).

use serde_json::{Map, Value};
use std::collections::HashMap;

/// Python's round(x, n) on a float: the nearest double to the correctly rounded decimal.
pub fn py_round(x: f64, n: usize) -> f64 {
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

fn obj<'a>(v: &'a Value, what: &str) -> Result<&'a Map<String, Value>, String> {
    v.as_object().ok_or_else(|| format!("look.json: no {what}"))
}

fn num(v: &Value, what: &str) -> Result<f64, String> {
    v.as_f64().ok_or_else(|| format!("look.json: {what} is not a number"))
}

impl RoadModel {
    /// From the look's `roads_model`, the theme's `roads` and the map options `args` (render's offset_frac, width_frac, offset_zoom).
    pub fn new(r: &Value, th: &Value, args: &Value) -> Result<RoadModel, String> {
        let mut width = HashMap::new();
        for (g, t) in obj(&r["width"], "roads_model.width")? {
            let mut stops: Vec<(f64, f64)> = obj(t, "a width table")?.iter()
                .map(|(z, w)| Ok((z.parse::<f64>().map_err(|e| e.to_string())?, num(w, "a width")?))).collect::<Result<_, String>>()?;
            stops.sort_by(|a, b| a.0.total_cmp(&b.0));
            width.insert(g.clone(), stops);
        }
        let floats = |v: &Value, what: &str| -> Result<HashMap<String, f64>, String> {
            obj(v, what)?.iter().map(|(k, x)| Ok((k.clone(), num(x, what)?))).collect()
        };
        let group: Vec<(String, String)> = obj(&r["group"], "roads_model.group")?.iter()
            .map(|(c, g)| (c.clone(), g.as_str().unwrap_or_default().to_string())).collect();
        let links: Vec<String> = r["links"].as_array().ok_or("look.json: no roads_model.links")?.iter()
            .filter_map(|v| v.as_str().map(String::from)).collect();
        let classes = group.iter().map(|(c, _)| c.clone()).chain(links.iter().cloned()).collect();
        let split = &th["split"];
        let fb = &th["fallback"];
        Ok(RoadModel {
            width,
            hi_rate: floats(&r["width_zoom_rate"], "roads_model.width_zoom_rate")?,
            casing_ratio: floats(&r["casing_ratio"], "roads_model.casing_ratio")?,
            group,
            classes,
            zstops: r["zoom_stops"].as_array().ok_or("look.json: no roads_model.zoom_stops")?.clone(),
            z_order: obj(&r["z_order"], "roads_model.z_order")?.clone(),
            link_w: num(&th["links"]["width"], "theme roads.links.width")?,
            // render(offset_frac=, width_frac=) over the theme's split: mapstyle passes 0 and 1 for a mode without lanes (one centred line per road)
            offset_frac: args["offset_frac"].as_f64().map_or_else(|| num(&split["offset_frac"], "split.offset_frac"), Ok)?,
            width_frac: args["width_frac"].as_f64().map_or_else(|| num(&split["width_frac"], "split.width_frac"), Ok)?,
            offset_zoom: args["offset_zoom"].as_f64().map_or_else(|| num(&split["offset_zoom"], "split.offset_zoom"), Ok)?,
            ramp_zooms: num(&split["ramp_zooms"], "split.ramp_zooms")?,
            fb_group: fb["group"].as_str().ok_or("look.json: no fallback group")?.to_string(),
            fb_order: fb["order"].clone(),
            fb_link_order: num(&fb["link_order"], "fallback.link_order")?,
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
        py_round(w, 2)
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
