//! The chains of a group: its roads joined through nodes of degree 2.

use super::{Node, Rep};
use crate::simple::Pt;
use std::collections::HashMap;

/// A chain's line and the group positions of its roads.
pub(super) type Chain = (Vec<Pt>, Vec<usize>);

/// The chains through degree-2 nodes; a one-way chain only through directed continuations.
pub(super) fn chains(edges: &[&Rep], oneway: bool) -> Vec<Chain> {
    let mut used = vec![false; edges.len()];
    let mut at: HashMap<Node, Vec<usize>> = HashMap::new();
    for (i, e) in edges.iter().enumerate() {
        at.entry(e.a.0).or_default().push(i);
        at.entry(e.z.0).or_default().push(i);
    }
    let mut out = Vec::new();
    for start in 0..edges.len() {
        if used[start] {
            continue;
        }
        used[start] = true;
        let mut members = vec![start];
        let mut chain = edges[start].c.clone();
        for prepend in [false, true] {
            let mut nd = if prepend { edges[start].a.0 } else { edges[start].z.0 };
            while let Some((j, seg, nxt)) = next_road(edges, &at, &used, nd, prepend, oneway) {
                used[j] = true;
                members.push(j);
                if prepend {
                    chain.splice(0..0, seg[..seg.len() - 1].iter().copied());
                } else {
                    chain.extend_from_slice(&seg[1..]);
                }
                nd = nxt;
            }
        }
        out.push((chain, members));
    }
    out
}

/// The one unused road that continues at the node `nd` (a node of degree 2), as its line from `nd` away, and the node at its other end.
/// With `prepend`, the chain grows at its start: the road's line ends at `nd`.
fn next_road(edges: &[&Rep], at: &HashMap<Node, Vec<usize>>, used: &[bool], nd: Node, prepend: bool, oneway: bool) -> Option<(usize, Vec<Pt>, Node)> {
    let here = &at[&nd];
    let cand: Vec<usize> = here.iter().copied().filter(|&j| !used[j]).collect();
    if here.len() != 2 || cand.len() != 1 {
        return None;
    }
    let j = cand[0];
    let e = edges[j];
    let (near, far) = if prepend { (e.z.0, e.a.0) } else { (e.a.0, e.z.0) };
    if near == nd {
        Some((j, e.c.clone(), far))
    } else if !oneway {
        Some((j, e.c.iter().rev().copied().collect(), near))
    } else {
        None
    }
}
