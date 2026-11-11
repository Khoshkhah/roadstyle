// THE FOUR REQUESTS (docs/design/memory_budget.md, "Step 2"; docs/guides/data-and-memory.md). The dashboard asks for data in four ways:
//   tile    one tile of a source at z/x/y            adapter.tile(source, z, x, y)   -> Promise<Uint8Array | null>
//   rows    the fields of some roads (a popup)       adapter.rows(source, ids)       -> Promise<(object | null)[]>, one for each id
//   query   a SQL query (the data dock, Ask)         adapter.query(sql, {signal})    -> Promise<{columns: [{name, type}], rows}>
//   frames  a window of frames of a run              adapter.frames(from, to)        -> Promise<{t, values: Float32Array}[]>
// The adapter also has `lines(ids)` (the line of each road, [[lon, lat], ...]), `schema()` (the tables, as the data dock asks) and `style()` (the
// roads' style, with the tile addresses of the way). Every function is optional. A page uses what it needs. A function that the adapter has not got
// makes `rs.request.<name>` throw an error that says so: nothing replaces it.
// Each way gives one adapter. The dashboard does not know which way it runs in:
//   A. one HTML file   no adapter: the road table and the overlays' rows are in the page (RoadTable, OV_ROWS)
//   B. files on a server   the style points at the PMTiles file; the host gives `rows` and `query` (DuckDB-wasm on the Parquet files)
//   C. made in the browser   the host gives the functions of its map worker and of its DuckDB-wasm
//   D. a local program   rsHttpAdapter(base): the program answers the four requests at addresses of `base` (below)
import {ADAPTER, _setAdapter} from "./core.js";

// `rs.request`: the four requests, as the dashboard makes them. `row` is `rows` for one id.
export function requestsOf(){
  const need = name => {
    const f = ADAPTER && ADAPTER[name];
    if(typeof f !== "function") throw new Error(`rs.request.${name}: ${ADAPTER ? "the adapter has no " + name : "the page has no adapter"}`);
    return f.bind(ADAPTER);
  };
  return {
    tile: (source, z, x, y) => need("tile")(source, z, x, y),
    rows: (source, ids) => need("rows")(source, ids),
    row: async (source, id) => (await need("rows")(source, [id]))[0] ?? null,
    query: (sql, opt) => need("query")(sql, opt),
    schema: () => need("schema")(),
    frames: (from, to) => need("frames")(from, to),
    lines: ids => need("lines")(ids),
  };
}
// `rs.setAdapter(adapter)`: the adapter of the page (null: none). The rows and lines of the old adapter go.
export const setAdapter = _setAdapter;

// The adapter of way D, and of any server that has the same addresses. `base` is the address of the program, for example "http://127.0.0.1:8830".
//   GET  base/style.json                          the roads' style, with the tile addresses of the program
//   GET  base/tiles/<source>/<z>/<x>/<y>          one tile (the bytes of the tile; 204: no tile)
//   POST base/rows/<source>    [id, ...]          [{...fields} | null, ...]: one object for each id
//   POST base/lines            [id, ...]          [[[lon, lat], ...] | null, ...]
//   POST base/query            {sql}              {columns: [{name, type}], rows: [[...]]}: a BIGINT value is a text, and this adapter makes it a BigInt
//   GET  base/schema                              {tables: [{name, rows, about}]}
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
