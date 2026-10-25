//! The drawing values of each road (docs/design/rust_library.md, "The numbers and ends of a road: RoadDraw"): what the stages of
//! render_web.render bake as `__rs_*` properties, as typed fields. `Draw::marks` gives them by their property names, in the order that
//! the stages set them, so the output text is the text of the old properties.

use roadstyle_model::mark::Mark;
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
    /// the property of each colour option's fill (mark::option_fill; colors::bake sets them)
    pub fill_names: Vec<String>,
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
pub const STYLE: [&str; 8] = [Mark::Fill.name(), Mark::Width.name(), Mark::Opacity.name(), Mark::Dash.name(), Mark::Casing.name(), Mark::CasingWidth.name(), Mark::CasingOpacity.name(), Mark::StyleClass.name()];

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
    pub fn marks<'a>(&'a self, values: &'a Values) -> Vec<(&'a str, Cell<'a>)> {
        let mut out: Vec<(&'a str, Cell<'a>)> = Vec::with_capacity(32);
        let id = |i: u32| Cell::Json(values.get(i));
        if let Some(a) = self.access {
            out.push((Mark::Access.name(), a.map_or(Cell::Null, Cell::Str)));
        }
        if let Some(c) = self.color {
            out.push((Mark::Color.name(), id(c)));
        }
        if let Some(s) = self.style {
            out.extend(STYLE.iter().zip(s).map(|(k, v)| (*k, id(v))));
        }
        for (i, &f) in self.fills.iter().enumerate() {
            out.push((values.fill_names[i + 1].as_str(), id(f)));
        }
        let int = |v: i64| Cell::Int(v);
        let flag = |out: &mut Vec<_>, k, v: Option<bool>| if let Some(b) = v { out.push((k, Cell::Bool(b))) };
        flag(&mut out, Mark::Twoway.name(), self.twoway);
        flag(&mut out, Mark::Oneway.name(), self.oneway);
        if self.dup {
            out.push((Mark::Dup.name(), Cell::Bool(true)));
        }
        if let Some(e) = self.edge2 {
            out.push((Mark::Edge2.name(), int(e.get() as i64)));
        }
        if let Some(l) = self.lvl {
            out.push(("lvl", int(l)));
        }
        flag(&mut out, Mark::Bridge.name(), self.bridge);
        flag(&mut out, Mark::Tunnel.name(), self.tunnel);
        let caps = |out: &mut Vec<(&'a str, Cell<'a>)>| {
            if let Some(c) = self.cap {
                out.push((Mark::Cap.name(), c.cell()));
            }
            if let Some([a, b]) = self.split {
                out.extend([(Mark::Cap0.name(), a.cell()), (Mark::Cap1.name(), b.cell()), (Mark::Split.name(), Cell::Bool(true))]);
            }
        };
        if !self.caps_late {
            caps(&mut out);
        }
        if let Some(h) = self.head_start {
            out.push((Mark::HeadStart.name(), Cell::Float(h)));
        }
        if let Some(h) = self.head_end {
            out.push((Mark::HeadEnd.name(), Cell::Float(h)));
        }
        if let Some([cl, fl, cs, ce]) = self.levels {
            out.extend([(Mark::CasingLevel.name(), int(cl)), (Mark::FillLevel.name(), int(fl)), (Mark::CasingStart.name(), int(cs)), (Mark::CasingEnd.name(), int(ce)), (Mark::Band.name(), int(0))]);
        }
        if let Some(t) = self.twin {
            out.push((Mark::Twin.name(), int(t as i64)));
        }
        if self.caps_late {
            caps(&mut out);
        }
        for (k, v) in [(Mark::WidthM.name(), self.width_m), (Mark::CasingM.name(), self.casing_m), (Mark::TwinWidthM.name(), self.twin_width_m)] {
            if let Some(v) = v {
                out.push((k, Cell::Float(v)));
            }
        }
        if let Some(e) = self.edge {
            out.push((Mark::Edge.name(), int(e.get() as i64)));
        }
        if let Some(c) = self.cls {
            out.push((Mark::Class.name(), id(c)));
        }
        out
    }

    /// One property by its name (as `marks` gives it).
    pub fn get<'a>(&'a self, values: &'a Values, k: &str) -> Option<Cell<'a>> {
        let id = |i: u32| Cell::Json(values.get(i));
        let b = |v: Option<bool>| v.map(Cell::Bool);
        let caps = self.split;
        let lv = |i: usize| self.levels.map(|l| Cell::Int(l[i]));
        let Some(m) = Mark::of(k) else {
            let n = roadstyle_model::mark::option_of_fill(k)?;
            return self.fills.get(n.checked_sub(1)?).map(|&f| id(f));
        };
        match m {
            Mark::Access => self.access.map(|a| a.map_or(Cell::Null, Cell::Str)),
            Mark::Color => self.color.map(id),
            Mark::Twoway => b(self.twoway),
            Mark::Oneway => b(self.oneway),
            Mark::Dup => self.dup.then_some(Cell::Bool(true)),
            Mark::Edge2 => self.edge2.map(|e| Cell::Int(e.get() as i64)),
            Mark::Lvl => self.lvl.map(Cell::Int),
            Mark::Bridge => b(self.bridge),
            Mark::Tunnel => b(self.tunnel),
            Mark::Cap => self.cap.map(Cap::cell),
            Mark::Cap0 => caps.map(|c| c[0].cell()),
            Mark::Cap1 => caps.map(|c| c[1].cell()),
            Mark::Split => caps.map(|_| Cell::Bool(true)),
            Mark::HeadStart => self.head_start.map(Cell::Float),
            Mark::HeadEnd => self.head_end.map(Cell::Float),
            Mark::CasingLevel => lv(0),
            Mark::FillLevel => lv(1),
            Mark::CasingStart => lv(2),
            Mark::CasingEnd => lv(3),
            Mark::Band => self.levels.map(|_| Cell::Int(0)),
            Mark::Twin => self.twin.map(|t| Cell::Int(t as i64)),
            Mark::WidthM => self.width_m.map(Cell::Float),
            Mark::CasingM => self.casing_m.map(Cell::Float),
            Mark::TwinWidthM => self.twin_width_m.map(Cell::Float),
            Mark::Edge => self.edge.map(|e| Cell::Int(e.get() as i64)),
            Mark::Class => self.cls.map(id),
            m => STYLE.iter().position(|s| *s == m.name()).and_then(|i| self.style.map(|s| id(s[i]))),
        }
    }
}
