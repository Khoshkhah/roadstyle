//! The drawing values of each road (docs/design/rust_library.md, "The numbers and ends of a road: RoadDraw"): what the stages of
//! render_web.render bake as `__rs_*` properties, as typed fields. `Draw::marks` gives them by their property names, in the order that
//! the stages set them, so the output text is the text of the old properties.

use roadstyle_model::{Cell, RoadKey};
use serde_json::Value;
use std::collections::HashMap;

/// The shape of a road end (render_web._cap_value): round (null), flat at the end point (true) or square.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Cap {
    Round,
    Flat,
    Square,
}

impl Cap {
    pub fn from_value(v: &Value) -> Cap {
        match v {
            Value::Null => Cap::Round,
            Value::String(s) if s == "square" => Cap::Square,
            _ => Cap::Flat,
        }
    }

    pub fn cell(self) -> Cell<'static> {
        match self {
            Cap::Round => Cell::Null,
            Cap::Flat => Cell::Bool(true),
            Cap::Square => Cell::Str("square"),
        }
    }

    pub fn value(self) -> Value {
        self.cell().to_value()
    }
}

/// The style values of a map (colours, widths, classes), each kept once: a road holds their numbers.
#[derive(Default)]
pub struct Values {
    list: Vec<Value>,
    at: HashMap<String, u32>,
}

impl Values {
    pub fn id(&mut self, v: &Value) -> u32 {
        let key = v.to_string();
        if let Some(&i) = self.at.get(&key) {
            return i;
        }
        self.list.push(v.clone());
        let i = (self.list.len() - 1) as u32;
        self.at.insert(key, i);
        i
    }

    pub fn get(&self, id: u32) -> &Value {
        &self.list[id as usize]
    }
}

/// The names of the eight style values of bake_props, in its order.
pub const STYLE: [&str; 8] = ["__rs_fill", "__rs_w", "__rs_op", "__rs_dash", "__rs_casing", "__rs_cw", "__rs_cop", "__rs_class"];

/// One road's drawing values. None (or false for a flag): the stage did not set the property.
#[derive(Clone, Debug, Default)]
pub struct Draw {
    /// access_col: the road's access kind (Some(None): not one of the kinds)
    pub access: Option<Option<&'static str>>,
    /// color_table: the road's own colour
    pub color: Option<u32>,
    /// bake_props: fill, width, opacity, dash, casing colour, casing width, casing opacity and class (STYLE)
    pub style: Option<[u32; 8]>,
    /// color_options: the fill of the options after the first (__rs_fill__1, ...)
    pub fills: Vec<u32>,
    pub twoway: Option<bool>,
    pub oneway: Option<bool>,
    /// a reverse pair of a single-line class: the later edge, and each edge's partner
    pub dup: bool,
    pub edge2: Option<RoadKey>,
    pub lvl: Option<i64>,
    pub bridge: Option<bool>,
    pub tunnel: Option<bool>,
    /// the cap of both ends (only when it is not round)
    pub cap: Option<Cap>,
    /// two different ends: the cap of each (__rs_cap0, __rs_cap1 and __rs_split)
    pub split: Option<[Cap; 2]>,
    /// the cap properties came after the twin's (_mark_twin_dead_ends set them new)
    pub caps_late: bool,
    pub head_start: Option<f64>,
    pub head_end: Option<f64>,
    /// casing_level, fill_level, casing_start and casing_end (and band 0)
    pub levels: Option<[i64; 4]>,
    pub twin: Option<u32>,
    /// metre widths: the width, the casing and the twin's width (over cos(latitude))
    pub width_m: Option<f64>,
    pub casing_m: Option<f64>,
    pub twin_width_m: Option<f64>,
    /// the road's key (the pieces' promoteId)
    pub edge: Option<RoadKey>,
    /// _mark_cls: the class filter's value
    pub cls: Option<u32>,
}

impl Draw {
    /// The properties of the road, by name and in the stages' order.
    pub fn marks<'a>(&'a self, values: &'a Values) -> Vec<(&'static str, Cell<'a>)> {
        let mut out: Vec<(&'static str, Cell<'a>)> = Vec::with_capacity(32);
        let id = |i: u32| Cell::Json(values.get(i));
        if let Some(a) = self.access {
            out.push(("__rs_access", a.map_or(Cell::Null, Cell::Str)));
        }
        if let Some(c) = self.color {
            out.push(("__rs_color", id(c)));
        }
        if let Some(s) = self.style {
            out.extend(STYLE.iter().zip(s).map(|(k, v)| (*k, id(v))));
        }
        for (i, &f) in self.fills.iter().enumerate() {
            out.push((fill_name(i + 1), id(f)));
        }
        let int = |v: i64| Cell::Int(v);
        let flag = |out: &mut Vec<_>, k, v: Option<bool>| if let Some(b) = v { out.push((k, Cell::Bool(b))) };
        flag(&mut out, "__rs_twoway", self.twoway);
        flag(&mut out, "__rs_oneway", self.oneway);
        if self.dup {
            out.push(("__rs_dup", Cell::Bool(true)));
        }
        if let Some(e) = self.edge2 {
            out.push(("__rs_edge2", int(e.get() as i64)));
        }
        if let Some(l) = self.lvl {
            out.push(("lvl", int(l)));
        }
        flag(&mut out, "__rs_bridge", self.bridge);
        flag(&mut out, "__rs_tunnel", self.tunnel);
        let caps = |out: &mut Vec<(&'static str, Cell<'a>)>| {
            if let Some(c) = self.cap {
                out.push(("__rs_cap", c.cell()));
            }
            if let Some([a, b]) = self.split {
                out.extend([("__rs_cap0", a.cell()), ("__rs_cap1", b.cell()), ("__rs_split", Cell::Bool(true))]);
            }
        };
        if !self.caps_late {
            caps(&mut out);
        }
        if let Some(h) = self.head_start {
            out.push(("__rs_hs", Cell::Float(h)));
        }
        if let Some(h) = self.head_end {
            out.push(("__rs_he", Cell::Float(h)));
        }
        if let Some([cl, fl, cs, ce]) = self.levels {
            out.extend([("__rs_cl", int(cl)), ("__rs_fl", int(fl)), ("__rs_cs", int(cs)), ("__rs_ce", int(ce)), ("__rs_band", int(0))]);
        }
        if let Some(t) = self.twin {
            out.push(("__rs_twin", int(t as i64)));
        }
        if self.caps_late {
            caps(&mut out);
        }
        for (k, v) in [("__rs_wm", self.width_m), ("__rs_cm", self.casing_m), ("__rs_twm", self.twin_width_m)] {
            if let Some(v) = v {
                out.push((k, Cell::Float(v)));
            }
        }
        if let Some(e) = self.edge {
            out.push(("__rs_edge", int(e.get() as i64)));
        }
        if let Some(c) = self.cls {
            out.push(("__rs_cls", id(c)));
        }
        out
    }

    /// One property by its name (as `marks` gives it).
    pub fn get<'a>(&'a self, values: &'a Values, k: &str) -> Option<Cell<'a>> {
        let id = |i: u32| Cell::Json(values.get(i));
        let b = |v: Option<bool>| v.map(Cell::Bool);
        let caps = self.split;
        match k {
            "__rs_access" => self.access.map(|a| a.map_or(Cell::Null, Cell::Str)),
            "__rs_color" => self.color.map(id),
            "__rs_twoway" => b(self.twoway),
            "__rs_oneway" => b(self.oneway),
            "__rs_dup" => self.dup.then_some(Cell::Bool(true)),
            "__rs_edge2" => self.edge2.map(|e| Cell::Int(e.get() as i64)),
            "lvl" => self.lvl.map(Cell::Int),
            "__rs_bridge" => b(self.bridge),
            "__rs_tunnel" => b(self.tunnel),
            "__rs_cap" => self.cap.map(Cap::cell),
            "__rs_cap0" => caps.map(|c| c[0].cell()),
            "__rs_cap1" => caps.map(|c| c[1].cell()),
            "__rs_split" => caps.map(|_| Cell::Bool(true)),
            "__rs_hs" => self.head_start.map(Cell::Float),
            "__rs_he" => self.head_end.map(Cell::Float),
            "__rs_cl" | "__rs_fl" | "__rs_cs" | "__rs_ce" | "__rs_band" => self.levels.map(|[cl, fl, cs, ce]| Cell::Int(match k {
                "__rs_cl" => cl, "__rs_fl" => fl, "__rs_cs" => cs, "__rs_ce" => ce, _ => 0,
            })),
            "__rs_twin" => self.twin.map(|t| Cell::Int(t as i64)),
            "__rs_wm" => self.width_m.map(Cell::Float),
            "__rs_cm" => self.casing_m.map(Cell::Float),
            "__rs_twm" => self.twin_width_m.map(Cell::Float),
            "__rs_edge" => self.edge.map(|e| Cell::Int(e.get() as i64)),
            "__rs_cls" => self.cls.map(id),
            _ => {
                if let Some(i) = STYLE.iter().position(|s| *s == k) {
                    return self.style.map(|s| id(s[i]));
                }
                let n: usize = k.strip_prefix("__rs_fill__")?.parse().ok()?;
                self.fills.get(n.checked_sub(1)?).map(|&f| id(f))
            }
        }
    }
}

/// The property of a colour option's fill (option 0: __rs_fill), as the one copy of the property names (props::intern).
pub fn fill_name(i: usize) -> &'static str {
    if i == 0 { "__rs_fill" } else { roadstyle_model::props::intern(&format!("__rs_fill__{i}")) }
}
