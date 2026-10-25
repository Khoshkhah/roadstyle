//! The errors of the road model: one kind for each cause, each with the text that the bindings show. The pattern of every crate's error:
//! commit 3e366ee (roadstyle-look); the rules: docs/design/target_architecture.md, (e).

use std::fmt;

/// An error of roadstyle-model, always in the input data (a regional build skips the table and logs it). `Display` gives its message;
/// `String::from` gives the same text, for a caller whose error is text.
#[derive(Clone, Debug, PartialEq)]
#[non_exhaustive]
pub enum Error {
    /// A column that the model does not take: a type that it does not read, a length that is not the table's, values of more than one
    /// type, a JSON array or object.
    Column { column: String, message: String },
    /// Geometries that the model does not take: bytes that are not WKB, a count that is not the count of the features.
    Geometry(String),
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::Column { column, message } => write!(f, "column {column}: {message}"),
            Error::Geometry(m) => f.write_str(m),
        }
    }
}

impl std::error::Error for Error {}

impl From<Error> for String {
    fn from(e: Error) -> String {
        e.to_string()
    }
}

/// A column error of `column`.
pub(crate) fn column(column: &str, message: impl Into<String>) -> Error {
    Error::Column { column: column.to_string(), message: message.into() }
}
