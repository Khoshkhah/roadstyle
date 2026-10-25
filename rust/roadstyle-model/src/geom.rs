//! Geometry from WKB for the base map (full port step 3): GeoJSON, and the area and the centroid as shapely (GEOS) computes them. DuckDB's
//! core has no ST_AsGeoJSON, ST_Area or ST_Centroid, so the worker reads WKB (ST_AsWKB) and this file does the rest, as Pyodide's shapely does.

use serde_json::{json, Value};

type Pt = [f64; 2];
type Ring = Vec<Pt>;

pub enum Geom {
    Point(Pt),
    LineString(Vec<Pt>),
    Polygon(Vec<Ring>),
    MultiPoint(Vec<Pt>),
    MultiLineString(Vec<Vec<Pt>>),
    MultiPolygon(Vec<Vec<Ring>>),
}

/// A WKB geometry (a point, a line, a polygon or their Multi forms; a Z or an M is left out: crate::wkb, the one reader).
pub fn from_wkb(b: &[u8]) -> Option<Geom> {
    let (kind, parts) = crate::wkb::read(b)?;
    Geom::from_parts(kind, parts)
}

fn coords(p: &[Pt]) -> Value {
    json!(p)
}

impl Geom {
    /// A geometry from its type and parts (crate::wkb's form); None for a part with no ring or no point where the type needs one.
    pub fn from_parts(kind: crate::feature_table::GeomType, mut parts: crate::wkb::Parts) -> Option<Geom> {
        use crate::feature_table::GeomType as T;
        let first = |p: &mut Vec<Vec<Pt>>| (!p.is_empty()).then(|| p.swap_remove(0));     // the one ring of a point's or a line's part
        Some(match kind {
            T::Point => Geom::Point(*first(parts.first_mut()?)?.first()?),
            T::LineString => Geom::LineString(first(parts.first_mut()?)?),
            T::Polygon => Geom::Polygon((!parts.is_empty()).then(|| parts.swap_remove(0))?),
            T::MultiPoint => Geom::MultiPoint(parts.iter_mut().map(|p| first(p).and_then(|r| r.first().copied())).collect::<Option<_>>()?),
            T::MultiLineString => Geom::MultiLineString(parts.iter_mut().map(first).collect::<Option<_>>()?),
            T::MultiPolygon => Geom::MultiPolygon(parts),
        })
    }

    /// The GeoJSON geometry (shapely's mapping, DuckDB's ST_AsGeoJSON): the rings as stored.
    pub fn geojson(&self) -> Value {
        match self {
            Geom::Point(p) => json!({"type": "Point", "coordinates": p}),
            Geom::LineString(l) => json!({"type": "LineString", "coordinates": coords(l)}),
            Geom::Polygon(r) => json!({"type": "Polygon", "coordinates": r}),
            Geom::MultiPoint(p) => json!({"type": "MultiPoint", "coordinates": p}),
            Geom::MultiLineString(l) => json!({"type": "MultiLineString", "coordinates": l}),
            Geom::MultiPolygon(p) => json!({"type": "MultiPolygon", "coordinates": p}),
        }
    }

    /// GEOS's area: a polygon's shell less its holes (Area::ofRing, the shoelace from the first point); a line or a point has none.
    pub fn area(&self) -> f64 {
        fn ring(r: &Ring) -> f64 {
            if r.len() < 3 {
                return 0.0;
            }
            let x0 = r[0][0];
            let mut sum = 0.0;
            for i in 1..r.len() - 1 {
                let x = r[i][0] - x0;
                sum += x * (r[i - 1][1] - r[i + 1][1]);
            }
            sum / 2.0
        }
        fn polygon(p: &[Ring]) -> f64 {
            p.first().map_or(0.0, |s| ring(s).abs()) - p.iter().skip(1).map(|h| ring(h).abs()).sum::<f64>()
        }
        match self {
            Geom::Polygon(p) => polygon(p),
            Geom::MultiPolygon(ps) => ps.iter().map(|p| polygon(p)).sum(),
            _ => 0.0,
        }
    }

    /// GEOS's Centroid: the area-weighted centre of the triangles from the area base point; else the length-weighted centre of the lines;
    /// else the mean of the points.
    pub fn centroid(&self) -> Pt {
        let mut c = Centroid::default();
        c.add(self);
        c.get()
    }
}

#[derive(Default)]
struct Centroid {
    base: Option<Pt>,
    cg3: Pt,
    area2: f64,
    line: Pt,
    length: f64,
    pts: Pt,
    n: f64,
}

fn area2(p1: Pt, p2: Pt, p3: Pt) -> f64 {
    (p2[0] - p1[0]) * (p3[1] - p1[1]) - (p3[0] - p1[0]) * (p2[1] - p1[1])
}

/// Orientation::isCCW by the signed area (the rings of a base map are not degenerate).
fn ccw(r: &Ring) -> bool {
    let mut s = 0.0;
    for w in r.windows(2) {
        s += (w[1][0] - w[0][0]) * (w[1][1] + w[0][1]);
    }
    s < 0.0
}

impl Centroid {
    fn add(&mut self, g: &Geom) {
        match g {
            Geom::Point(p) => self.point(*p),
            Geom::MultiPoint(ps) => ps.iter().for_each(|p| self.point(*p)),
            Geom::LineString(l) => self.segments(l),
            Geom::MultiLineString(ls) => ls.iter().for_each(|l| self.segments(l)),
            Geom::Polygon(p) => self.polygon(p),
            Geom::MultiPolygon(ps) => ps.iter().for_each(|p| self.polygon(p)),
        }
    }
    fn point(&mut self, p: Pt) {
        self.n += 1.0;
        self.pts[0] += p[0];
        self.pts[1] += p[1];
    }
    fn segments(&mut self, l: &[Pt]) {
        let mut len = 0.0;
        for w in l.windows(2) {
            let d = ((w[1][0] - w[0][0]).powi(2) + (w[1][1] - w[0][1]).powi(2)).sqrt();
            if d == 0.0 {
                continue;
            }
            len += d;
            self.line[0] += d * ((w[0][0] + w[1][0]) / 2.0); // GEOS: segmentLen * midpoint
            self.line[1] += d * ((w[0][1] + w[1][1]) / 2.0);
        }
        self.length += len;
        if len == 0.0 && !l.is_empty() {
            self.point(l[0]);
        }
    }
    fn triangle(&mut self, p0: Pt, p1: Pt, p2: Pt, positive: bool) {
        let sign = if positive { 1.0 } else { -1.0 };
        let (cx, cy) = (p0[0] + p1[0] + p2[0], p0[1] + p1[1] + p2[1]);
        let a2 = area2(p0, p1, p2);
        self.cg3[0] += sign * a2 * cx;
        self.cg3[1] += sign * a2 * cy;
        self.area2 += sign * a2;
    }
    fn polygon(&mut self, p: &[Ring]) {
        let Some(shell) = p.first() else { return };
        if !shell.is_empty() && self.base.is_none() {
            self.base = Some(shell[0]);
        }
        let base = self.base.unwrap_or([0.0, 0.0]);
        let pos = !ccw(shell);
        for w in shell.windows(2) {
            self.triangle(base, w[0], w[1], pos);
        }
        self.segments(shell);
        for h in &p[1..] {
            let pos = ccw(h);
            for w in h.windows(2) {
                self.triangle(base, w[0], w[1], pos);
            }
            self.segments(h);
        }
    }
    fn get(&self) -> Pt {
        if self.area2.abs() > 0.0 {
            [self.cg3[0] / 3.0 / self.area2, self.cg3[1] / 3.0 / self.area2]
        } else if self.length > 0.0 {
            [self.line[0] / self.length, self.line[1] / self.length]
        } else if self.n > 0.0 {
            [self.pts[0] / self.n, self.pts[1] / self.n]
        } else {
            [f64::NAN, f64::NAN]
        }
    }
}

/// A road line's place for the road table (the page's sidecar, tiles.sidecar): its middle by length, the way it runs there and its box.
pub mod line {
    type P = [f64; 2];

    /// GEOS's length of a line: the sum of each segment's sqrt(dx² + dy²), in the line's order.
    pub fn length(c: &[P]) -> f64 {
        c.windows(2).map(|w| ((w[1][0] - w[0][0]) * (w[1][0] - w[0][0]) + (w[1][1] - w[0][1]) * (w[1][1] - w[0][1])).sqrt()).sum()
    }

    /// The point at the distance `d` along the line and its segment, as GEOS's LengthIndexedLine finds it (shapely's interpolate).
    pub fn along(c: &[P], d: f64) -> Option<(P, usize)> {
        let first = *c.first()?;
        if d <= 0.0 || c.len() < 2 {
            return Some((first, 0));
        }
        let mut total = 0.0;
        for (i, w) in c.windows(2).enumerate() {
            let seg = ((w[1][0] - w[0][0]) * (w[1][0] - w[0][0]) + (w[1][1] - w[0][1]) * (w[1][1] - w[0][1])).sqrt();
            if total + seg > d {
                let f = (d - total) / seg;
                let at = |k: usize| if f <= 0.0 { w[0][k] } else if f >= 1.0 { w[1][k] } else { (w[1][k] - w[0][k]) * f + w[0][k] };
                return Some(([at(0), at(1)], i));
            }
            total += seg;
        }
        Some((c[c.len() - 1], c.len() - 2))
    }

    /// The middle of the line by its length (shapely's interpolate(0.5, normalized=True)); a line of one point is that point.
    pub fn mid(c: &[P]) -> Option<P> {
        if c.len() < 2 {
            return c.first().copied();
        }
        along(c, 0.5 * length(c)).map(|m| m.0)
    }

    /// [min lon, min lat, max lon, max lat].
    pub fn bbox(c: &[P]) -> Option<[f64; 4]> {
        c.first()?;
        let f = |k: usize, max: bool| c.iter().map(|p| p[k]).fold(if max { f64::NEG_INFINITY } else { f64::INFINITY }, |a, b| if max { a.max(b) } else { a.min(b) });
        Some([f(0, false), f(1, false), f(0, true), f(1, true)])
    }
}
