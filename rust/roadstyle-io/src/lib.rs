//! roadstyle's readers and writers (docs/design/rust_library.md, "The crates"): the roads and other tables from GeoParquet (`read`),
//! a table or a source's features as Parquet or GeoParquet (`write`, stage 1's files), and a table of typed columns (`columns`).

// Ported numeric code: index loops over parallel arrays and tuple types of the Python stages read as they are in Python.
#![allow(clippy::needless_range_loop, clippy::type_complexity)]

pub mod columns;
pub mod read;
pub mod write;
