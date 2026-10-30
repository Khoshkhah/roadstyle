//! The errors of the engine: one kind for each cause, with the text that the bindings show. The pattern of every crate's error: commit
//! 3e366ee (roadstyle-look); the rules: docs/design/target_architecture.md, (e). A message names no binding: a binding adds its own
//! advice.

use std::fmt;

/// An error of roadstyle-engine. `Display` gives its message; `String::from` gives the same text, for a caller whose error is text.
/// A regional build tells the kinds apart: `Data`, `Column` and `Model` are in the input data (skip and log), the others in the options
/// (stop).
#[derive(Clone, Debug, PartialEq)]
#[non_exhaustive]
pub enum Error {
    /// A column that an option names and the roads do not have, or whose values do not fit (color_by, access_col, edge_id_col,
    /// color_key).
    Column { column: String, message: String },
    /// An option that is not correct: its shape, its value, or options that do not go together.
    Options(String),
    /// Input data that the engine does not take: an overlay's edge that is not a road, a building with no height, levels solved for
    /// other edges, a part of a feature table that is not there.
    Data(String),
    /// More than the engine draws (`found` of `what`, at most `max`).
    Limit { what: Limit, found: usize, max: usize },
    /// A part of the look or the options that this engine does not draw.
    Unsupported(Unsupported),
    /// The look (roadstyle-look's error).
    Look(roadstyle_look::Error),
    /// The drawing positions (roadstyle-levels' error).
    Levels(roadstyle_levels::Error),
    /// A table of the roads or of the base map (roadstyle-model's error: in the input data).
    Model(roadstyle_model::Error),
}

/// What a `Limit` counts.
#[derive(Clone, Copy, Debug, PartialEq)]
#[non_exhaustive]
pub enum Limit {
    /// the roads of an area that a browser page draws (MAX_ROADS: the browser's memory)
    Roads,
    /// the edges of simple mode (the sort key's tie-breaker and the feature ids)
    Edges,
    /// the pieces of one edge in simple mode (its feature ids), `edge`: the edge
    Pieces { edge: usize },
    /// the items of one edge in simple mode (they fit between its fill and the next casings), `edge`: the edge
    Items { edge: usize },
}

/// A part that this engine does not draw.
#[derive(Clone, Debug, PartialEq)]
#[non_exhaustive]
pub enum Unsupported {
    /// A Styler object: the engine takes color_by, colors, cmap, vmin, vmax and width_by.
    Styler,
    /// A palette other than the look's.
    Palette { palette: String, look: String },
    /// A view's palette that changes `key` of an item and not of its road.
    ItemPalette { palette: String, key: String },
    /// An overlay's line item that is a MultiLineString (the engine draws LineString items).
    MultiLineItem { overlay: String, item: usize },
    /// Line items of an overlay from a typed table (only a caller's overlay has items).
    TableItems { overlay: String },
    /// A tiled page with a view's palette (the tiles have one palette).
    TiledPalettes,
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::Column { column, message } => write!(f, "column {column}: {message}"),
            Error::Options(m) | Error::Data(m) => f.write_str(m),
            Error::Limit { what, found, max } => match what {
                Limit::Roads => write!(f, "this area has {found} roads, and a browser page draws at most {max} (its memory): use a smaller area"),
                Limit::Edges => write!(f, "simple mode: {found} edges, at most {max}"),
                Limit::Pieces { edge } => write!(f, "simple mode: edge {edge} has more than {max} pieces"),
                Limit::Items { edge } => write!(f, "simple mode: edge {edge} has more than {max} items; they do not fit between its fill and the next casings"),
            },
            Error::Unsupported(u) => match u {
                Unsupported::Styler => f.write_str("a Styler object (style=) is not in this engine: use color_by, colors, cmap, vmin, vmax or width_by"),
                Unsupported::Palette { palette, look } => write!(f, "palette {palette:?}: this engine has the look's palette ({look:?}) only"),
                Unsupported::ItemPalette { palette, key } => write!(f, "palette {palette:?} changes {key} of an item and not of its road: not in this engine"),
                Unsupported::MultiLineItem { overlay, item } => write!(f, "overlay {overlay}: item {item} is a MultiLineString; this engine draws LineString items only"),
                Unsupported::TableItems { overlay } => write!(f, "overlay {overlay}: line items from a typed table are not made (only a caller's overlay has items)"),
                Unsupported::TiledPalettes => f.write_str("tiles=True with a view's palette: the tiles have one palette (a page with a palette in a view needs tiles=False)"),
            },
            Error::Look(e) => e.fmt(f),
            Error::Levels(e) => e.fmt(f),
            Error::Model(e) => e.fmt(f),
        }
    }
}

impl std::error::Error for Error {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Error::Look(e) => Some(e),
            Error::Levels(e) => Some(e),
            Error::Model(e) => Some(e),
            _ => None,
        }
    }
}

impl From<Error> for String {
    fn from(e: Error) -> String {
        e.to_string()
    }
}

impl From<roadstyle_look::Error> for Error {
    fn from(e: roadstyle_look::Error) -> Error {
        Error::Look(e)
    }
}

impl From<roadstyle_levels::Error> for Error {
    fn from(e: roadstyle_levels::Error) -> Error {
        Error::Levels(e)
    }
}

impl From<roadstyle_model::Error> for Error {
    fn from(e: roadstyle_model::Error) -> Error {
        Error::Model(e)
    }
}

/// A column error of `column`.
pub(crate) fn column(column: &str, message: impl Into<String>) -> Error {
    Error::Column { column: column.to_string(), message: message.into() }
}

/// An options error.
pub(crate) fn options(message: impl Into<String>) -> Error {
    Error::Options(message.into())
}

/// A data error.
pub(crate) fn data(message: impl Into<String>) -> Error {
    Error::Data(message.into())
}
