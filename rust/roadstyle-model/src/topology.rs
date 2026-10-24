//! The roads' topology, made one time for all the stages (audit R4): a node for each end of a road, the number of road ends at each
//! node, and one R-tree of the roads' boxes. A node is an end point rounded to 6 decimal places as Python's round does it (the correctly
//! rounded decimal; -0 is 0), so two ends are one node when their rounded points are the same.

use crate::table::RoadTable;
use rstar::primitives::{GeomWithData, Rectangle};
use rstar::{RTree, AABB};

/// Python's round(x, 6) as a float: the nearest double to the correctly rounded decimal (no tie can occur at 6 places), and no -0.
pub fn round6(x: f64) -> f64 {
    let v: f64 = format!("{x:.6}").parse().unwrap();
    if v == 0.0 { 0.0 } else { v }
}

pub struct Topology {
    /// the nodes of each road's first and last point (None: not a line of two points or more)
    pub ends: Vec<Option<[u32; 2]>>,
    /// each node's rounded point
    pub points: Vec<[f64; 2]>,
    /// the number of road ends at each node
    pub degree: Vec<u32>,
    /// the box of each road with a point or more, with its row
    tree: RTree<GeomWithData<Rectangle<[f64; 2]>, usize>>,
}

impl Topology {
    pub fn new(t: &RoadTable) -> Topology {
        let mut at: std::collections::HashMap<(u64, u64), u32> = std::collections::HashMap::new();
        let (mut points, mut degree) = (Vec::new(), Vec::new());
        let mut node = |p: &[f64; 2]| {
            let q = [round6(p[0]), round6(p[1])];
            let id = *at.entry((q[0].to_bits(), q[1].to_bits())).or_insert_with(|| {
                points.push(q);
                degree.push(0);
                (points.len() - 1) as u32
            });
            degree[id as usize] += 1;
            id
        };
        let ends = (0..t.len()).map(|i| t.line(i).filter(|c| c.len() >= 2).map(|c| [node(&c[0]), node(&c[c.len() - 1])])).collect();
        let tree = RTree::bulk_load((0..t.len()).filter_map(|i| t.line(i).filter(|c| !c.is_empty()).map(|c| {
            let [x0, y0, x1, y1] = crate::geom::line::bbox(c).expect("a point or more");
            GeomWithData::new(Rectangle::from_corners([x0, y0], [x1, y1]), i)
        })).collect());
        Topology { ends, points, degree, tree }
    }

    /// The rows of the roads whose box meets the box `lo`..`hi` (in no order).
    pub fn near(&self, lo: [f64; 2], hi: [f64; 2]) -> impl Iterator<Item = usize> + '_ {
        self.tree.locate_in_envelope_intersecting(&AABB::from_corners(lo, hi)).map(|g| g.data)
    }
}

#[cfg(test)]
mod tests {
    use super::round6;

    #[test]
    fn round6_is_pythons_round() {
        assert_eq!(round6(18.0000004999), 18.0);
        assert_eq!(round6(-0.0000004), 0.0);
        assert!(round6(-0.0000004).is_sign_positive());
        assert_eq!(round6(59.3141515), 59.314152);
    }
}
