//! roadstyle-sim on a run made by SUMO itself: duckOSM's Monaco network (`to_sumo`, netconvert), random trips, 90 s,
//! `--fcd-output monaco_fcd.parquet --fcd-output.geo true` (SUMO 1.28.0). `monaco_net.xml` holds only the edges of the
//! 60 vehicles' routes from their first to their last sample (and one edge more), the internal lanes between them and
//! their connections. The edges of the routes, not only the sampled edges: a vehicle crosses a short edge between two
//! samples.

use roadstyle_sim::{read_fcd_parquet, read_net, Placement, Run, RunOptions, Samples};
use std::collections::HashMap;

const DATA: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/tests/data");

fn sizes() -> HashMap<String, [f32; 3]> {
    HashMap::from([("passenger".to_string(), [5.0, 1.8, 1.5])])
}

fn opts(placement: Placement) -> RunOptions {
    RunOptions { placement, teleport_m: 50.0, lane_change_s: 2.0, heading_lookahead_m: 2.0, class_sizes: sizes() }
}

fn monaco() -> Run {
    let s = read_fcd_parquet(std::fs::read(format!("{DATA}/monaco_fcd.parquet")).unwrap()).unwrap();
    let net = read_net(&std::fs::read_to_string(format!("{DATA}/monaco_net.xml")).unwrap()).unwrap();
    Run::new(s, Some(net), &[], opts(Placement::Lane)).unwrap()
}

fn median(mut v: Vec<f64>) -> f64 {
    v.sort_by(f64::total_cmp);
    v[v.len() / 2]
}

fn quantile(mut v: Vec<f64>, q: f64) -> f64 {
    v.sort_by(f64::total_cmp);
    v[((v.len() - 1) as f64 * q) as usize]
}

#[test]
fn reads_sumo_parquet_and_net() {
    let run = monaco();
    let r = run.report();
    assert_eq!((r.samples, r.vehicles, r.empty_rows), (2676, 60, 0));
    assert_eq!((r.t0, r.t1), (0.0, 89.0));
    assert_eq!(r.lanes_unknown, 0, "every lane of the samples is in net.xml");
    assert_eq!(r.teleports, 0);
    assert_eq!(r.path_gaps, 0, "every pair of samples has a chain of lanes");
    // ids stay text: SUMO's lane ids hold duckOSM edge ids past 2**53
    assert!(run.samples.lanes.iter().any(|l| l.len() > 17 && !l.starts_with(':')));
}

/// At each sample's time, the middle of the vehicle is half its length (2.5 m) behind SUMO's front bumper (x, y).
/// SUMO computes x, y from its own lane shapes; the run takes the lanes of net.xml through proj4rs. So this tests the
/// reprojection, the station on the lane and the shift from the front bumper together.
#[test]
fn middle_is_half_a_length_behind_the_front_bumper() {
    let run = monaco();
    let s = &run.samples;
    let mut err = Vec::new();
    for v in 0..s.ids.len() {
        for &r in run.rows(v) {
            let r = r as usize;
            let st = run.vehicle_at(v, s.t[r]).unwrap();
            let d = geo_dist([st.lon, st.lat], [s.x[r], s.y[r]]);
            err.push((d - 2.5).abs());
        }
    }
    let (m, q90) = (median(err.clone()), quantile(err, 0.9));
    assert!(m < 0.1, "median |distance - 2.5 m| = {m:.3} m");
    assert!(q90 < 0.6, "90 % |distance - 2.5 m| = {q90:.3} m (curves make the chord shorter)");
}

/// No jump at a sample: the place just before a sample's time (from the pair before it) and at that time (from the
/// pair after it) are the same point.
#[test]
fn no_jump_at_a_sample() {
    let run = monaco();
    let s = &run.samples;
    let mut jumps = Vec::new();
    for v in 0..s.ids.len() {
        let rows = run.rows(v);
        if rows.len() < 3 {
            continue;
        }
        for &r in &rows[1..rows.len() - 1] {
            let t = s.t[r as usize];
            let (Some(a), Some(b)) = (run.vehicle_at(v, t - 1e-6), run.vehicle_at(v, t)) else { continue };
            jumps.push(geo_dist([a.lon, a.lat], [b.lon, b.lat]));
        }
    }
    let (q99, max) = (quantile(jumps.clone(), 0.99), quantile(jumps, 1.0));
    assert!(q99 < 0.05, "99 % of the jumps at a sample: {q99:.3} m");
    assert!(max < 0.1, "largest jump at a sample: {max:.3} m (lane changes too)");
}

/// The heading follows the lane: at each sample it is near SUMO's own angle.
#[test]
fn heading_near_sumo_angle() {
    let run = monaco();
    let s = &run.samples;
    let mut d = Vec::new();
    for v in 0..s.ids.len() {
        for &r in run.rows(v) {
            let r = r as usize;
            if s.speed[r] < 1.0 {
                continue;
            }
            let st = run.vehicle_at(v, s.t[r]).unwrap();
            d.push(((st.heading - s.angle[r] as f64 + 540.0).rem_euclid(360.0) - 180.0).abs());
        }
    }
    assert!(median(d.clone()) < 3.0, "median heading difference {:.2}°", median(d.clone()));
    assert!(quantile(d, 0.9) < 15.0);
}

/// A jump longer than teleport_m: the vehicle is hidden between the two samples, and the jump is counted.
#[test]
fn teleport_is_hidden_and_counted() {
    let mut s = Samples::default();
    for (t, x) in [(0.0, 7.40), (1.0, 7.40001), (2.0, 7.41)] {
        s.t.push(t);
        s.id.push(0);
        s.x.push(x);
        s.y.push(43.73);
        s.angle.push(90.0);
        s.speed.push(1.0);
        s.pos.push(f32::NAN);
        s.lane.push(roadstyle_sim::NONE);
        s.pos_lat.push(f32::NAN);
        s.vtype.push(0);
    }
    s.ids = vec!["v".into()];
    s.types = vec!["DEFAULT_VEHTYPE".into()];
    let run = Run::new(s, None, &[], opts(Placement::LonLat)).unwrap();
    assert_eq!(run.report().teleports, 1);
    assert!(run.vehicle_at(0, 0.5).is_some());
    assert!(run.vehicle_at(0, 1.5).is_none(), "hidden during the teleport");
    assert!(run.vehicle_at(0, 2.0).is_some());
}

#[test]
fn a_class_without_size_is_an_error() {
    let s = read_fcd_parquet(std::fs::read(format!("{DATA}/monaco_fcd.parquet")).unwrap()).unwrap();
    let mut o = opts(Placement::LonLat);
    o.class_sizes.clear();
    let e = Run::new(s, None, &[], o).err().unwrap();
    assert!(e.to_string().contains("vehicles.sizes.passenger"), "{e}");
}

fn geo_dist(a: [f64; 2], b: [f64; 2]) -> f64 {
    let k = ((a[1] + b[1]) * 0.5).to_radians().cos();
    let m = 6371008.8 * std::f64::consts::PI / 180.0;
    (((b[0] - a[0]) * m * k).powi(2) + ((b[1] - a[1]) * m).powi(2)).sqrt()
}
