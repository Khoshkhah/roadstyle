# Use roadstyle in the browser

<p class="lead">Make the style, the vector tiles or the whole page in a web page, with the WebAssembly package and the dashboard
modules. No Python runs.</p>

!!! warning "Experimental"
    The WebAssembly package is experimental. The functions of the package, the `roadstyle:*` metadata in the style and the `__rs_*` property names can change in the next versions. Use one exact version of the package.

The browser page of duckosm-rust and the GeoLibre plugin use roadstyle this way. The examples on this page use Monaco.

## Get the files

The WebAssembly package is not on npm yet. Build it from a roadstyle checkout ([Build from source](https://github.com/Khoshkhah/roadstyle/blob/main/docs/rust/build.md#build-the-webassembly-package)).
Then put these files in one folder of your site:

| Folder | Content | From |
|---|---|---|
| `pkg/` | `roadstyle_wasm.js`, `roadstyle_wasm_bg.wasm` and the TypeScript types | the output of `wasm-bindgen` |
| `dashboard/` | the dashboard modules (`index.js` and the files that it imports), `dashboard.css`, and its subfolders (`editor/`: the level editor, `worker/`: the worker calls) | `rust/roadstyle-assets/files/static/dashboard/` |
| `popup.js`, `popup.css` | the road popup; the dashboard imports `../popup.js` | `rust/roadstyle-assets/files/static/` |
| `level_editor.html` | the level editor's panel (only for the level editor) | `rust/roadstyle-assets/files/static/` |
| `js/` | `roads_sql.js` and `features_sql.js`, the worker SQL | `rust/roadstyle-wasm/js/` |

`rust/roadstyle-assets/files/` is the one copy of these files (the crate `roadstyle-assets`). Take them from there, not from the generated copy in `src/roadstyle/static/`. The npm package `roadstyle-dashboard` has the same files.

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
| `resolveLook(options)` | a `Look` | the look: `render_edges`' `palette`, `profile`, `settings` and keywords (`args`), from the JSON text `options` |
| `look.withArg(key, value)` | a `Look` | the same look with the keyword `key` (`color_by`, `state`, `live_data`, ...) set to `value` (JSON text) |
| `look.toJson()`, `Look.fromJson(text)` | JSON text, a `Look` | save a look and load it again (version 2; `fromJson` also reads 1 and 0) |
| `inlineStyle(roads, look, features?, planner?, name?)` | JSON text | the style with the roads in it (as `export_inline`) |
| `readGeoParquet(bytes)`, `readGeoJson(bytes)`, `readShp(shp, dbf, prj?, name?)` | a `Roads` | the roads of a file, read one time. `roads.page(look, options, given?, features?)` and `roads.sources(look, features?, planner?, name?)` use it |
| `new Tiler(roads, look, features?, name?, prefix, keep)` | a `Tiler` | the style with vector-tile sources, and the tiles on request |
| `tiler.style(format?)` | JSON text | the style of the `Tiler`; `format` (`"mvt"` or `"mlt"`) sets the `encoding` of the vector source |
| `tiler.tile("roads", z, x, y, format?)` | `Uint8Array` | one vector tile in `format` (default: the format of the `Tiler`); empty when no road is in it |
| `tiler.props("roads", row)` | JSON text | the properties of one road, or `null` |
| `tiler.archive(bounds, layers)` | `Uint8Array` | a PMTiles archive of all tiles in `[min lon, min lat, max lon, max lat]` |
| `pageFrom(roads, look, options, given?, features?)` | HTML text | the whole page, as `render_edges` writes it. The page's keys (`sidebar`, `popup_mode`, ...) come from `options`' args; `given` adds your values (`street_view_key`, `api_key`) |
| `styleSources(roads, look, features?, planner?, name?)` | a `Sources` | stage 1 alone: the style and its sources, for `new LiveMap(...)` ([Change the look of a live map](#change-the-look-of-a-live-map)) |
| `exportLook(look, cols, positions)` | JSON text | the look for another app's data layer (as `export_look`) |
| `makeArea(edges, options?)` | an `AreaFiles` | a level area's files in memory ([The level editor in a page](#the-level-editor-in-a-page)) |
| `new LevelArea(roads, pairs)` | a `LevelArea` | the level editor's solver on an area (`solve`, `solveLocal`, `check`, `draw`, `levelsCsv`) |
| `memoryBytes()` | number | the size of the module's memory, in bytes |

The tile format is MLT by default, as for every other way to make tiles. Use `"mvt"` for an app that cannot read MLT. An MLT tile costs 1 to 6 ms (Nacka, native), one time for each tile ([the measurements](tiles.md#measured-results)).

The JSON of a look (`toJson`) is a format to save and load a look, not an API. Its inner fields change between versions. Do not read or change them. Give your keywords to `resolveLook`, or change a saved look with `withArg`.

`roads` is the bytes of a GeoParquet file: the geometry as WKB in EPSG:4326, and the columns of [the data contract](../get-started.md#what-your-data-needs). An error is a thrown `Error` with a message that tells what is wrong. The engine takes at most 200,000 roads (`MAX_ROADS`).

## Draw a style with the roads in it

This page reads `monaco_roads.parquet`, makes the style and adds the dashboard. To make the file from Python:

```python
rs.as_edges(edges).gdf.to_parquet("monaco_roads.parquet", index=False)   # edges: from osmnx, as in the tutorial
```

```html
<div id="map" style="position:absolute;inset:0"></div>
<script type="module">
import init, {resolveLook, inlineStyle} from "./pkg/roadstyle_wasm.js";
import {rsDashboard} from "./dashboard/index.js";

await init();
const roads = new Uint8Array(await (await fetch("monaco_roads.parquet")).arrayBuffer());
// the look: render_edges' palette, profile, settings and keywords; state "live" keeps the controls' state in the style
const look = resolveLook(JSON.stringify({palette: "amber", args: {state: "live", color_by: "lanes", cmap: "YlOrRd"}}));
const style = JSON.parse(inlineStyle(roads, look, undefined, undefined, "Monaco"));

const map = new maplibregl.Map({container: "map", style});
const rs = rsDashboard(map, {style, find_control: true});     // it adds the style's images (roadstyle:images) too
</script>
```

The page shows the roads colored by `lanes`, the legend, the search box, the popup and the hover glow.

- `args` takes the keywords of `render_edges` that change the style, with their Python names: `color_by`, `cmap`, `arrows`,
  `labels`, `view_3d`, `highway_col`, ... ([every parameter](../reference/parameters.md)).
- `state: "live"` keeps the global state (`rs_co`, `rs_top`, ...) in the expressions, so the controls can change the map. Without it, the engine writes the start values, as `export_style` does.
- `rsDashboard` reads its options from the style's metadata (`roadstyle:controls`, `roadstyle:interaction`,
  `roadstyle:color_options`). An option that you give has priority.
- Call `rsDashboard` immediately after `new maplibregl.Map(...)`, before the map's `load` event.
- The value of `rsDashboard` is [the `rs` object](../reference/javascript.md#the-rs-object). It is also `window.rs`.

## Read the roads from a duckOSM file

`makeRoads` and `writeRoads` in `js/roads_sql.js` write `roads.parquet` from a duckOSM file in duckdb-wasm, with the columns that the
engine reads. They run the statements of `duckosmPlan` (roadstyle-io's `duckosm.rs`), the only copy of this SQL, which Python runs
too. duckosm-rust and the GeoLibre plugin use the same file. Load the module (`init()`) before you call them.

```js
import * as duckdb from "https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.33.1-dev57.0/+esm";
import {makeRoads, writeRoads} from "./js/roads_sql.js";
import init, {resolveLook, inlineStyle} from "./pkg/roadstyle_wasm.js";

await init();                                       // roads_sql.js asks the module for its SQL

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

// levels: the engine checks that the stored levels are for these edges
const look = resolveLook(JSON.stringify({args: {state: "live", casing_level_col: "casing_level", fill_level_col: "fill_level",
                                                 casing_start_col: "casing_start", casing_end_col: "casing_end", levels}}));
const style = JSON.parse(inlineStyle(roads, look, undefined, undefined, "Monaco"));
```

`makeRoads(q, catalog, opts)` runs one time for each file. It makes the run's temporary table (`duckosm_r_<run>`, from `duckosmPlan`'s
`"run"`): one row for each edge of all modes, with its levels. `writeRoads(q, mode)` runs for each mode, and writes only `roads.parquet`
from that table. Each reading has its own tables, so two readings at the same time on one connection do not drop or replace each other's
tables; `writeFeatures` drops its tables when it has written `features.parquet`.

- `mode`: `"all"`, `"driving"`, `"walking"` or `"cycling"`.
- `opts.levels: "stored"` reads `visualization.edge_levels`, the levels of a solved level area. `makeRoads` returns their
  `{edge_hash, n_edges}`. `opts.levels: "tags"` writes no levels, and `makeRoads` returns `"tags"`.
- Put the value of `makeRoads` in the look as `args.levels`. With `"tags"`, the engine computes the levels with the tags rule of
  `compute_levels(method="tags")`. With `{edge_hash, n_edges}`, the engine checks that the stored levels were solved for these edges
  (roadstyle-levels' `edge_hash`), and stops with an error if not.
- `edge_id`, `osm_id`, `source` and `target` are BIGINT, as in the duckOSM file. The engine writes an id that JavaScript cannot
  hold exactly as text.

`writeFeatures(q, catalog, specs)` in `js/features_sql.js` writes `features.parquet`, the base-map layers of mapstyle, for the
argument `features` of `inlineStyle` and `Tiler`. It runs the layers' queries of `duckosmPlan`; a layer whose queries all fail is skipped,
as mapstyle's `load_layers` does. The background is the whole boundary: the engine cuts the sea out of it when it reads
`features.parquet`, so duckdb-wasm needs no spatial extension.

## Add roads that come later, as vector tiles

Use this form when the map has its own base map and the roads come later or change, as on duckosm-rust's page. The page adds
the roads style's sources and layers with a prefix, and gives the dashboard the new style each time.

```js
import init, {resolveLook, Tiler} from "./pkg/roadstyle_wasm.js";
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
  const look = resolveLook(JSON.stringify({palette: "amber", args: {state: "live", ...args}}));
  tiler = new Tiler(roads, look, undefined, "Monaco", `rs://${++gen}/`, ["name", "highway", "lanes"]);
  const style = JSON.parse(tiler.style());
  for (const l of map.getStyle().layers) if (l.id.startsWith("rs-")) map.removeLayer(l.id);
  for (const id of Object.keys(map.getStyle().sources)) if (id.startsWith("rs-")) map.removeSource(id);
  for (const [id, im] of Object.entries(style.metadata["roadstyle:images"] || {}))
    if (!map.hasImage("rs-" + id)) map.addImage("rs-" + id, (await map.loadImage(im.url)).data, {sdf: im.sdf, pixelRatio: im.pixelRatio});
  // the start value of each global state that the layers read: the map's own style has no "state" block for them
  for (const [k, v] of Object.entries(style.metadata["roadstyle:state"] || {})) map.setGlobalStateProperty(k, v);
  for (const [id, src] of Object.entries(style.sources))
    map.addSource("rs-" + id, src);
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
- **The feature id.** All the pieces of a road have the road's row as their feature id (contract 2), so the hover glow and the selection
  light the whole road. There is no `promoteId`.
- **`style: null`, `prefix: "rs-"`.** The dashboard starts with no roads, and adds `rs-` to each source and layer id that it uses.
- **`engine.props`.** The dashboard asks the engine for one road's properties at a click, at `rsSelect` and for the tooltip.
- **`rs.setStyle(style)`.** The controls stay. Every control that a style gives (the colour options and the legend, the `roads` tool and
  its classes, the base-map layers, the arrows, the boundary) is made again for the new style, and goes when the new style has none.
  A switch that was off stays off. The selection is cleared.
  The dashboard sets the style's global state: a live style's layers read MapLibre's global state (`rs_co`, `rs_fill_on`, ...),
  whose start values are in the style's own `state` block, which your map does not have. The dashboard sets each value of
  `roadstyle:state` that your map does not have yet, and keeps the values that your map has.

With `engine.props` only, `rs.query`, `rs.find`, `rs.props` and `rs.focus` find nothing: they need all roads' properties in the
page.

## Change the look of a live map

A theme, a palette or a colour changes only how the roads are drawn, not the roads. `LiveMap.setLook(look, format?)` gives the map the new
look with no new tile, when the map's tiles are still right for it (docs/design/restyle_without_retile.md):

```js
const style = live.setLook(Look.fromJson(newLookText), format);
if (style !== undefined) {
  map.setStyle(JSON.parse(style), { diff: true });   // the tiles, the sources and the live colours stay
} else {
  live = new LiveMap(styleSources(roads, newLook), newLook, prefix, keep);   // the look changes the tiles: make a new map
  map.setStyle(JSON.parse(live.style(format)));
}
```

In a page with a dashboard, give the style to `rs.restyle(style)` in place of `map.setStyle`: it changes the road layers in place, adds
the images again and reads the controls again ([the design panel](../guides/design-panel.md) does this).

- **When the tiles stay.** The new look differs from the old one only in colours (the class colours, the access colours, the base map's
  colours, the dark colours, the labels, the selection). The colours of `map`, `data` and `overlays` count as structure: there a colour can be
  one of your data colours. A change of anything else (a width, an opacity, a dash, a first zoom, the base-map theme, a palette name) gives
  `undefined`, and the map stays as it was.
- **What stays.** The tile addresses (the `prefix`), the source ids, the tiles in MapLibre's cache and the feature state of the roads: the
  colours and widths of `rs.setData`, `rsColor` and `rsColorBase` (`rs_c`, `rs_w`). Give the style to MapLibre with `{diff: true}`, so that it keeps
  the sources. The images (`roadstyle:images`) and the controls are in the style's metadata, which the diff does not apply: add the images again,
  and read the controls again.
- **Time.** Burnaby (64,221 roads): about 0.1 s natively, against about 2.3 s for a new map. A refusal takes a few milliseconds.
- A style must have a name: a style with none has `"name": null`, which MapLibre's style check refuses. Give `styleSources` the area's name.


## Write the whole page

`pageFrom` writes the same page as `render_edges(backend="web")` in one call: stage 1, the arrows or the tiles, the views, the options of the dashboard and the page. `look` is the result of `resolveLook(options)`, with `"state": "live"` in its args. Give the same `options` text again, because a view with another palette resolves its look from it. The page has placeholders for MapLibre. Replace them:

```js
const options = JSON.stringify({palette: "amber", args: {state: "live", name: "Monaco", basemap: "osm", views: {plain: {road_fill: false}}}});
const html = pageFrom(roads, resolveLook(options), options)
  .replace("<style>__MAPLIBRE_CSS__</style>", '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/maplibre-gl@5.24.0/dist/maplibre-gl.css">')
  .replace("<script>__MAPLIBRE_JS__</script>", '<script src="https://cdn.jsdelivr.net/npm/maplibre-gl@5.24.0/dist/maplibre-gl.js"></script>');
```

`given` (JSON text) holds what only the host knows: `api_key` (the key of a tile URL), `street_view_key`, and `resolved_basemaps` (base map entries in the form of `data/basemaps.json`). The warnings of the stages go to `console.warn`.

## The level editor in a page

A page with no server can hold roadstyle's level editor: the page makes the area, the solver runs in the page, and the browser keeps
your changes.

1. Make the area's edges. For a duckOSM file, `duckosmPlan(...)` gives the query `"level_edges"`: run it with duckdb-wasm and write
   it as Parquet (`COPY (...) TO 'edges.parquet' (FORMAT parquet)`). It is the input of `duckosm levels`: one row for each `edge_id` of
   every mode's `edges` and `private_edges`, with `highway`, `layer`, `bridge`, `tunnel`, `walk_type`, `junction`, `name`, `edge_ref`,
   `lanes`, `driving`, `cycling`, `oneway` (the driving network's), `modes`, `bus_lines` and the line as WKB in `geometry`. The stored
   levels of `visualization.edge_levels` are for these edges.
2. Make the area's files with `makeArea(edges, options)`. `options` is JSON text with the keywords of `make_area`, each optional:
   `id_col` (default `edge_id`), `highway_col`, `layer_col`, `bridge_col`, `tunnel_col`, `junction_col`, `band_col`, `order`
   (`"priority"`, `"class"`, a column or `null`), `band_dist`, `head_m`, `near_rules`, and `heads` (the text of heads.csv). It gives
   `roads` (roads.parquet), `pairs` and `edits` (pairs.csv and an empty edits.csv), `roadCount`, `pairCount` and `warnings`.
3. Keep them in a store (`saveArea`) and start the editor. Make the area only when its edges changed (`areaIsFor`), and give the
   editor the levels that your map has (`levels`), so that the editor does not solve the whole area again:

```js
import init, * as pkg from "roadstyle-wasm";
import {levelEditor, browserStore, saveArea, areaIsFor} from "roadstyle/static/dashboard/editor/level_editor.js";

await init();
const store = browserStore("monaco", "Monaco");          // the files in the origin's private file system
// meta: visualization.edge_levels_meta; levelsCsv: visualization.edge_levels as CSV text with the columns
// edge, casing_start, casing_level, casing_end, fill_level (SELECT edge_id AS edge, ... FROM visualization.edge_levels)
if (!(await areaIsFor(store, meta.edge_hash))) {
  const a = pkg.makeArea(edges, JSON.stringify({id_col: "edge_id"}));
  await saveArea(store, a, meta.edge_hash);              // roads.parquet, pairs.csv, edits.csv (once) and edges.json
  a.free();
}
const pkgUrl = new URL("roadstyle-wasm/pkg/roadstyle_wasm.js", import.meta.url);   // the package's module, for the editor's worker
const editor = await levelEditor({map, panel: document.getElementById("sb"), backLabel: "Steps", pkgUrl, store,
                                  levels: {csv: levelsCsv, edge_hash: meta.edge_hash}});
editor.addEventListener("solved", async (e) => apply(e.detail.levelsCsv, await e.detail.draw()));
editor.addEventListener("back", () => { editor.destroy(); showSteps(); });   // "← Steps" (the editor asked first, if changes waited)
```

The editor starts from, in this order: the stored levels.csv, when `levels_info.json` names the same inputs (the SHA-256 of
roads.parquet, pairs.csv and edits.csv: `roadstyle_levels::inputs_key`); the `levels` that you give, when their `edge_hash` is the
area's (roadstyle's edge_hash of the area's edge ids) and they have a row for each edge; else a solve of the whole area, and
`editor.answer().resolve` says why (`how`: `"stored"`, `"given"` or `"full"`, and `why`). A cap or a head length is drawing only: the
editor saves it at once, with no solve. A rule (an order wish, a stack part, a rule switched off) is solved again around the change
(`solveLocal`), and the whole area only when the local answer would keep fewer rules.

`levelEditor({map, panel, pkgUrl, store})` runs the engine (the solver, the sources of the map and its tiles) in a Web Worker (`editor/level_worker.js`, which loads the package from `pkgUrl`). The page does not stop while the engine works. The editor draws the area on `map` (your MapLibre map; without it, a map of its own in `container`), and its panel into `panel`. Its tiles have the protocol `lv://`, apart from yours.

??? info "The options, the store and the events of the editor"
    - **A dashboard of yours.** A page has one dashboard (its state is the state of the module). When your map has one, give it as `levelEditor({..., dashboard, prefix})` with the prefix that it was made with. The editor then takes your roads off the map (the layers of the roles in your style's `roadstyle:sources`, by source and source layer; your base map stays). It draws its roads with your prefix and its own sources (`<prefix>lv-roads`), and gives your dashboard its style. The theme of the dashboard (`rs_theme`) and the layers of the base map stay while the editor draws. Without a dashboard of yours, the editor makes one with the prefix `lv-rs-`. When the page has a dashboard and you do not give it, `levelEditor` throws an error.
    - **`look`.** Give the text of your saved look (such as the `look.json` of the page), so that the roads of the editor have your palette and your sections (also the dark theme). The editor puts its own column names, the state `live` and the colours of its picks over it.
    - **`editor.destroy()`.** It closes the editor: it takes off its panel parts, listeners, roads, tiles and images, clears the colour and the glow of the picked roads, and puts your panel, roads, road table and dashboard style back. Your files stay in the store.
    - **The store.** A store is `{load(name, bytes), save(name, data)}`. `browserStore(key)` keeps the files in this browser (in the private file system of the origin; `pairs.csv` of a large area is more than the 5 MB of localStorage). `httpStore(base)` uses `roadstyle serve`.
    - **The event `"error"`.** The editor sends it when its worker stops (no memory, a file that does not load), with `{message, fatal: true}`. Close the editor and open it again.
    - **`editor.dirty` and `editor.exportFiles()`.** `dirty` is `true` after the person applied a change (a solve, a head or a cap): the host's own tables are then behind. `await editor.exportFiles()` gives the four files as texts, `{"edits.csv", "heads.csv", "caps.csv", "levels.csv"}`, so a host that keeps them in its own tables does not read the store by name. Call it before `destroy()`, or after an Apply.
    - **At the open** the editor calls `rsDeselect()` and removes the popups of the map: a road that the page selected is not the editor's.
    - **The event `"solved"`.** The editor sends it after each solve, with `levelsCsv` (one row for each edge: its four drawing numbers, its head lengths and its caps), `levelsInfo` and `draw()` (a Promise of the table of the map, GeoParquet).
    - **Other members.** `editor.roads` is the list of the road ids of the area, in their order. `editor.facts(ids)` gives a Promise of what the panel shows of those roads (by road id). `editor.download(name)` downloads `edits.csv`, `heads.csv`, `caps.csv` or `levels.csv` as they are now.
    - **The phone.** The editor has no frame, fold button, side, width or phone layout of its own: it draws into the panel of the host. Give your page `<meta name="viewport" content="width=device-width">`. A tap on a road picks it, and the targets are 44 px on a phone.
    - **The theme.** The panel follows the theme of the panel of the host (`#sb[data-theme]`).
    - **The files.** The module needs the files of `rust/roadstyle-assets/files/static/` beside it, in the same layout: `dashboard/` with its subfolders, `level_editor.html` (the panel), `dashboard.css` and `popup.css`.

### The editor in the host's panel

`panel` is the host's standard dashboard panel: an element with `.sb-card`, in it `.sb-top` (the title first, then the hide button) and
`.sb-body` (`levelEditor` throws an error when a part is missing). The editor changes only these parts, and `destroy()` puts them back:

- the host's `.sb-body` is hidden (its scroll place is kept), and the host's title in `.sb-top` is hidden. The top line is "← Steps"
  and "Edit levels" before the host's hide button; under it are the tabs Road ends, Stacking, History and Issues. `backLabel` is the label (default
  `"Steps"`); `backLabel: null` has no button (a page with no steps).
- the apply bar is at the bottom of the panel (on a phone: of the sheet) and shows only when changes wait: "N waiting", Discard and
  Apply and solve. "N waiting" opens the list of the changes, and each can be taken out. The bar stays when the panel scrolls.
- "← Steps" with no change waiting sends the event `"back"` at once. With changes waiting, the bar asks: Apply (solves, then sends
  `"back"`), Discard (drops the changes, then sends `"back"`) or Stay. The host answers `"back"` with `editor.destroy()` and shows its
  steps.
- the map keeps all roads. The picked roads have the dashboard's own selection glow (`rsSelect`), and the editor's colours tell road 1
  from road 2. The toolbar is the dashboard's and does not change.

The colours are the panel's tokens (`--bg --ink --mut --line --card --accent`). Without a map of its own (`map` not given), give
`template` (the `dashboard` of `data/host_options.json`) so that the editor's dashboard has the template's panel and bar; `roadstyle
serve` does this in `level_editor/app.js`.

### The editor on your map, with no map of its own

When your page already draws the area's roads and levels, give `host`: the editor then builds no roads and no tiles. At **open** it loads the
stored area into its worker (`LevelArea`), starts from the map's levels, and draws its panel. The map does not change: your roads, your road
table and your tiles stay as they are (Burnaby, 76,189 roads: about 1.7 s, against 7.9 s more for an own map: draw, stage 1, road table
and stage 2). At a **change** (an apply) the editor solves the changed rules and gives `replaceRoads` only the rows of the edges whose levels,
heads or caps changed. Your page redraws only those edges and the edges near them (`LiveMap`, below), and the map's other tiles stay.

```js
const editor = await levelEditor({map, container, pkgUrl, store, dashboard: rs, prefix: "rs-", look: lookText,
  host: {edgeIdCol: "edge_id", replaceRoads: async (rows) => redraw(rows)},
  colors: {select: "#e53935", hover: "#ff8a80", second: "#1e63d6"}});
```

- Your map, your roads and your pick stay as they are. Your road table (`window.RS_SIDE`) must keep the edge id field (`edgeIdCol`,
  default `edge_id`) and the lines. The editor adds the fields `road`, `s_lon`, `s_lat`, `e_lon` and `e_lat` to each row, and again
  when you put a new table in `window.RS_SIDE`. `destroy()` takes them off.
- The picks are the editor's. Give `look`, the text of the look that made your roads' style (such as the page's `look.json`): the editor
  finds your select and hover colours in it (`map.interaction.select_color` and `hover_color`, else `selection.select` and `hover`) and
  swaps them in your road layers' paint: road 1 is red, road 2 is blue, and the hover is lighter in the colour of the next pick (`colors`).
  `destroy()` puts your paint back. While the editor is open, a click shows no popup and a hover shows no tooltip (`quiet`
  of `dashboard/select.js`). Without `look`, your roads keep your own select and hover colours.
- After an apply, `replaceRoads(rows)` gets the rows of levels.csv (one object for each edge, its fields as text: `edge`,
  `casing_start`, `casing_level`, `casing_end`, `fill_level`, `head_start_m`, `head_end_m`, `cap_start`, `cap_end`) of only the edges
  whose levels, heads or caps changed. Draw them, then resolve the Promise. The `"solved"` event comes too. When the redraw sets a new
  style, the editor takes your new layers' colours again.
- To draw the rows fast, make your map's tiles with `LiveMap` in place of `tilesOfSources`: `new LiveMap(styleSources(roads, look), look,
  prefix, keep)` has the Tiler's `style()` and `tile(source, z, x, y)`, and `relevel(JSON.stringify(rows))` gives the edges new
  values. It runs stage 1 again and replaces in the tiles only the pieces of the edges that changed and of the edges at their end
  nodes. The answer is `{edges, pieces_gone, sources, style_changed}`: then load the visible tiles again (with `style_changed`, set
  the style again). Your roads must have the level, head and cap columns that the look names (`casing_start_col`, ...,
  `cap_end_col`). A head or a cap: Monaco about 70 ms, Burnaby 0.8 s; a level change: Monaco about 120 ms, Burnaby 1.7 s (stage 1 of
  the whole area; a new map is about 5 s).
- `colors` (each optional, also without `host`): `select` is road 1 of the panel, `second` is road 2, `hover` is the hover of the
  editor's own map.

The editor's engine (its worker, the `LevelArea` in it and the parse of the area's files) takes seconds to make, so the editor keeps it. With `host` and
`levels.edge_hash`, `destroy()` leaves the engine alive, and the next `levelEditor` with the same `edge_hash` and the same `store` uses it: the open then
starts no worker and loads no area (Burnaby: 0.4 s, against 1.4 s). `prepareEditor({store, pkgUrl, look, edgeHash})` (exported) makes the engine ahead of
the first open, in the background, for example when the page is idle after it drew the map: the open then waits only for what is left. A new
`edge_hash` (the area's edges changed) ends the old engine and makes a new one. Each open reads the small files again (`edits.csv`, `heads.csv`, `caps.csv`,
`levels.csv`) and gives the engine the map's levels (`startFrom`).

A test keeps the open fast: with `host`, the editor's worker gets no `build`, `draw` or `tile` call at open or at a change
(`tests/test_level_editor_page.py`).

## Keep the main thread free

For a large area, run the engine in a Web Worker, as duckosm-rust does: the worker keeps the `Tiler` and answers `tile` and
`props`, and the main thread only draws. A new worker for each style gives the memory of the old style back to the browser.
`memoryBytes()` tells you how much memory the module uses.

**See also:** [The `rs` object](../reference/javascript.md#the-rs-object) ·
[Interaction contract](../reference/contract.md) · [Make tiles and PMTiles](tiles.md)
