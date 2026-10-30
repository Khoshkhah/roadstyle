use super::*;

/// The road layers' MapLibre expressions from the road width model.
pub trait Exprs {
    /// _width_expr: interpolate(zoom) of match(class -> width); two-way lanes narrow to width_frac from offset_zoom (over 2 zooms).
    fn width_expr(&self, col: &str, casing: bool, scale: f64) -> Value;
    /// _offset_match: a two-way direction's offset at zoom z, per class.
    fn offset_match(&self, col: &str, z: f64) -> Value;
    /// _offset_expr (no metre widths): line-offset of a two-way edge; with `pairs`, a pair's one casing (__rs_pair) is not shifted.
    fn offset_expr(&self, col: &str, pairs: bool) -> Value;
    /// _width_m_expr: _width_expr, but a line with a metre width (__rs_wm) is drawn at exactly that width from width_m_zoom on, on a base-2
    /// exponential curve to zoom 22. `kind`: "fill" (the width less two casings), "casing" (the width) or "wings" (a bridge's casing: the
    /// width and two casings). `bridge_m` / `bridge_px`: config bridge_casing_m / _px; `casing_px`: render's casing_min_px.
    fn width_m_expr(&self, col: &str, kind: &str, ml: &MetreLook) -> Value;
    /// _offset_expr with width_m_zoom: from width_m_zoom on, a direction whose pair has metres on both (__rs_twm) is shifted by metres.
    fn offset_expr_m(&self, col: &str, pairs: bool, wmz: &Value) -> Value;
    /// _sort_key: the grade (lvl * 1000), then the class.
    fn sort_key(&self, col: &str) -> Value;
    /// _pair_width: a two-way pair's one casing as wide as its two directions (no metre widths).
    /// _pair_width; with width_m_zoom (`wmz`), a pair with metres on both has its width in `expr` already from that zoom on.
    fn pair_width(&self, col: &str, expr: &Value, wmz: Option<f64>) -> Value;
}

impl Exprs for Model {
    fn width_expr(&self, col: &str, casing: bool, scale: f64) -> Value {
        let (split_zoom, split_frac) = (self.offset_zoom, self.width_frac);
        let mut e = vec![json!("interpolate"), json!(["linear"]), json!(["zoom"])];
        for (z, zv) in self.stops() {
            let w_of = |g: &str, lk: bool| self.group_px(g, lk, z, casing, scale);
            let mut m = vec![json!("match"), json!(["get", col])];
            for c in &self.classes {
                let (b, lk) = Self::base(c);
                m.push(json!(c));
                m.push(json!(w_of(self.group_of(b), lk)));
            }
            m.push(json!(w_of(&self.fb_group, false)));
            let f = if z <= split_zoom { 1.0 } else if z >= split_zoom + 2.0 { split_frac } else { 1.0 - (1.0 - split_frac) * (z - split_zoom) / 2.0 };
            let m = if f < 1.0 { json!(["*", m, ["case", ["to-boolean", ["get", Mark::Twoway.name()]], round_to(f, 3), 1]]) } else { Value::Array(m) };
            e.push(zv.clone());
            e.push(m);
        }
        Value::Array(e)
    }

    fn offset_match(&self, col: &str, z: f64) -> Value {
        let ramp = ((z - self.offset_zoom) / self.ramp_zooms).clamp(0.0, 1.0);
        let mut m = vec![json!("match"), json!(["get", col])];
        for c in &self.classes {
            let (b, lk) = Self::base(c);
            let w = self.gwidth(self.group_of(b), z) * if lk { self.link_w } else { 1.0 };
            m.push(json!(c));
            m.push(json!(round_to(w * self.offset_frac * ramp, 3)));
        }
        m.push(json!(round_to(self.gwidth(&self.fb_group, z) * self.offset_frac * ramp, 3)));
        Value::Array(m)
    }

    fn offset_expr(&self, col: &str, pairs: bool) -> Value {
        let two = json!(["to-boolean", ["get", Mark::Twoway.name()]]);
        let two = if pairs { json!(["all", two, ["!", ["to-boolean", ["get", Mark::Pair.name()]]]]) } else { two };
        let mut e = vec![json!("interpolate"), json!(["linear"]), json!(["zoom"])];
        for (z, zv) in self.stops() {
            e.push(zv.clone());
            e.push(json!(["case", two, self.offset_match(col, z), 0]));
        }
        Value::Array(e)
    }

    fn width_m_expr(&self, col: &str, kind: &str, ml: &MetreLook) -> Value {
        let MetreLook { wmz, bridge_m, bridge_px, casing_px, wing_scale } = ml;
        let (wmz, wing_scale) = (wmz, *wing_scale);
        let casing = kind != "fill";
        let cls_e = self.width_expr(col, casing, if kind == "wings" { wing_scale } else { 1.0 });
        let cls: Vec<Value> = cls_e.as_array().unwrap()[4..].iter().step_by(2).cloned().collect();
        let k = match kind { "fill" => -2, "casing" => 0, _ => 2 };
        let cm = if kind == "wings" && crate::roads::yes(bridge_m) { json!(["max", ["get", Mark::CasingM.name()], bridge_m]) } else { json!(["get", Mark::CasingM.name()]) };
        let mut w = json!(["get", Mark::WidthM.name()]);
        if casing {     // a two-way pair's one casing with metres on both: both directions, their two casings in the middle once
            w = json!(["case", ["all", ["to-boolean", ["get", Mark::Pair.name()]], ["has", Mark::TwinWidthM.name()]], ["+", w, ["get", Mark::TwinWidthM.name()], ["*", -2, ["get", Mark::CasingM.name()]]], w]);
        }
        let wm = if k != 0 { json!(["max", ["+", w, ["*", k, cm]], 0]) } else { w.clone() };
        let twice = |v: &Value| if let Some(i) = v.as_i64() { json!(2 * i) } else { json!(2.0 * v.as_f64().unwrap_or(0.0)) };
        let stops: Vec<f64> = self.zstops.iter().map(|z| z.as_f64().unwrap()).collect();
        let wz = wmz.as_f64().unwrap_or(f64::INFINITY);
        let mut e = vec![json!("interpolate"), json!(["exponential", 2]), json!(["zoom"])];
        for (z, zv) in self.metre_stops(wmz) {
            let zz = self.clamp_stop(z);
            let lo = stops.iter().rposition(|s| *s <= zz).unwrap();
            let hi = stops.iter().position(|s| *s >= zz).unwrap();
            let c = if lo == hi { cls[lo].clone() } else {
                let (a, b) = (stops[lo], stops[hi]);
                json!(["+", ["*", cls[lo], round_to((b - zz) / (b - a), 4)], ["*", cls[hi], round_to((zz - a) / (b - a), 4)]])
            };
            let px = round_to(512.0 * 2f64.powf(z) / 40075016.686, 4);
            let mut m = json!(["*", wm, px]);
            if kind == "casing" && crate::roads::yes(casing_px) {     // a casing never thinner than casing_px each side of its fill
                m = json!(["max", m, ["+", ["*", ["max", ["+", w, ["*", -2, ["get", Mark::CasingM.name()]]], 0], px], twice(casing_px)]]);
            }
            if kind == "wings" && crate::roads::yes(bridge_px) {      // never thinner than the fill and bridge_px each side
                let fill = json!(["max", ["+", ["get", Mark::WidthM.name()], ["*", -2, ["get", Mark::CasingM.name()]]], 0]);
                m = json!(["max", m, ["+", ["*", fill, px], twice(bridge_px)]]);
            }
            e.push(zv);
            e.push(if z < wz { c } else { json!(["case", ["has", Mark::WidthM.name()], m, c]) });
        }
        Value::Array(e)
    }

    fn offset_expr_m(&self, col: &str, pairs: bool, wmz: &Value) -> Value {
        let two = json!(["to-boolean", ["get", Mark::Twoway.name()]]);
        let two = if pairs { json!(["all", two, ["!", ["to-boolean", ["get", Mark::Pair.name()]]]]) } else { two };
        let wz = wmz.as_f64().unwrap_or(f64::INFINITY);
        let mut e = vec![json!("interpolate"), json!(["exponential", 2]), json!(["zoom"])];
        for (z, zv) in self.metre_stops(wmz) {
            let mut c = self.offset_match(col, self.clamp_stop(z));
            if z >= wz {
                let px = round_to(512.0 * 2f64.powf(z) / 40075016.686, 4);
                c = json!(["case", ["has", Mark::TwinWidthM.name()], ["*", ["-", ["*", 0.5, ["get", Mark::TwinWidthM.name()]], ["get", Mark::CasingM.name()]], px], c]);
            }
            e.push(zv);
            e.push(json!(["case", two, c, 0]));
        }
        Value::Array(e)
    }

    fn sort_key(&self, col: &str) -> Value {
        let mut m = vec![json!("match"), json!(["get", col])];
        for c in &self.classes {
            m.push(json!(c));
            m.push(self.class_order(c));
        }
        m.push(self.fb_order.clone());
        json!(["+", ["*", ["coalesce", ["get", "lvl"], 0], 1000], m])
    }

    fn pair_width(&self, col: &str, expr: &Value, wmz: Option<f64>) -> Value {
        let (z0, z1) = (self.zstops[0].as_f64().unwrap(), self.zstops[self.zstops.len() - 1].as_f64().unwrap());
        plus_px(expr, |z| {
            let zf = z.as_f64().unwrap();
            let add = json!(["*", 2, self.offset_match(col, zf.clamp(z0, z1))]);
            match wmz { Some(w) if zf >= w => json!(["case", ["has", Mark::TwinWidthM.name()], 0, add]), _ => add }
        }, Some(&json!(["to-boolean", ["get", Mark::Pair.name()]])))
    }
}


// --- step 2: the road layers of simple mode with stored levels, the passes and the export ---

pub(super) fn gs(name: &str) -> Value {
    json!(["global-state", name])
}

/// `each(p)` for the property of the active colour option (state rs_co); `props`: the baked fill property of each option, in order.
fn by_option(props: &[String], each: impl Fn(&str) -> Value) -> Value {
    if props.len() == 1 {
        return each(&props[0]);
    }
    let mut m = vec![json!("match"), gs("rs_co")];
    for (i, p) in props.iter().enumerate().skip(1) {
        m.push(i.into());
        m.push(each(p));
    }
    m.push(each(&props[0]));
    Value::Array(m)
}

/// _fill_base: a road's fill under the active colour option.
pub(super) fn fill_base(props: &[String], fb_fill: &Value) -> Value {
    by_option(props, |p| json!(["coalesce", ["get", p], fb_fill]))
}

/// A colour that a piece holds as a place in the style's table (the let variable `table`; place 0 is the fallback colour).
pub(super) fn place_colour(place: Value, table: &str) -> Value {
    json!(["to-color", ["at", ["number", place, 0], ["var", table]]])
}

/// The place of a road's fill colour under the active colour option.
pub(super) fn fill_place(props: &[String], table: &str) -> Value {
    place_colour(by_option(props, |p| json!(["get", p])), table)
}

/// _tun_mix: a tunnel feature's colour moved toward the tunnel colour by the strength, keeping its own alpha.
pub(super) fn tun_mix(expr: &Value) -> Value {
    let mixed = json!(["to-rgba", ["interpolate", ["linear"], gs("rs_tun_strength"), 0, expr, 100, gs("rs_tun_toward")]]);
    let keep = json!(["rgba", ["at", 0, ["var", "m"]], ["at", 1, ["var", "m"]], ["at", 2, ["var", "m"]], ["at", 3, ["to-rgba", expr]]]);
    json!(["case", ["to-boolean", ["get", Mark::Tunnel.name()]], ["let", "m", mixed, keep], expr])
}

pub(crate) fn tun_gap() -> Value {
    json!(["case", gs("rs_tun_two"), ["interpolate", ["linear"], gs("rs_tun_strength"), 0, gs("rs_tun_c1"), 100, gs("rs_tun_toward")], "rgba(0,0,0,0)"])
}

pub(crate) fn tun_dash() -> Value {
    json!(["interpolate", ["linear"], gs("rs_tun_strength"), 0, gs("rs_tun_c0"), 100, gs("rs_tun_toward")])
}

/// The settings of the metre-width curves (_width_m_expr): width_m_zoom, config bridge_casing_m / bridge_casing_px, render's
/// casing_min_px, and the theme's bridge wing scale.
pub struct MetreLook {
    pub wmz: Value,
    pub bridge_m: Value,
    pub bridge_px: Value,
    pub casing_px: Value,
    pub wing_scale: f64,
}

/// _plus_px: a zoom curve `px(zoom)` pixels wider at each stop (only where `when` holds, if given).
pub(crate) fn plus_px(expr: &Value, px: impl Fn(&Value) -> Value, when: Option<&Value>) -> Value {
    let e = expr.as_array().unwrap();
    let first = if e[0] == "interpolate" { 4 } else { 2 };
    let mut out: Vec<Value> = e[..first].to_vec();
    for i in first..e.len() {
        let v = &e[i];
        out.push(if (i - first) % 2 == 0 {
            let p = px(&e[i - 1]);
            match when {
                None => json!(["+", v, p]),
                Some(w) => json!(["case", w, ["+", v, p], v]),
            }
        } else {
            v.clone()
        });
    }
    Value::Array(out)
}

/// _by_feature: one zoom curve that picks a curve per feature, the choice inside each stop.
/// _exp2: a zoom curve as a base-2 exponential one with a stop at 22 (its last value), so a metre curve on its stops is exact at every zoom.
pub(super) fn exp2(curve: &Value) -> Value {
    let c = curve.as_array().unwrap();
    let mut out = vec![json!("interpolate"), json!(["exponential", 2]), json!(["zoom"])];
    out.extend(c[3..].iter().cloned());
    if c[c.len() - 2].as_f64().is_some_and(|z| z < 22.0) {
        out.extend([json!(22), c[c.len() - 1].clone()]);
    }
    Value::Array(out)
}

/// _metre_curve: a zoom curve in px for the metres in `prop` (null 0) on the stops and interpolation of `like` (512 * 2^z / C px per metre).
pub(super) fn metre_curve(like: &Value, prop: &str) -> Value {
    let l = like.as_array().unwrap();
    let mut out: Vec<Value> = l[..3].to_vec();
    for z in l[3..].iter().step_by(2) {
        out.push(z.clone());
        out.push(json!(["*", ["coalesce", ["get", prop], 0], round_to(512.0 * 2f64.powf(z.as_f64().unwrap()) / 40075016.686, 6)]));
    }
    Value::Array(out)
}

/// R22's feature states on a road's row: its colour and the factor of its drawn width (metadata roadstyle:live).
/// R8: each feature of the road layer's source has its class's place in the classes (`Model::classes`; their number: another class).
pub const CLASS_INDEX: &str = Mark::ClassIndex.name();

/// R8: a class table, `["match", ["get", col], c0, v0, ..., fallback]` over the classes in their order with literal values, as one lookup
/// by the feature's class index: `["at", ["get", Mark::ClassIndex.name()], ["literal", [v0, ..., fallback]]]` (the road layer's width and offset have
/// ~100 such tables).
pub fn class_index(e: &mut Value, col: &str, classes: &[String]) {
    let Value::Array(a) = e else {
        if let Value::Object(o) = e {
            o.values_mut().for_each(|x| class_index(x, col, classes));
        }
        return;
    };
    let n = classes.len();
    let table = a.len() == 3 + 2 * n && a[0] == "match" && a[1] == json!(["get", col]) && classes.iter().enumerate().all(|(i, c)| a[2 + 2 * i] == c.as_str())
        && (0..n).all(|i| !a[3 + 2 * i].is_array()) && !a[2 + 2 * n].is_array();
    if table {
        let vals: Vec<Value> = (0..classes.len()).map(|i| a[3 + 2 * i].clone()).chain([a[a.len() - 1].clone()]).collect();
        *e = json!(["at", ["get", CLASS_INDEX], ["literal", vals]]);
        return;
    }
    a.iter_mut().for_each(|x| class_index(x, col, classes));
}

pub const LIVE_COLOR: &str = "rs_c";
pub const LIVE_WIDTH: &str = "rs_w";

/// `e` with each output of its zoom curve times `f`: a zoom curve must stay at the top of a paint value (MapLibre), so the factor goes
/// into each stop.
pub fn times_each_stop(e: &Value, f: &Value) -> Value {
    let times = |v: &Value| json!(["*", v, f]);
    match e.as_array().map(Vec::as_slice) {
        Some([op, how, input, rest @ ..]) if op == "interpolate" && input == &json!(["zoom"]) => {
            let mut out = vec![op.clone(), how.clone(), input.clone()];
            for p in rest.chunks(2) {
                out.extend([p[0].clone(), times(&p[1])]);
            }
            Value::Array(out)
        }
        Some([op, input, first, rest @ ..]) if op == "step" && input == &json!(["zoom"]) => {
            let mut out = vec![op.clone(), input.clone(), times(first)];
            for p in rest.chunks(2) {
                out.extend([p[0].clone(), times(&p[1])]);
            }
            Value::Array(out)
        }
        _ => times(e),
    }
}

pub(crate) fn by_feature(cases: &[(Value, Value)], default: &Value) -> Value {
    let d = default.as_array().unwrap();
    let mut out: Vec<Value> = d[..3].to_vec();
    let mut i = 0;
    while 3 + 2 * i < d.len() {
        let mut c = vec![json!("case")];
        for (cond, curve) in cases {
            c.push(cond.clone());
            c.push(curve[4 + 2 * i].clone());
        }
        c.push(d[4 + 2 * i].clone());
        out.push(d[3 + 2 * i].clone());
        out.push(Value::Array(c));
        i += 1;
    }
    Value::Array(out)
}

/// The key of the minzoom mapping for the roads with private access (the access kind `private`, access_col): they show only from this zoom or
/// from their class's first zoom, whichever is later. `{"@private": 15}`.
pub(crate) const PRIVATE_KEY: &str = "@private";

/// _minzoom_filter: a feature only from its class's first zoom (a class that the table does not name: 0, always drawn); a road with private access
/// also not before the zoom of the table's key `@private`. The clauses are `>=` of the zoom and an `all` / `any` of them, which the tiles read too.
pub(crate) fn minzoom_filter(col: &str, table: &Map<String, Value>) -> Value {
    let mut keys: Vec<&String> = table.keys().filter(|k| k.as_str() != PRIVATE_KEY).collect();
    keys.sort();
    let mut m = vec![json!("match"), json!(["coalesce", ["get", col], ""])];
    for k in keys {
        m.push(json!(k));
        m.push(json!(table[k].as_f64().unwrap_or(0.0)));
    }
    m.push(json!(0.0));
    let by_class = json!([">=", ["zoom"], m]);
    match table.get(PRIVATE_KEY).and_then(Value::as_f64).filter(|z| *z > 0.0) {
        Some(z) => json!(["all", by_class, ["any", ["!=", ["coalesce", ["get", roadstyle_model::mark::Mark::Access.name()], ""], "private"], [">=", ["zoom"], z]]]),
        None => by_class,
    }
}

/// render's minzoom (_minzoom_filter): null or true the config's table of the classes' first zooms (the default since 2026-10-25, as
/// OpenMapTiles and OSM-Carto do), a mapping that table with changes, false every class at every zoom (None). In a mapping the key `"*"`
/// sets every class of the table first (`{"*": 0, "steps": 15}` is every class at every zoom but the steps), and the key `"@private"` is the
/// first zoom of the roads with private access, whatever their class (`PRIVATE_KEY`).
pub(crate) fn class_minzoom(look: &crate::Look) -> Option<Map<String, Value>> {
    use roadstyle_look::options::ClassMinzoom;
    let table = || look.sections.roads.class_values("minzoom");
    match &look.map.roads.minzoom {
        ClassMinzoom::Profile => Some(table()),
        ClassMinzoom::Table(o) => {
            let mut t = table();
            if let Some(all) = o.get("*") {
                t.values_mut().for_each(|v| *v = all.clone());
            }
            t.extend(o.iter().filter(|(k, _)| k.as_str() != "*").map(|(k, v)| (k.clone(), v.clone())));
            Some(t)
        }
        ClassMinzoom::Off => None,
    }.map(|mut t| {
        t.retain(|_, z| z.as_f64().is_some_and(|z| z > 0.0));          // a class from zoom 0 needs no entry
        t
    }).filter(|t| !t.is_empty())
}

/// casing.drop_below_px (2026-10-25): a casing piece (`__rs_k` 0, not a bridge's) only from its class's first zoom whose tiles show the
/// casing line at least `drop` px wide: the first z with the class's casing width at z + 1 >= `drop` (the width grows with the zoom).
/// None when `drop` is 0, when every class has a casing from zoom 0, or when `kept` (a road in metres with casing.min_px >= drop).
///; the tiles read the clause (roadstyle-tiles rules.rs).
pub(crate) fn casing_drop_filter(m: &Model, drop: f64, kept: bool) -> Option<Value> {
    if drop <= 0.0 || kept {
        return None;
    }
    let first = |c: Option<&str>| (0..24).find(|&z| m.class_width_px(c, (z + 1) as f64, true) >= drop).unwrap_or(24);
    let zs: Vec<u32> = m.classes.iter().map(|c| first(Some(c))).chain([first(None)]).collect();
    if zs.iter().all(|&z| z == 0) {
        return None;
    }
    let casing = json!(["all", ["==", ["get", Mark::PieceKind.name()], 0], ["!", ["to-boolean", ["get", Mark::Bridge.name()]]]]);
    Some(json!([">=", ["zoom"], ["case", casing, ["at", ["get", CLASS_INDEX], ["literal", zs]], 0]]))
}

/// `filter` with `extra` added at its end (["all", ...]), or as it is.
pub(super) fn with_minzoom(filter: Value, extra: Option<Value>) -> Value {
    match (filter, extra) {
        (Value::Array(mut a), Some(z)) => {
            a.push(z);
            Value::Array(a)
        }
        (f, _) => f,
    }
}

pub(crate) fn seam_filter() -> Value {
    let (seam, lap) = (json!(["to-boolean", ["get", Mark::Seam.name()]]), json!(["to-boolean", ["get", Mark::Lap.name()]]));
    json!(["any", ["!", seam], ["all", ["!", lap], [">=", ["zoom"], 17]], ["all", lap, ["<", ["zoom"], 17]]])
}

pub(super) fn simple_cap() -> Value {
    json!(["case", ["to-boolean", ["get", Mark::Dash.name()]], "butt", ["==", ["get", Mark::PieceKind.name()], 4], "butt", ["==", ["get", Mark::PieceKind.name()], 5], "butt",
           ["==", ["get", Mark::Cap.name()], "square"], "square", ["to-boolean", ["get", Mark::Cap.name()]], "butt", "round"])
}

pub(super) fn simple_dasharray(dashes: &[String]) -> Value {
    let solid = json!(["literal", [1, 0]]);
    let by = if dashes.is_empty() { solid } else {
        let mut m = vec![json!("match"), json!(["to-string", ["coalesce", ["get", Mark::Dash.name()], ""]])];
        for d in dashes {
            m.push(json!(d));
            m.push(json!(["literal", d.split(',').map(|v| v.trim().parse::<f64>().unwrap()).collect::<Vec<_>>()]));
        }
        m.push(solid);
        Value::Array(m)
    };
    json!(["case", ["==", ["get", Mark::PieceKind.name()], 4], gs("rs_tun_ratio"), by])
}


#[cfg(test)]
mod class_minzoom_tests {
    use super::class_minzoom;
    use roadstyle_look::{Look, Options};
    use serde_json::{json, Map, Value};

    fn first(args: Value) -> Option<Map<String, Value>> {
        class_minzoom(&Look::resolve(&Options { args, ..Default::default() }).expect("a look"))
    }

    /// `{"*": 0, "service": 14}` is every class at every zoom but the service roads; the profile's table is the default; `false` has no first zoom; the
    /// dashboard's default (every class at every zoom but the steps, the platforms and the corridors, from zoom 15) has three entries and no zero.
    #[test]
    fn a_star_in_the_minzoom_mapping_sets_every_class_first() {
        let profile = first(json!({})).expect("the profile's table");
        assert_eq!(profile["residential"].as_f64(), Some(13.0));
        assert_eq!(first(json!({"minzoom": {"*": 0, "service": 14}})), json!({"service": 14}).as_object().cloned());
        assert_eq!(first(json!({"minzoom": false})), None);
        let dashboard = first(json!({"minzoom": {"*": 0, "service": 14, "living_street": 14, "steps": 15, "platform": 15, "corridor": 15, "road": 15, "@private": 15}})).expect("a table");
        assert_eq!(dashboard, json!({"service": 14, "living_street": 14, "steps": 15, "platform": 15, "corridor": 15, "road": 15, "@private": 15}).as_object().cloned().unwrap());
        // a change of a class without the star keeps the rest of the profile's table
        let some = first(json!({"minzoom": {"service": 16}})).expect("a table");
        assert_eq!((some["service"].as_f64(), some["residential"].as_f64()), (Some(16.0), Some(13.0)));
    }

    /// A road with private access is drawn from the table's `@private` zoom or from its class's zoom, whichever is later; without the key the filter is the class's only.
    #[test]
    fn a_private_access_road_shows_from_the_private_zoom_at_the_earliest() {
        let table = json!({"service": 14, "@private": 15}).as_object().cloned().unwrap();
        let f = super::minzoom_filter("highway", &table);
        assert_eq!(f[0], "all");
        let access = roadstyle_model::mark::Mark::Access.name();
        assert_eq!(f[2], json!(["any", ["!=", ["coalesce", ["get", access], ""], "private"], [">=", ["zoom"], 15.0]]));
        let plain = super::minzoom_filter("highway", json!({"service": 14}).as_object().unwrap());
        assert_eq!(plain[0], ">=");
    }
}
