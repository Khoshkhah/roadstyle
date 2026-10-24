//! The PNG images of the look: a texture's mask (8-bit grey) read, and a texture in its colour (8-bit RGBA) written. Only the forms
//! that the bundled files and the textures use: no interlace, no palette, 8 bits to a channel.

use crate::Error;
use std::io::{Read, Write};

/// The pixels of an 8-bit PNG with no interlace: (width, height, channels, the rows one after the other).
pub fn decode(png: &[u8]) -> Result<(usize, usize, usize, Vec<u8>), Error> {
    if png.get(..8) != Some(b"\x89PNG\r\n\x1a\n".as_slice()) {
        return Err(Error::Image("not a PNG".into()));
    }
    let (mut i, mut head, mut data) = (8, None, Vec::new());
    while i + 8 <= png.len() {
        let n = u32::from_be_bytes(png[i..i + 4].try_into().unwrap()) as usize;
        let body = png.get(i + 8..i + 8 + n).ok_or_else(|| Error::Image("a PNG chunk past the end".into()))?;
        match &png[i + 4..i + 8] {
            b"IHDR" => head = Some((u32::from_be_bytes(body[0..4].try_into().unwrap()) as usize,
                                    u32::from_be_bytes(body[4..8].try_into().unwrap()) as usize, body[8], body[9], body[12])),
            b"IDAT" => data.extend_from_slice(body),
            _ => {}
        }
        i += 12 + n;
    }
    let (w, h, depth, color, interlace) = head.ok_or_else(|| Error::Image("a PNG with no IHDR".into()))?;
    let ch = match (depth, color, interlace) {
        (8, 0, 0) => 1,
        (8, 2, 0) => 3,
        (8, 4, 0) => 2,
        (8, 6, 0) => 4,
        _ => return Err(Error::Image(format!("a PNG of bit depth {depth}, colour type {color}, interlace {interlace}: not read"))),
    };
    let mut raw = Vec::new();
    flate2::read::ZlibDecoder::new(&data[..]).read_to_end(&mut raw).map_err(|e| Error::Image(format!("PNG data: {e}")))?;
    let stride = w * ch;
    if raw.len() < h * (stride + 1) {
        return Err(Error::Image("PNG data: too short".into()));
    }
    let mut out = vec![0u8; h * stride];
    for y in 0..h {
        let (filter, line) = (raw[y * (stride + 1)], &raw[y * (stride + 1) + 1..(y + 1) * (stride + 1)]);
        for x in 0..stride {
            let a = if x >= ch { out[y * stride + x - ch] as i32 } else { 0 };
            let b = if y > 0 { out[(y - 1) * stride + x] as i32 } else { 0 };
            let c = if x >= ch && y > 0 { out[(y - 1) * stride + x - ch] as i32 } else { 0 };
            let pred = match filter {
                0 => 0,
                1 => a,
                2 => b,
                3 => (a + b) / 2,
                4 => {
                    let p = a + b - c;
                    let (pa, pb, pc) = ((p - a).abs(), (p - b).abs(), (p - c).abs());
                    if pa <= pb && pa <= pc { a } else if pb <= pc { b } else { c }
                }
                f => return Err(Error::Image(format!("PNG data: filter {f}"))),
            };
            out[y * stride + x] = (line[x] as i32 + pred) as u8;
        }
    }
    Ok((w, h, ch, out))
}

/// An 8-bit RGBA PNG of `w` x `h` pixels (`rgba`: the rows one after the other).
pub fn encode_rgba(w: usize, h: usize, rgba: &[u8]) -> Vec<u8> {
    let mut raw = Vec::with_capacity(h * (4 * w + 1));
    for row in rgba.chunks(4 * w) {
        raw.push(0);
        raw.extend_from_slice(row);
    }
    let mut z = flate2::write::ZlibEncoder::new(Vec::new(), flate2::Compression::best());
    z.write_all(&raw).expect("a Vec takes every byte");
    let mut ihdr = Vec::new();
    ihdr.extend((w as u32).to_be_bytes());
    ihdr.extend((h as u32).to_be_bytes());
    ihdr.extend([8, 6, 0, 0, 0]);
    let mut out = b"\x89PNG\r\n\x1a\n".to_vec();
    for (kind, body) in [(&b"IHDR"[..], ihdr), (b"IDAT", z.finish().expect("a Vec takes every byte")), (b"IEND", Vec::new())] {
        out.extend((body.len() as u32).to_be_bytes());
        let start = out.len();
        out.extend_from_slice(kind);
        out.extend_from_slice(&body);
        let crc = crc32fast::hash(&out[start..]);
        out.extend(crc.to_be_bytes());
    }
    out
}

#[cfg(test)]
mod tests {
    #[test]
    fn an_image_written_reads_back() {
        let px: Vec<u8> = (0..3 * 2 * 4).map(|i| (i * 37 % 256) as u8).collect();
        let (w, h, ch, back) = super::decode(&super::encode_rgba(3, 2, &px)).unwrap();
        assert_eq!((w, h, ch, back), (3, 2, 4, px));
    }
}
