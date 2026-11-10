//! `VehicleScene`: a run of roadstyle-sim in the browser (docs/design/vehicles_spec.md, section 7), built with the feature
//! `vehicles`. One call for each frame: `frame(t)` gives every vehicle on the network at clock time `t` as 16 numbers.
//!
//! Positions are Mercator offsets from the scene origin divided by the Mercator size of one metre at the origin ("origin
//! metres"): small numbers, exact in float32, that the vehicle layer turns back with one matrix
//! (`mainMatrix x translate(origin) x scale(metre)`). x is east, y is south (Mercator's direction), z is up.

use roadstyle_camera::{GroundGrid, RoadHeights};
use roadstyle_sim::{read_fcd_parquet, read_net, read_vtypes, Placement, Run, RunOptions};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::f64::consts::PI;
use wasm_bindgen::prelude::*;

/// The numbers for each vehicle in `frame`: x, y, z (origin metres), heading (radians, 0 = north, clockwise), pitch,
/// roll, length, width, height (m), class (index into `classes()`), r, g, b, a (0: the layer colours by class), flags (1: in a tunnel),
/// vehicle (index into `ids()`).
const STRIDE: usize = 16;
/// The side of a cell of the ground grid, m: the terrain DEM is 30 m data, so 5 m keeps its shape and asks few points.
const GROUND_CELL_M: f64 = 5.0;
/// The step of a road's height profile, m (docs/design/road_heights.md: 5 m on a ground road; the decks' 2 m comes with them).
const ROAD_STEP_M: f64 = 5.0;
/// MapLibre's earth radius (its Mercator coordinates).
const EARTH_R: f64 = 6371008.8;

fn mercator(lon: f64, lat: f64) -> [f64; 2] {
    [(lon + 180.0) / 360.0, 0.5 - (PI / 4.0 + lat.to_radians() / 2.0).tan().ln() / (2.0 * PI)]
}

#[wasm_bindgen]
extern "C" {
    /// The host's ground: `height(lon, lat)` gives the drawn terrain's height there (m above sea level, times the exaggeration; 0
    /// with no terrain), NaN when it is not known yet (a tile that has not come).
    pub type Ground;
    #[wasm_bindgen(method)]
    fn height(this: &Ground, lon: f64, lat: f64) -> f64;

    /// The host's roads: `line(edgeId)` gives the drawn line of the road with that edge id (lon, lat, lon, lat, ...), in the road's
    /// direction; undefined while the host does not have it yet.
    pub type Roads;
    #[wasm_bindgen(method)]
    fn line(this: &Roads, edge: &str) -> Option<Vec<f64>>;
}

#[wasm_bindgen]
pub struct VehicleScene {
    run: Run,
    /// lon, lat, Mercator x, Mercator y, the Mercator size of one metre at the origin
    origin: [f64; 5],
    /// the class of each vehicle type, as an index into `classes`
    type_class: Vec<u16>,
    classes: Vec<String>,
    ground: Option<Ground>,
    grid: GroundGrid,
    roads: Option<Roads>,
    heights: RoadHeights,
    /// the vehicles that the last frame left out because their ground is not known yet
    waiting: usize,
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
        Ok(VehicleScene { run, origin: [lon, lat, m[0], m[1], unit], type_class, classes, ground: None,
                          grid: GroundGrid::new([lon, lat], GROUND_CELL_M), roads: None,
                          heights: RoadHeights::new(ROAD_STEP_M), waiting: 0 })
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

    /// setGround(ground): the host's ground (`{height(lon, lat)}`); the vehicles then stand on it and tilt with it. With no ground they
    /// stand at 0 m.
    #[wasm_bindgen(js_name = setGround)]
    pub fn set_ground(&mut self, ground: Ground) {
        self.ground = Some(ground);
        self.grid.clear();
    }

    /// setRoads(roads): the host's drawn roads (`{line(edgeId)}`). A vehicle placed on its lanes then takes its height from its roads'
    /// height profiles (docs/design/road_heights.md), never from the ground at its lon/lat.
    #[wasm_bindgen(js_name = setRoads)]
    pub fn set_roads(&mut self, roads: Roads) {
        self.roads = Some(roads);
        self.heights.clear();
    }

    /// clearGround(): forgets the ground's heights and the roads' profiles (the map's terrain changed: on, off, another exaggeration).
    #[wasm_bindgen(js_name = clearGround)]
    pub fn clear_ground(&mut self) {
        self.grid.clear();
        self.heights.clear();
    }

    /// [roads with a profile, the profiles' bytes]: the memory of the road heights (docs/design/road_heights.md, "Memory").
    #[wasm_bindgen(js_name = roadProfiles)]
    pub fn road_profiles(&self) -> Vec<f64> {
        vec![self.heights.len() as f64, self.heights.bytes() as f64]
    }

    /// setTunnelEdges(ids): the edges whose roads are below the ground (the page's roads with a level below 0); a vehicle on them gets
    /// the flag "tunnel" in `frame`, and the page draws it with the tunnels' look (fade, hide).
    #[wasm_bindgen(js_name = setTunnelEdges)]
    pub fn set_tunnel_edges(&mut self, ids: Vec<String>) {
        self.run.set_tunnel_edges(&ids.into_iter().collect());
    }

    /// The vehicles that the last frame left out because their ground is not known yet.
    pub fn waiting(&self) -> usize {
        self.waiting
    }

    /// Every vehicle on the network at clock time `t` (seconds of the run), STRIDE numbers each. A vehicle whose ground is not known
    /// yet is left out of this frame (and counted in `waiting`), never drawn at a wrong height.
    pub fn frame(&mut self, t: f64) -> Vec<f32> {
        let states = self.run.at(t);
        let [_, _, ox, oy, unit] = self.origin;
        let mut out = Vec::with_capacity(states.len() * STRIDE);
        self.waiting = 0;
        for s in states {
            let size = self.run.sizes[s.vtype as usize];
            let pose = match (&self.ground, &self.roads, &self.run.net) {
                // on its lanes: the height of its roads
                (Some(g), Some(r), Some(net)) if !s.roads.is_empty() => {
                    let mut ground = |lon: f64, lat: f64| Some(g.height(lon, lat)).filter(|h| h.is_finite());
                    let mut line_of = |e: &str| r.line(e).map(|v| v.chunks_exact(2).map(|c| [c[0], c[1]]).collect::<Vec<_>>());
                    self.heights.pose(net, &s.roads, size[0] as f64, &mut line_of, &mut ground)
                }
                // lon/lat placement: no road, the ground at its lon/lat
                (Some(g), _, _) if s.roads.is_empty() => {
                    let mut sample = |lon: f64, lat: f64| Some(g.height(lon, lat)).filter(|h| h.is_finite());
                    self.grid.pose([s.lon, s.lat], s.heading, size[0] as f64, size[1] as f64, &mut sample)
                }
                // on its lanes, and the host has not given its roads yet: it waits (never the ground at its lon/lat)
                (Some(_), _, _) => None,
                _ => Some(roadstyle_camera::Pose { z: 0.0, pitch: 0.0, roll: 0.0 }),
            };
            let Some(pose) = pose else {
                self.waiting += 1;
                continue;
            };
            let m = mercator(s.lon, s.lat);
            out.extend_from_slice(&[
                ((m[0] - ox) / unit) as f32,
                ((m[1] - oy) / unit) as f32,
                pose.z as f32,
                s.heading.to_radians() as f32,
                pose.pitch as f32,
                pose.roll as f32,
                size[0],
                size[1],
                size[2],
                self.type_class[s.vtype as usize] as f32,
                0.0,
                0.0,
                0.0,
                0.0,
                if s.tunnel { 1.0 } else { 0.0 },
                s.vehicle as f32,
            ]);
        }
        out
    }
}
