//! roadstyle's readers (docs/design/rust_library.md, "The crates"): the roads and other tables from GeoParquet. The writers and the
//! other formats come later (phase P4).

// Ported numeric code: index loops over parallel arrays and tuple types of the Python stages read as they are in Python.
#![allow(clippy::needless_range_loop, clippy::type_complexity)]

pub mod read;
