//! The roles of the road table's columns (docs/design/target_architecture.md, (b) item 2): which column is the class, the edge id, the
//! bridge flag and the others. A caller names a role's column with a keyword (render's `highway_col`, ...); else the role has its
//! contract name (duckOSM's). The roles resolve one time to column indexes: the engine reads a role's cell by its index and writes the
//! table's own name in its expressions. No column is renamed, in or out.

use crate::{Cell, Error, RoadTable};

/// A role of a road column.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Role {
    Class,
    EdgeId,
    Tunnel,
    Bridge,
    Layer,
    CasingStart,
    CasingLevel,
    CasingEnd,
    FillLevel,
    HeadStartM,
    HeadEndM,
    CapStart,
    CapEnd,
    Directed,
    Driving,
}

impl Role {
    pub const ALL: [Role; 15] = [Role::Class, Role::EdgeId, Role::Tunnel, Role::Bridge, Role::Layer, Role::CasingStart, Role::CasingLevel,
                                 Role::CasingEnd, Role::FillLevel, Role::HeadStartM, Role::HeadEndM, Role::CapStart, Role::CapEnd,
                                 Role::Directed, Role::Driving];

    /// The contract name: the column of the role when no keyword names another one.
    pub fn name(self) -> &'static str {
        match self {
            Role::Class => "highway",
            Role::EdgeId => "edge_id",
            Role::Tunnel => "tunnel",
            Role::Bridge => "bridge",
            Role::Layer => "layer",
            Role::CasingStart => "casing_start",
            Role::CasingLevel => "casing_level",
            Role::CasingEnd => "casing_end",
            Role::FillLevel => "fill_level",
            Role::HeadStartM => "head_start_m",
            Role::HeadEndM => "head_end_m",
            Role::CapStart => "cap_start",
            Role::CapEnd => "cap_end",
            Role::Directed => "is_directed",
            Role::Driving => "has_arrows",
        }
    }

    /// The keyword that names the role's column (render's).
    pub fn keyword(self) -> &'static str {
        KEYWORDS[self as usize]
    }
}

const KEYWORDS: [&str; 15] = ["highway_col", "edge_id_col", "tunnel_col", "bridge_col", "layer_col", "casing_start_col", "casing_level_col",
                              "casing_end_col", "fill_level_col", "head_start_m_col", "head_end_m_col", "cap_start_col", "cap_end_col",
                              "directed_col", "driving_col"];

/// The roles of one road table: for each role, its column's index and name in the table (None: the table has no column for it).
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Roles {
    cols: [Option<usize>; 15],
    names: [Option<String>; 15],
}

impl Roles {
    /// The roles of `table`. `given`: the column that a keyword names for a role (None or "": the contract name). An error for a column
    /// that a keyword names and the table does not have, with the table's nearest names.
    pub fn resolve(table: &RoadTable, given: &[(Role, Option<&str>)]) -> Result<Roles, Error> {
        let mut r = Roles::default();
        for role in Role::ALL {
            let named = given.iter().find(|(g, _)| *g == role).and_then(|(_, n)| *n).filter(|n| !n.is_empty());
            let name = named.unwrap_or(role.name());
            match table.col(name) {
                Some(i) => (r.cols[role as usize], r.names[role as usize]) = (Some(i), Some(name.to_string())),
                None if named.is_some_and(|n| n != role.name()) => {
                    return Err(Error::MissingColumn { keyword: role.keyword().into(), column: name.into(), nearest: nearest(name, table.names()) });
                }
                None => {}
            }
        }
        Ok(r)
    }

    /// The index of the role's column.
    pub fn col(&self, role: Role) -> Option<usize> {
        self.cols[role as usize]
    }

    /// The table's own name of the role's column (the name that an expression gets).
    pub fn name(&self, role: Role) -> Option<&str> {
        self.names[role as usize].as_deref()
    }

    /// The role's cell of the road `row` (None: the table has no column for the role).
    pub fn cell<'a>(&self, table: &'a RoadTable, role: Role, row: usize) -> Option<Cell<'a>> {
        self.col(role).map(|c| table.cell(c, row))
    }
}

/// Up to three names of `names` nearest to `name` (edit distance at most 3, nearest first), for the error of a missing column.
fn nearest(name: &str, names: &[String]) -> Vec<String> {
    let mut d: Vec<(usize, &String)> = names.iter().map(|n| (distance(&name.to_lowercase(), &n.to_lowercase()), n)).filter(|(d, _)| *d <= 3).collect();
    d.sort();
    d.into_iter().take(3).map(|(_, n)| n.clone()).collect()
}

/// The edit distance (Levenshtein) of two texts, by characters.
fn distance(a: &str, b: &str) -> usize {
    let b: Vec<char> = b.chars().collect();
    let mut row: Vec<usize> = (0..=b.len()).collect();
    for (i, ca) in a.chars().enumerate() {
        let mut prev = row[0];
        row[0] = i + 1;
        for (j, cb) in b.iter().enumerate() {
            let cur = row[j + 1];
            row[j + 1] = (prev + usize::from(ca != *cb)).min(row[j] + 1).min(cur + 1);
            prev = cur;
        }
    }
    row[b.len()]
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::Lines;
    use arrow_array::{ArrayRef, StringArray};
    use std::sync::Arc;

    fn table(names: &[&str]) -> RoadTable {
        let mut lines = Lines::default();
        lines.push(None);
        let cols: Vec<ArrayRef> = names.iter().map(|_| Arc::new(StringArray::from(vec![Some("x")])) as ArrayRef).collect();
        RoadTable::new(names.iter().map(|n| n.to_string()).collect(), cols, lines).unwrap()
    }

    #[test]
    fn a_role_is_its_keywords_column_else_its_contract_name() {
        let t = table(&["fclass", "highway", "bridge", "edge"]);
        let r = Roles::resolve(&t, &[(Role::Class, Some("fclass")), (Role::EdgeId, Some("edge")), (Role::Tunnel, Some(""))]).unwrap();
        assert_eq!((r.col(Role::Class), r.name(Role::Class)), (Some(0), Some("fclass")), "the keyword's column, not the one named highway");
        assert_eq!((r.col(Role::Bridge), r.name(Role::Bridge)), (Some(2), Some("bridge")), "no keyword: the contract name");
        assert_eq!(r.name(Role::EdgeId), Some("edge"));
        assert_eq!(r.col(Role::Tunnel), None, "no column: no role (\"\" is no keyword)");
        assert_eq!(r.cell(&t, Role::Class, 0), Some(Cell::Str("x")));
        // a keyword with the contract name: the role is optional, as with no keyword
        assert_eq!(Roles::resolve(&t, &[(Role::Layer, Some("layer"))]).unwrap().col(Role::Layer), None);
    }

    #[test]
    fn a_missing_column_is_an_error_with_the_nearest_names() {
        let t = table(&["fclass", "class", "name", "bridge"]);
        let e = Roles::resolve(&t, &[(Role::Class, Some("fclas"))]).unwrap_err();
        assert_eq!(e, Error::MissingColumn { keyword: "highway_col".into(), column: "fclas".into(), nearest: vec!["fclass".into(), "class".into()] });
        assert_eq!(e.to_string(), "highway_col: the roads have no column fclas (the nearest: fclass, class)");
        let e = Roles::resolve(&t, &[(Role::EdgeId, Some("osm_way_id"))]).unwrap_err();
        assert_eq!(e.to_string(), "edge_id_col: the roads have no column osm_way_id");
        assert_eq!(distance("kitten", "sitting"), 3);
    }
}
