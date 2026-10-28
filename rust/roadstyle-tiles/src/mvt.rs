//! The Mapbox Vector Tile 2.1 encoding: the geometry commands, the varints and the layer message.

use super::*;

// --- the geometry commands (MoveTo 1, LineTo 2, ClosePath 7) with zigzag deltas ---

pub(crate) fn command(id: u32, count: usize) -> u32 {
    (id & 7) | ((count as u32) << 3)
}

pub(crate) fn zigzag(v: i32) -> u32 {
    ((v << 1) ^ (v >> 31)) as u32
}

pub(crate) struct Cursor(Vec<u32>, [i32; 2]);

impl Cursor {
    pub(crate) fn to(&mut self, p: [i32; 2]) {
        self.0.push(zigzag(p[0] - self.1[0]));
        self.0.push(zigzag(p[1] - self.1[1]));
        self.1 = p;
    }
}

pub(crate) fn points_cmd(ps: &[[i32; 2]]) -> Vec<u32> {
    let mut c = Cursor(Vec::new(), [0, 0]);
    if !ps.is_empty() {
        c.0.push(command(1, ps.len()));
        ps.iter().for_each(|&p| c.to(p));
    }
    c.0
}

pub(crate) fn lines_cmd(ls: &[Vec<[i32; 2]>]) -> Vec<u32> {
    let mut c = Cursor(Vec::new(), [0, 0]);
    for l in ls {
        c.0.push(command(1, 1));
        c.to(l[0]);
        c.0.push(command(2, l.len() - 1));
        l[1..].iter().for_each(|&p| c.to(p));
    }
    c.0
}

pub(crate) fn rings_cmd(rs: &[Vec<[i32; 2]>]) -> Vec<u32> {
    let mut c = Cursor(Vec::new(), [0, 0]);
    for r in rs {
        c.0.push(command(1, 1));
        c.to(r[0]);
        c.0.push(command(2, r.len() - 1));
        r[1..].iter().for_each(|&p| c.to(p));
        c.0.push(command(7, 1));
    }
    c.0
}

// --- protocol buffers: the tile with one layer ---

pub(crate) fn varint(out: &mut Vec<u8>, mut v: u64) {
    while v >= 0x80 {
        out.push((v as u8) | 0x80);
        v >>= 7;
    }
    out.push(v as u8);
}

pub(crate) fn bytes_field(out: &mut Vec<u8>, field: u32, data: &[u8]) {
    varint(out, ((field << 3) | 2) as u64);
    varint(out, data.len() as u64);
    out.extend_from_slice(data);
}

pub(crate) fn packed(out: &mut Vec<u8>, field: u32, vs: &[u32]) {
    let mut d = Vec::with_capacity(vs.len() * 2);
    vs.iter().for_each(|&v| varint(&mut d, v as u64));
    bytes_field(out, field, &d);
}

/// The bytes of a value's Value message in a tile, written to `m`.
pub(crate) fn encode_into(v: &Val<'_>, m: &mut Vec<u8>) {
    match v {
        Val::Str(s) => bytes_field(m, 1, s.as_bytes()),
        Val::Dbl(d) => {
            m.push((3 << 3) | 1);
            m.extend_from_slice(&d.to_le_bytes());
        }
        Val::Int(i) if *i < 0 => {
            m.push(6 << 3);
            varint(m, ((*i << 1) ^ (*i >> 63)) as u64);
        }
        Val::Int(i) => {
            m.push(5 << 3);
            varint(m, *i as u64);
        }
        Val::UInt(u) => {
            m.push(5 << 3);
            varint(m, *u);
        }
        Val::Bool(b) => {
            m.push(7 << 3);
            m.push(*b as u8);
        }
    }
}

/// One layer of a tile: its keys and values in the order they first come (the layer's numbers of them), and the features.
#[derive(Default)]
pub(crate) struct Encoder {
    pub(crate) features: Vec<u8>,
    pub(crate) keys: Vec<String>,
    pub(crate) key_at: HashMap<u32, u32>,
    pub(crate) values: Vec<u32>,
    pub(crate) value_at: HashMap<u32, u32>,
}

impl Encoder {
    pub(crate) fn feature(&mut self, f: &Feat, kind: u32, geometry: &[u32], names: &[String]) {
        let mut tags = Vec::with_capacity(f.props.len() * 2);
        for (k, v) in &f.props {
            let key = *self.key_at.entry(*k).or_insert_with(|| {
                self.keys.push(names[*k as usize].clone());
                self.keys.len() as u32 - 1
            });
            let at = *self.value_at.entry(*v).or_insert_with(|| {
                self.values.push(*v);
                self.values.len() as u32 - 1
            });
            tags.push(key);
            tags.push(at);
        }
        let mut msg = Vec::new();
        if let Some(id) = f.id {
            msg.push(1 << 3);
            varint(&mut msg, id);
        }
        packed(&mut msg, 2, &tags);
        msg.push(3 << 3);
        varint(&mut msg, kind as u64);
        packed(&mut msg, 4, geometry);
        bytes_field(&mut self.features, 2, &msg);
    }

    pub(crate) fn finish(self, name: &str, encoded: &[Vec<u8>]) -> Vec<u8> {
        if self.features.is_empty() {
            return Vec::new();
        }
        let mut layer = Vec::new();
        layer.push(15 << 3);
        varint(&mut layer, 2); // version
        bytes_field(&mut layer, 1, name.as_bytes());
        layer.extend_from_slice(&self.features);
        self.keys.iter().for_each(|k| bytes_field(&mut layer, 3, k.as_bytes()));
        self.values.iter().for_each(|&v| bytes_field(&mut layer, 4, &encoded[v as usize]));
        layer.push(5 << 3);
        varint(&mut layer, EXTENT as u64);
        let mut tile = Vec::with_capacity(layer.len() + 8);
        bytes_field(&mut tile, 3, &layer);
        tile
    }
}
