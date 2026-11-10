//! The map terrain from the area's own ground (docs/design/ground_terrain.md): Terrarium PNG tiles in one PMTiles archive, made from a
//! ground grid (duckOSM `main.elevation_grid`: `col`, `row`, `lon`, `lat` of each pixel centre and its height `z`). The grid must be a full
//! rectangle, regular in longitude and latitude (duckOSM reads a DEM in EPSG:4326 only).
//!
//! A tile pixel's height is the bilinear value of the grid at the pixel's north-west corner: MapLibre reads pixel (i, j) of a DEM tile as the
//! height at the point (i, j) of the tile, not at its centre (measured on a plane: the centre gave all heights half a pixel's slope too
//! high, 0.84 m at z13). A pixel outside the grid gets the value at the nearest
//! edge of the grid, and a nodata cell gets the height of the nearest valid cell: MapLibre needs a height in every pixel, and a step to
//! 0 m at the edge of the area is worse. The Python binding, the CLI and the browser call `terrain_pmtiles`, so they make the same bytes.

use crate::pmtiles::{tile_id, Place, Writer};
use std::collections::VecDeque;
use std::f64::consts::PI;
use std::io::Write as _;

/// The tile type PNG of a PMTiles header.
const PNG: u8 = 2;
/// The last zoom is at most the roads' last zoom.
const MAX_ZOOM: u8 = 16;
/// The zooms below the last zoom that the archive has. ponytail: a fixed count; below it the map has no terrain from this file (MapLibre
/// requests no tile under the source's minzoom), so a page zoomed out to a country shows no smear of the area's edge over the world.
const ZOOMS_BELOW: u8 = 5;

/// A ground grid: the heights of the pixel centres, row by row from the north. Centre of (c, r): lon = west + (c + 0.5) dx,
/// lat = north - (r + 0.5) dy.
#[derive(Debug)]
pub struct Ground {
    pub west: f64,
    pub north: f64,
    pub dx: f64,
    pub dy: f64,
    pub cols: usize,
    pub rows: usize,
    z: Vec<f64>,
}

impl Ground {
    /// The grid from its cells (any order). `z`: NaN on nodata. An error when the cells are not a full rectangle of at least 2 x 2,
    /// when they are not regular in longitude and latitude, or when no cell has a height.
    pub fn from_cells(col: &[i32], row: &[i32], lon: &[f64], lat: &[f64], z: &[f64]) -> Result<Ground, String> {
        let n = col.len();
        if [row.len(), lon.len(), lat.len(), z.len()].iter().any(|&l| l != n) {
            return Err("the ground grid: the columns col, row, lon, lat and z must have the same length".into());
        }
        let (c0, c1) = (col.iter().min().copied().unwrap_or(0), col.iter().max().copied().unwrap_or(-1));
        let (r0, r1) = (row.iter().min().copied().unwrap_or(0), row.iter().max().copied().unwrap_or(-1));
        let (cols, rows) = ((c1 - c0 + 1).max(0) as usize, (r1 - r0 + 1).max(0) as usize);
        if cols < 2 || rows < 2 || cols * rows != n {
            return Err(format!("the ground grid must be a full rectangle of at least 2 x 2 cells: {n} cells, {cols} columns, {rows} rows"));
        }
        let fold = |v: &[f64], f: fn(f64, f64) -> f64, s: f64| v.iter().copied().fold(s, f);
        let (lon0, lon1) = (fold(lon, f64::min, f64::INFINITY), fold(lon, f64::max, f64::NEG_INFINITY));
        let (lat0, lat1) = (fold(lat, f64::min, f64::INFINITY), fold(lat, f64::max, f64::NEG_INFINITY));
        let (dx, dy) = ((lon1 - lon0) / (cols - 1) as f64, (lat1 - lat0) / (rows - 1) as f64);
        let mut g = Ground { west: lon0 - dx / 2.0, north: lat1 + dy / 2.0, dx, dy, cols, rows, z: vec![f64::NAN; n] };
        let mut seen = vec![false; n];
        for i in 0..n {
            let (c, r) = ((col[i] - c0) as usize, (row[i] - r0) as usize);
            let (elon, elat) = (g.west + (c as f64 + 0.5) * dx, g.north - (r as f64 + 0.5) * dy);
            if (lon[i] - elon).abs() > dx * 1e-3 || (lat[i] - elat).abs() > dy * 1e-3 {
                return Err(format!("the ground grid is not regular in lon and lat: cell ({c}, {r}) is at ({}, {}), not ({elon}, {elat})", lon[i], lat[i]));
            }
            let k = r * cols + c;
            if std::mem::replace(&mut seen[k], true) {
                return Err(format!("the ground grid has cell ({c}, {r}) two times"));
            }
            g.z[k] = z[i];
        }
        g.fill()?;
        Ok(g)
    }

    /// Each nodata cell takes the height of the nearest valid cell (in steps of 4 neighbours).
    fn fill(&mut self) -> Result<(), String> {
        let mut q: VecDeque<usize> = (0..self.z.len()).filter(|&k| self.z[k].is_finite()).collect();
        if q.is_empty() {
            return Err("the ground grid has no height".into());
        }
        while let Some(k) = q.pop_front() {
            let (r, c) = (k / self.cols, k % self.cols);
            let near = [(r > 0).then(|| k - self.cols), (r + 1 < self.rows).then(|| k + self.cols), (c > 0).then(|| k - 1), (c + 1 < self.cols).then(|| k + 1)];
            for j in near.into_iter().flatten() {
                if !self.z[j].is_finite() {
                    self.z[j] = self.z[k];
                    q.push_back(j);
                }
            }
        }
        Ok(())
    }

    /// The bilinear height of the grid at a point; outside the grid, the value at the nearest edge.
    pub fn height(&self, lon: f64, lat: f64) -> f64 {
        let fc = ((lon - self.west) / self.dx - 0.5).clamp(0.0, (self.cols - 1) as f64);
        let fr = ((self.north - lat) / self.dy - 0.5).clamp(0.0, (self.rows - 1) as f64);
        let (c, r) = ((fc as usize).min(self.cols - 2), (fr as usize).min(self.rows - 2));
        let (tx, ty) = (fc - c as f64, fr - r as f64);
        let at = |r: usize, c: usize| self.z[r * self.cols + c];
        (at(r, c) * (1.0 - tx) + at(r, c + 1) * tx) * (1.0 - ty) + (at(r + 1, c) * (1.0 - tx) + at(r + 1, c + 1) * tx) * ty
    }

    /// The last zoom: the first zoom whose pixel is not wider than a cell (east-west; the cosine of the latitude is the same on both
    /// sides), at most 16. 1 arc-second (a 30 m DEM): 13.
    pub fn max_zoom(&self) -> u8 {
        (0..MAX_ZOOM).find(|&z| 360.0 / (256.0 * f64::from(1u32 << z)) <= self.dx).unwrap_or(MAX_ZOOM)
    }

    /// The box of the grid: [west, south, east, north].
    pub fn bounds(&self) -> [f64; 4] {
        [self.west, self.north - self.rows as f64 * self.dy, self.west + self.cols as f64 * self.dx, self.north]
    }
}

/// The tile (x, y) of a point at zoom z.
fn tile_of(lon: f64, lat: f64, z: u8) -> (u32, u32) {
    let n = f64::from(1u32 << z);
    let y = (1.0 - (lat.to_radians().tan() + 1.0 / lat.to_radians().cos()).ln() / PI) / 2.0 * n;
    let clamp = |v: f64| (v.floor().max(0.0) as u32).min((1u32 << z) - 1);
    (clamp((lon + 180.0) / 360.0 * n), clamp(y))
}

/// The point of a place in a tile (u, v in pixels from the tile's north-west corner).
pub fn tile_point(z: u8, x: u32, y: u32, u: f64, v: f64) -> (f64, f64) {
    let n = 256.0 * f64::from(1u32 << z);
    let (px, py) = (f64::from(x) * 256.0 + u, f64::from(y) * 256.0 + v);
    (px / n * 360.0 - 180.0, (PI * (1.0 - 2.0 * py / n)).sinh().atan().to_degrees())
}

/// A height as Terrarium RGB: R * 256 + G + B / 256 - 32768, to the nearest 1/256 m.
pub fn terrarium(h: f64) -> [u8; 3] {
    let n = ((h + 32768.0) * 256.0).round().clamp(0.0, f64::from((1u32 << 24) - 1)) as u32;
    [(n >> 16) as u8, (n >> 8) as u8, n as u8]
}

/// One Terrarium PNG tile (256 x 256, RGB, each row with the filter Sub).
pub fn terrain_tile(g: &Ground, z: u8, x: u32, y: u32) -> Vec<u8> {
    let mut raw = Vec::with_capacity(256 * (1 + 256 * 3));
    for v in 0..256u16 {
        raw.push(1u8);
        let mut last = [0u8; 3];
        for u in 0..256u16 {
            let (lon, lat) = tile_point(z, x, y, f64::from(u), f64::from(v));
            let p = terrarium(g.height(lon, lat));
            raw.extend((0..3).map(|i| p[i].wrapping_sub(last[i])));
            last = p;
        }
    }
    let mut zl = flate2::write::ZlibEncoder::new(Vec::new(), flate2::Compression::new(6));
    zl.write_all(&raw).expect("a Vec takes every byte");
    let idat = zl.finish().expect("a Vec takes every byte");
    let mut ihdr = Vec::with_capacity(13);
    ihdr.extend(256u32.to_be_bytes());
    ihdr.extend(256u32.to_be_bytes());
    ihdr.extend([8, 2, 0, 0, 0]);
    let mut png = b"\x89PNG\r\n\x1a\n".to_vec();
    for (kind, data) in [(b"IHDR", &ihdr[..]), (b"IDAT", &idat[..]), (b"IEND", &[][..])] {
        png.extend((data.len() as u32).to_be_bytes());
        let mut crc = flate2::Crc::new();
        crc.update(kind);
        crc.update(data);
        png.extend(kind);
        png.extend(data);
        png.extend(crc.sum().to_be_bytes());
    }
    png
}

/// The terrain file: every tile over the grid's box, from 5 zooms below the last zoom to the last zoom, in one PMTiles archive. `ground`:
/// the ground's facts (JSON object: id, source, product, vertical_datum, resolution_m, license), written in the metadata.
pub fn terrain_pmtiles(g: &Ground, ground: &serde_json::Value) -> Vec<u8> {
    let (z1, [w, s, e, n]) = (g.max_zoom(), g.bounds());
    let z0 = z1.saturating_sub(ZOOMS_BELOW);
    let mut wr = Writer::plain();
    for z in z0..=z1 {
        let ((x0, y0), (x1, y1)) = (tile_of(w, n, z), tile_of(e, s, z));
        let mut tiles: Vec<(u64, u32, u32)> = (x0..=x1).flat_map(|x| (y0..=y1).map(move |y| (tile_id(u32::from(z), x, y), x, y))).collect();
        tiles.sort_unstable();
        for (id, x, y) in tiles {
            wr.write_tile(id, &terrain_tile(g, z, x, y));
        }
    }
    let e7 = |d: f64| (d * 1e7).round() as i32;
    let place = Place { min_lon_e7: e7(w), min_lat_e7: e7(s), max_lon_e7: e7(e), max_lat_e7: e7(n), center_zoom: z1,
                        center_lon_e7: e7((w + e) / 2.0), center_lat_e7: e7((s + n) / 2.0) };
    let meta = serde_json::json!({"name": "ground", "type": "baselayer", "format": "png", "encoding": "terrarium", "ground": ground});
    wr.finish(PNG, &place, &meta.to_string()).expect("the grid's box has at least one tile")
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Read as _;

    /// A tile's heights, decoded as MapLibre decodes them (this file writes only the filter Sub).
    fn decode(png: &[u8]) -> Vec<f64> {
        let idat_len = u32::from_be_bytes(png[33..37].try_into().unwrap()) as usize;
        assert_eq!(&png[37..41], b"IDAT");
        let mut raw = Vec::new();
        flate2::read::ZlibDecoder::new(&png[41..41 + idat_len]).read_to_end(&mut raw).unwrap();
        let mut out = Vec::with_capacity(256 * 256);
        for row in raw.chunks(1 + 256 * 3) {
            assert_eq!(row[0], 1);
            let mut p = [0u8; 3];
            for px in row[1..].chunks(3) {
                for i in 0..3 {
                    p[i] = p[i].wrapping_add(px[i]);
                }
                out.push(f64::from(p[0]) * 256.0 + f64::from(p[1]) + f64::from(p[2]) / 256.0 - 32768.0);
            }
        }
        out
    }

    /// A steep 1 arc-second grid near Monaco: a slope, a hill and a 60 m cliff, with nodata cells.
    fn cells() -> (Vec<i32>, Vec<i32>, Vec<f64>, Vec<f64>, Vec<f64>) {
        let (d, w, n) = (1.0 / 3600.0, 7.405, 43.752);
        let mut v = (vec![], vec![], vec![], vec![], vec![]);
        for r in 0..40 {
            for c in 0..50 {
                let (lon, lat) = (w + (c as f64 + 0.5) * d, n - (r as f64 + 0.5) * d);
                let h = 3.0 * c as f64 + 150.0 * ((r as f64) / 7.0).sin() + if c > 30 { 60.0 } else { 0.0 } - 20.0;
                v.0.push(c);
                v.1.push(r);
                v.2.push(lon);
                v.3.push(lat);
                v.4.push(if (r, c) == (5, 5) || (r, c) == (20, 44) { f64::NAN } else { h });
            }
        }
        v
    }

    /// The bilinear value of the input cells, written again here (not `Ground::height`); None next to nodata or outside the grid.
    fn expected(v: &(Vec<i32>, Vec<i32>, Vec<f64>, Vec<f64>, Vec<f64>), lon: f64, lat: f64) -> Option<f64> {
        let d = 1.0 / 3600.0;
        let (fc, fr) = ((lon - 7.405) / d - 0.5, (43.752 - lat) / d - 0.5);
        let (c, r) = (fc.floor(), fr.floor());
        if c < 0.0 || r < 0.0 || c >= 49.0 || r >= 39.0 {
            return None;
        }
        let at = |r: f64, c: f64| v.4[(r as usize) * 50 + c as usize];
        let (tx, ty) = (fc - c, fr - r);
        let h = (at(r, c) * (1.0 - tx) + at(r, c + 1.0) * tx) * (1.0 - ty) + (at(r + 1.0, c) * (1.0 - tx) + at(r + 1.0, c + 1.0) * tx) * ty;
        h.is_finite().then_some(h)
    }

    #[test]
    fn the_last_zoom_follows_the_resolution() {
        let v = cells();
        assert_eq!(Ground::from_cells(&v.0, &v.1, &v.2, &v.3, &v.4).unwrap().max_zoom(), 13);
    }

    /// The standard's check of the map terrain, at the tile pixels (docs/design/ground_terrain.md, "The checks", check 1): each pixel of
    /// each tile minus the grid's value at the pixel's point (its north-west corner), at most 0.10 m. Expected: the Terrarium step, 1/512 m.
    #[test]
    fn every_tile_pixel_equals_the_grid() {
        let v = cells();
        let g = Ground::from_cells(&v.0, &v.1, &v.2, &v.3, &v.4).unwrap();
        let [w, s, e, n] = g.bounds();
        let (mut worst, mut count) = (0.0f64, 0);
        for z in 8..=13 {
            let ((x0, y0), (x1, y1)) = (tile_of(w, n, z), tile_of(e, s, z));
            for x in x0..=x1 {
                for y in y0..=y1 {
                    for (i, h) in decode(&terrain_tile(&g, z, x, y)).into_iter().enumerate() {
                        let (lon, lat) = tile_point(z, x, y, (i % 256) as f64, (i / 256) as f64);
                        if let Some(want) = expected(&v, lon, lat) {
                            worst = worst.max((h - want).abs());
                            count += 1;
                        }
                    }
                }
            }
        }
        assert!(count > 1000, "{count} pixels over the grid");
        assert!(worst <= 1.0 / 512.0 + 1e-9, "the largest difference is {worst} m");
    }

    #[test]
    fn nodata_and_outside_take_the_nearest_height() {
        let v = cells();
        let g = Ground::from_cells(&v.0, &v.1, &v.2, &v.3, &v.4).unwrap();
        assert!((g.height(v.2[5 * 50 + 5], v.3[5 * 50 + 5]) - v.4[4 * 50 + 5]).abs() < 1e-6);       // (5, 5) is nodata: the cell north of it, found first
        assert!((g.height(0.0, 43.752 - 0.5 / 3600.0) - v.4[0]).abs() < 1e-6);                         // far to the west, at row 0's centre: cell (0, 0)
    }

    #[test]
    fn the_archive_has_png_tiles_from_z8_to_z13_and_the_ground() {
        let v = cells();
        let g = Ground::from_cells(&v.0, &v.1, &v.2, &v.3, &v.4).unwrap();
        let a = terrain_pmtiles(&g, &serde_json::json!({"id": "abc"}));
        assert_eq!(&a[..7], b"PMTiles");
        assert_eq!(&a[97..102], &[2, 1, PNG, 8, 13]);           // internal compression gzip, tile compression none, PNG, zooms 8 to 13
    }

    #[test]
    fn a_grid_with_a_hole_is_an_error() {
        let v = cells();
        let k = v.0.len() - 1;
        assert!(Ground::from_cells(&v.0[..k], &v.1[..k], &v.2[..k], &v.3[..k], &v.4[..k]).unwrap_err().contains("full rectangle"));
    }
}
