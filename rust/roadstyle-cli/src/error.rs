//! The errors of the program: one kind for each cause, each with the text that the program writes (the same text as before the type).

use std::fmt;

/// An error of a command. `Display` gives its message; `String::from` gives the same text.
#[derive(Clone, Debug, PartialEq)]
pub enum Error {
    /// A command, an argument, an option or a value that the program does not take (the text has the usage when it helps).
    Usage(String),
    /// A file that is not read or not written.
    File(String),
    /// The engine, a reader, the levels or Chromium refused the input: their text (the facade's errors are still text).
    Engine(String),
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::Usage(m) | Error::File(m) | Error::Engine(m) => f.write_str(m),
        }
    }
}

impl std::error::Error for Error {}

impl From<Error> for String {
    fn from(e: Error) -> String {
        e.to_string()
    }
}

/// The facade's errors, which are text.
impl From<String> for Error {
    fn from(m: String) -> Error {
        Error::Engine(m)
    }
}

/// The look's errors (roadstyle-look), as the engine's text.
impl From<roadstyle::look::Error> for Error {
    fn from(e: roadstyle::look::Error) -> Error {
        Error::Engine(e.to_string())
    }
}
