//! roadstyle-sim: the output of a traffic microsimulation (SUMO first) as one run (the samples, the vehicle types and the
//! lanes of the network), and the place of each vehicle at a clock time. The specification is
//! docs/design/vehicles_spec.md, sections 4 and 5.

mod fcd;
mod geo;
mod net;
mod track;

pub use fcd::{read_fcd_parquet, Samples, NONE};
pub use net::{read_net, read_vtypes, Lane, Net, VTypeRow};
pub use track::{Placement, Report, Run, RunOptions, VehicleState};

/// An error of this crate: the input is not what the reader needs. The message names the input and the problem.
#[derive(Debug)]
pub enum Error {
    Format(String),
    Crs(String),
    Options(String),
}

impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Error::Format(m) | Error::Crs(m) | Error::Options(m) => f.write_str(m),
        }
    }
}

impl std::error::Error for Error {}
