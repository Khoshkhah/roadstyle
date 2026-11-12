//! The vertical profile of a chain with the curve `design` (docs/design/bridge_height_design.md): straight grades between control points (the PVIs of road design), and at each interior
//! point a parabolic vertical curve of the length that the profile gives. The chain's two end nodes are the first and the last point and have no curve.
//!
//! This file has no rules about the design speed or the grade of a road class, except `curve_length`, which the filler (`bridge_fill`) calls to write the length of a curve into the
//! profile. The maker only evaluates: the height at a distance along the chain (`z_at`) and the places where the shape changes (`breaks`). The page has the same evaluation in
//! JavaScript (`bridgemesh.js`, `_bmZ`), and a browser test requires that the two agree.

/// A control point of a chain: the distance along the chain (metres), the height (metres), and the length of the vertical curve around it (0: none).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Pvi {
    pub s: f64,
    pub z: f64,
    pub curve_m: f64,
}

/// The stopping sight distance in metres at a design speed in km/h: 2.5 s of reaction and a braking of 3.4 m/s² (the AASHTO values).
pub fn stopping_sight_m(v_kmh: f64) -> f64 {
    0.278 * v_kmh * 2.5 + v_kmh * v_kmh / (254.0 * 3.4 / 9.81)
}

/// K of a crest curve (the grade decreases): metres of curve for each percent of change of grade.
pub fn k_crest(v_kmh: f64) -> f64 {
    stopping_sight_m(v_kmh).powi(2) / 658.0
}

/// K of a sag curve (the grade increases).
pub fn k_sag(v_kmh: f64) -> f64 {
    let s = stopping_sight_m(v_kmh);
    s * s / (120.0 + 3.5 * s)
}

/// The length of the vertical curve that joins the grade `g1` to the grade `g2` (fractions, 0.05 is 5 %) at the design speed `v_kmh`: `K × A`, and at least `0.6 × V`. 0 where the grade does not change.
pub fn curve_length(v_kmh: f64, g1: f64, g2: f64) -> f64 {
    let a = (g2 - g1).abs() * 100.0;
    if a < 1e-9 {
        return 0.0;
    }
    let k = if g2 < g1 { k_crest(v_kmh) } else { k_sag(v_kmh) };
    (k * a).max(0.6 * v_kmh)
}

fn grade(a: &Pvi, b: &Pvi) -> f64 {
    (b.z - a.z) / (b.s - a.s)
}

/// The height at the distance `d` along the chain. The points are in order of `s`, at least two, the first at 0 and the last at the length of the chain; the curves do not overlap (`check`).
pub fn z_at(p: &[Pvi], d: f64) -> f64 {
    let n = p.len();
    for i in 1..n - 1 {
        let l = p[i].curve_m;
        let start = p[i].s - l / 2.0;
        if l > 0.0 && d > start && d < p[i].s + l / 2.0 {
            let (g1, g2) = (grade(&p[i - 1], &p[i]), grade(&p[i], &p[i + 1]));
            let u = d - start;
            return p[i].z - g1 * l / 2.0 + g1 * u + (g2 - g1) / (2.0 * l) * u * u;
        }
    }
    let i = (0..n - 1).rev().find(|&i| p[i].s <= d).unwrap_or(0);
    p[i].z + grade(&p[i], &p[i + 1]) * (d - p[i].s)
}

/// The distances along the chain where the shape changes: each point, and the start and the end of each curve. A piece of the deck between two of them is a straight grade or a part of one curve.
/// The ends of the curves are the places where a piece must be cut so that it is straight, and a curve itself is cut in steps by the caller.
pub fn breaks(p: &[Pvi]) -> Vec<f64> {
    p.iter().flat_map(|q| [q.s - q.curve_m / 2.0, q.s, q.s + q.curve_m / 2.0]).collect()
}

/// The curves as `(start, end)` distances: a piece inside one is cut in steps.
pub fn curves(p: &[Pvi]) -> Vec<(f64, f64)> {
    p.iter().filter(|q| q.curve_m > 0.0).map(|q| (q.s - q.curve_m / 2.0, q.s + q.curve_m / 2.0)).collect()
}

/// The checks of a list of points: in order of `s` with the first at 0 and the last at `length` (the chain's ends), heights of 0 or more, curves that do not leave the chain or overlap.
/// The message names the first thing that is wrong.
pub fn check(p: &[Pvi], length: f64) -> Result<(), String> {
    if p.len() < 2 || p[0].s != 0.0 || (p[p.len() - 1].s - length).abs() > 1e-6 {
        return Err("the points must start at 0 and end at the length of the chain".into());
    }
    if let Some(w) = p.windows(2).find(|w| !(w[1].s > w[0].s)) {
        return Err(format!("the points are not in order of s: {} m comes after {} m", w[1].s, w[0].s));
    }
    if let Some(q) = p.iter().find(|q| !(q.z.is_finite() && q.z >= 0.0)) {
        return Err(format!("the point at {} m has z_m {}; a height is a number of metres, 0 or more", q.s, q.z));
    }
    for (i, q) in p.iter().enumerate() {
        if !(q.curve_m.is_finite() && q.curve_m >= 0.0) || (q.curve_m > 0.0 && (i == 0 || i == p.len() - 1)) {
            return Err(format!("the point at {} m has curve_m {}; a curve is a length of 0 or more, and the two ends of the chain have none", q.s, q.curve_m));
        }
    }
    // two curves that share a gap must fit in it together; a curve next to an end must fit in half the gap on its side
    for w in p.windows(2) {
        let (a, b) = (w[0].curve_m / 2.0, w[1].curve_m / 2.0);
        if a + b > w[1].s - w[0].s + 1e-6 {
            return Err(format!("the curves at {} m and {} m overlap: {} m of curve in a gap of {} m", w[0].s, w[1].s, a + b, w[1].s - w[0].s));
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn p(s: f64, z: f64, c: f64) -> Pvi {
        Pvi { s, z, curve_m: c }
    }

    /// The values of the TxDOT table (the note checked them): K at 70 mph and 85 mph. 247 ft per percent at 70 mph is 75.3 m, 473 ft at 85 mph is 144.2 m, 260 ft is 79.2 m.
    #[test]
    fn k_follows_the_txdot_table() {
        let mph = 1.609344;
        assert!((k_crest(70.0 * mph) * 3.28084 - 247.0).abs() < 8.0, "{}", k_crest(70.0 * mph) * 3.28084);
        assert!((k_crest(85.0 * mph) * 3.28084 - 473.0).abs() < 15.0);
        assert!((k_sag(85.0 * mph) * 3.28084 - 260.0).abs() < 8.0);
        // the table of the note, 50 km/h: stopping sight distance 63 m, K 6.1 and 11.7, least curve 30 m
        assert!((stopping_sight_m(50.0) - 63.0).abs() < 1.0);
        assert!((k_crest(50.0) - 6.1).abs() < 0.2 && (k_sag(50.0) - 11.7).abs() < 0.2);
        assert!((curve_length(50.0, 0.05, 0.0) - 30.5).abs() < 1.0, "a 5 % crest at 50 km/h: K × A = 30 m");
        assert!((curve_length(50.0, 0.0, 0.05) - 58.5).abs() < 1.0, "a 5 % sag at 50 km/h: 58 m");
        assert_eq!(curve_length(50.0, 0.03, 0.03), 0.0);
        assert_eq!(curve_length(50.0, 0.0, 0.001), 30.0, "the least length is 0.6 V");
    }

    #[test]
    fn a_straight_grade_and_a_curve_meet_at_the_curve_ends_without_a_step() {
        let pts = [p(0.0, 0.0, 0.0), p(100.0, 10.0, 40.0), p(300.0, 10.0, 0.0)];
        // the straight grade before the curve (0.1), the flat after it
        assert!((z_at(&pts, 50.0) - 5.0).abs() < 1e-9 && (z_at(&pts, 200.0) - 10.0).abs() < 1e-9);
        let (a, b) = (z_at(&pts, 80.0 - 1e-9), z_at(&pts, 80.0 + 1e-9));
        assert!((a - b).abs() < 1e-6, "no step at the start of the curve");
        let (a, b) = (z_at(&pts, 120.0 - 1e-9), z_at(&pts, 120.0 + 1e-9));
        assert!((a - b).abs() < 1e-6, "no step at the end of the curve");
        // a crest is below its point by A L / 800 (A in percent, L in metres): 10 × 40 / 800 = 0.5
        assert!((z_at(&pts, 100.0) - 9.5).abs() < 1e-9);
        assert!((z_at(&pts, 0.0), z_at(&pts, 300.0)) == (0.0, 10.0));
    }

    #[test]
    fn the_checks_say_what_is_wrong() {
        let ok = [p(0.0, 0.0, 0.0), p(100.0, 5.0, 30.0), p(200.0, 0.0, 0.0)];
        assert!(check(&ok, 200.0).is_ok());
        assert!(check(&ok, 250.0).unwrap_err().contains("end at the length"));
        assert!(check(&[p(0.0, 0.0, 0.0), p(120.0, 5.0, 0.0), p(100.0, 5.0, 0.0), p(200.0, 0.0, 0.0)], 200.0).unwrap_err().contains("not in order"));
        assert!(check(&[p(0.0, 0.0, 0.0), p(100.0, 5.0, 250.0), p(200.0, 0.0, 0.0)], 200.0).unwrap_err().contains("overlap"));
        assert!(check(&[p(0.0, 0.0, 10.0), p(200.0, 0.0, 0.0)], 200.0).unwrap_err().contains("two ends"));
    }
}
