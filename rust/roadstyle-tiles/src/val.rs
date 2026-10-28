//! The values of a tile feature's properties.

use super::*;

/// A value of a tile feature (the vector tile spec's value kinds that the tiles use).
/// A layer keeps `Val<'static>`; a property that is read borrows its text (no copy of a value that the layer has).
#[derive(Clone, PartialEq)]
pub enum Val<'a> {
    Str(std::borrow::Cow<'a, str>),
    Bool(bool),
    Int(i64),
    UInt(u64),
    Dbl(f64),
}

/// A property's value as the tiles keep it: a JSON value, or a cell of the roads' Arrow columns (audit N5: no JSON copy of each cell).
pub trait TileValue {
    fn tile_val(&self) -> Option<Val<'_>>;
}

impl TileValue for Value {
    fn tile_val(&self) -> Option<Val<'_>> {
        val(self)
    }
}

impl TileValue for roadstyle_model::Cell<'_> {
    fn tile_val(&self) -> Option<Val<'_>> {
        use roadstyle_model::Cell;
        Some(match *self {
            Cell::Null => return None,
            Cell::Bool(b) => Val::Bool(b),
            // an integer past 2**53 - 1 as text, as every JSON form writes it
            Cell::Int(i) if i.unsigned_abs() > roadstyle_model::table::JS_MAX_SAFE_INT => Val::Str(i.to_string().into()),
            Cell::Int(i) => Val::Int(i),
            Cell::Float(f) if f.is_finite() => Val::Dbl(f),
            Cell::Float(_) => return None,
            Cell::Str(s) => Val::Str(s.into()),
            Cell::Json(v) => return val(v),
        })
    }
}

pub(crate) fn val(v: &Value) -> Option<Val<'_>> {
    Some(match v {
        Value::String(s) => Val::Str(s.as_str().into()),
        Value::Bool(b) => Val::Bool(*b),
        Value::Number(n) => match (n.as_i64(), n.as_u64()) {
            // an integer past 2**53 - 1 as text, as every JSON form writes it
            (Some(i), _) if i.unsigned_abs() > roadstyle_model::table::JS_MAX_SAFE_INT => Val::Str(i.to_string().into()),
            (_, Some(u)) if u > roadstyle_model::table::JS_MAX_SAFE_INT => Val::Str(u.to_string().into()),
            (Some(i), _) => Val::Int(i),
            (_, Some(u)) => Val::UInt(u),
            _ => Val::Dbl(n.as_f64()?),
        },
        Value::Null | Value::Array(_) | Value::Object(_) => return None, // (mapbox_vector_tile) leaves out a list or an object
    })
}

impl Val<'_> {
    /// The value with its own text (a layer keeps it).
    pub(crate) fn owned(&self) -> Val<'static> {
        match self {
            Val::Str(s) => Val::Str(std::borrow::Cow::Owned(s.to_string())),
            Val::Bool(b) => Val::Bool(*b),
            Val::Int(i) => Val::Int(*i),
            Val::UInt(u) => Val::UInt(*u),
            Val::Dbl(d) => Val::Dbl(*d),
        }
    }
}

pub(crate) fn json_of(v: &Val<'_>) -> Value {
    match v {
        Val::Str(s) => Value::from(&**s),
        Val::Bool(b) => Value::from(*b),
        Val::Int(i) => Value::from(*i),
        Val::UInt(u) => Value::from(*u),
        Val::Dbl(d) => Value::from(*d),
    }
}
