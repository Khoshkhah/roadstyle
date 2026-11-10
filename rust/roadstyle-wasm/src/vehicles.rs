//! `VehicleScene`: a run of roadstyle-sim in the browser (docs/design/vehicles_spec.md, section 7), built with the feature
//! `vehicles`. One call for each frame: `frame(t)` gives every vehicle on the network at clock time `t` as 16 numbers.
//!
//! Positions are Mercator offsets from the scene origin divided by the Mercator size of one metre at the origin ("origin
//! metres"): small numbers, exact in float32, that the vehicle layer turns back with one matrix
//! (`mainMatrix x translate(origin) x scale(metre)`). x is east, y is south (Mercator's direction), z is up.

use roadstyle_sim::{read_fcd_parquet, read_net, read_vtypes, Placement, Run, RunOptions};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::f64::consts::PI;
use wasm_bindgen::prelude::*;

/// The numbers for each vehicle in `frame`: x, y, z (origin metres), heading (radians, 0 = north, clockwise), pitch,
/// roll, length, width, height (m), class (index into `classes()`), r, g, b, a (0: the layer colours by class), flags,
/// vehicle (index into `ids()`).
const STRIDE: usize = 16;
/// MapLibre's earth radius (its Mercator coordinates).
const EARTH_R: f64 = 6371008.8;

fn mercator(lon: f64, lat: f64) -> [f64; 2] {
    [(lon + 180.0) / 360.0, 0.5 - (PI / 4.0 + lat.to_radians() / 2.0).tan().ln() / (2.0 * PI)]
}

#[wasm_bindgen]
pub struct VehicleScene {
    run: Run,
    /// lon, lat, Mercator x, Mercator y, the Mercator size of one metre at the origin
    origin: [f64; 5],
    /// the class of each vehicle type, as an index into `classes`
    type_class: Vec<u16>,
    classes: Vec<String>,
}

fn opt_f64(o: &Value, k: &str) -> Result<f64, JsError> {
    o.get(k).and_then(Value::as_f64).ok_or_else(|| JsError::new(&format!("VehicleScene: options.{k} (a number) is missing")))
}

#[wasm_bindgen]
impl VehicleScene {
    /// new VehicleScene(fcd, net, routes, options): `fcd` the bytes of SUMO's FCD Parquet file; `net` the text of the run's
    /// net.xml (required for placement "lane"); `routes` the text of a file with the `<vType>` elements, or undefined;
    /// `options` JSON: {placement: "lane" | "lonlat", teleport_m, lane_change_s, heading_lookahead_m,
    /// class_sizes: {class: [length, width, height]}}. Every key is required (the page gives the profile's values).
    #[wasm_bindgen(constructor)]
    pub fn new(fcd: Vec<u8>, net: Option<String>, routes: Option<String>, options: &str) -> Result<VehicleScene, JsError> {
        let o: Value = serde_json::from_str(options).map_err(|e| JsError::new(&format!("VehicleScene: options are not JSON: {e}")))?;
        let placement = match o.get("placement").and_then(Value::as_str) {
            Some("lane") => Placement::Lane,
            Some("lonlat") => Placement::LonLat,
            p => return Err(JsError::new(&format!("VehicleScene: options.placement must be \"lane\" or \"lonlat\", not {p:?}"))),
        };
        let mut class_sizes = HashMap::new();
        for (k, v) in o.get("class_sizes").and_then(Value::as_object).ok_or_else(|| JsError::new("VehicleScene: options.class_sizes is missing"))? {
            let a: Vec<f32> = v.as_array().map(|a| a.iter().filter_map(|x| x.as_f64().map(|x| x as f32)).collect()).unwrap_or_default();
            if a.len() != 3 {
                return Err(JsError::new(&format!("VehicleScene: options.class_sizes.{k} must be [length, width, height]")));
            }
            class_sizes.insert(k.clone(), [a[0], a[1], a[2]]);
        }
        let opts = RunOptions {
            placement,
            teleport_m: opt_f64(&o, "teleport_m")?,
            lane_change_s: opt_f64(&o, "lane_change_s")?,
            heading_lookahead_m: opt_f64(&o, "heading_lookahead_m")?,
            class_sizes,
        };
        let err = |e: roadstyle_sim::Error| JsError::new(&e.to_string());
        let samples = read_fcd_parquet(fcd).map_err(err)?;
        let net = match net { Some(t) => Some(read_net(&t).map_err(err)?), None => None };
        let vtypes = routes.map(|t| read_vtypes(&t)).unwrap_or_default();
        let by_name: HashMap<&str, &str> = vtypes.iter().map(|v| (v.name.as_str(), v.class.as_str())).collect();
        let mut classes: Vec<String> = Vec::new();
        let type_class = samples
            .types
            .iter()
            .map(|t| {
                let c = by_name.get(t.as_str()).copied().unwrap_or("passenger");
                match classes.iter().position(|x| x == c) {
                    Some(i) => i as u16,
                    None => {
                        classes.push(c.to_string());
                        (classes.len() - 1) as u16
                    }
                }
            })
            .collect();
        let (mut x0, mut x1, mut y0, mut y1) = (f64::INFINITY, f64::NEG_INFINITY, f64::INFINITY, f64::NEG_INFINITY);
        for (&x, &y) in samples.x.iter().zip(&samples.y) {
            (x0, x1, y0, y1) = (x0.min(x), x1.max(x), y0.min(y), y1.max(y));
        }
        if samples.is_empty() {
            return Err(JsError::new("VehicleScene: the FCD file has no vehicle"));
        }
        let (lon, lat) = ((x0 + x1) / 2.0, (y0 + y1) / 2.0);
        let m = mercator(lon, lat);
        let unit = 1.0 / (2.0 * PI * EARTH_R * lat.to_radians().cos());
        let run = Run::new(samples, net, &vtypes, opts).map_err(err)?;
        Ok(VehicleScene { run, origin: [lon, lat, m[0], m[1], unit], type_class, classes })
    }

    /// [lon, lat, Mercator x, Mercator y, Mercator size of one metre] of the scene origin.
    pub fn origin(&self) -> Vec<f64> {
        self.origin.to_vec()
    }

    /// The vehicle classes (SUMO `vClass`) of the run, in the order of the class numbers in `frame`.
    pub fn classes(&self) -> Vec<String> {
        self.classes.clone()
    }

    /// The vehicle ids (SUMO's text), in the order of the vehicle numbers in `frame`.
    pub fn ids(&self) -> Vec<String> {
        self.run.samples.ids.clone()
    }

    /// The run's report as JSON: samples, vehicles, t0, t1, empty_rows, lanes_unknown, path_gaps, teleports.
    pub fn report(&self) -> String {
        let r = self.run.report();
        json!({"samples": r.samples, "vehicles": r.vehicles, "t0": r.t0, "t1": r.t1, "empty_rows": r.empty_rows,
               "lanes_unknown": r.lanes_unknown, "path_gaps": r.path_gaps, "teleports": r.teleports})
        .to_string()
    }

    /// Every vehicle on the network at clock time `t` (seconds of the run), STRIDE numbers each.
    pub fn frame(&self, t: f64) -> Vec<f32> {
        let states = self.run.at(t);
        let [_, _, ox, oy, unit] = self.origin;
        let mut out = Vec::with_capacity(states.len() * STRIDE);
        for s in states {
            let m = mercator(s.lon, s.lat);
            let size = self.run.sizes[s.vtype as usize];
            out.extend_from_slice(&[
                ((m[0] - ox) / unit) as f32,
                ((m[1] - oy) / unit) as f32,
                0.0,
                s.heading.to_radians() as f32,
                0.0,
                0.0,
                size[0],
                size[1],
                size[2],
                self.type_class[s.vtype as usize] as f32,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                s.vehicle as f32,
            ]);
        }
        out
    }
}
