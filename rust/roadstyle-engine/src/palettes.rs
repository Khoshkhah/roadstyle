//! A view's palette in one page (render_web._merge_palettes; docs/design/style_config.md, the view row `palette`). Stage 1 runs one
//! time; each other palette restyles the same prepared roads (`crate::restyle`: no read and no level solve) and only what differs goes
//! into the first output. A mark that differs becomes `<mark>@<palette>` on the roads (the road table and the pieces read it there), a
//! property of a JSON source or of an item gets its copy, and a paint or layout value becomes one value for each palette (the state
//! `rs_palette`). A palette holds only colours: other layers or other features are an error.

use crate::road::{Extra, Roads};
use crate::simple::SimpleSource;
use crate::sources::Sources;
use crate::Src;
use roadstyle_model::Cell;
use serde_json::{json, Value};

/// The palettes `looks` ({palette: the look of the same call with that palette}) of a page's views, merged into stage 1's output `s`
/// (the palette `base_name`). A warning of a palette that the first palette gave too is given one time (`s.warnings`).
pub fn add(s: &mut Sources, base_name: &str, looks: &[(String, crate::Look)]) -> Result<(), String> {
    let copies = looks.iter().map(|(n, l)| Ok((n.clone(), crate::restyle(s, l)?))).collect::<Result<Vec<_>, String>>()?;
    for w in copies.iter().flat_map(|(_, c)| &c.warnings) {
        if !s.warnings.contains(w) {
            s.warnings.push(w.clone());
        }
    }
    merge(s, base_name, &copies)
}

/// Merge the palettes `copies` (each made by `crate::restyle` from `base`'s roads) into `base` (the palette `base_name`).
pub fn merge(base: &mut Sources, base_name: &str, copies: &[(String, Sources)]) -> Result<(), String> {
    let ids: Vec<&Value> = base.layers.iter().map(|l| &l["id"]).collect();
    let mut differ: Vec<(String, Vec<String>)> = Vec::new();     // each property that differs, with the palettes it differs in
    let mut note = |keys: Vec<String>, n: &str| for k in keys {
        match differ.iter_mut().find(|(d, _)| *d == k) {
            Some((_, ps)) => ps.push(n.to_string()),
            None => differ.push((k, vec![n.to_string()])),
        }
    };
    for (n, cp) in copies {
        if cp.layers.len() != ids.len() || cp.layers.iter().zip(&ids).any(|(l, id)| &l["id"] != *id) {
            return Err(format!("palette {n:?} makes other layers than {base_name:?}: a palette holds only colours (docs/design/style_config.md)"));
        }
        let other = || format!("palette {n:?} makes other features than {base_name:?}: a palette holds only colours");
        if cp.roads.roads.len() != base.roads.roads.len() || cp.sources.len() != base.sources.len() {
            return Err(other());
        }
        let from = base.roads.roads.extra.len();
        note(roads(&mut base.roads.roads, &cp.roads.roads, n), n);
        for ((k, s), (ck, c)) in base.sources.iter_mut().zip(&cp.sources) {
            let keys = match (s, c) {
                _ if k != ck => return Err(other()),
                (Src::Roads(_), Src::Roads(_)) => Vec::new(),
                (Src::Simple(b), Src::Simple(c)) => {
                    if b.pieces.len() != c.pieces.len() || b.items.len() != c.items.len() {
                        return Err(other());
                    }
                    simple(b, c, &base.roads.roads, &cp.roads.roads, from, n)?
                }
                (Src::Json(b), Src::Json(c)) => {
                    let (Some(bf), Some(cf)) = (b["data"]["features"].as_array_mut(), c["data"]["features"].as_array()) else { continue };
                    if bf.len() != cf.len() {
                        return Err(other());
                    }
                    features(bf, cf, n)
                }
                _ => return Err(other()),
            };
            note(keys, n);
        }
        for (l, o) in base.layers.iter().zip(&cp.layers) {
            for k in ["filter", "minzoom", "maxzoom", "source", "source-layer", "type"] {
                if l.get(k) != o.get(k) {
                    return Err(format!("palette {n:?} changes {k} of layer {}: a palette holds only colours", l["id"]));
                }
            }
        }
    }
    for (i, l) in base.layers.iter_mut().enumerate() {
        for part in ["paint", "layout"] {
            let Some(p) = l.get_mut(part).and_then(Value::as_object_mut) else { continue };
            for (k, v) in p.iter_mut() {
                let vals: Vec<(&str, &Value)> = copies.iter().map(|(n, cp)| (n.as_str(), cp.layers[i][part].get(k).unwrap_or(&Value::Null))).collect();
                *v = by_palette(v, &vals);
            }
        }
    }
    for l in base.layers.iter_mut() {
        for part in ["paint", "layout", "filter"] {
            match l.get_mut(part) {
                Some(Value::Object(p)) if part != "filter" => p.values_mut().for_each(|v| pick(v, &differ)),
                Some(f) if part == "filter" && !f.is_null() => pick(f, &differ),
                _ => {}
            }
        }
    }
    base.set_reads();       // the layers read the copies now
    Ok(())
}

/// Two values of a road as Python's `!=` sees them (the same stages write both, so the same kinds).
fn same(a: Cell, b: Cell) -> bool {
    match (a, b) {
        (Cell::Null, Cell::Null) => true,
        (Cell::Bool(x), Cell::Bool(y)) => x == y,
        (Cell::Int(x), Cell::Int(y)) => x == y,
        (Cell::Float(x), Cell::Float(y)) => x == y,
        (Cell::Str(x), Cell::Str(y)) => x == y,
        (Cell::Json(x), Cell::Json(y)) => x == y,
        _ => a.to_value() == b.to_value(),
    }
}

/// The roads: the marks that differ, in the order they first differ, each as an `Extra` of every road that has it in the copy.
fn roads(base: &mut Roads, cp: &Roads, n: &str) -> Vec<String> {
    let mut keys: Vec<String> = Vec::new();
    for i in 0..cp.len() {
        let b = base.road(i);
        for (k, v) in cp.road(i).iter() {
            if !keys.iter().any(|x| x == k) && !b.get(k).is_some_and(|w| same(w, v)) {
                keys.push(k.to_string());
            }
        }
    }
    for k in &keys {
        let vals = (0..cp.len()).map(|i| cp.road(i).get(k).map(Cell::to_value)).collect();
        base.extra.push(Extra { name: format!("{k}@{n}"), key: k.clone(), vals });
    }
    keys
}

/// The simple source: a piece's values are its road's (the roads' `Extra` from `from` on holds this palette's; `SimpleSource::palette`
/// names those that the pieces differ in, in the order they first differ); an item's are its own, and it gets its copies here.
fn simple(b: &mut SimpleSource, c: &SimpleSource, roads: &Roads, cp: &Roads, from: usize, n: &str) -> Result<Vec<String>, String> {
    let mut keys: Vec<String> = Vec::new();
    let ex = from..roads.extra.len();
    for (_, p) in &b.pieces {
        if keys.len() == ex.len() {
            break;          // every mark that differs is found
        }
        let (r, e) = (roads.road(p.edge as usize), p.edge as usize);
        for (k, v) in cp.road(e).own() {
            if b.cols.keeps(p.part, k) && !keys.iter().any(|x| x == k) && !r.get(k).is_some_and(|w| same(w, v)) {
                let x = ex.clone().find(|&x| roads.extra[x].key == k).ok_or_else(|| format!("palette {n:?}: a piece differs in {k}, its road not"))?;
                keys.push(k.to_string());
                b.palette.push(x);
            }
        }
    }
    // the items follow the pieces in the source; a key that only they differ in is their own (`__rs_ic`), which no piece has
    for ((_, bi), (_, ci)) in b.items.iter().zip(&c.items) {
        for (k, v) in ci.props.iter() {
            if !keys.iter().any(|x| x == k) && bi.props.get(k) != Some(v) {
                if b.pieces.iter().any(|(_, p)| b.cols.keeps(p.part, k) && cp.road(p.edge as usize).get(k).is_some()) {
                    return Err(format!("palette {n:?} changes {k} of an item and not of its road: not in the Rust engine (use engine='python')"));
                }
                keys.push(k.to_string());
            }
        }
    }
    for ((_, bi), (_, ci)) in b.items.iter_mut().zip(&c.items) {
        for k in &keys {
            if let Some(v) = ci.props.get(k) {
                bi.props.insert(&format!("{k}@{n}"), v.clone());
            }
        }
    }
    Ok(keys)
}

/// A JSON source's features: the properties that differ, in the order they first differ, each copied into every feature that has it in
/// the copy.
fn features(b: &mut [Value], c: &[Value], n: &str) -> Vec<String> {
    let props = |f: &Value| f["properties"].as_object().cloned().unwrap_or_default();
    let mut keys: Vec<String> = Vec::new();
    for (bf, cf) in b.iter().zip(c) {
        for (k, v) in cf["properties"].as_object().into_iter().flatten() {
            if !keys.contains(k) && bf["properties"].get(k) != Some(v) {
                keys.push(k.clone());
            }
        }
    }
    if keys.is_empty() {
        return keys;
    }
    for (bf, cf) in b.iter_mut().zip(c) {
        let cp = props(cf);
        if let Some(p) = bf["properties"].as_object_mut() {
            for k in &keys {
                if let Some(v) = cp.get(k) {
                    p.insert(format!("{k}@{n}"), v.clone());
                }
            }
        }
    }
    keys
}

/// _zoom_curve: an interpolate or a step on the zoom (MapLibre takes the zoom only at the top of an expression).
fn zoom_curve(v: &Value) -> bool {
    v.as_array().is_some_and(|a| a.len() > 3 && ((a[0] == "interpolate" && a[2] == json!(["zoom"])) || (a[0] == "step" && a[1] == json!(["zoom"]))))
}

/// _by_palette: one value for each palette, `base` for the page's palette and `vals` for the others; a zoom curve keeps the zoom at the
/// top and the choice goes into each stop.
fn by_palette(base: &Value, vals: &[(&str, &Value)]) -> Value {
    if zoom_curve(base) {
        let b = base.as_array().unwrap();
        let first = if b[0] == "interpolate" { 4 } else { 3 };
        let alike = vals.iter().all(|(_, v)| zoom_curve(v) && v.as_array().is_some_and(|a| {
            a.len() == b.len() && a[..first - 1] == b[..first - 1] && a[first - 1..].iter().step_by(2).eq(b[first - 1..].iter().step_by(2))
        }));
        if alike {
            return Value::Array(b.iter().enumerate().map(|(i, x)| {
                if i < first - 1 || (i - (first - 1)) % 2 == 0 {
                    x.clone()
                } else {
                    let at: Vec<(&str, &Value)> = vals.iter().map(|(n, v)| (*n, &v[i])).collect();
                    by_palette(x, &at)
                }
            }).collect());
        }
    }
    if vals.iter().all(|(_, v)| *v == base) {
        return base.clone();
    }
    let mut m = vec![json!("match"), json!(["global-state", "rs_palette"])];
    for (n, v) in vals {
        m.extend([json!(n), (*v).clone()]);
    }
    m.push(base.clone());
    Value::Array(m)
}

/// The expressions that read a property that differs read the copy of the palette in force.
fn pick(e: &mut Value, differ: &[(String, Vec<String>)]) {
    let Value::Array(a) = e else { return };
    if a.len() == 2 && a[0] == "get" {
        if let Some((k, ps)) = a[1].as_str().and_then(|k| differ.iter().find(|(d, _)| d == k)) {
            let mut m = vec![json!("match"), json!(["global-state", "rs_palette"])];
            let mut seen: Vec<&String> = Vec::new();
            for p in ps {
                if !seen.contains(&p) {
                    seen.push(p);
                    m.extend([json!(p), json!(["get", format!("{k}@{p}")])]);
                }
            }
            m.push(e.clone());
            *e = Value::Array(m);
            return;
        }
    }
    a.iter_mut().for_each(|x| pick(x, differ));
}

impl SimpleSource {
    /// A piece's copy of its road's mark in another palette (the roads' `Extra`), where the copy's piece has the mark.
    pub(crate) fn palette_props(&self, p: &crate::simple::Piece, roads: &Roads) -> Vec<(String, Value)> {
        self.palette.iter().filter_map(|&x| {
            let e = &roads.extra[x];
            e.vals[p.edge as usize].as_ref().filter(|_| self.cols.keeps(p.part, &e.key)).map(|v| (e.name.clone(), v.clone()))
        }).collect()
    }
}
