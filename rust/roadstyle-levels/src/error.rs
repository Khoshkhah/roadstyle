//! The errors of the levels: one kind for each cause, each with the text that the bindings show (the same text as before the type).

use std::fmt;

/// An error of the levels crate. `Display` gives its message; `String::from` gives the same text, for a caller whose error is text.
#[derive(Clone, Debug, PartialEq)]
pub enum Error {
    /// Options that are not correct: a keyword for another method, a margin or max_level not above 0, a fixed number or edge that is
    /// not possible.
    Options(String),
    /// Edges that the solver cannot use: a line of less than two points.
    Input(String),
    /// A row of the edits, the pairs or the heads that is not correct: an edge or road that is not there, an end that the relation
    /// does not have, an unknown relation, a pair to switch off that is not there, a head length that is not a positive number.
    Edits(String),
    /// The hard rules (with the fixed numbers) have no solution.
    NoSolution(String),
    /// An answer that failed the solver's own check (a bug of the solver, not of the input).
    Check(String),
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::Options(m) | Error::Input(m) | Error::Edits(m) | Error::NoSolution(m) | Error::Check(m) => f.write_str(m),
        }
    }
}

impl std::error::Error for Error {}

impl From<Error> for String {
    fn from(e: Error) -> String {
        e.to_string()
    }
}
