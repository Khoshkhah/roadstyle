//! A PMTiles v3 archive: the tiles gzipped, each
//! content once (a run of one content on consecutive tile ids is one entry), the directory in one root (or a root of leaves when it is
//! more than 16 KB), the metadata as gzipped JSON. The gzip streams have no time in them.

use std::collections::HashMap;
use std::io::Write;

/// zxy_to_tileid: the tile's place on the Hilbert curve of its zoom, after the tiles of the lower zooms.
pub fn tile_id(z: u32, x: u32, y: u32) -> u64 {
    let (mut x, mut y) = (x as u64, y as u64);
    let mut acc: u64 = ((1u64 << (z * 2)) - 1) / 3;
    for a in (0..z).rev() {
        let s = 1u64 << a;
        let (rx, ry) = (s & x, s & y);
        acc += ((3 * rx) ^ ry) << a;
        if ry == 0 {
            if rx != 0 {
                // go-pmtiles' ZxyToID (rotate(s, ...) on uint32) wraps here when x or y >= s; the steps after this one read only the
                // bits below s, and s - 1 - x and n - 1 - x differ by a multiple of s, so the wrapped value is the right one
                x = s.wrapping_sub(1).wrapping_sub(x);
                y = s.wrapping_sub(1).wrapping_sub(y);
            }
            std::mem::swap(&mut x, &mut y);
        }
    }
    acc
}

#[derive(Clone, Copy)]
struct Entry {
    id: u64,
    offset: u64,
    length: u64,
    run: u64,
}

pub(crate) fn gzip(data: &[u8]) -> Vec<u8> {
    let mut e = flate2::GzBuilder::new().mtime(0).write(Vec::new(), flate2::Compression::new(6));
    e.write_all(data).unwrap();
    e.finish().unwrap()
}

fn varint(out: &mut Vec<u8>, mut i: u64) {
    loop {
        let b = (i & 0x7f) as u8;
        i >>= 7;
        if i == 0 {
            out.push(b);
            return;
        }
        out.push(b | 0x80);
    }
}

fn directory(entries: &[Entry]) -> Vec<u8> {
    let mut b = Vec::new();
    varint(&mut b, entries.len() as u64);
    let mut last = 0;
    for e in entries {
        varint(&mut b, e.id - last);
        last = e.id;
    }
    for e in entries {
        varint(&mut b, e.run);
    }
    for e in entries {
        varint(&mut b, e.length);
    }
    for (i, e) in entries.iter().enumerate() {
        varint(&mut b, if i > 0 && e.offset == entries[i - 1].offset + entries[i - 1].length { 0 } else { e.offset + 1 });
    }
    gzip(&b)
}

/// The archive's place: the bounds and the centre in degrees x 1e7, and the centre's zoom.
pub struct Place {
    pub min_lon_e7: i32,
    pub min_lat_e7: i32,
    pub max_lon_e7: i32,
    pub max_lat_e7: i32,
    pub center_zoom: u8,
    pub center_lon_e7: i32,
    pub center_lat_e7: i32,
}

/// The Writer: tiles in any order (`clustered` when in tile id order), then `finish`.
#[derive(Default)]
pub struct Writer {
    entries: Vec<Entry>,
    seen: HashMap<Vec<u8>, u64>,
    data: Vec<u8>,
    addressed: u64,
    unordered: bool,
}

impl Writer {
    /// A tile's bytes as they go into the archive (gzipped vector tiles: tile compression gzip).
    pub fn write_tile(&mut self, id: u64, data: &[u8]) {
        if self.entries.last().is_some_and(|l| id < l.id) {
            self.unordered = true;
        }
        match self.seen.get(data) {
            Some(&found) => {
                let last = self.entries.last_mut().unwrap();
                if id == last.id + last.run && last.offset == found {
                    last.run += 1;
                } else {
                    self.entries.push(Entry { id, offset: found, length: data.len() as u64, run: 1 });
                }
            }
            None => {
                self.entries.push(Entry { id, offset: self.data.len() as u64, length: data.len() as u64, run: 1 });
                self.seen.insert(data.to_vec(), self.data.len() as u64);
                self.data.extend_from_slice(data);
            }
        }
        self.addressed += 1;
    }

    /// The archive: the header (127 bytes), the root directory, the metadata (JSON text), the leaves and the tiles. None: no tile.
    pub fn finish(mut self, place: &Place, metadata: &str) -> Option<Vec<u8>> {
        let (contents, entries_n) = (self.seen.len() as u64, self.entries.len() as u64);
        self.entries.sort_by_key(|e| e.id);
        let zoom = |id: u64| ((64 - (3 * id + 1).leading_zeros()) - 1) / 2;
        let (min_zoom, max_zoom) = (zoom(self.entries.first()?.id), zoom(self.entries.last()?.id));
        let (root, leaves) = {
            let all = directory(&self.entries);
            if all.len() < 16384 - 127 {
                (all, Vec::new())
            } else {
                let mut size = 4096;
                loop {
                    let (mut roots, mut leaves) = (Vec::new(), Vec::new());
                    for chunk in self.entries.chunks(size) {
                        let d = directory(chunk);
                        roots.push(Entry { id: chunk[0].id, offset: leaves.len() as u64, length: d.len() as u64, run: 0 });
                        leaves.extend(d);
                    }
                    let r = directory(&roots);
                    if r.len() < 16384 - 127 {
                        break (r, leaves);
                    }
                    size *= 2;
                }
            }
        };
        let meta = gzip(metadata.as_bytes());
        let (root_off, meta_off) = (127u64, 127 + root.len() as u64);
        let leaf_off = meta_off + meta.len() as u64;
        let data_off = leaf_off + leaves.len() as u64;
        let mut h = Vec::with_capacity(127);
        h.extend_from_slice(b"PMTiles");
        h.push(3);
        for v in [root_off, root.len() as u64, meta_off, meta.len() as u64, leaf_off, leaves.len() as u64, data_off, self.data.len() as u64,
                  self.addressed, entries_n, contents] {
            h.extend_from_slice(&v.to_le_bytes());
        }
        // clustered, internal compression (gzip), tile compression (gzip), tile type (MVT), the zooms
        h.extend_from_slice(&[(!self.unordered) as u8, 2, 2, 1, min_zoom as u8, max_zoom as u8]);
        for v in [place.min_lon_e7, place.min_lat_e7, place.max_lon_e7, place.max_lat_e7] {
            h.extend_from_slice(&v.to_le_bytes());
        }
        h.push(place.center_zoom);
        h.extend_from_slice(&place.center_lon_e7.to_le_bytes());
        h.extend_from_slice(&place.center_lat_e7.to_le_bytes());
        let mut out = h;
        out.extend(root);
        out.extend(meta);
        out.extend(leaves);
        out.extend(self.data);
        Some(out)
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn tile_ids_are_the_pmtiles_ones() {
        // zxy_to_tileid of the pmtiles package
        for ((z, x, y), id) in [((0, 0, 0), 0), ((1, 0, 0), 1), ((1, 0, 1), 2), ((1, 1, 1), 3), ((1, 1, 0), 4), ((2, 0, 0), 5), ((12, 2132, 1493), 19832288), ((15, 17068, 11949), 1269266272)] {
            assert_eq!(super::tile_id(z, x, y), id, "{z}/{x}/{y}");
        }
    }
}
