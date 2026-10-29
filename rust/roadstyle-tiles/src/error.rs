//! The errors of the tiles: one kind for each cause, each with the text that the bindings show. The pattern of every crate's error:
//! commit 3e366ee (roadstyle-look); the rules: docs/design/target_architecture.md, (e).

use std::fmt;

/// An error of roadstyle-tiles. `Display` gives its message; `String::from` gives the same text, for a caller whose error is text.
#[derive(Clone, Debug, PartialEq)]
#[non_exhaustive]
pub enum Error {
    /// Tile settings that are not correct: a style with no tile settings, a setting that is not a number, an extent that is not the
    /// tiles' own, zooms out of 0 to `MAX_ZOOM` or a first zoom after the last, bounds that are not longitude and latitude.
    Options(String),
    /// An archive with no tile: no feature in its bounds.
    Empty,
    /// A tile that the MLT encoder did not take (mlt-core's message).
    Mlt(String),
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::Options(m) => f.write_str(m),
            Error::Empty => f.write_str("the archive has no tile"),
            Error::Mlt(m) => write!(f, "MLT tile: {m}"),
        }
    }
}

impl std::error::Error for Error {}

impl From<Error> for String {
    fn from(e: Error) -> String {
        e.to_string()
    }
}
