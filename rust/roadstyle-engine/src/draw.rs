//! The drawing values of each road (docs/design/rust_library.md, "The numbers and ends of a road: RoadDraw"): what the stages of
//! bake as `__rs_*` properties, as typed fields. `Draw::marks` gives them by their property names, in the order that
//! the stages set them, so the output text is the text of the old properties.

use roadstyle_model::mark::Mark;
use roadstyle_model::Cell;
use serde_json::Value;
use std::collections::HashMap;

/// The shape of a road end: round (null), flat at the end point (true) or square.
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

/// A number into one of the roads' shared tables (`Values`), or a road's row: stored + 1, so that an `Option<Ix>` is 4 bytes.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct Ix(std::num::NonZeroU32);

impl Ix {
    pub fn new(i: usize) -> Ix {
        Ix(u32::try_from(i + 1).ok().and_then(std::num::NonZeroU32::new).expect("a number below u32::MAX"))
    }

    pub fn get(self) -> usize {
        self.0.get() as usize - 1
    }
}

/// The style values of a map (colours, widths, classes, head lengths), each kept once: a road holds their numbers.
#[derive(Default)]
pub struct Values {
    list: Vec<Value>,
    at: HashMap<String, u32>,
    /// the eight style values of bake_props (STYLE) of the roads, each set of eight kept once
    styles: Vec<[u32; 8]>,
    style_at: HashMap<[u32; 8], u32>,
    /// the property of each colour option's fill (mark::option_fill; colors::bake sets them)
    pub fill_names: Vec<String>,
    /// the JSON text of the value that `id` looks for (one buffer: a value that is there makes no new text)
    key: Vec<u8>,
}

impl Values {
    pub fn id(&mut self, v: &Value) -> u32 {
        self.key.clear();
        serde_json::to_writer(&mut self.key, v).expect("a Vec takes every byte");
        let key = std::str::from_utf8(&self.key).expect("JSON text is UTF-8");
        if let Some(&i) = self.at.get(key) {
            return i;
        }
        let key = key.to_string();
        self.list.push(v.clone());
        let i = (self.list.len() - 1) as u32;
        self.at.insert(key, i);
        i
    }

    pub fn get(&self, id: u32) -> &Value {
        &self.list[id as usize]
    }

    /// The number of a value, as an `Ix`.
    pub fn ix(&mut self, v: &Value) -> Ix {
        Ix::new(self.id(v) as usize)
    }

    pub fn at(&self, i: Ix) -> &Value {
        &self.list[i.get()]
    }

    /// The number of a road's eight style values.
    pub fn style_ix(&mut self, s: [u32; 8]) -> Ix {
        let n = self.styles.len() as u32;
        let i = *self.style_at.entry(s).or_insert(n);
        if i == n {
            self.styles.push(s);
        }
        Ix::new(i as usize)
    }

    pub fn style(&self, i: Ix) -> [u32; 8] {
        self.styles[i.get()]
    }
}

/// The names of the eight style values of bake_props, in its order.
pub const STYLE: [Mark; 8] = [Mark::Fill, Mark::Width, Mark::Opacity, Mark::Dash, Mark::Casing, Mark::CasingWidth, Mark::CasingOpacity, Mark::StyleClass];

/// The access kinds of access_col (`Draw::access` is a number into it).
pub const ACCESS_KINDS: [&str; 4] = ["private", "bus", "pedestrian", "delivery"];

/// Metre widths (width_m_col): the width, the casing and the twin's width, over cos(latitude).
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Metres {
    pub width: Option<f64>,
    pub casing: Option<f64>,
    pub twin_width: Option<f64>,
}

/// One road's drawing values. None (or false for a flag): the stage did not set the property.
#[derive(Clone, Debug, Default)]
pub struct Draw {
    /// access_col: the road's access kind, a number into ACCESS_KINDS (Some(None): not one of the kinds)
    pub access: Option<Option<u8>>,
    /// color_table: the road's own colour
    pub color: Option<Ix>,
    /// bake_props: fill, width, opacity, dash, casing colour, casing width, casing opacity and class (STYLE), one set of `Values`
    pub style: Option<Ix>,
    /// color_options: the fill of the options after the first (__rs_fill__1, ...)
    pub fills: Box<[u32]>,
    pub twoway: Option<bool>,
    pub oneway: Option<bool>,
    /// a reverse pair of a single-line class: the later edge, and each edge's partner (its row)
    pub dup: bool,
    pub edge2: Option<Ix>,
    pub lvl: Option<i16>,
    pub bridge: Option<bool>,
    pub tunnel: Option<bool>,
    /// the cap of both ends (only when it is not round)
    pub cap: Option<Cap>,
    /// two different ends: the cap of each (__rs_cap0, __rs_cap1 and __rs_split)
    pub split: Option<[Cap; 2]>,
    /// the cap properties came after the twin's (_mark_twin_dead_ends set them new)
    pub caps_late: bool,
    /// the head lengths in metres (start, end): numbers of `Values`
    pub heads: [Option<Ix>; 2],
    /// casing_level, fill_level, casing_start and casing_end (and band 0)
    pub levels: Option<[i16; 4]>,
    /// the twin's row
    pub twin: Option<Ix>,
    /// metre widths (only a map in metres has them)
    pub metres: Option<Box<Metres>>,
    /// the road's key is written (`__rs_edge`: the pieces' promoteId), from its row
    pub keyed: bool,
    /// _mark_cls: the class filter's value
    pub cls: Option<Ix>,
}

impl Draw {
    /// The drawing positions as i64 (casing_level, fill_level, casing_start, casing_end), as the stages compute with them.
    pub fn levels64(&self) -> Option<[i64; 4]> {
        self.levels.map(|l| l.map(i64::from))
    }

    /// Set the drawing positions (each within i16: a position is a small number).
    pub fn set_levels(&mut self, l: [i64; 4]) {
        self.levels = Some(l.map(|x| x.clamp(i16::MIN.into(), i16::MAX.into()) as i16));
    }

    /// A head length in metres (0: start, 1: end).
    pub fn head(&self, values: &Values, end: usize) -> Option<f64> {
        self.heads[end].and_then(|i| values.at(i).as_f64())
    }

    pub fn width_m(&self) -> Option<f64> {
        self.metres.as_ref().and_then(|m| m.width)
    }

    pub fn casing_m(&self) -> Option<f64> {
        self.metres.as_ref().and_then(|m| m.casing)
    }

    pub fn twin_width_m(&self) -> Option<f64> {
        self.metres.as_ref().and_then(|m| m.twin_width)
    }

    /// The metre widths, made when the first is set.
    pub fn metres_mut(&mut self) -> &mut Metres {
        self.metres.get_or_insert_with(Default::default)
    }

    /// The properties of the road in row `row`, by name and in the stages' order.
    pub fn marks<'a>(&'a self, values: &'a Values, row: usize) -> Vec<(&'a str, Cell<'a>)> {
        let mut out: Vec<(&'a str, Cell<'a>)> = Vec::with_capacity(32);
        let id = |i: u32| Cell::Json(values.get(i));
        if let Some(a) = self.access {
            out.push((Mark::Access.name(), a.map_or(Cell::Null, |k| Cell::Str(ACCESS_KINDS[k as usize]))));
        }
        if let Some(c) = self.color {
            out.push((Mark::Color.name(), Cell::Json(values.at(c))));
        }
        if let Some(s) = self.style {
            out.extend(STYLE.iter().zip(values.style(s)).map(|(k, v)| (k.name(), id(v))));
        }
        for (i, &f) in self.fills.iter().enumerate() {
            out.push((values.fill_names[i + 1].as_str(), id(f)));
        }
        let int = |v: i64| Cell::Int(v);
        let flag = |out: &mut Vec<_>, k: Mark, v: Option<bool>| if let Some(b) = v { out.push((k.name(), Cell::Bool(b))) };
        flag(&mut out, Mark::Twoway, self.twoway);
        flag(&mut out, Mark::Oneway, self.oneway);
        if self.dup {
            out.push((Mark::Dup.name(), Cell::Bool(true)));
        }
        if let Some(e) = self.edge2 {
            out.push((Mark::Edge2.name(), int(crate::road::key(e.get()).get() as i64)));
        }
        if let Some(l) = self.lvl {
            out.push((Mark::Lvl.name(), int(l.into())));
        }
        flag(&mut out, Mark::Bridge, self.bridge);
        flag(&mut out, Mark::Tunnel, self.tunnel);
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
        for (k, end) in [(Mark::HeadStart, 0), (Mark::HeadEnd, 1)] {
            if let Some(h) = self.head(values, end) {
                out.push((k.name(), Cell::Float(h)));
            }
        }
        if let Some([cl, fl, cs, ce]) = self.levels {
            out.extend([(Mark::CasingLevel.name(), int(cl.into())), (Mark::FillLevel.name(), int(fl.into())), (Mark::CasingStart.name(), int(cs.into())),
                        (Mark::CasingEnd.name(), int(ce.into())), (Mark::Band.name(), int(0))]);
        }
        if let Some(t) = self.twin {
            out.push((Mark::Twin.name(), int(t.get() as i64)));
        }
        if self.caps_late {
            caps(&mut out);
        }
        for (k, v) in [(Mark::WidthM, self.width_m()), (Mark::CasingM, self.casing_m()), (Mark::TwinWidthM, self.twin_width_m())] {
            if let Some(v) = v {
                out.push((k.name(), Cell::Float(v)));
            }
        }
        if self.keyed {
            out.push((Mark::Edge.name(), int(crate::road::key(row).get() as i64)));
        }
        if let Some(c) = self.cls {
            out.push((Mark::Class.name(), Cell::Json(values.at(c))));
        }
        out
    }

    /// One property by its name (as `marks` gives it), of the road in row `row`.
    pub fn get<'a>(&'a self, values: &'a Values, row: usize, k: &str) -> Option<Cell<'a>> {
        let id = |i: u32| Cell::Json(values.get(i));
        let b = |v: Option<bool>| v.map(Cell::Bool);
        let caps = self.split;
        let lv = |i: usize| self.levels.map(|l| Cell::Int(l[i].into()));
        let Some(m) = Mark::of(k) else {
            let n = roadstyle_model::mark::option_of_fill(k)?;
            return self.fills.get(n.checked_sub(1)?).map(|&f| id(f));
        };
        match m {
            Mark::Access => self.access.map(|a| a.map_or(Cell::Null, |k| Cell::Str(ACCESS_KINDS[k as usize]))),
            Mark::Color => self.color.map(|c| Cell::Json(values.at(c))),
            Mark::Twoway => b(self.twoway),
            Mark::Oneway => b(self.oneway),
            Mark::Dup => self.dup.then_some(Cell::Bool(true)),
            Mark::Edge2 => self.edge2.map(|e| Cell::Int(crate::road::key(e.get()).get() as i64)),
            Mark::Lvl => self.lvl.map(|l| Cell::Int(l.into())),
            Mark::Bridge => b(self.bridge),
            Mark::Tunnel => b(self.tunnel),
            Mark::Cap => self.cap.map(Cap::cell),
            Mark::Cap0 => caps.map(|c| c[0].cell()),
            Mark::Cap1 => caps.map(|c| c[1].cell()),
            Mark::Split => caps.map(|_| Cell::Bool(true)),
            Mark::HeadStart => self.head(values, 0).map(Cell::Float),
            Mark::HeadEnd => self.head(values, 1).map(Cell::Float),
            Mark::CasingLevel => lv(0),
            Mark::FillLevel => lv(1),
            Mark::CasingStart => lv(2),
            Mark::CasingEnd => lv(3),
            Mark::Band => self.levels.map(|_| Cell::Int(0)),
            Mark::Twin => self.twin.map(|t| Cell::Int(t.get() as i64)),
            Mark::WidthM => self.width_m().map(Cell::Float),
            Mark::CasingM => self.casing_m().map(Cell::Float),
            Mark::TwinWidthM => self.twin_width_m().map(Cell::Float),
            Mark::Edge => self.keyed.then(|| Cell::Int(crate::road::key(row).get() as i64)),
            Mark::Class => self.cls.map(|c| Cell::Json(values.at(c))),
            m => STYLE.iter().position(|s| *s == m).and_then(|i| self.style.map(|s| id(values.style(s)[i]))),
        }
    }
}

#[cfg(test)]
mod size {
    /// One `Draw` for each road (target_architecture.md (b) item 3): 288 bytes before the tight types (2026-10-25), 80 after (64-bit).
    #[test]
    fn a_road_draw_is_small() {
        assert!(std::mem::size_of::<super::Draw>() <= 80, "{} bytes", std::mem::size_of::<super::Draw>());
    }
}
