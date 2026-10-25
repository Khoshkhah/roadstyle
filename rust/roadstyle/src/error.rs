//! The errors of the facade: a kind for each crate's error, and the facade's own (the page's options, the files of the stages, the level
//! editor's input). The pattern of every crate's error: commit 3e366ee (roadstyle-look); the rules: docs/design/target_architecture.md,
//! (e). A message names no binding: a binding adds its own advice.

use std::fmt;

/// An error of the facade. `Display` gives its message; `String::from` gives the same text, for a caller whose error is text.
#[derive(Clone, Debug, PartialEq)]
#[non_exhaustive]
pub enum Error {
    /// The engine's error (stage 1: the look on the roads).
    Engine(roadstyle_engine::Error),
    /// The tiles' error (stage 2).
    Tiles(roadstyle_tiles::Error),
    /// A file that roadstyle-io does not read or write.
    Io(roadstyle_io::Error),
    /// A table of the roads or of the base map (in the input data).
    Model(roadstyle_model::Error),
    /// The look.
    Look(roadstyle_look::Error),
    /// The drawing positions.
    Levels(roadstyle_levels::Error),
    /// A page or stage-2 option that is not correct, or options that do not go together.
    Options(String),
    /// A file of a stage or of a level area that is not read, written or parsed (`name`: the file).
    File { name: String, message: String },
    /// The level editor's input that is not correct: pairs.csv, heads.csv, the edits, the level numbers.
    Edits(String),
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::Engine(e) => e.fmt(f),
            Error::Tiles(e) => e.fmt(f),
            Error::Io(e) => e.fmt(f),
            Error::Model(e) => e.fmt(f),
            Error::Look(e) => e.fmt(f),
            Error::Levels(e) => e.fmt(f),
            Error::Options(m) | Error::Edits(m) => f.write_str(m),
            Error::File { name, message } => write!(f, "{name}: {message}"),
        }
    }
}

impl std::error::Error for Error {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Error::Engine(e) => Some(e),
            Error::Tiles(e) => Some(e),
            Error::Io(e) => Some(e),
            Error::Model(e) => Some(e),
            Error::Look(e) => Some(e),
            Error::Levels(e) => Some(e),
            _ => None,
        }
    }
}

impl From<Error> for String {
    fn from(e: Error) -> String {
        e.to_string()
    }
}

macro_rules! from {
    ($($kind:ident: $t:ty),*) => {$(
        impl From<$t> for Error {
            fn from(e: $t) -> Error {
                Error::$kind(e)
            }
        }
    )*};
}
from!(Engine: roadstyle_engine::Error, Tiles: roadstyle_tiles::Error, Io: roadstyle_io::Error, Model: roadstyle_model::Error,
      Look: roadstyle_look::Error, Levels: roadstyle_levels::Error);

/// An options error.
pub(crate) fn options(message: impl Into<String>) -> Error {
    Error::Options(message.into())
}

/// A file error of `name`.
pub(crate) fn file(name: impl fmt::Display, message: impl fmt::Display) -> Error {
    Error::File { name: name.to_string(), message: message.to_string() }
}

/// A level editor input error.
pub(crate) fn edits(message: impl Into<String>) -> Error {
    Error::Edits(message.into())
}
