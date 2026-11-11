//! `roadstyle local` (way D, docs/guides/data-and-memory.md): the engine as a program on 127.0.0.1. It answers the four requests of the dashboard
//! (dashboard/adapter.js, `rsHttpAdapter`) from the files on the disk:
//!
//! | address | answer | made by |
//! |---|---|---|
//! | `GET /style.json` | the roads' style, with the tile addresses of this program | the engine (`tiled_sources`) |
//! | `GET /tiles/<source>/<z>/<x>/<y>` | one tile (204: none) | the engine (`Tiles::tile_in`): the bytes of the map worker's tile |
//! | `POST /rows/<source>` `[id, ...]` | the fields of each road | the engine (the road table, `write_road_table`) |
//! | `POST /lines` `[id, ...]` | the line of each road | the engine (`write_road_lines`) |
//! | `POST /query` `{"sql"}`, `GET /schema` | a result, the tables | DuckDB on the Parquet files and the tables of a `.duckdb` file |
//! | `GET /frames?from=&to=` | a window of frames | DuckDB on the file of the run |
//! | `GET /road_table`, `GET /road_ends` | the whole road table (JSON: props, mids, bboxes), and the two ends of each road (f64 LE) | the engine (`write_road_table`, `road_ends`) |
//! | `POST /walls` (GeoJSON of `rsSetWalls`) | `{"source", "walls"}`: the 3D walls as tiles of this map (`GET /tiles/walls/...`) | the engine (`LiveTiles::set_walls`) |
//! | `POST /relevel` `[levels.csv rows]` | `{"counts", "style"}`: the changed roads are drawn again (the style when its layers changed) | the engine (`relevel::LiveTiles`) |
//!
//! The server (roadstyle-serve) moves bytes and the functions here call the engine or DuckDB: this crate has no rule of its own for a tile, a
//! row or a line (rule 1 of the guide). The page files come from roadstyle-assets (`local/`, the dashboard).

// with no DuckDB (the feature `duckdb` off) the program has no queries, schema or frames: the files are not read
#![cfg_attr(not(feature = "duckdb"), allow(dead_code, unused_imports))]

use roadstyle::relevel::LiveTiles;
use roadstyle_serve::{Api, Page, Request, Response};
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

/// What the program is given: the roads (read by the caller), the base-map rows (buildings, water, ...: read by the caller; their sources go in the
/// tiles as the look says), the roads' file (the table `roads` of the queries; none for another format), a `.duckdb` file (each of its tables is a table of the queries, in
/// its own schema; it is opened read only), more Parquet files as tables (`name`, file), the Parquet file of a run (frames),
/// the look and the port.
pub struct Config {
    pub roads: roadstyle::RoadTable,
    pub features: Option<roadstyle::FeatureTable>,
    pub database: Option<PathBuf>,
    pub roads_file: Option<PathBuf>,
    pub name: String,
    pub look: roadstyle::Look,
    pub tables: Vec<(String, PathBuf)>,
    pub frames: Option<PathBuf>,
    pub port: u16,
}

/// The program's state: stage 1 and stage 2 of the roads (a map that redraws with new levels), its style, the rows, and the DuckDB connection over
/// the files.
pub struct Local {
    map: Mutex<LiveTiles>,
    style: Mutex<String>,
    bounds: [f64; 4],
    rows: Vec<Value>,
    database: Option<PathBuf>,
    #[cfg(feature = "duckdb")]
    db: Mutex<duckdb::Connection>,
    frames: Option<PathBuf>,
}

/// Serves the page and the four requests on 127.0.0.1:`port` until the program stops.
pub fn serve(c: Config, page: Page) -> Result<(), String> {
    let port = c.port;
    let local = Arc::new(Local::open(c)?);
    println!("roadstyle local: http://127.0.0.1:{port}/local/  ({} roads; Ctrl+C to stop)", local.rows.len());
    let dir = std::env::current_dir().map_err(|e| e.to_string())?;
    roadstyle_serve::serve_with(&dir, page, port, Some(Vec::new()), Vec::new(), Some(local))
}

impl Local {
    /// Stage 1 and stage 2 of the roads (the tiles are cut when a tile is asked), the road table, and the views of DuckDB over the files.
    pub fn open(c: Config) -> Result<Local, String> {
        let styled = roadstyle::sources_of(c.roads, &c.look, c.features, None, Some(c.name.clone())).map_err(|e| e.to_string())?;
        let mut table = Vec::new();
        roadstyle::write_road_table(&styled, None, false, &mut table).map_err(|e| e.to_string())?;
        let table: Value = serde_json::from_slice(&table).map_err(|e| e.to_string())?;
        let rows = table["props"].as_array().cloned().unwrap_or_default();
        // the box of the roads (the road table's boxes), in the style: the page's first view
        let bounds = table["bboxes"].as_array().into_iter().flatten().filter_map(|b| b.as_array()?.iter().map(Value::as_f64).collect::<Option<Vec<f64>>>())
            .filter(|b| b.len() == 4).fold([f64::INFINITY, f64::INFINITY, f64::NEG_INFINITY, f64::NEG_INFINITY],
                                           |a, b| [a[0].min(b[0]), a[1].min(b[1]), a[2].max(b[2]), a[3].max(b[3])]);
        // the style's tile addresses are relative: the page puts its own origin before them (adapter.js). The tiles are `tiled_sources`'s.
        let map = LiveTiles::new(styled, c.look, "/tiles/", &[]).map_err(|e| e.to_string())?;
        let style = with_bounds(map.style(), bounds)?;
        #[cfg(feature = "duckdb")]
        let db = {
            let db = duckdb::Connection::open_in_memory().map_err(|e| e.to_string())?;
            let view = |db: &duckdb::Connection, name: &str, file: &Path| -> Result<(), String> {
                let sql = format!("CREATE VIEW {} AS SELECT * FROM read_parquet({})", ident(name), text(&file.display().to_string()));
                db.execute_batch(&sql).map_err(|e| format!("{}: {e}", file.display()))
            };
            if let Some(f) = &c.database {
                attach(&db, f)?;
            }
            if let Some(f) = &c.roads_file {
                view(&db, "roads", f)?;
            }
            for (name, file) in &c.tables {
                view(&db, name, file)?;
            }
            if let Some(f) = &c.frames {
                view(&db, "frames", f)?;           // the run's file is also a table, so the data dock can read it
            }
            db
        };
        #[cfg(not(feature = "duckdb"))]
        if c.database.is_some() || c.roads_file.is_some() || !c.tables.is_empty() || c.frames.is_some() {
            return Err(NO_DB.into());
        }
        Ok(Local { map: Mutex::new(map), style: Mutex::new(style), bounds, rows, database: c.database, #[cfg(feature = "duckdb")] db: Mutex::new(db), frames: c.frames })
    }

    /// The number of roads (the length of a frame).
    pub fn roads(&self) -> usize {
        self.rows.len()
    }

    /// One tile of a source: the bytes of the tile, empty for no tile.
    pub fn tile(&self, source: &str, z: u32, x: u32, y: u32) -> Result<Vec<u8>, String> {
        let mut map = self.map.lock().map_err(|e| e.to_string())?;
        let format = map.format();
        match source {
            roadstyle::tiles::SOURCE => map.tile_in(format, z, x, y).map_err(|e| e.to_string()),
            "walls" => map.walls_tile(format, z, x, y).map_err(|e| e.to_string()),
            _ => Ok(Vec::new()),
        }
    }

    /// The whole road table as the page loads it (JSON text: props, mids, bboxes; no lines): a part that needs every row (the level editor,
    /// `levelEditPart`) asks for it while it is open.
    pub fn road_table(&self) -> Result<Vec<u8>, String> {
        let map = self.map.lock().map_err(|e| e.to_string())?;
        let mut out = Vec::new();
        roadstyle::write_road_table(map.sources(), None, false, &mut out).map_err(|e| e.to_string())?;
        Ok(out)
    }

    /// The two ends of each road, 4 numbers for each row (start lon, lat, end lon, lat; NaN: no line), as f64 little endian.
    pub fn road_ends(&self) -> Result<Vec<u8>, String> {
        let map = self.map.lock().map_err(|e| e.to_string())?;
        Ok(roadstyle::road_ends(map.sources()).iter().flat_map(|v| v.to_le_bytes()).collect())
    }

    /// The 3D walls of the page's buildings (`fc`: the GeoJSON text of `rsSetWalls`) as tiles of this map, in place of the walls before:
    /// `{"source": the vector source of the walls (tiles at /tiles/walls/...), "walls": the number of walls and roofs}`.
    pub fn set_walls(&self, fc: &[u8]) -> Result<Value, String> {
        let mut map = self.map.lock().map_err(|e| e.to_string())?;
        let (source, n) = map.set_walls(fc).map_err(|e| e.to_string())?;
        Ok(json!({"source": source, "walls": n}))
    }

    /// Read the `.duckdb` file again, after another connection wrote it (a host that saves the levels): a new table gets its view too.
    #[cfg(feature = "duckdb")]
    pub fn reopen_database(&self) -> Result<(), String> {
        let Some(f) = &self.database else { return Ok(()) };
        let db = self.db.lock().map_err(|e| e.to_string())?;
        db.execute_batch("DETACH file").map_err(|e| e.to_string())?;
        attach(&db, f)
    }

    #[cfg(not(feature = "duckdb"))]
    pub fn reopen_database(&self) -> Result<(), String> {
        Ok(())
    }

    /// The style now (with the tile addresses of this program and `roadstyle:bounds`).
    pub fn style(&self) -> String {
        self.style.lock().map(|s| s.clone()).unwrap_or_default()
    }

    /// Draw the roads of `rows` (a JSON list of levels.csv rows, `relevel::LevelRow::of_json`) again with their new levels: `{"counts": {"edges",
    /// "pieces_gone", "sources", "style_changed"}, "style": the new style or null}`. The page loads the tiles again, or sets the new style.
    pub fn relevel(&self, rows: &str) -> Result<Value, String> {
        let rows = roadstyle::relevel::LevelRow::of_json(rows)?;
        let mut map = self.map.lock().map_err(|e| e.to_string())?;
        let counts = map.relevel(&rows).map_err(|e| e.to_string())?;
        let style = if counts.style_changed {
            let s = with_bounds(map.style(), self.bounds)?;
            *self.style.lock().map_err(|e| e.to_string())? = s.clone();
            serde_json::from_str::<Value>(&s).map_err(|e| e.to_string())?
        } else {
            Value::Null
        };
        Ok(json!({"counts": counts, "style": style}))
    }

    /// The fields of the roads `ids` (null for an id that no road has).
    pub fn rows(&self, source: &str, ids: &[u64]) -> Value {
        Value::Array(ids.iter().map(|&i| if source == roadstyle::tiles::SOURCE {
            self.rows.get(i as usize).cloned().unwrap_or(Value::Null)
        } else {
            self.map.lock().ok().and_then(|m| serde_json::from_str(&m.tiles.props(source, i)).ok()).unwrap_or(Value::Null)
        }).collect())
    }

    /// The line of each road `ids` (JSON text: a list, null for no line).
    pub fn lines(&self, ids: &[u64]) -> Result<Vec<u8>, String> {
        let ids: Vec<u32> = ids.iter().map(|&i| i as u32).collect();
        let mut out = Vec::new();
        let map = self.map.lock().map_err(|e| e.to_string())?;
        roadstyle::write_road_lines(map.sources(), &ids, &mut out).map_err(|e| e.to_string())?;
        Ok(out)
    }

    /// A query: `{"columns": [{"name", "type"}], "rows": [[...]]}`. A 64-bit integer is a text (JSON numbers keep 53 bits); a date or a time is its text.
    #[cfg(not(feature = "duckdb"))]
    pub fn query(&self, _sql: &str) -> Result<Value, String> {
        Err(NO_DB.into())
    }

    #[cfg(feature = "duckdb")]
    pub fn query(&self, sql: &str) -> Result<Value, String> {
        let db = self.db.lock().map_err(|e| e.to_string())?;
        let mut stmt = db.prepare(sql).map_err(|e| e.to_string())?;
        let mut rows = stmt.query([]).map_err(|e| e.to_string())?;
        let mut data: Vec<Vec<Value>> = Vec::new();
        let mut kinds: Vec<&'static str> = Vec::new();
        let n = rows.as_ref().map_or(0, |s| s.column_count());
        while let Some(row) = rows.next().map_err(|e| e.to_string())? {
            let mut out = Vec::with_capacity(n);
            for i in 0..n {
                let (v, kind) = cell(row.get::<_, duckdb::types::Value>(i).map_err(|e| e.to_string())?);
                if kinds.len() <= i {
                    kinds.resize(i + 1, "");
                }
                if kinds[i].is_empty() && !kind.is_empty() {
                    kinds[i] = kind;
                }
                out.push(v);
            }
            data.push(out);
        }
        let names: Vec<String> = rows.as_ref().map_or_else(Vec::new, |s| s.column_names());
        let columns: Vec<Value> = names.iter().enumerate().map(|(i, n)| json!({"name": n, "type": kinds.get(i).copied().filter(|k| !k.is_empty()).unwrap_or("VARCHAR")})).collect();
        Ok(json!({"columns": columns, "rows": data}))
    }

    /// The tables and the views of DuckDB, `main` first: `{"tables": [{"name": "main.roads", "rows": n}]}`.
    #[cfg(not(feature = "duckdb"))]
    pub fn schema(&self) -> Result<Value, String> {
        Err(NO_DB.into())
    }

    #[cfg(feature = "duckdb")]
    pub fn schema(&self) -> Result<Value, String> {
        let db = self.db.lock().map_err(|e| e.to_string())?;
        let names: Vec<String> = {
            let mut stmt = db.prepare("SELECT table_schema || '.' || table_name FROM information_schema.tables WHERE table_catalog = current_database() ORDER BY table_schema <> 'main', 1")
                .map_err(|e| e.to_string())?;
            let r = stmt.query_map([], |r| r.get::<_, String>(0)).map_err(|e| e.to_string())?.collect::<Result<_, _>>().map_err(|e| e.to_string())?;
            r
        };
        let mut tables = Vec::new();
        for n in names {
            let rows = db.query_row(&format!("SELECT count(*) FROM {n}"), [], |r| r.get::<_, i64>(0)).map_err(|e| e.to_string())?;
            tables.push(json!({"name": n, "rows": rows}));
        }
        Ok(json!({"tables": tables}))
    }

    /// The frames `from` up to `to` of the run: u32 frames, u32 values (one for each road), then for each frame f64 `t` and one f32 for each road, NaN
    /// where the file has no value. The file has the columns `frame` (from 0), `t`, `row` (the road's row) and `value`.
    #[cfg(not(feature = "duckdb"))]
    pub fn frames(&self, _from: u32, _to: u32) -> Result<Vec<u8>, String> {
        Err(NO_DB.into())
    }

    #[cfg(feature = "duckdb")]
    pub fn frames(&self, from: u32, to: u32) -> Result<Vec<u8>, String> {
        let Some(_) = &self.frames else { return Err("this program has no run: give --frames FILE.parquet".into()) };
        let n = self.roads();
        let db = self.db.lock().map_err(|e| e.to_string())?;
        let mut stmt = db.prepare("SELECT CAST(frame AS BIGINT), CAST(t AS DOUBLE), CAST(row AS BIGINT), CAST(value AS FLOAT) FROM frames \
                                   WHERE frame >= ? AND frame < ? ORDER BY frame, row").map_err(|e| e.to_string())?;
        let mut rows = stmt.query([from, to]).map_err(|e| e.to_string())?;
        let mut frames: Vec<(f64, Vec<f32>)> = Vec::new();
        let mut last = None;
        while let Some(r) = rows.next().map_err(|e| e.to_string())? {
            let (frame, t, row, value): (i64, f64, i64, f32) = (r.get(0).map_err(|e| e.to_string())?, r.get(1).map_err(|e| e.to_string())?,
                                                                 r.get(2).map_err(|e| e.to_string())?, r.get(3).map_err(|e| e.to_string())?);
            if last != Some(frame) {
                frames.push((t, vec![f32::NAN; n]));
                last = Some(frame);
            }
            if let (Some(f), true) = (frames.last_mut(), (row as usize) < n) {
                f.1[row as usize] = value;
            }
        }
        let mut out = Vec::with_capacity(8 + frames.len() * (8 + 4 * n));
        out.extend((frames.len() as u32).to_le_bytes());
        out.extend((n as u32).to_le_bytes());
        for (t, values) in frames {
            out.extend(t.to_le_bytes());
            out.extend(values.iter().flat_map(|v| v.to_le_bytes()));
        }
        Ok(out)
    }
}

/// The answer of a query, the schema or the frames in a build with no DuckDB.
#[cfg(not(feature = "duckdb"))]
const NO_DB: &str = "this build of roadstyle-local has no DuckDB (the feature `duckdb`): no queries, schema, frames or files";

/// Attach the `.duckdb` file `f` read only, and make each of its tables a view with the same schema and name (`main.edges`, `driving.edges`): the
/// queries name them as in the file.
#[cfg(feature = "duckdb")]
fn attach(db: &duckdb::Connection, f: &Path) -> Result<(), String> {
    db.execute_batch(&format!("ATTACH {} AS file (READ_ONLY)", text(&f.display().to_string()))).map_err(|e| format!("{}: {e}", f.display()))?;
    let names: Vec<(String, String)> = {
        let mut stmt = db.prepare("SELECT table_schema, table_name FROM information_schema.tables WHERE table_catalog = 'file' ORDER BY 1, 2")
            .map_err(|e| e.to_string())?;
        let r = stmt.query_map([], |r| Ok((r.get::<_, String>(0)?, r.get::<_, String>(1)?))).map_err(|e| e.to_string())?
            .collect::<Result<_, _>>().map_err(|e| e.to_string())?;
        r
    };
    for (schema, n) in names {
        let (s, t) = (ident(&schema), ident(&n));
        db.execute_batch(&format!("CREATE SCHEMA IF NOT EXISTS {s}; CREATE OR REPLACE VIEW {s}.{t} AS SELECT * FROM file.{s}.{t}"))
            .map_err(|e| format!("{}: {schema}.{n}: {e}", f.display()))?;
    }
    Ok(())
}

/// A style's text with `roadstyle:bounds` (the box of the roads: the page's first view) in its metadata.
fn with_bounds(style: &str, bounds: [f64; 4]) -> Result<String, String> {
    let mut v: Value = serde_json::from_str(style).map_err(|e| e.to_string())?;
    v["metadata"]["roadstyle:bounds"] = json!(bounds);
    Ok(v.to_string())
}

/// A SQL identifier, and a SQL text, quoted.
fn ident(s: &str) -> String {
    format!("\"{}\"", s.replace('"', "\"\""))
}

fn text(s: &str) -> String {
    format!("'{}'", s.replace('\'', "''"))
}

/// One cell as JSON, and its DuckDB type's name ("" for NULL).
#[cfg(feature = "duckdb")]
fn cell(v: duckdb::types::Value) -> (Value, &'static str) {
    use duckdb::types::Value as V;
    match v {
        V::Null => (Value::Null, ""),
        V::Boolean(b) => (json!(b), "BOOLEAN"),
        V::TinyInt(i) => (json!(i), "TINYINT"),
        V::SmallInt(i) => (json!(i), "SMALLINT"),
        V::Int(i) => (json!(i), "INTEGER"),
        V::BigInt(i) => (json!(i.to_string()), "BIGINT"),
        V::HugeInt(i) => (json!(i.to_string()), "HUGEINT"),
        V::UHugeInt(i) => (json!(i.to_string()), "UHUGEINT"),
        V::UTinyInt(i) => (json!(i), "UTINYINT"),
        V::USmallInt(i) => (json!(i), "USMALLINT"),
        V::UInt(i) => (json!(i), "UINTEGER"),
        V::UBigInt(i) => (json!(i.to_string()), "UBIGINT"),
        V::Float(f) => (if f.is_finite() { json!(f) } else { Value::Null }, "FLOAT"),
        V::Double(f) => (if f.is_finite() { json!(f) } else { Value::Null }, "DOUBLE"),
        V::Text(s) => (json!(s), "VARCHAR"),
        // a decimal is a number with its scale applied (a JSON number holds 53 bits: a DECIMAL with more digits is rounded)
        V::Decimal(d) => (json!(d.value() as f64 / 10f64.powi(i32::from(d.scale()))), "DOUBLE"),
        // a date, a time, a blob, a list, ...: its text (Debug), so a result always shows
        other => (json!(format!("{other:?}")), "VARCHAR"),
    }
}

/// `/<a>/<b>/...` as its parts.
fn parts(path: &str) -> Vec<&str> {
    path.split('/').filter(|p| !p.is_empty()).collect()
}

fn json_response(v: &Value) -> Response {
    Response { status: 200, kind: "application/json", body: v.to_string().into_bytes() }
}

fn fail(status: u16, message: &str) -> Response {
    Response { status, kind: "text/plain; charset=utf-8", body: message.as_bytes().to_vec() }
}

fn ids(body: &[u8]) -> Result<Vec<u64>, Response> {
    serde_json::from_slice::<Vec<u64>>(body).map_err(|e| fail(400, &format!("the body is a JSON list of ids: {e}")))
}

impl Api for Local {
    fn answer(&self, r: &Request) -> Option<Response> {
        let p = parts(r.path);
        let done = |x: Result<Response, Response>| Some(x.unwrap_or_else(|e| e));
        match (r.method, p.as_slice()) {
            ("GET", ["style.json"]) => Some(Response { status: 200, kind: "application/json", body: self.style().into_bytes() }),
            ("GET", ["road_table"]) => done(self.road_table().map(|body| Response { status: 200, kind: "application/json", body }).map_err(|e| fail(500, &e))),
            ("GET", ["road_ends"]) => done(self.road_ends().map(|body| Response { status: 200, kind: "application/octet-stream", body }).map_err(|e| fail(500, &e))),
            ("POST", ["walls"]) => done(self.set_walls(r.body).map(|v| json_response(&v)).map_err(|e| fail(400, &e))),
            ("POST", ["relevel"]) => done(self.relevel(&String::from_utf8_lossy(r.body)).map(|v| json_response(&v)).map_err(|e| fail(400, &e))),
            ("GET", ["tiles", source, z, x, y]) => {
                let n = |s: &str| s.parse::<u32>().map_err(|_| fail(400, "a tile address has numbers: /tiles/<source>/<z>/<x>/<y>"));
                done((|| {
                    let bytes = self.tile(source, n(z)?, n(x)?, n(y)?).map_err(|e| fail(500, &e))?;
                    Ok(if bytes.is_empty() { Response { status: 204, kind: "application/octet-stream", body: bytes } }
                       else { Response { status: 200, kind: "application/octet-stream", body: bytes } })
                })())
            }
            ("POST", ["rows", source]) => done(ids(r.body).map(|ids| json_response(&self.rows(source, &ids)))),
            ("POST", ["lines"]) => done(ids(r.body).and_then(|ids| self.lines(&ids).map_err(|e| fail(500, &e)))
                .map(|body| Response { status: 200, kind: "application/json", body })),
            ("POST", ["query"]) => done((|| {
                let sql = serde_json::from_slice::<Value>(r.body).ok().and_then(|v| v["sql"].as_str().map(String::from))
                    .ok_or_else(|| fail(400, "the body is {\"sql\": \"...\"}"))?;
                self.query(&sql).map(|v| json_response(&v)).map_err(|e| fail(400, &e))
            })()),
            ("GET", ["schema"]) => done(self.schema().map(|v| json_response(&v)).map_err(|e| fail(500, &e))),
            ("GET", ["frames"]) => done((|| {
                let get = |k: &str| r.query.split('&').find_map(|kv| kv.strip_prefix(&format!("{k}="))).and_then(|v| v.parse::<u32>().ok())
                    .ok_or_else(|| fail(400, "frames: /frames?from=<i>&to=<j>"));
                let body = self.frames(get("from")?, get("to")?).map_err(|e| fail(400, &e))?;
                Ok(Response { status: 200, kind: "application/octet-stream", body })
            })()),
            _ => None,
        }
    }
}
