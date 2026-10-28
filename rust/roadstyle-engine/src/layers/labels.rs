use super::*;

/// _label_base_px: the size every name had (labels.base_size: px at two zooms).
pub(super) fn label_base_px(l: &LabelLook, z: f64) -> f64 {
    let b = &l.base_size;
    let (z0, p0, z1, p1) = (b[0][0].f(), b[0][1].f(), b[1][0].f(), b[1][1].f());
    p0 + (p1 - p0) * ((z - z0) / (z1 - z0)).clamp(0.0, 1.0)
}

/// _label_px: a name's size: at most the base size, labels.fraction of its road's fill width.
pub(super) fn label_px(m: &Model, l: &LabelLook, cls: Option<&str>, z: f64) -> f64 {
    label_base_px(l, z).min(l.fraction.f() * m.class_width_px(cls, z, false))
}

/// _label_size_expr: text-size per class (or labels.size's own stops).
pub(crate) fn label_size_expr(m: &Model, l: &LabelLook, fixed: Option<&Value>) -> Value {
    if let Some(stops) = fixed {
        let mut s: Vec<Vec<f64>> = stops.as_array().unwrap().iter().map(|zp| zp.as_array().unwrap().iter().map(|v| v.as_f64().unwrap()).collect()).collect();
        s.sort_by(|a, b| a.partial_cmp(b).unwrap());
        let mut e = vec![json!("interpolate"), json!(["linear"]), json!(["zoom"])];
        e.extend(s.into_iter().flatten().map(|v| json!(v)));
        return Value::Array(e);
    }
    let mut zs: Vec<i64> = m.zstops.iter().filter_map(Value::as_f64).filter(|z| *z >= 14.0).map(|z| z as i64).collect();
    zs.extend([14, 18]);
    zs.sort();
    zs.dedup();
    let mut e = vec![json!("interpolate"), json!(["linear"]), json!(["zoom"])];
    for z in zs {
        let mut mm = vec![json!("match"), json!(["get", "highway"])];
        for c in &m.classes {
            mm.push(json!(c));
            mm.push(json!(round_to(label_px(m, l, Some(c), z as f64), 2)));
        }
        mm.push(json!(round_to(label_px(m, l, None, z as f64), 2)));
        e.push(json!(z));
        e.push(Value::Array(mm));
    }
    Value::Array(e)
}

/// _label_readable_filter: the first whole zoom from which a class's name is at least labels.min_px tall.
pub(crate) fn label_readable_filter(m: &Model, l: &LabelLook) -> Value {
    let min = l.min_px.f();
    let first = |c: Option<&str>| (0..23).find(|&z| label_px(m, l, c, z as f64) >= min).unwrap_or(99);
    let mut mm = vec![json!("match"), json!(["get", "highway"])];
    for c in &m.classes {
        mm.push(json!(c));
        mm.push(json!(first(Some(c))));
    }
    mm.push(json!(first(None)));
    json!([">=", ["zoom"], mm])
}

