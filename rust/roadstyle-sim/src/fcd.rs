//! SUMO's FCD output as Parquet (`--fcd-output fcd.parquet --fcd-output.geo true`, SUMO 1.24 and later) to the samples
//! of a run. The column names are SUMO's (`timestep_time`, `vehicle_id`, ...). Ids stay text in lists; the samples hold
//! indices into them (a SUMO edge id is a duckOSM `edge_id`, past 2**53).

use crate::Error;
use arrow_array::cast::AsArray;
use arrow_array::types::{Float32Type, Float64Type};
use arrow_array::{Array, ArrayRef, RecordBatch};
use arrow_schema::DataType;
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use std::collections::HashMap;

/// No value in an index column (`lane`).
pub const NONE: u32 = u32::MAX;

/// The samples of a run: one row per vehicle per time, in the order of the file (SUMO writes them by time).
#[derive(Debug, Default, Clone)]
pub struct Samples {
    pub t: Vec<f64>,
    /// index into `ids`
    pub id: Vec<u32>,
    /// lon, lat of the front bumper (SUMO's `x`, `y` with `--fcd-output.geo`)
    pub x: Vec<f64>,
    pub y: Vec<f64>,
    /// degrees, 0 = north, clockwise
    pub angle: Vec<f32>,
    /// m/s
    pub speed: Vec<f32>,
    /// the station of the front bumper on `lane`, m; NaN when the file has no `vehicle_pos`
    pub pos: Vec<f32>,
    /// index into `lanes`; NONE when the file has no lane for the row
    pub lane: Vec<u32>,
    /// the lateral offset (sublane model), m; NaN when the file has none
    pub pos_lat: Vec<f32>,
    /// index into `types`
    pub vtype: Vec<u16>,
    pub ids: Vec<String>,
    pub lanes: Vec<String>,
    pub types: Vec<String>,
    /// rows that the reader left out because they have no vehicle (a time step with no vehicle)
    pub empty_rows: usize,
}

impl Samples {
    pub fn len(&self) -> usize {
        self.t.len()
    }

    pub fn is_empty(&self) -> bool {
        self.t.is_empty()
    }
}

struct Interner(HashMap<String, u32>, Vec<String>);

impl Interner {
    fn new() -> Interner {
        Interner(HashMap::new(), Vec::new())
    }
    fn get(&mut self, s: &str) -> u32 {
        if let Some(&i) = self.0.get(s) {
            return i;
        }
        let i = self.1.len() as u32;
        self.0.insert(s.to_string(), i);
        self.1.push(s.to_string());
        i
    }
}

fn col<'a>(b: &'a RecordBatch, name: &str) -> Result<&'a ArrayRef, Error> {
    b.column_by_name(name).ok_or_else(|| Error::Format(format!("the FCD file has no column {name}: write it with --fcd-output.geo true")))
}

/// A float column (SUMO writes f64 and f32) as f64; a null is NaN.
fn floats(a: &ArrayRef, name: &str) -> Result<Vec<f64>, Error> {
    let n = a.len();
    let v: Vec<f64> = match a.data_type() {
        DataType::Float64 => {
            let p = a.as_primitive::<Float64Type>();
            (0..n).map(|i| if p.is_null(i) { f64::NAN } else { p.value(i) }).collect()
        }
        DataType::Float32 => {
            let p = a.as_primitive::<Float32Type>();
            (0..n).map(|i| if p.is_null(i) { f64::NAN } else { p.value(i) as f64 }).collect()
        }
        t => return Err(Error::Format(format!("the FCD column {name} is {t}, not a float"))),
    };
    Ok(v)
}

/// A text column (plain, large, view or dictionary) as optional strings.
fn texts(a: &ArrayRef, name: &str) -> Result<Vec<Option<String>>, Error> {
    let n = a.len();
    let v = match a.data_type() {
        DataType::Utf8 => {
            let s = a.as_string::<i32>();
            (0..n).map(|i| (!s.is_null(i)).then(|| s.value(i).to_string())).collect()
        }
        DataType::LargeUtf8 => {
            let s = a.as_string::<i64>();
            (0..n).map(|i| (!s.is_null(i)).then(|| s.value(i).to_string())).collect()
        }
        DataType::Utf8View => {
            let s = a.as_string_view();
            (0..n).map(|i| (!s.is_null(i)).then(|| s.value(i).to_string())).collect()
        }
        DataType::Dictionary(_, _) => {
            let d = a.as_any_dictionary();
            let values = texts(d.values(), name)?;
            let keys = d.normalized_keys();
            (0..n).map(|i| if d.is_null(i) { None } else { values[keys[i]].clone() }).collect()
        }
        t => return Err(Error::Format(format!("the FCD column {name} is {t}, not text"))),
    };
    Ok(v)
}

/// Reads the bytes of an FCD Parquet file.
pub fn read_fcd_parquet(bytes: Vec<u8>) -> Result<Samples, Error> {
    let fail = |e: &dyn std::fmt::Display| Error::Format(format!("the FCD Parquet file cannot be read: {e}"));
    let reader = ParquetRecordBatchReaderBuilder::try_new(bytes::Bytes::from(bytes)).map_err(|e| fail(&e))?.build().map_err(|e| fail(&e))?;
    let (mut ids, mut lanes, mut types) = (Interner::new(), Interner::new(), Interner::new());
    let mut s = Samples::default();
    for batch in reader {
        let b = batch.map_err(|e| fail(&e))?;
        let t = floats(col(&b, "timestep_time")?, "timestep_time")?;
        let id = texts(col(&b, "vehicle_id")?, "vehicle_id")?;
        let x = floats(col(&b, "vehicle_x")?, "vehicle_x")?;
        let y = floats(col(&b, "vehicle_y")?, "vehicle_y")?;
        let angle = floats(col(&b, "vehicle_angle")?, "vehicle_angle")?;
        let speed = floats(col(&b, "vehicle_speed")?, "vehicle_speed")?;
        let vtype = texts(col(&b, "vehicle_type")?, "vehicle_type")?;
        let pos = match b.column_by_name("vehicle_pos") { Some(a) => Some(floats(a, "vehicle_pos")?), None => None };
        let lane = match b.column_by_name("vehicle_lane") { Some(a) => Some(texts(a, "vehicle_lane")?), None => None };
        let pos_lat = match b.column_by_name("vehicle_posLat") { Some(a) => Some(floats(a, "vehicle_posLat")?), None => None };
        for i in 0..b.num_rows() {
            let Some(v) = &id[i] else {
                s.empty_rows += 1;
                continue;
            };
            if x[i].is_nan() || y[i].is_nan() || t[i].is_nan() {
                return Err(Error::Format(format!("the FCD row of vehicle {v} at t={} has no position", t[i])));
            }
            s.t.push(t[i]);
            s.id.push(ids.get(v));
            s.x.push(x[i]);
            s.y.push(y[i]);
            s.angle.push(angle[i] as f32);
            s.speed.push(speed[i] as f32);
            s.vtype.push(types.get(vtype[i].as_deref().unwrap_or("DEFAULT_VEHTYPE")) as u16);
            s.pos.push(pos.as_ref().map_or(f32::NAN, |p| p[i] as f32));
            s.lane.push(lane.as_ref().and_then(|l| l[i].as_deref()).map_or(NONE, |l| lanes.get(l)));
            s.pos_lat.push(pos_lat.as_ref().map_or(f32::NAN, |p| p[i] as f32));
        }
    }
    if types.1.len() > u16::MAX as usize {
        return Err(Error::Format(format!("the FCD file has {} vehicle types; the reader takes at most {}", types.1.len(), u16::MAX)));
    }
    s.ids = ids.1;
    s.lanes = lanes.1;
    s.types = types.1;
    Ok(s)
}
