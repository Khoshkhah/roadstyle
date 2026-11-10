//! The heights of the roads (docs/design/road_heights.md): one height profile for each drawn road, made along the road's own line, and a
//! vehicle's height from the roads it is on, never from the ground at its lon/lat.
//!
//! - A road (a drawn edge, by its edge id) has heights at every `step_m` along its drawn line, linear between them. The profile is built
//!   the first time a vehicle needs it, from the host's line of the road and the host's ground along that line (today the map's terrain;
//!   later the road model's or duckOSM's heights, by the same function).
//! - A lane of SUMO's network belongs to the road of its edge: a distance along the lane is the same fraction of the road's drawn line.
//! - A junction's internal lane has no drawn road: its height goes linearly from the end of the road coming in to the start of the road
//!   going out.
//! - A vehicle has one to three (lane, distance, weight) entries (a lane change blends two lanes); its height is the weighted sum, its
//!   pitch the slope of its main road over its length, its roll 0 (a road is level across).

use crate::Pose;
use roadstyle_sim::geo::{dist_m, Line};
use roadstyle_sim::{Net, NONE};
use std::collections::HashMap;

/// The line of a drawn road (lon/lat points in the road's direction), by its edge id; None when the host does not have it yet.
pub type LineOf<'a> = dyn FnMut(&str) -> Option<Vec<[f64; 2]>> + 'a;
/// The ground at a lon/lat; None when the host does not know it yet.
pub type GroundAt<'a> = dyn FnMut(f64, f64) -> Option<f64> + 'a;

struct Profile {
    len: f64,
    z: Vec<f32>,
    /// the drawn line runs against the SUMO lanes of its edge (some drawn roads are stored in the other direction): read it backwards
    reversed: bool,
}

impl Profile {
    fn at(&self, step: f64, s: f64) -> f64 {
        let n = self.z.len();
        if n == 1 {
            return self.z[0] as f64;
        }
        let s = s.clamp(0.0, self.len);
        let x = s / step;
        let i = (x.floor() as usize).min(n - 2);
        // the last sample is at the line's end, which can be nearer than one step to the one before it
        let (s0, s1) = (i as f64 * step, if i + 1 == n - 1 { self.len } else { (i + 1) as f64 * step });
        let u = if s1 > s0 { ((s - s0) / (s1 - s0)).clamp(0.0, 1.0) } else { 0.0 };
        self.z[i] as f64 + (self.z[i + 1] - self.z[i]) as f64 * u
    }
}

/// The height profiles of the roads that vehicles use.
pub struct RoadHeights {
    step_m: f64,
    profiles: HashMap<String, Profile>,
    /// the lanes that lead into each lane (the reverse of the network's connections), made at the first junction
    prev: Option<Vec<Vec<u32>>>,
}

impl RoadHeights {
    pub fn new(step_m: f64) -> RoadHeights {
        RoadHeights { step_m, profiles: HashMap::new(), prev: None }
    }

    /// Forgets every profile: their source changed (the terrain on or off, another exaggeration, new data).
    pub fn clear(&mut self) {
        self.profiles.clear();
    }

    /// The number of roads with a profile.
    pub fn len(&self) -> usize {
        self.profiles.len()
    }

    pub fn is_empty(&self) -> bool {
        self.profiles.is_empty()
    }

    /// The bytes of the profiles' heights (4 for each height), and about 64 more for each road (its key and its record).
    pub fn bytes(&self) -> usize {
        self.profiles.iter().map(|(k, p)| p.z.len() * 4 + k.len() + 64).sum()
    }

    /// The height at fraction `frac` of road `edge` in the direction of its SUMO lane `lane`; None while its line or a height along it is
    /// not known.
    fn road_z(&mut self, edge: &str, lane: &Line, frac: f64, line_of: &mut LineOf, ground: &mut GroundAt) -> Option<f64> {
        if !self.profiles.contains_key(edge) {
            let line = Line::new(line_of(edge)?);
            // the road's direction against its lane's: the pairing of the two lines' ends that is nearer
            let (a, b) = (line.pts[0], *line.pts.last().unwrap());
            let (c, d) = (lane.pts[0], *lane.pts.last().unwrap());
            let reversed = dist_m(a, d) + dist_m(b, c) < dist_m(a, c) + dist_m(b, d);
            let len = line.len();
            let n = (len / self.step_m).ceil().max(1.0) as usize;
            let mut z = Vec::with_capacity(n + 1);
            for i in 0..=n {
                let (p, _) = line.at((i as f64 * self.step_m).min(len));
                // a height that the host does not know yet: no profile now, asked again next time
                z.push(ground(p[0], p[1]).filter(|h| h.is_finite())? as f32);
            }
            self.profiles.insert(edge.to_string(), Profile { len, z, reversed });
        }
        let p = &self.profiles[edge];
        let f = frac.clamp(0.0, 1.0);
        Some(p.at(self.step_m, if p.reversed { 1.0 - f } else { f } * p.len))
    }

    /// The normal lanes at the two ends of internal lane `lane`: the lane coming in and the lane going out (through other internal lanes of
    /// the same junction).
    fn ends(&mut self, net: &Net, lane: u32) -> (u32, u32) {
        let prev = self.prev.get_or_insert_with(|| {
            let mut p = vec![Vec::new(); net.lanes.len()];
            for (i, next) in net.next.iter().enumerate() {
                for &n in next {
                    p[n as usize].push(i as u32);
                }
            }
            p
        });
        let follow = |start: u32, step: &dyn Fn(u32) -> Option<u32>| {
            let mut l = start;
            for _ in 0..8 {
                match step(l) {
                    Some(n) if !net.lanes[n as usize].internal => return n,
                    Some(n) => l = n,
                    None => break,
                }
            }
            NONE
        };
        let incoming = follow(lane, &|l| prev[l as usize].first().copied());
        let outgoing = follow(lane, &|l| net.next[l as usize].first().copied());
        (incoming, outgoing)
    }

    /// The height `along` drawn metres on net lane `lane`; None while a height it needs is not known.
    pub fn lane_z(&mut self, net: &Net, lane: u32, along: f64, line_of: &mut LineOf, ground: &mut GroundAt) -> Option<f64> {
        let l = &net.lanes[lane as usize];
        let len = l.line.len();
        let frac = if len > 0.0 { along / len } else { 0.0 };
        if !l.internal {
            let (edge, line) = (l.edge.clone(), l.line.clone());
            return self.road_z(&edge, &line, frac, line_of, ground);
        }
        let (i, o) = self.ends(net, lane);
        if i == NONE || o == NONE {
            return None;
        }
        let (li, lo) = (&net.lanes[i as usize], &net.lanes[o as usize]);
        let (ie, il, oe, ol) = (li.edge.clone(), li.line.clone(), lo.edge.clone(), lo.line.clone());
        let z_in = self.road_z(&ie, &il, 1.0, line_of, ground)?;
        let z_out = self.road_z(&oe, &ol, 0.0, line_of, ground)?;
        Some(z_in + (z_out - z_in) * frac.clamp(0.0, 1.0))
    }

    /// The pose of a vehicle on `roads` ((lane, distance along, weight), the first its main road), `length` m long.
    pub fn pose(&mut self, net: &Net, roads: &[(u32, f64, f64)], length: f64, line_of: &mut LineOf, ground: &mut GroundAt)
                -> Option<Pose> {
        let (&(main, along, _), _) = roads.split_first()?;
        let mut z = 0.0;
        for &(lane, at, w) in roads {
            z += w * self.lane_z(net, lane, at, line_of, ground)?;
        }
        // the slope of the main road over the vehicle's length, within the lane
        let lane_len = net.lanes[main as usize].line.len();
        let (a, b) = ((along - length * 0.5).max(0.0), (along + length * 0.5).min(lane_len));
        let pitch = if b - a > 0.5 {
            let (za, zb) = (self.lane_z(net, main, a, line_of, ground)?, self.lane_z(net, main, b, line_of, ground)?);
            (zb - za).atan2(b - a)
        } else {
            0.0
        };
        Some(Pose { z, pitch, roll: 0.0 })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use roadstyle_sim::geo::{delta_m, offset};
    use roadstyle_sim::read_net;

    // a small network in UTM zone 32: edge A (west to east, 100 m), a junction's internal lane, edge B (east, 100 m)
    const NET: &str = r#"<net><location netOffset="0.00,0.00" projParameter="+proj=utm +zone=32 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"/>
<edge id="A"><lane id="A_0" index="0" length="100" width="3.2" shape="371000,4842000 371100,4842000"/></edge>
<edge id=":J_0" function="internal"><lane id=":J_0_0" index="0" length="10" width="3.2" shape="371100,4842000 371110,4842000"/></edge>
<edge id="B"><lane id="B_0" index="0" length="100" width="3.2" shape="371110,4842000 371210,4842000"/></edge>
<connection from="A" to="B" fromLane="0" toLane="0" via=":J_0_0"/>
</net>"#;

    fn net() -> Net {
        read_net(NET).unwrap()
    }

    fn origin(n: &Net) -> [f64; 2] {
        n.lanes[0].line.pts[0]
    }

    #[test]
    fn a_road_has_the_heights_along_its_own_line() {
        let n = net();
        let o = origin(&n);
        // the ground climbs 0.10 per metre east
        let mut ground = |lon: f64, lat: f64| Some(5.0 + 0.10 * delta_m(o, [lon, lat])[0]);
        let lines: HashMap<String, Vec<[f64; 2]>> = n.lanes.iter().map(|l| (l.edge.clone(), l.line.pts.clone())).collect();
        let mut line_of = |e: &str| lines.get(e).cloned();
        let mut r = RoadHeights::new(5.0);
        let a = n.by_id["A_0"];
        for along in [0.0, 12.5, 50.0, 99.0] {
            let z = r.lane_z(&n, a, along, &mut line_of, &mut ground).unwrap();
            assert!((z - (5.0 + 0.10 * along)).abs() < 0.02, "{along}: {z}");
        }
        assert_eq!(r.len(), 1);
        assert!(r.bytes() < 1000, "21 heights of road A: {}", r.bytes());
    }

    #[test]
    fn a_junction_goes_from_the_road_in_to_the_road_out() {
        let n = net();
        // road A ends at 20 m, road B starts at 30 m: a step that only the junction joins
        let mut ground = |_: f64, _: f64| Some(0.0);
        let lines: HashMap<String, Vec<[f64; 2]>> = n.lanes.iter().map(|l| (l.edge.clone(), l.line.pts.clone())).collect();
        let mut r = RoadHeights::new(5.0);
        r.profiles.insert("A".into(), Profile { len: 100.0, z: vec![20.0, 20.0], reversed: false });
        r.profiles.insert("B".into(), Profile { len: 100.0, z: vec![30.0, 30.0], reversed: false });
        let mut line_of = |e: &str| lines.get(e).cloned();
        let j = n.by_id[":J_0_0"];
        let len = n.lanes[j as usize].line.len();
        let z0 = r.lane_z(&n, j, 0.0, &mut line_of, &mut ground).unwrap();
        let zm = r.lane_z(&n, j, len * 0.5, &mut line_of, &mut ground).unwrap();
        let z1 = r.lane_z(&n, j, len, &mut line_of, &mut ground).unwrap();
        assert!((z0 - 20.0).abs() < 1e-6 && (zm - 25.0).abs() < 1e-6 && (z1 - 30.0).abs() < 1e-6, "{z0} {zm} {z1}");
    }

    #[test]
    fn a_lane_change_blends_the_heights_with_the_place_weights() {
        let n = net();
        let o = origin(&n);
        let mut ground = |lon: f64, lat: f64| Some(5.0 + 0.10 * delta_m(o, [lon, lat])[0]);
        let lines: HashMap<String, Vec<[f64; 2]>> = n.lanes.iter().map(|l| (l.edge.clone(), l.line.pts.clone())).collect();
        let mut line_of = |e: &str| lines.get(e).cloned();
        let mut r = RoadHeights::new(5.0);
        let (a, b) = (n.by_id["A_0"], n.by_id["B_0"]);
        // 30 % on A at 40 m (9 m), 70 % on B at 20 m (5 + 0.1 * 130 = 18 m)
        let p = r.pose(&n, &[(a, 40.0, 0.3), (b, 20.0, 0.7)], 5.0, &mut line_of, &mut ground).unwrap();
        assert!((p.z - (0.3 * 9.0 + 0.7 * 18.0)).abs() < 0.05, "{p:?}");
        assert!((p.pitch - 0.10f64.atan()).abs() < 1e-3 && p.roll == 0.0, "{p:?}");
        let _ = offset(o, 0.0, 0.0);
    }

    #[test]
    fn a_road_drawn_the_other_way_is_read_backwards() {
        let n = net();
        let o = origin(&n);
        let mut ground = |lon: f64, lat: f64| Some(5.0 + 0.10 * delta_m(o, [lon, lat])[0]);
        // road A's drawn line runs east to west, against its lane
        let mut lines: HashMap<String, Vec<[f64; 2]>> = n.lanes.iter().map(|l| (l.edge.clone(), l.line.pts.clone())).collect();
        lines.get_mut("A").unwrap().reverse();
        let mut line_of = |e: &str| lines.get(e).cloned();
        let mut r = RoadHeights::new(5.0);
        let a = n.by_id["A_0"];
        let z = r.lane_z(&n, a, 20.0, &mut line_of, &mut ground).unwrap();
        assert!((z - 7.0).abs() < 0.02, "20 m along the lane is 7 m high, whatever the drawn line's direction: {z}");
    }

    #[test]
    fn a_road_with_an_unknown_height_waits() {
        let n = net();
        let lines: HashMap<String, Vec<[f64; 2]>> = n.lanes.iter().map(|l| (l.edge.clone(), l.line.pts.clone())).collect();
        let mut line_of = |e: &str| lines.get(e).cloned();
        let mut r = RoadHeights::new(5.0);
        let a = n.by_id["A_0"];
        assert!(r.lane_z(&n, a, 10.0, &mut line_of, &mut |_, _| None).is_none());
        assert!(r.is_empty(), "no profile is kept while a height is not known");
        let mut no_line = |_: &str| None;
        assert!(r.lane_z(&n, a, 10.0, &mut no_line, &mut |_, _| Some(1.0)).is_none(), "no line: no height");
    }
}
