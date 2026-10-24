# Use roadstyle in the browser

<p class="lead">Make the style, the vector tiles or the whole page in a web page, with the WebAssembly package and the dashboard
modules. No Python runs.</p>

!!! warning "Experimental"
    The Rust engine is experimental in 0.25. The functions of the WebAssembly package, the `roadstyle:*` metadata in the style
    and the `__rs_*` property names can change in the next versions. Use one exact version of the package.

duckosm-rust's browser page and the GeoLibre plugin use roadstyle this way. The examples on this page use Monaco.

## Get the files

The WebAssembly package is not on npm yet. Build it from a roadstyle checkout ([Build from source](build.md#build-the-webassembly-package)).
Then put these files in one folder of your site:

| Folder | Content | From |
|---|---|---|
| `pkg/` | `roadstyle_wasm.js`, `roadstyle_wasm_bg.wasm` and the TypeScript types | the output of `wasm-bindgen` |
| `dashboard/` | the dashboard modules (`index.js` and the files that it imports), `dashboard.css` | `src/roadstyle/static/dashboard/` |
| `popup.js`, `popup.css` | the road popup; the dashboard imports `../popup.js` | `src/roadstyle/static/` |
| `js/` | `roads_sql.js` and `features_sql.js`, the worker SQL | `rust/roadstyle-wasm/js/` |

The `dashboard/` folder and the popup files are also in the installed Python package, in the folder that this command writes:

```bash
python -c "import roadstyle, pathlib; print(pathlib.Path(roadstyle.__file__).parent / 'static')"
```

The page must load MapLibre GL JS 5.24 as a script, because the dashboard uses the global `maplibregl`:

```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/maplibre-gl@5.24.0/dist/maplibre-gl.css">
<script src="https://cdn.jsdelivr.net/npm/maplibre-gl@5.24.0/dist/maplibre-gl.js"></script>
<link rel="stylesheet" href="dashboard/dashboard.css">
<link rel="stylesheet" href="popup.css">
```

Serve the folder over http. A module script does not load from a `file://` address.

## The functions of the package

| Function | Returns | What it does |
|---|---|---|
| `init()` | a Promise | loads the WebAssembly module; call it one time, first |
| `makeLook(options)` | JSON text | the look: `render_edges`' `palette`, `profile`, `settings` and keywords (`args`), from the JSON text `options` |
| `makeStyle(roads, look, features?, planner?, name?)` | JSON text | the style with the roads in it (as `export_inline`) |
| `new Tiler(roads, look, features?, name?, prefix, keep)` | a `Tiler` | the style with vector-tile sources, and the tiles on request |
| `tiler.style()` | JSON text | the style of the `Tiler` |
| `tiler.tile("roads", z, x, y)` | `Uint8Array` | one vector tile; empty when no road is in it |
| `tiler.props("roads", row)` | JSON text | the properties of one road, or `null` |
| `tiler.archive(bounds, layers)` | `Uint8Array` | a PMTiles archive of all tiles in `[min lon, min lat, max lon, max lat]` |
| `makePage(roads, look, options, given?)` | HTML text | the whole page, as `render_edges` writes it |
| `exportLook(look, cols, positions)` | JSON text | the look for another app's data layer (as `export_look`) |
| `memoryBytes()` | number | the size of the module's memory, in bytes |

`roads` is the bytes of a GeoParquet file: the geometry as WKB in EPSG:4326, and the columns of
[the data contract](../get-started.md#what-your-data-needs). An error is a thrown `Error` with a message that tells what is wrong.
The engine takes at most 200,000 roads.

## Draw a style with the roads in it

This page reads `monaco_roads.parquet`, makes the style and adds the dashboard. To make the file from Python:

```python
rs.as_edges(edges).gdf.to_parquet("monaco_roads.parquet", index=False)   # edges: from osmnx, as in the tutorial
```

```html
<div id="map" style="position:absolute;inset:0"></div>
<script type="module">
import init, {makeLook, makeStyle} from "./pkg/roadstyle_wasm.js";
import {rsDashboard} from "./dashboard/index.js";

await init();
const roads = new Uint8Array(await (await fetch("monaco_roads.parquet")).arrayBuffer());
// the look: render_edges' palette, profile, settings and keywords; state "live" keeps the controls' state in the style
const look = makeLook(JSON.stringify({palette: "amber", args: {state: "live", color_by: "lanes", cmap: "YlOrRd"}}));
const style = JSON.parse(makeStyle(roads, look, undefined, undefined, "Monaco"));

const map = new maplibregl.Map({container: "map", style});
for (const [id, im] of Object.entries(style.metadata["roadstyle:images"] || {}))
  map.loadImage(im.url).then((r) => map.addImage(id, r.data, {sdf: im.sdf, pixelRatio: im.pixelRatio}));
const rs = rsDashboard(map, {style, find_control: true});
</script>
```

The page shows the roads colored by `lanes`, the legend, the Roads box, the search box, the popup and the hover glow.

- `args` takes the keywords of `render_edges` that change the style, with their Python names: `color_by`, `cmap`, `arrows`,
  `labels`, `view_3d`, `highway_col`, ... ([Keywords by engine](keywords.md)).
- `state: "live"` keeps the global state (`rs_co`, `rs_colors`, ...) in the expressions, so the controls can change the map.
  Without it, the engine writes the start values, as `export_style` does.
- `rsDashboard` reads its options from the style's metadata (`roadstyle:controls`, `roadstyle:interaction`,
  `roadstyle:color_options`). An option that you give has priority.
- Call `rsDashboard` immediately after `new maplibregl.Map(...)`, before the map's `load` event.
- The value of `rsDashboard` is [the `rs` object](../reference/javascript.md#the-rs-object). It is also `window.rs`.

## Read the roads from a duckOSM file

`makeRoads` and `writeRoads` in `js/roads_sql.js` are the SQL that writes `roads.parquet` from a duckOSM file in duckdb-wasm, with
the columns that the engine reads. It is the only copy of this SQL: duckosm-rust and the GeoLibre plugin use the same file.

```js
import * as duckdb from "https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.33.1-dev57.0/+esm";
import {makeRoads, writeRoads} from "./js/roads_sql.js";
import init, {makeLook, makeStyle} from "./pkg/roadstyle_wasm.js";

// duckdb-wasm in its own worker
const bundle = await duckdb.selectBundle(duckdb.getJsDelivrBundles());
const url = URL.createObjectURL(new Blob([`importScripts("${bundle.mainWorker}");`], {type: "text/javascript"}));
const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), new Worker(url));
await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
const conn = await db.connect();
const q = async (sql) => (await conn.query(sql)).toArray().map((r) => r.toJSON());

// a duckOSM file: its driving roads and their stored levels as roads.parquet
const file = new Uint8Array(await (await fetch("monaco.duckdb")).arrayBuffer());
await db.registerFileBuffer("monaco.duckdb", file);
await q("ATTACH 'monaco.duckdb' AS monaco (READ_ONLY); USE monaco");
const levels = await makeRoads(q, "monaco", {levels: "stored"});   // the stored levels' {edge_hash, n_edges}
await writeRoads(q, "driving");
const roads = await db.copyFileToBuffer("roads.parquet");

await init();
const look = JSON.parse(makeLook(JSON.stringify({args: {state: "live", casing_level_col: "casing_level", fill_level_col: "fill_level",
                                                         casing_start_col: "casing_start", casing_end_col: "casing_end"}})));
look.args.levels = levels;                          // the engine checks that the stored levels are for these edges
const style = JSON.parse(makeStyle(roads, JSON.stringify(look), undefined, undefined, "Monaco"));
```

`makeRoads(q, catalog, opts)` runs one time for each file. It makes the temporary table `r`: one row for each edge of all modes, with
its levels. `writeRoads(q, mode)` runs for each mode, and writes only `roads.parquet` from `r`.

- `mode`: `"all"`, `"driving"`, `"walking"` or `"cycling"`.
- `opts.levels: "stored"` reads `visualization.edge_levels`, the levels of a solved level area. `makeRoads` returns their
  `{edge_hash, n_edges}`. `opts.levels: "tags"` writes no levels, and `makeRoads` returns `"tags"`.
- Put the value of `makeRoads` in the look as `args.levels`. With `"tags"`, the engine computes the levels with the tags rule of
  `compute_levels(method="tags")`. With `{edge_hash, n_edges}`, the engine checks that the stored levels were solved for these edges
  (roadstyle-levels' `edge_hash`), and stops with an error if not.
- `edge_id`, `osm_id`, `source` and `target` are BIGINT, as in the duckOSM file. The engine writes an id that JavaScript cannot
  hold exactly as text.

`writeFeatures(q, catalog, specs)` in `js/features_sql.js` writes `features.parquet`, the base-map layers of mapstyle, for the
argument `features` of `makeStyle` and `Tiler`.

## Add roads that come later, as vector tiles

Use this form when the map has its own base map and the roads come later or change, as on duckosm-rust's page. The page adds
the roads style's sources and layers with a prefix, and gives the dashboard the new style each time.

```js
import init, {makeLook, Tiler} from "./pkg/roadstyle_wasm.js";
import {rsDashboard} from "./dashboard/index.js";

await init();
const roads = new Uint8Array(await (await fetch("monaco_roads.parquet")).arrayBuffer());
const map = new maplibregl.Map({container: "map", style: "https://tiles.openfreemap.org/styles/positron",
                                center: [7.42, 43.735], zoom: 14});

// the tiles of the roads style: rs://<generation>/<source>/<z>/<x>/<y>
let tiler = null, gen = 0;
maplibregl.addProtocol("rs", async ({url}) => {
  const [g, source, z, x, y] = url.slice("rs://".length).split("/");
  return {data: +g === gen ? tiler.tile(source, +z, +x, +y) : new Uint8Array()};
});
// the dashboard before the roads: no style yet; one road's properties come from the engine
const rs = rsDashboard(map, {style: null, prefix: "rs-", tiles: true, simple: "roads-simple",
                             engine: {props: async (row) => JSON.parse(tiler.props("roads", row))}});

async function showRoads(args) {
  const look = makeLook(JSON.stringify({palette: "amber", args: {state: "live", ...args}}));
  tiler = new Tiler(roads, look, undefined, "Monaco", `rs://${++gen}/`, ["name", "highway", "lanes"]);
  const style = JSON.parse(tiler.style());
  for (const l of map.getStyle().layers) if (l.id.startsWith("rs-")) map.removeLayer(l.id);
  for (const id of Object.keys(map.getStyle().sources)) if (id.startsWith("rs-")) map.removeSource(id);
  for (const [id, im] of Object.entries(style.metadata["roadstyle:images"] || {}))
    if (!map.hasImage("rs-" + id)) map.addImage("rs-" + id, (await map.loadImage(im.url)).data, {sdf: im.sdf, pixelRatio: im.pixelRatio});
  // the start value of each global state that the layers read: the map's own style has no "state" block for them
  for (const [k, v] of Object.entries(style.metadata["roadstyle:state"] || {})) map.setGlobalStateProperty(k, v);
  for (const [id, src] of Object.entries(style.sources))
    map.addSource("rs-" + id, id === "roads" ? {...src, promoteId: {simple: "__rs_edge"}} : src);
  for (const id of Object.keys(style.sources)) map.getSource("rs-" + id).calculateTileZoom = (z) => z;   // one tile zoom
  for (const l of style.layers) {
    const layer = JSON.parse(JSON.stringify(l).replaceAll('"oneway"', '"rs-oneway"'));   // the image name
    map.addLayer({...layer, id: "rs-" + l.id, source: "rs-" + l.source});
  }
  rs.setStyle(style);
}
await map.once("load");
await showRoads({});                                  // later: showRoads({color_by: "lanes", cmap: "YlOrRd"})
```

The parts of this page:

- **`new Tiler(roads, look, features, name, prefix, keep)`.** `prefix` is the start of the tile address in the style
  (`rs://1/`). Use a new generation for each style, so the map does not show tiles of the old style. `keep` is the list of the
  columns that the tiles keep for the popup and the tooltip.
- **The global state.** The page adds the layers to a style that is not roadstyle's, so it must set the start value of each state
  in `roadstyle:state`. Without this step, MapLibre writes errors and draws the roads in black.
- **`calculateTileZoom`.** One tile zoom on the whole screen, so a road keeps one width in a view tilted more than 60°
  ([One tile zoom or several](drawing.md#one-tile-zoom-or-several)).
- **`promoteId: {simple: "__rs_edge"}`.** All the pieces of a road get the road's id, so the hover glow and the selection light
  the whole road.
- **`style: null`, `prefix: "rs-"`.** The dashboard starts with no roads, and adds `rs-` to each source and layer id that it uses.
- **`engine.props`.** The dashboard asks the engine for one road's properties at a click, at `rsSelect` and for the tooltip.
- **`rs.setStyle(style)`.** The controls stay. The Colour by menu and the legend are made again, and the selection is cleared.

With `engine.props` only, `rs.query`, `rs.find`, `rs.props` and `rs.focus` find nothing: they need all roads' properties in the
page.

## Write the whole page

`makePage` writes the same page as `render_edges(backend="web")` in one call: stage 1, the arrows or the tiles, the views, the
dashboard's options and the page. `look` is the result of `makeLook(options)`, with `"state": "live"` in its args. Give the same
`options` text again: a view with another palette resolves its look from it. The page has placeholders for MapLibre, which you
replace:

```js
const options = JSON.stringify({palette: "amber", args: {state: "live", name: "Monaco", basemap: "osm", views: {plain: {road_fill: false}}}});
const html = makePage(roads, makeLook(options), options)
  .replace("<style>__MAPLIBRE_CSS__</style>", '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/maplibre-gl@5.24.0/dist/maplibre-gl.css">')
  .replace("<script>__MAPLIBRE_JS__</script>", '<script src="https://cdn.jsdelivr.net/npm/maplibre-gl@5.24.0/dist/maplibre-gl.js"></script>');
```

`given` (JSON text) holds what only the host knows: `api_key` (the key of a CARTO base map), `street_view_key`, and
`resolved_basemaps` (base map entries in the form of `data/basemaps.json`). The warnings of the stages go to `console.warn`.

## Keep the main thread free

For a large area, run the engine in a Web Worker, as duckosm-rust does: the worker keeps the `Tiler` and answers `tile` and
`props`, and the main thread only draws. A new worker for each style gives the memory of the old style back to the browser.
`memoryBytes()` tells you how much memory the module uses.

**See also:** [The `rs` object](../reference/javascript.md#the-rs-object) ·
[Interaction contract](../reference/contract.md) · [Make tiles and PMTiles](tiles.md)
