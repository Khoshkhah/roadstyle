// THE ADAPTERS OF THE WAYS (adapter.js has the interface; docs/guides/data-and-memory.md, "The four ways to run a dashboard"). Each function gives
// the adapter of one way: a page gives it to the dashboard (`rs.setAdapter(adapter)`, or the option `adapter`). This module has no import, so a
// test in Node and a page of any way can load it alone.
//   A. one HTML file          no adapter: the road table is in the page
//   B. files on a server      filesAdapter(base): the files of export_style (style.json, roads.pmtiles, props.json) at the URL `base`
//   C. made in the browser    engineAdapter({tiler, sources}): the WebAssembly engine in the page (roadstyle-wasm: Tiler, Sources)
//   D. a local program        httpAdapter(base): the program (roadstyle local, duckosm studio) at `base`
// The data dock's queries need a database: a way with no program (B, C) takes `query` and `schema` from the host (for example its DuckDB-wasm).

// The adapter of way D, and of any server that has the same addresses. `base` is the address of the program, for example "http://127.0.0.1:8830".
//   GET  base/style.json                          the roads' style, with the tile addresses of the program
//   GET  base/tiles/<source>/<z>/<x>/<y>          one tile (the bytes of the tile; 204: no tile)
//   POST base/rows/<source>    [id, ...]          [{...fields} | null, ...]: one object for each id
//   POST base/lines            [id, ...]          [[[lon, lat], ...] | null, ...]
//   POST base/query            {sql}              {columns: [{name, type}], rows: [[...]]}: a BIGINT value is a text, and this adapter makes it a BigInt
//   GET  base/schema                              {tables: [{name, rows, about}]}
//   GET  base/road_table, base/road_ends          the whole road table ({props, mids, bboxes}), and the ends of each road (f64: start lon, lat, end lon, lat)
//   GET  base/frames?from=<i>&to=<j>              the frames from i up to j: u32 frames, u32 values, then for each frame f64 t and f32 for each value (little endian)
// An error status is an Error with the text of the answer.
const BIG = /^(U?BIGINT|HUGEINT|UHUGEINT)$/i;
export function httpAdapter(base, {fetch: get = globalThis.fetch.bind(globalThis)} = {}){
  const url = path => base.replace(/\/$/, "") + path;
  const ok = async r => { if(!r.ok) throw new Error(`${r.url}: ${r.status} ${(await r.text()).slice(0, 300)}`); return r; };
  const post = async (path, body, opt = {}) => (await ok(await get(url(path), {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(body), ...opt}))).json();
  return {
    // the program's tile addresses are relative ("/tiles/roads/{z}/{x}/{y}"): the base goes before them (MapLibre needs an address with its origin)
    style: async () => {
      const st = await (await ok(await get(url("/style.json")))).json();
      for(const s of Object.values(st.sources || {})) if(s.tiles) s.tiles = s.tiles.map(t => t.startsWith("/") ? url(t) : t);
      return st;
    },
    tile: async (source, z, x, y) => {
      const r = await get(url(`/tiles/${source}/${z}/${x}/${y}`));
      if(r.status === 204) return null;
      return new Uint8Array(await (await ok(r)).arrayBuffer());
    },
    rows: (source, ids) => post(`/rows/${source}`, ids),
    lines: ids => post("/lines", ids),
    query: async (sql, {signal} = {}) => {
      const r = await post("/query", {sql}, {signal});
      const big = r.columns.map(c => BIG.test(c.type));
      return {columns: r.columns, rows: r.rows.map(row => row.map((v, k) => big[k] && v !== null ? BigInt(v) : v))};
    },
    schema: async () => (await ok(await get(url("/schema")))).json(),
    // the whole road table ({props, mids, bboxes}) and the ends of each road (4 numbers for each row): for a part that needs every row (the level editor)
    table: async () => (await ok(await get(url("/road_table")))).json(),
    ends: async () => new Float64Array(await (await ok(await get(url("/road_ends")))).arrayBuffer()),
    frames: async (from, to) => {
      const buf = await (await ok(await get(url(`/frames?from=${from}&to=${to}`)))).arrayBuffer(), v = new DataView(buf);
      const n = v.getUint32(0, true), len = v.getUint32(4, true), out = [];
      let at = 8;
      for(let i = 0; i < n; i++){
        const t = v.getFloat64(at, true); at += 8;
        out.push({t, values: new Float32Array(buf.slice(at, at + 4 * len))}); at += 4 * len;
      }
      return out;
    },
  };
}

// The adapter of way B: the files of export_style (format "pmtiles") at the URL `base`, on any file host that answers range requests.
//   style()   base/style.json
//   tile()    the tile of roads.pmtiles (the PMTiles library, window.pmtiles or the option `pmtiles`; the map itself reads the tiles through the style)
//   rows()    the fields of the roads from base/props.json (one record for each road, in the order of the rows: a tile's feature id is its row),
//             read one time at the first request
// `query` and `schema` are the host's (for example DuckDB-wasm on Parquet files at the URL); with none, the data dock says that the page has none.
export function filesAdapter(base, {fetch: get = globalThis.fetch.bind(globalThis), pmtiles = globalThis.pmtiles, query = null, schema = null} = {}){
  const url = path => base.replace(/\/$/, "") + path;
  const ok = async r => { if(!r.ok) throw new Error(`${r.url}: ${r.status}`); return r; };
  let props = null, archive = null;
  const out = {
    style: async () => (await ok(await get(url("/style.json")))).json(),
    tile: async (source, z, x, y) => {
      if(source !== "roads") return null;
      if(!pmtiles) throw new Error("filesAdapter: the tiles need the PMTiles library (window.pmtiles, or the option pmtiles)");
      archive ??= new pmtiles.PMTiles(url("/roads.pmtiles"));
      const t = await archive.getZxy(z, x, y);
      return t ? new Uint8Array(t.data) : null;
    },
    rows: async (source, ids) => {
      if(source !== "roads") return ids.map(() => null);       // the rows of the other layers are in their tiles
      props ??= get(url("/props.json")).then(ok).then(r => r.json()).catch(e => { props = null; throw e; });
      const p = await props;
      return ids.map(i => p[i] ?? null);
    },
  };
  if(query) out.query = query;
  if(schema) out.schema = schema;
  return out;
}

// The adapter of way C: the WebAssembly engine in the page. `tiler` is roadstyle-wasm's Tiler (the style and the tiles); `sources` is a Sources of
// the same roads (styleSources): the fields of each road (its road table, read one time at the first request) and the line of a road. With no
// `sources`, the rows of the roads are null. The rows of the other layers come from the Tiler. `format` ("mvt" or "mlt", else the Tiler's own) is the
// format of the tiles and of the style. `query` and `schema` are the host's (for example its DuckDB-wasm).
// A page that runs the engine in a worker gives its own functions in the same shape.
export function engineAdapter({tiler, sources = null, format = undefined, query = null, schema = null}){
  if(!tiler) throw new Error("engineAdapter: give the Tiler of the page");
  let table = null;
  const out = {
    style: async () => JSON.parse(tiler.style(format)),
    tile: async (source, z, x, y) => { const b = tiler.tile(source, z, x, y, format); return b.length ? b : null; },
    rows: async (source, ids) => {
      if(source !== "roads") return ids.map(i => JSON.parse(tiler.props(source, i)));
      if(!sources) return ids.map(() => null);
      table ??= JSON.parse(new TextDecoder().decode(sources.roadTable(undefined, false))).props;
      return ids.map(i => table[i] ?? null);
    },
  };
  if(sources){
    out.lines = async ids => JSON.parse(new TextDecoder().decode(sources.roadLines(Uint32Array.from(ids))));
    out.table = async () => JSON.parse(new TextDecoder().decode(sources.roadTable(undefined, false)));
  }
  if(query) out.query = query;
  if(schema) out.schema = schema;
  return out;
}
