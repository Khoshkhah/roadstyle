//! The key of a road over all road tables (docs/design/target_architecture.md, (b) item 4): the table (a regional build's number; 0 for
//! one build) and the road's row in it, as one number. A piece, a slot and a deck carry their road's key (`__rs_edge`, the pieces'
//! `promoteId`), and the page sets the feature state on it.

use crate::Error;
use std::fmt;

/// A road's key: `table << 32 | row`. It stays below 2^53 while the table is below 2^21 (`TABLES`), so JavaScript holds it exactly and
/// MapLibre takes it as a feature id. For one build the table is 0, so the key is the road's row.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct RoadKey(u64);

impl RoadKey {
    /// The number of tables: a key of a table below it is below 2^53.
    pub const TABLES: u32 = 1 << 21;

    /// The key of the row `row` of the table `table`. An error for a table of `TABLES` or more.
    pub fn new(table: u32, row: u32) -> Result<RoadKey, Error> {
        if table >= Self::TABLES {
            return Err(Error::Key { table });
        }
        Ok(RoadKey((table as u64) << 32 | row as u64))
    }

    /// The key of the row `row` of a build of one table (table 0).
    pub const fn of_row(row: u32) -> RoadKey {
        RoadKey(row as u64)
    }

    /// The key from its number (a feature id, `__rs_edge`). None for a number of a table of `TABLES` or more.
    pub fn from_u64(key: u64) -> Option<RoadKey> {
        (key >> 32 < Self::TABLES as u64).then_some(RoadKey(key))
    }

    pub fn table(self) -> u32 {
        (self.0 >> 32) as u32
    }

    pub fn row(self) -> u32 {
        self.0 as u32
    }

    /// The key as one number (the feature id).
    pub fn get(self) -> u64 {
        self.0
    }
}

impl fmt::Display for RoadKey {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl serde::Serialize for RoadKey {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_u64(self.0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_key_is_the_table_and_the_row_below_2_53() {
        let k = RoadKey::new(3, 7).unwrap();
        assert_eq!((k.table(), k.row(), k.get()), (3, 7, 3 << 32 | 7));
        assert_eq!(RoadKey::of_row(7), RoadKey::new(0, 7).unwrap(), "one build: the key is the row");
        assert_eq!(RoadKey::of_row(7).get(), 7);
        let last = RoadKey::new(RoadKey::TABLES - 1, u32::MAX).unwrap();
        assert!(last.get() < 1 << 53, "JavaScript holds every key exactly");
        assert_eq!(last.get() as f64 as u64, last.get());
        assert_eq!(RoadKey::new(RoadKey::TABLES, 0), Err(Error::Key { table: RoadKey::TABLES }));
        assert_eq!(RoadKey::from_u64(last.get()), Some(last));
        assert_eq!(RoadKey::from_u64(1 << 53), None);
        assert_eq!(serde_json::to_string(&k).unwrap(), (3u64 << 32 | 7).to_string());
    }
}
