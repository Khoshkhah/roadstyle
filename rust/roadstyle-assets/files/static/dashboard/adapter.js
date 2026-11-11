// THE FOUR REQUESTS (docs/design/memory_budget.md, "Step 2"; docs/guides/data-and-memory.md). The dashboard asks for data in four ways:
//   tile    one tile of a source at z/x/y            adapter.tile(source, z, x, y)   -> Promise<Uint8Array | null>
//   rows    the fields of some roads (a popup)       adapter.rows(source, ids)       -> Promise<(object | null)[]>, one for each id
//   query   a SQL query (the data dock, Ask)         adapter.query(sql, {signal})    -> Promise<{columns: [{name, type}], rows}>
//   frames  a window of frames of a run              adapter.frames(from, to)        -> Promise<{t, values: Float32Array}[]>
// Also `table()` (the whole road table, {props, mids, bboxes}) and `ends()` (Float64Array, 4 numbers for each row): a part that needs every row, the
// level editor (levelEditPart), asks for them on a page that keeps no road table.
// The adapter also has `lines(ids)` (the line of each road, [[lon, lat], ...]), `schema()` (the tables, as the data dock asks) and `style()` (the
// roads' style, with the tile addresses of the way). Every function is optional. A page uses what it needs. A function that the adapter has not got
// makes `rs.request.<name>` throw an error that says so: nothing replaces it.
// Each way gives one adapter. The dashboard does not know which way it runs in:
//   A. one HTML file   no adapter: the road table and the overlays' rows are in the page (RoadTable, OV_ROWS)
//   B. files on a server   the style points at the PMTiles file; the host gives `rows` and `query` (DuckDB-wasm on the Parquet files)
//   C. made in the browser   the host gives the functions of its map worker and of its DuckDB-wasm
//   D. a local program   rsHttpAdapter(base): the program answers the four requests at addresses of `base`
// The adapters of ways B, C and D are in ways.js (a module with no import: a test in Node and a page of any way load it alone).
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
    table: () => need("table")(),
    ends: () => need("ends")(),
  };
}
// `rs.setAdapter(adapter)`: the adapter of the page (null: none). The rows and lines of the old adapter go.
export const setAdapter = _setAdapter;
