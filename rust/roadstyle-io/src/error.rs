//! The errors of the readers and the writers: one kind for each cause, each with the text that the bindings show (the same text as
//! before the type). The pattern of every crate's error: commit 3e366ee (roadstyle-look).

use std::fmt;

/// An error of roadstyle-io. `Display` gives its message; `String::from` gives the same text, for a caller whose error is text.
#[derive(Clone, Debug, PartialEq)]
pub enum Error {
    /// Bytes that are not a file of the kind (Parquet, GeoJSON, a Shapefile, a GeoPackage), or a part of the file that the reader does
    /// not read (a column type, a geometry that is not WKB).
    Format(String),
    /// A file that is read, with data that the call cannot use (the base map's background is not a polygon, a JSON column that is not
    /// JSON).
    Data(String),
    /// An argument of the call that is not correct (a mode that is not known, a map of one mode with no mode).
    Options(String),
    /// A duckOSM file with no stored levels, or with stored levels of other edges: make and solve its level area again.
    Levels(String),
    /// A file with no CRS, or a CRS that the reader cannot read or use.
    Crs(String),
    /// The Parquet writer stopped (Arrow or Parquet).
    Write(String),
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::Format(m) | Error::Data(m) | Error::Options(m) | Error::Levels(m) | Error::Crs(m) | Error::Write(m) => f.write_str(m),
        }
    }
}

impl std::error::Error for Error {}

/// A table or a geometry that the road model does not take: a part of the file that the reader does not read.
impl From<roadstyle_model::Error> for Error {
    fn from(e: roadstyle_model::Error) -> Error {
        Error::Format(e.to_string())
    }
}

impl From<Error> for String {
    fn from(e: Error) -> String {
        e.to_string()
    }
}
