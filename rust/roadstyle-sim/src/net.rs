//! SUMO's `net.xml` (the location, the lanes with their shapes, also the internal lanes of the junctions, and the
//! connections) and the `<vType>` elements of a route or additional file. SUMO's XML is plain: elements with attributes,
//! so a small tag scanner reads it (no XML library, as SimReady's `netconvert.rs`).

use crate::geo::Line;
use crate::Error;
use roadstyle_io::crs::{Crs, ToWgs84};
use std::collections::HashMap;

/// One tag: its name, its attributes, and whether it closes an element (`</edge>`).
struct Tag<'a> {
    name: &'a str,
    attrs: Vec<(&'a str, String)>,
    closing: bool,
}

impl Tag<'_> {
    fn get(&self, k: &str) -> Option<&str> {
        self.attrs.iter().find(|(a, _)| *a == k).map(|(_, v)| v.as_str())
    }
}

fn unescape(s: &str) -> String {
    if !s.contains('&') {
        return s.to_string();
    }
    s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", "\"").replace("&apos;", "'").replace("&amp;", "&")
}

/// The tags of an XML text, without comments, the declaration and text content.
fn tags(text: &str) -> Vec<Tag<'_>> {
    let mut out = Vec::new();
    let mut rest = text;
    while let Some(i) = rest.find('<') {
        rest = &rest[i..];
        if rest.starts_with("<!--") {
            rest = rest.find("-->").map_or("", |j| &rest[j + 3..]);
            continue;
        }
        let Some(end) = rest.find('>') else { break };
        let body = &rest[1..end];
        rest = &rest[end + 1..];
        if body.starts_with('?') || body.starts_with('!') {
            continue;
        }
        let closing = body.starts_with('/');
        let body = body.trim_start_matches('/').trim_end_matches('/');
        let name_end = body.find(|c: char| c.is_whitespace()).unwrap_or(body.len());
        let name = &body[..name_end];
        let mut attrs = Vec::new();
        let mut a = &body[name_end..];
        while let Some(eq) = a.find('=') {
            let key = a[..eq].trim();
            let after = a[eq + 1..].trim_start();
            let Some(q) = after.chars().next() else { break };
            let Some(close) = after[1..].find(q) else { break };
            attrs.push((key, unescape(&after[1..1 + close])));
            a = &after[close + 2..];
        }
        out.push(Tag { name, attrs, closing });
    }
    out
}

/// One lane of the network, its shape in lon/lat.
#[derive(Debug, Clone)]
pub struct Lane {
    pub id: String,
    /// the lane's edge; for an internal lane `:<junction>_<n>`
    pub edge: String,
    pub internal: bool,
    /// SUMO's lane index: 0 is the rightmost lane
    pub index: i32,
    /// SUMO's length of the lane (a vehicle's `pos` is measured on it), m
    pub length: f64,
    pub width: f64,
    pub line: Line,
}

/// The network of a run.
#[derive(Debug, Clone)]
pub struct Net {
    pub net_offset: [f64; 2],
    pub proj: String,
    pub lanes: Vec<Lane>,
    pub by_id: HashMap<String, u32>,
    /// the lanes a vehicle can drive onto from each lane (through a junction's internal lane, or straight on)
    pub next: Vec<Vec<u32>>,
}

fn pair(s: &str, what: &str) -> Result<[f64; 2], Error> {
    let mut it = s.split(',').map(|v| v.trim().parse::<f64>());
    match (it.next(), it.next()) {
        (Some(Ok(a)), Some(Ok(b))) => Ok([a, b]),
        _ => Err(Error::Format(format!("net.xml: {what} {s:?} is not a pair of numbers"))),
    }
}

/// A lane as the file gives it: id, edge, internal, index, length, width, shape (network coordinates).
type RawLane = (String, String, bool, i32, f64, f64, Vec<[f64; 2]>);

/// Reads the text of a `net.xml`. The lane shapes are turned into lon/lat with `<location>`: the network coordinates less
/// `netOffset`, then the inverse of `projParameter`. A network with no projection (`projParameter="!"`) is an error.
pub fn read_net(text: &str) -> Result<Net, Error> {
    let mut offset = None;
    let mut proj = None;
    let mut raw: Vec<RawLane> = Vec::new();
    let mut conns: Vec<(String, String)> = Vec::new();
    let mut edge: Option<(String, bool)> = None;
    for t in tags(text) {
        match (t.name, t.closing) {
            ("location", false) => {
                offset = Some(pair(t.get("netOffset").unwrap_or("0,0"), "netOffset")?);
                proj = t.get("projParameter").map(str::to_string);
            }
            ("edge", false) => {
                let id = t.get("id").ok_or_else(|| Error::Format("net.xml: an <edge> has no id".into()))?;
                edge = Some((id.to_string(), t.get("function") == Some("internal")));
            }
            ("edge", true) => edge = None,
            ("lane", false) => {
                let Some((e, internal)) = &edge else { continue };
                let id = t.get("id").ok_or_else(|| Error::Format(format!("net.xml: a <lane> of edge {e} has no id")))?;
                let num = |k: &str, d: f64| t.get(k).and_then(|v| v.parse::<f64>().ok()).unwrap_or(d);
                let shape = t.get("shape").ok_or_else(|| Error::Format(format!("net.xml: lane {id} has no shape")))?;
                let pts = shape.split_whitespace().map(|p| pair(p, "a shape point")).collect::<Result<Vec<_>, _>>()?;
                // SUMO's default lane width is 3.2 m (netconvert --default.lanewidth)
                raw.push((id.to_string(), e.clone(), *internal, num("index", 0.0) as i32, num("length", f64::NAN), num("width", 3.2), pts));
            }
            ("connection", false) => {
                let (Some(from), Some(to)) = (t.get("from"), t.get("to")) else { continue };
                let (fl, tl) = (t.get("fromLane").unwrap_or("0"), t.get("toLane").unwrap_or("0"));
                let a = format!("{from}_{fl}");
                match t.get("via") {
                    Some(via) => {
                        conns.push((a, via.to_string()));
                        conns.push((via.to_string(), format!("{to}_{tl}")));
                    }
                    None => conns.push((a, format!("{to}_{tl}"))),
                }
            }
            _ => {}
        }
    }
    let net_offset = offset.ok_or_else(|| Error::Format("net.xml has no <location>".into()))?;
    let proj = proj.ok_or_else(|| Error::Format("net.xml: <location> has no projParameter".into()))?;
    if proj == "!" || proj == "-" {
        return Err(Error::Crs(format!("net.xml: projParameter is {proj:?}, so the lanes have no lon/lat; build the network with a projection")));
    }
    let to_ll = ToWgs84::new(Some(Crs::Proj(proj.clone())), "net.xml").map_err(|e| Error::Crs(e.to_string()))?;
    let mut lanes = Vec::with_capacity(raw.len());
    let mut by_id = HashMap::with_capacity(raw.len());
    for (id, edge, internal, index, length, width, pts) in raw {
        let mut ll: Vec<[f64; 2]> = pts.iter().map(|p| [p[0] - net_offset[0], p[1] - net_offset[1]]).collect();
        to_ll.line(&mut ll).map_err(|e| Error::Crs(e.to_string()))?;
        let line = Line::new(ll);
        let length = if length.is_nan() { line.len() } else { length };
        by_id.insert(id.clone(), lanes.len() as u32);
        lanes.push(Lane { id, edge, internal, index, length, width, line });
    }
    let mut next = vec![Vec::new(); lanes.len()];
    for (a, b) in conns {
        if let (Some(&i), Some(&j)) = (by_id.get(&a), by_id.get(&b)) {
            if !next[i as usize].contains(&j) {
                next[i as usize].push(j);
            }
        }
    }
    Ok(Net { net_offset, proj, lanes, by_id, next })
}

/// One `<vType>`: the values the file gives. A missing size is None (the run takes the default of its class).
#[derive(Debug, Clone, PartialEq)]
pub struct VTypeRow {
    pub name: String,
    pub class: String,
    pub length: Option<f32>,
    pub width: Option<f32>,
    pub height: Option<f32>,
    pub colour: Option<String>,
    pub shape: Option<String>,
}

/// Reads the `<vType>` elements of a route or additional file. A vType with no `vClass` is `passenger` (SUMO's default).
pub fn read_vtypes(text: &str) -> Vec<VTypeRow> {
    tags(text)
        .into_iter()
        .filter(|t| t.name == "vType" && !t.closing)
        .filter_map(|t| {
            let f = |k: &str| t.get(k).and_then(|v| v.parse::<f32>().ok());
            Some(VTypeRow {
                name: t.get("id")?.to_string(),
                class: t.get("vClass").unwrap_or("passenger").to_string(),
                length: f("length"),
                width: f("width"),
                height: f("height"),
                colour: t.get("color").map(str::to_string),
                shape: t.get("guiShape").map(str::to_string),
            })
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn scanner_skips_comments_and_reads_escapes() {
        let t = tags(r#"<?xml version="1.0"?><!-- a <lane> in a comment --><a x="1 &amp; 2" y='q'/><b></b>"#);
        let names: Vec<_> = t.iter().map(|t| (t.name, t.closing)).collect();
        assert_eq!(names, vec![("a", false), ("b", false), ("b", true)]);
        assert_eq!(t[0].get("x"), Some("1 & 2"));
        assert_eq!(t[0].get("y"), Some("q"));
    }

    #[test]
    fn vtypes() {
        let v = read_vtypes(r#"<routes><vType id="bus1" vClass="bus" length="12.5"/><vType id="car"/></routes>"#);
        assert_eq!(v.len(), 2);
        assert_eq!((v[0].class.as_str(), v[0].length, v[0].width), ("bus", Some(12.5), None));
        assert_eq!(v[1].class, "passenger");
    }
}
