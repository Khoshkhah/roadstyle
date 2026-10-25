//! The errors of the look: one kind for each cause, each with the text that the bindings show (the same text as before the type).

use std::fmt;

/// An error of the look crate. `Display` gives its message; `String::from` gives the same text, for a caller whose error is text.
#[derive(Clone, Debug, PartialEq)]
pub enum Error {
    /// A saved look that this engine does not read: its JSON, or a part that it does not have.
    Look(String),
    /// A saved look of a later version (`found`) than this engine reads (`VERSION`).
    Version { found: u32 },
    /// Options of a look that are not correct: a key, a type of value, keys that go not together.
    Options(String),
    /// A name that is not bundled or given: a palette, a profile, a theme, a mode, a path style, a colour map, a colour, a texture or an
    /// icon.
    Unknown(String),
    /// A settings, profile or palette file that is not correct YAML or not a mapping.
    File(String),
    /// An image that is not read (a bundled PNG).
    Image(String),
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::Version { found } => write!(f, "look version {found}: this engine reads versions 0 to {}", crate::VERSION),
            Error::Look(m) | Error::Options(m) | Error::Unknown(m) | Error::File(m) | Error::Image(m) => f.write_str(m),
        }
    }
}

impl std::error::Error for Error {}

impl From<Error> for String {
    fn from(e: Error) -> String {
        e.to_string()
    }
}
