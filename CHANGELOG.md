# Changelog

All notable changes to **roadstyle** are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **The level editor in a page with no server.** `makeArea(edges, options)` (roadstyle-wasm; `roadstyle::level_area::make_files` in
  Rust) makes a level area's roads.parquet, pairs.csv and edits.csv in memory, the same bytes as the folder form. `duckosmPlan` gives
  the query `level_edges`, the edges of a duckOSM file's level area (duckOSM's `load_roads`, the same rows and columns on Monaco). The
  editor is a module, `static/dashboard/editor/level_editor.js`: `levelEditor({map, container, pkg, store})` on a host's map or one of
  its own, with `browserStore` (the files in the browser) or `httpStore` (`roadstyle serve`), the event `"solved"` (levels.csv and the
  map's table) and downloads of edits.csv and levels.csv. `roadstyle serve`'s page uses the same module. On a host map the editor's
  sources have names of their own (a host whose base map shares the roads' tile source keeps it), and the panel follows the page's
  theme (dark with the system, unless `data-theme` on `<html>` says otherwise). The engine runs in a Web Worker
  (`editor/level_worker.js`): on Tartu (64,828 edges) the longest main-thread task is 0.3 s, not 4.4 s. **A host changes one argument:**
  `levelEditor({..., pkgUrl})` (the URL of `roadstyle_wasm.js`) in place of `pkg`; the event's `draw()` gives a Promise, and `editor.roads`
  (the roads) takes the place of `editor.area`. The worker's calls are `static/dashboard/worker/call.js` (`caller`, `answer`), which the
  browser studio (`ui/studio`) uses too; a worker that stops rejects its waiting calls. On a phone the panel is a sheet at the bottom
  (`layout`: `"auto"`, a sheet up to 700 px wide; `"sheet"`; `"side"`), with a handle (one row, half, full), taps on the roads, 44 px
  targets, room for the keyboard, and a fold when a Street View or Google 3D window opens at the bottom.
  `browserStore` keeps every file in the origin's private file system, also the texts (pairs.csv of Burnaby is more than
  localStorage's 5 MB); a text that an older version kept in localStorage moves there when it is read.

### Changed
- **roadstyle's files have one copy, the crate roadstyle-assets** (audit N25). The profiles and palettes, the base map's files,
  `cmaps.json`, `basemaps.json`, `defaults.json`, the sprite, the dashboard's JS and CSS, the popup files, the page templates, the
  level editor's page and the vendored MapLibre moved from `src/roadstyle/{data,static,templates,vendor}/` to
  `rust/roadstyle-assets/files/`, with the same names under it. Each crate takes its files from there at compile time
  (`roadstyle_assets::text!`): a wrong name does not compile, and a binary has only the files that it names (the wasm module does not
  change). No crate builds in a file of `src/roadstyle/` now, so the crates can be packed (`cargo package`). Python has no copy: it
  asks the extension (`roadstyle._assets`, `_rust.asset(name)`), so a source checkout needs the built extension. The npm package
  `roadstyle-dashboard` packs from `rust/roadstyle-assets/files/static/`. The level editor's wasm package is now built to
  `$CARGO_TARGET_DIR/editor-pkg/` (rust/roadstyle-wasm/build_editor.sh).
- **Deprecated: the old paths `src/roadstyle/static/dashboard/`, `popup.css`, `popup.js` and `level_editor.html`.** They are a
  generated copy (`rust/roadstyle-assets/sync_old_paths.py`, checked by a test) for one release, for a page build that copies them
  from a roadstyle checkout. They go in roadstyle 0.27.0. They are not in the wheel.
- **`roadstyle-levels` is a leaf crate** (audit N26): its only dependencies are rstar and sha2, 17 crates in all (it was 49, with
  Arrow through roadstyle-model). The road flags' rule (`NO`, `yes_text`, `layer`, `level`, `directed`, `sql_yes`) is
  `roadstyle_levels::flags` now; `roadstyle_model::flags` re-exports it with the JSON value's `yes` and `maplibre_yes`. duckosm-rust
  can take the levels alone. CI fails when the levels depend on more.
- **`cargo test` at `rust/` builds 113 crates in about 1 minute, not 195 in 5** (review D1). The programs `roadstyle-cli` and
  `roadstyle-snapshot` (bundled SQLite, headless_chrome) are not default members: CI tests them in a step of their own (`-p`). Fat LTO
  and one codegen unit moved from `release` to a new profile `dist` (`inherits = "release"`), which the wheels (`maturin --profile
  dist`) and the wasm packages (`build_editor.sh`, `npm run build`) use. `roadstyle snapshot` is the default feature `snapshot` of
  roadstyle-cli.
- **`roadstyle_levels::ROADSTYLE_VERSION` is the crate's version** (review D13): it said 0.24.2 in 0.25.0, and duckosm-rust writes
  it into `edge_levels_meta.roadstyle_version`. No level check reads that value (they compare `edge_hash` and `n_edges`).
- **A level area's roads.parquet has the ids as Int64** (audit N28, both engines). `road`, `edges` and `reversed` are Int64 and
  list<Int64>, duckOSM's BIGINT edge ids, written by `make_area` in Rust and in Python (`roadstyle.level_area.write_roads`; an id
  column of text, which only the Python engine takes, stays text). The readers take both, so an area made before still opens:
  `read_roads` (new) and the editors give the ids as text in memory. `rs.level_input` keeps its in-memory frame as text, because
  duckosm-rust/tools compares the ids as text (a frozen repo). The level editor's answers are typed in Rust (`Answer`, the conflicts),
  and the program's `levels solve` reads them without a JSON parse back. The page's JSON does not change.
- **The program reads GeoJSON, Shapefile and GeoPackage roads** (audit N18). `roadstyle sources`, `page` and `levels make` read
  the roads by the file's extension (`.parquet`, `.geojson`, `.shp` with its `.dbf` and `.prj`, `.gpkg`) through roadstyle-io's
  readers. Before, they read only GeoParquet, though the program was built with the GeoPackage reader. Another extension is an error
  that names the file.
- **`serve` is a crate of its own, `roadstyle-serve`** (audit N17). The program (`roadstyle serve`) and the Python binding
  (`roadstyle._rust.serve`) call it, so the Python extension no longer builds roadstyle-cli: 105 crates, not 170, with no
  headless_chrome and no C SQLite. httparse (=1.10.1) parses the request line and the headers in place of the hand-written parser;
  tiny_http 0.12.0 was not used, because it has no limit on them. The limits and checks do not change (127.0.0.1, Host, Origin, 64 KB
  of headers, 16 MB of body). New: more than 64 headers is 431, a PUT with no Content-Length (a chunked body) is 411, a request that is
  not HTTP is 400, and each `serve` call answers with its own area's name (before, a second call in one process kept the first name).
### Security
- **The page does not run a script from its data** (audit N23), in both engines. The dashboard put road names, column values and the
  labels of overlays and legends into HTML with no escape, so a road named `<img src=x onerror=...>` ran a script on every page. Now one
  `_esc` (`static/popup.js`) escapes them, at each place. The page writers (`render_web._script_json`, `page.rs` `script_json`) write each
  `<` of the JSON in a page's `<script>` as `\u003c`, so a data value with `</script>` in it (a legend's label) cannot end the script
  either. The HTML that the page's author gives (`side_panel_html`, a sidebar's template, `rsInfoShow(html)`) is not escaped:
  `docs/design/dashboard_module.md`, "Trusted inputs".

### Fixed
- **The 3D buildings of a duckOSM file have the height of all the digits of their tags.** The reader's SQL
  (`roadstyle_io::duckosm`, for Python and the browser) read a tag as `tags['k'][1]`. In DuckDB 1.5 and in duckdb-wasm, `tags['k']` is
  the text, so `[1]` gave its first character: `building:levels` "25" was "2", and the building was 7.32 m high, not 91.5 m. The SQL
  now reads `map_extract(tags, 'k')[1]`, which is a list in every DuckDB version. On Monaco, 104 buildings have a tag with two or more
  characters.
- **A road is picked again on a page whose style has no interaction contract** (a host's `makeStyle`, the duckosm-rust page, the
  level editor). Since R7 the dashboard picked a road only on the layers of the option `pick`, which only a style with the contract
  has: on the other pages no road had a hover, a tooltip or a click (`rs:select`), and Street View waited for a click. With no `pick`,
  the dashboard picks on the road layer of simple mode again. A test moves and clicks the real mouse on both kinds of page.
- **Two readings of a duckOSM file at the same time on one connection no longer break each other** (the duckosm-rust page: "Table with
  name e does not exist!"). The reader's temporary tables have the run's own names (`duckosmPlan`'s optional `run`, returned in
  `"run"`; each base-map layer's `"table"`; `"drop"` drops them), and `duckosmFeaturesSelect(specs, run)` takes the run. `roads_sql.js`,
  `features_sql.js` and Python's `duckosm.read` use them.
- **On a phone, the boxes start folded.** On a screen 700 px wide or less, the Roads, Layers and Legend boxes start folded,
  as the side panel starts closed; a tap on a box's title opens it. Before, the Roads box of a page with the default options
  covered about half of the map at 390 px. A wider screen does not change.
- **A look colour "#fff" no longer crashes `export_look`** (review D4: a panic in Rust, an abort in the browser). One colour module in the
  look crate (`roadstyle_look::color`) reads every colour of the look: "#rrggbb", "#rgb" and a CSS colour name; any other "#..." text is
  an error that names it. One mix rounds half up for the look and the export (the base map's look rounded half to even: some of its
  casing colours move by 1 in one channel).
- **The duckOSM reader reads a file with no `private_edges`** (an older file, granville_island): the union typed its `access` as an
  integer, and the roads failed with "Could not convert string 'bus' to INT32". mapstyle's SQL had the same fault. And the reader's plan
  gives the base map's queries also for a file with no network ("roads" is null, "roads_error" says why).

### Dependencies
- **The `numeric` extra no longer installs matplotlib.** Only the colour ramps used it, and they are data now
  (`data/cmaps.json`). A matplotlib colormap name still works for `cmap`. branca stays: folium's page elements use it.

### Changed
- **The dashboard tests no layer id for a prefix** (R7). The road filters act on the layers of the road roles (`sources`, `roadstyle:sources`), and a road is picked on the layers of the new option `pick` (`roadstyle:controls`). A deck is known by its role `decks`.

- **The colour ramps have one source for both engines**: `src/roadstyle/data/cmaps.json` (branca's 269 schemes and colour names, and the
  180 matplotlib colormaps at 9 stops). Python's `ColorRamp` reads it, as roadstyle-look does, and no longer asks branca or matplotlib:
  all 445 ramps give the same colours as before (tests/test_colors.py).
- **The look's and the readers' errors are typed** (Rust only). `roadstyle_look::Error`: a saved look that is not read, a later look
  version, wrong options, an unknown name, a YAML file that is not correct, an image that is not read. `roadstyle_io::Error`: bytes that
  are not a file of the kind, data that the call cannot use, a wrong argument, stored levels that are missing or of other edges, a CRS
  that is missing or not read, a Parquet writer that stopped. Each has the same message text as before; `String::from(error)` gives
  it, so a caller whose errors are text keeps its `?`. Python and JavaScript show the same messages.
- **The road model's and the tiles' errors are typed** (Rust only; docs/design/target_architecture.md, T3). `roadstyle_model::Error`:
  a column that the model does not take (`Column`, with the column's name: a column type that it does not read now names its column)
  or a geometry that it does not take. `roadstyle_tiles::Error`: tile settings that are not correct, or an archive with no tile
  (`Empty`). Both enums are `#[non_exhaustive]`. Tile zooms after 24 (MapLibre's last zoom), a first zoom after the last and a buffer
  below 0 are errors: before, a `maxzoom` after 31 stopped the program (an overflow in the archive). `Tiles::new`, `tile_stage` and
  `Tiles::archive` return a `Result` (`archive` gave `None` both for bounds that are not longitude and latitude and for no tile).
- **A road's key is a type: `roadstyle_model::RoadKey`** (Rust only; docs/design/target_architecture.md, (b) item 4): `table << 32 | row`,
  below 2^53 while the table is below 2^21 (`RoadKey::TABLES`; a larger table is `Error::Key`). The engine writes the keys of the
  roads (`__rs_edge`, `__rs_edge2`, the decks' `__rs_edges`, the slots) through it and reads a row back from a key. A build has one
  table (0), so a key is its road's row and the output does not change.
- **The base map goes through stage 1 as typed tables** (audit R10, step 2; docs/design/r10_feature_table.md). The Rust engine reads
  features.parquet into one table (Arrow columns and one coordinate buffer), cuts the sea out of it, and keeps each base-map layer as a
  table until it writes the GeoJSON text, not a JSON tree for each feature. The output is the same bytes (the styles, the files and the
  tiles of Monaco and Tartu). On Tartu, stage 1 needs 284 MB, not 403 MB, and the base map's part of make_sources takes 58 ms, not 115 ms. Stage 2 cuts the tiles from the tables too: make_tiled takes 1,752 ms, not 2,074 ms, and 344 MB, not 483 MB.
- **export_look: the yes/no tags use the engine's rule** (audit R6, both engines). A oneway, tunnel or bridge value is yes unless it
  is missing or "", "no", "false" or "0" (lower-cased), as on the map that the engine draws. Before, the exported look had lists of
  yes values, so tunnel=covered and other values not in the lists were not tunnels in it. Of Monaco, Södermalm and Tartu, only
  Tartu's 6 edges with tunnel=covered change (edge_id 362803906715553762, 2028099516943553165, 2430057063666112407,
  4366746885451034747, 6872884880915285120, 7467383434792342616): they are now tunnels in the exported look. The engine's own
  yes/no check (roads.rs) uses the same rule (`roadstyle_model::flags`).
- **Python gives the roads to the Rust engine as an Arrow table, not as GeoParquet bytes** (audit R15). The binding
  (`roadstyle._rust`: `make_style`, `make_sources`, `Tiler`, `compute_levels`, `make_area`) reads any object with
  `__arrow_c_stream__` (GeoPandas' `to_arrow`, a pyarrow table, DuckDB's `arrow()`) through the Arrow C stream interface. Bytes are a
  `TypeError`. The output does not change. On Tartu (64,828 edges), `compute_levels(method="tags")` takes 66 ms, not 123 ms: there is
  no Parquet encode in Python and no Parquet decode in Rust. `duckosm.read` gives Arrow tables. In Rust, `roadstyle_io::read::roads_from`
  and `table_from` read Arrow batches, and the facade has `tiled_of` and `features_of` for roads that a reader gave.
- **The Rust engine makes the whole page in one call** (audit R3). `roadstyle::page_options::page_from(roads, look, options, given)`
  runs stage 1, the arrows or the tiles, the views and their palettes, builds the options of `rsDashboard` (typed: `page::PageOptions`)
  and writes the page. Python's `render_edges(engine="rust")`, the new command `roadstyle page` and the browser's `makePage(roads,
  look, options, given?)` call it. Python gives only what it alone knows: the data steps, the look's options, the base maps' keys and the
  Google Maps key. A view's palette resolves its look in Rust (Python makes no extra looks). The page writer gzips the road table and
  the big sources itself; the two engines' pages are the same byte for byte but these blobs, which are the same when read back.
- **`rust/roadstyle-wasm/bench.mjs` measures the browser's path** in Node: `makeSources` and `tileSources` with the base map, and the
  wasm memory after them (Monaco 110 MiB, 7.0 KiB for each road; Tartu 213 MiB, 3.1 KiB). docs/rust/parity.md has the table, and the
  target architecture's (j) the memory target for each road in the browser.
- **A test that the Python binding passes the output through** (`tests/test_binding.py`): on Monaco, the binding's style, road
  table and page are the Rust facade's texts byte for byte (the hashes in the Rust goldens, which `tests/areas.rs` makes). A page
  gives the CARTO no-key warning once, not once for each CARTO base map of the switcher.
- **The areas' goldens are the Rust engine's own** (2026-10-24: the Rust API is the design). `tests/areas.rs` checks the style and
  the tiles of Monaco, Södermalm and Tartu against summaries in git (`rust_style.json`, `rust_tiles.json`, about 2 KB each), which
  `ROADSTYLE_BLESS=1 cargo test` writes. The comparisons with Python's `golden_style` and `golden_tiles` are gone; the levels, the
  colour cases and the looks are still checked against Python.
- **`examples/bench.rs` measures the stages** (review 4, D9): the time, the peak memory and the memory after each stage, on Monaco
  and Tartu (`cargo run --release -p roadstyle --example bench`; the numbers are in docs/rust/parity.md). The archive (PMTiles) and
  the CLI's XYZ folder make each tile once, with no cache (`Tiles::build`; `Tiles::tile` keeps its cache for a map): Tartu's archive
  7.2 s to 6.4 s, peak 663 MB to 596 MB, and no 68 MB of cached tiles after it.
- **One style builder, and the page writes each source once** (review 4, D3 and N29). `Sources::style_with` makes the style with
  no source's data in it, and `Sources::write_with` writes it, with each source's data written into the text as it goes. Stage 2
  (`tile_stage`) and the page (`page_from`) use them: no source is cloned, written and parsed back any more. The page's JSON is
  `serde_json`'s compact text, each `<` as `\u003c`; Python's `json.dumps` copy in Rust (`pyjson`) is gone. On Tartu, the Rust page:
  peak memory 1.91 GB to 0.60 GB and 4.1 s to 2.5 s (no gzip), 1.84 GB to 0.42 GB and 6.3 s to 5.5 s (gzip); `make_tiled` stays
  at 173 MB (it tiles every source).
- **An exported style tells an app's dashboard its roads** (audit 3, N27, both engines). `export_style`'s metadata has
  `roadstyle:sources` (the road roles) and `roadstyle:controls.pick` (the layers that a road is picked on), from its final layers, as a
  live style has them. A dashboard on an exported style finds and picks the roads with no layer-id prefix.
- **The Rust tests compare with Python's own output again** (audit 3, N27). The goldens are made again with today's Python
  (`goldens-2.tar` on the pre-release `rust-test-data`; `goldens-1.tar` stays for the older commits), and the test helper that
  rewrote the old goldens (`as_decided`) is gone.
- **The dashboard gets its road layers from the engine** (R7, both engines). `roadstyle:sources` has only the road roles: the
  overlays (`ov<i>`) are in their own list, `overlays`, and the boundary is not a road. The new control `pick` lists the layers that a
  road is picked on: `roads-simple` (the full look: its fill layers) and the 3D decks' tops, not their casing.
- **`roadstyle:controls` has no page keywords** (rule 5, R3). It has the facts of the look and of the roads that a host's dashboard
  needs (the filter panel, the overlays, the tunnel look, `select_color`, `pitch_3d`, ...). `tiles` and `views` are not in it any more:
  they are the caller's page keywords, which the page gives in `RS_OPTIONS` and a host gives to `rsDashboard` itself.
- **`sidebar="dashboard"` or `"report"`**: the bundled sidebar of `render_dashboard` and `render_report`, in both engines. It sets
  `name`, `basemap_switcher`, `filter_control` and `road_popup` where the call gives none (`pages.SIDEBAR_DEFAULTS`). The two
  functions now pass `sidebar=` to `render_edges`, so the Rust engine makes these pages too, and the CLI with `--sidebar`.
- **The page has its options in one object** (audit R3, step 1, both engines). The template's 38 placeholders of the dashboard's
  options and the camera are one `__RS_OPTIONS__`: the JSON object `RS_OPTIONS` has the options of `rsDashboard` and `camera`
  (`center`, `pitch`, `bearing`, `max_pitch`, `bounds`), and the page calls `rsDashboard(map, {...RS_OPTIONS, style})`. The page
  writers fill in the frame's four tokens in one pass, so a value is not read again. A script that read the page's text
  (`maxPitch:70`, `\n  tiles: true,`) reads `RS_OPTIONS` now.
- **`js/roads_sql.js` and `js/features_sql.js` run the SQL of `duckosmPlan`** (roadstyle-io's `duckosm.rs`), the one copy that
  Python runs too. They have no SQL of their own now. Their functions and arguments do not change, and a new `readCatalog(q, catalog)`
  gives the catalog that `duckosmPlan` reads. Load the module (`init()`) before you call them. On Monaco they write the same
  `roads.parquet` (stored levels and tags, every mode) and `features.parquet`, byte for byte, as before.
- **The simple look reads the colour of `rsColor` and `rsColorBase` from the feature state `rs_c` only** (audit N8, part 2, both
  engines). The fill is the active option's colour under `rs_c`; an item's colour is `rs_c`, else its own; a painted road sorts on top
  by the global state `rs_top` (the rows that `rsColor` painted, start value `[]`). The state has `rs_top` in place of `rs_colors` and
  `rs_base`. The full look (`simple=False`, Python only) keeps `rs_colors` and `rs_base`.
- **Every style reads a road's colour and width from the feature state** (audit N8, both engines). The road layer reads
  `["coalesce", ["feature-state", "rs_c"], <baked colour>]` and each width and offset stop × `["coalesce", ["feature-state", "rs_w"], 1]`,
  in every style, not only with `live_data`; `live_data` now only adds the metadata `roadstyle:live` and the page's option `live`.
- **`rsColor` and `rsColorBase` write the feature state `rs_c`** (audit N8, the dashboard). A road gets one colour on the row that draws
  it: the colour of `rsColor`, else that of `rsColorBase`, else that of `rs.setData`. A road of a two-way pair drawn as one line
  (`__rs_dup`) gets its colour on its twin's row. The rows that `rsColor` painted are in the global state `rs_top` (a list of rows, with
  no colours), which the sort key reads: a painted road stays on top of the others of its level. The global states `rs_colors` and
  `rs_base` (a colour for each road, which made MapLibre lay out every tile again) are not written any more on the simple look. The full
  look (`simple=False`) keeps them until it is removed.
- **The base maps are a data file**, `src/roadstyle/data/basemaps.json`: one list for Python (`roadstyle.basemaps.BASEMAPS` and the
  switcher's default set) and the studio in the browser. The values are the same as before.
- **The look is a crate of its own, typed and versioned** (`rust/roadstyle-look`, design step (c), audit R16). `Look::resolve` makes
  the look one time from the palette, the profile, the settings and the keywords; `Look::from_json` reads a saved look of version 1 or of
  version 0 (the `look.json` of 0.25.0, with no `schema_version`). A look of a later version, or an unknown key, is an error that names
  it. The look has `schema_version: 1`; all else in it is as before, and every style is the same (the Rust goldens, Monaco and Tartu).
  The engine reads the typed parts that the look makes one time (the road width model, the class styles, the slots and the decks), not
  the JSON again in each stage: before, one `make_tiled` parsed the look 3 times and made the width model 4 times. The look crate and
  the road model do not depend on each other.
- **The bindings take a look handle, not its text.** JavaScript: `resolveLook(options)` gives a `Look` (`makeLook` is its old name for
  one version), `Look.fromJson(text)` reads a saved look, and `makeStyle`, `makeSources`, `new Tiler` and `exportLook` take the `Look`.
  Python (`roadstyle._rust`): `resolve_look(options)` and `Look.from_json(text)`, with `json()`, `part(key)` and `with_arg(key, value)`.
  **A host that passes the look's text** (the duckosm-rust map worker, the GeoLibre plugin's worker) changes one line when it moves to
  this version: `makeStyle(roads, Look.fromJson(lookText), ...)`, and the same for `new Tiler(...)`.
- **The engine has no hidden state between calls** (audit R17). The class filter's column goes with the roads through the stages, and
  the warnings come back with the output (`Sources::warnings`, the third value of `make_tiled`), not in thread-locals; the user's own
  profiles and palettes go through the look's resolution. A colour option's fill name uses the one table of property names. The Python
  binding keeps the warnings of its calls for `take_warnings()`, so the Python warnings do not change. The property names' table
  (`props::intern`) and the level solver's cache stay global for now: the first is part of R11, the second belongs to the level solver.
- **The road layer reads its class tables by an index** (R8, both engines). Each width and offset table over the classes is one
  `["at", ["get", "__rs_ci"], ["literal", [...]]]`, and each feature of `simple` has its class index `__rs_ci`. A piece keeps only what
  the road layer and the page read on it, so it has no `highway` any more (the page reads the class from the road table). On Tartu:
  the road layer 63.5 KB to 31.7 KB, the `simple` source 40.3 MB to 39.5 MB.
- **The features carry only what is read** (R1, both engines). A road piece keeps the properties that the layers' expressions, the
  page's modules (`static/dashboard/reads.json`), the popup and the tooltip read; a road keeps its fields and the stage values that are
  read; the road table keeps the fields, the stage values that the page reads on a row, and the fills. The GeoJSON, the GeoParquet files
  and the tiles follow the same rule. On Tartu: the page 16.0 MB to 14.5 MB, the `simple` source 58.9 MB to 40.3 MB, the `roads` source
  64.7 MB to 53.4 MB. The level editor's update in place sends its features as the page has them.
- **Every simple style can be driven by a dashboard.** The pieces have their road's row as their feature id (`promoteId: "__rs_edge"`
  on `simple`, `{simple: "__rs_edge"}` on the vector source of a tiled style), and the road layer has the glow of a selected or hovered
  road, in both engines and in every style: a page, `export_inline`, `export_style`, and a host that calls `makeStyle` or
  `makeSources` directly. Before, only a page had them, so no road glowed on a host's map.
- **A view's palette on a Rust page is a restyle in Rust.** Stage 1 runs one time. Each other palette of `views` restyles the same roads
  in memory (no second read, no second level solve, no JSON text), and the Rust engine merges the properties that differ
  (`roadstyle-engine::palettes`, as `render_web._merge_palettes`). On Tartu with two palettes: 13.4 s to 5.7 s, peak memory 1.84 GB to
  0.87 GB. A page with no views does not parse the road table in Python any more (4.8 s to 4.0 s).
- **The palette copies of a page have a fixed order.** `_merge_palettes` writes `<key>@<palette>` in the order in which the keys first
  differ, not in the order of a Python set (which changes with the hash seed). A feature gets a copy only when its feature in that palette
  has the key: a casing piece has no `__rs_fill@<palette>: null` any more. The map does not change.

### Added
- **A base-map layer's overlay entry names its 3D layer** (`roadstyle:controls.overlays[].extrude`, the fill-extrusion's id), so a host's
  dashboard finds the 3D buildings on a page, whose layers have no metadata. The dashboard reads it (`features.js`, with the page's
  prefix), not the layer metadata: before, `rsSetBuildings3D(true)` did nothing on `roadstyle.duckosm.page`.
- **`roadstyle.duckosm.page(db, mode, ...)`: mapstyle's `render_map` on the Rust engine.** The page of a duckOSM file: its roads, its
  base map and the shared dashboard with the base map's controls (modes, kinds, each layer's clicks, tooltip and popup). The keywords of
  render_map: `theme`, `paths`, `layers`, `only`, `interaction` (a layer's start `{clickable, tooltip, popup}`; a layer that the map does
  not have is a warning) and `dashboard=True` (the report page with the colour option "Modes"); the others are render_edges' keywords.
  The base map's look gives the page its base map: blank, in the theme's land colour, with the raster maps in the switcher. The route
  planner stays mapstyle's. In Rust, `page_options::page_from` takes the base map's rows (`features`), and so do the Python binding's
  `page_from` and the browser's `makePage`.
- **`duckosm.read(levels="auto")`, the default of `duckosm.page`** (render_map's rule): the stored levels when the file has
  `visualization.edge_levels`, else the engine solves them, with the warning "no visualization.edge_levels in this file: roadstyle solved
  the levels; run duckosm levels to store them". Stored levels of other roads stay an error, and `levels="stored"` stays strict (now with
  the reader's message, not DuckDB's, when the file has no table). `layers` can be a list of layer names, as in render_map.
- **What the dashboard needs to draw a duckOSM map's page** (for its port of mapstyle's page scripts): the base map's look bakes the
  restricted roads' colour (private, bus, pedestrian, delivery) into every colour option's fill (`access_col: "access"`; mapstyle's
  `layers.js` painted the same colours on the page); `roadstyle:controls.modes` gives the map's modes with their counts of roads
  (`[[mode, count], ...]`, from the map option `modes`); `roadstyle:controls.box_layout` is `"stack"` for a base map's page; and each
  base-map layer's entry in `roadstyle:controls.overlays` has its start `interactive` (mapstyle's rule: not for landcover, water, paved
  and the decoration lines) and its `kinds` with their counts, most first. On Monaco all 17 layers equal mapstyle's.
- **`rs.setData(rows, {stepped: true})`**: each road gets the ramp's nearest stop, not a colour between two stops, and the legend shows the
  same steps. SonoFlow's Daily page colours so, which lets it move to live data in the simple look with the same look.
- **The dashboard has mapstyle's page functions** (docs/design/mapstyle_page_scripts.md), found by their roles in the metadata, not by
  layer ids: `rsSetModes` / `rsGetModes` / `RS_MODES` (the roads of some modes, from `roadstyle:controls.modes` and the road table's
  flags), `rsSetKinds` / `rsGetKinds` / `RS_KINDS` (a base-map layer's kinds), `rsSetInteraction` / `rsGetInteraction` (a layer's
  clicks, tooltip and popup), `rsSetBuildings3D` / `rsGetBuildings3D` (the layers with `roadstyle:group` "buildings 3D", with a button
  and a Layers row), and `box_layout: "stack"` (the Roads and Layers boxes folded, Layers under Roads). `rsFilter` on an overlay now
  keeps each layer's own filter. The engine writes the new metadata (`modes`, the overlays' `interactive` and `kinds`, `box_layout`)
  in a later change.
- **The Rust engine reads Shapefile and GeoPackage road files** (`roadstyle-io`: `shp.rs`, `gpkg.rs`, `crs.rs`). Each gives the
  `RoadTable` of the GeoJSON reader, with the same column types. A file's CRS goes to EPSG:4326 with the rule of Python's
  `validate.to_wgs84`: no CRS is an error, EPSG:4326 stays as it is, another CRS is reprojected (proj4rs, pure Rust; an EPSG code
  through crs-definitions, a WKT text through proj4wkt). A CRS that the reader cannot read is an error that names it. GeoPackage is
  SQLite (C), so it is the feature `gpkg`, for the native programs only. The wasm package has `readShp(shp, dbf, prj?, name?)`, and
  CI fails if `roadstyle-wasm` depends on SQLite.
- **The map of one mode from a duckOSM file** (`only=True` in `roadstyle.duckosm.read`, `export_inline` and `export_style`, as mapstyle's
  `render_map(only=True)`): the `edges` and `private_edges` of one network. The stored levels were solved for every mode together, so each
  road must have its stored row (as Python's `load_area_levels(subset=True)`), else an error that names how many and one of them; then the
  look's `levels` keyword names these roads. JavaScript: `duckosmPlan(..., only)` and `duckosmSubsetLevels`. On Monaco the driving and
  walking maps are mapstyle's but for the 3D decks and, in these maps only, 87 name slots and 1 to 2 attached points of the Rust engine.
- **The base map's look for Python callers**: `roadstyle.duckosm.base_map(mode, theme=, paths=)` (the palette, the settings, the base
  map's part and the mode's map options), `roadstyle.duckosm.theme(name)` and `roadstyle.duckosm.recolor(colour, transform)`, all made
  by the Rust engine. The mapstyle shim reads them. `Look.part` also gives `palette`, `settings` and `features`.
- **mapstyle's export_style on the Rust engine**: `roadstyle.duckosm.export_style(db, out_dir, base_url=, mode=, theme=, paths=)` writes
  the map of a duckOSM file as style.json, vector tiles (the roads and the base map), the sprite and the popup's files. On Monaco its
  style.json has mapstyle's layers and sources. The Rust engine's `export_style` now writes, as Python's does, every tile with data
  (the base map can reach past the roads) and an empty file for each other tile in the roads' box, and keeps the base map's images.
- **mapstyle's export_inline on the Rust engine**: `roadstyle.duckosm.export_inline(db, mode, theme=, paths=)` reads the duckOSM file
  (`roadstyle.duckosm.read`), makes the base map's look (`roadstyle.duckosm.look`: with render_map's map options) and runs stage 1 in
  Rust. On Monaco its style is today's mapstyle style in 6 choices of mode, theme and path style, with the differences that were decided
  (ids as BIGINT, `source` and `target`, the last digit of a centroid, the PNG bytes) and one that is open: the 3D decks of the Rust
  engine are not Python's on all of Monaco (1,312 against 1,311, for the same roads). The background's land is the boundary less the sea
  in every path, as mapstyle makes it, cut in Rust (`duckosm::cut_sea`, i_overlay 9.0.1): no reader needs DuckDB's spatial extension
  (in the browser it is 6 MB and about 1.2 s). On Monaco its points are mapstyle's to 9 places; 0.2 ms.
- **A duckOSM reader with one copy of its SQL** (the mapstyle merge, step 2): `roadstyle-io::duckosm` makes the SQL that reads a duckOSM
  file: the roads of every mode with their stored levels and the columns that `render_map` adds, and the base map's tables (`features.*`).
  It is the SQL of `roads_sql.js` and `features_sql.js`. Python runs it with `roadstyle.duckosm.read(db, mode)` (the engine's input files as
  GeoParquet bytes, and the look's `levels` keyword); JavaScript gets it from `duckosmPlan`, `duckosmLevels` and `duckosmFeaturesSelect`.
  On Monaco the roads are mapstyle's roads, value for value and in the same order (plus `source` and `target`), and the base map's rows are
  the browser's `features.parquet`.
- **`rampStops(cmap, n)` in JavaScript**: `n` colours at even steps along a ramp (a branca scheme, a matplotlib colormap, or a list of
  colours), as Python's `ColorRamp(cmap).stops(n)`: for example a colour for each category of a column in the studio. The ramps and their
  data (`cmaps.json`) are now in the look crate (`roadstyle-look::Ramp`); the engine's legends use the same `stops`.
- **Roads from a GeoJSON file in Rust** (`roadstyle-io::geojson::read_roads`, for the studio in the browser). It gives a `RoadTable`, as the
  GeoParquet reader does: one row for each feature, a column for each property (Boolean, Int64, Float64, else text), and a LineString's
  points as the line. The facade's `sources_of(roads, look, ...)` is stage 1 of the roads that any reader gave. JavaScript:
  `readGeoJson(bytes)` gives a `Roads` handle (`length`, `columns()`, `sources(look, features?, planner?, name?)`). Monaco's roads as
  GeoJSON make the same style as their GeoParquet file.
- **The base map's look in Rust** (the mapstyle merge, step 1): `Look::resolve` takes `base_map: {mode, theme, paths}` (a duckOSM map's
  travel mode, its theme and its path style) and makes mapstyle's look with no Python: the mode's palette and settings (`mode_settings`),
  the theme's colours, and the base map's part of the look (the layers of `layers.yaml`, the 3D heights, the base map's style, the
  texture and icon images). mapstyle's style files are now roadstyle's (`src/roadstyle/data/basemap/`); the textures are colour masks
  drawn one time from mapstyle's `patterns.py`, coloured by the engine. The 64 looks of the GeoLibre plugin (4 modes x 4 themes x 4 path
  styles) are equal to mapstyle's (`rust/roadstyle-look/tests/basemap.rs`; a texture by its pixels). A mode's palette has a fixed class
  order; mapstyle's came from a Python set and changed with each run.
- **Live data on the web page** (R22, `dashboard_module.md`): `rs.setData(table, {key, colorBy, widthBy, ...})` joins a table to the roads by
  `edge_id` or the row and colours and sizes them through feature state, with no new style; `rs.clearData()` takes it away. It needs a style
  made with `live_data=True`. Tartu, 64,828 roads: 78 ms to set a colour on each road.
- **Live data on the road layer** (`live_data=True`, the Rust engine only). The road layer reads its colour and its width factor from
  MapLibre feature state on the road's row (`rs_c`, `rs_w`), with the baked values as the fallback. A host or the dashboard's
  `rs.setData` changes them with no new build. The pieces have the road's row as their id (`promoteId: "__rs_edge"`, also on the vector
  source), and the metadata `roadstyle:live` names the states, the default ramp and the no-data colour. Off by default: the styles of
  today do not change. With the Python engine, `live_data=True` is a `ValueError`.
- **The two stages of the Rust engine as their own calls** (docs/rust/architecture.md, "The three stages and the one call").
  Stage 1 makes the style and its sources; stage 2 cuts the vector tiles from them, with no roads and no look.
  - Python: `export_geojson(edges, out_dir, format="geojson" | "geoparquet", keep=None, **kwargs)` writes stage 1's files:
    `style.json`, one file for each source and `road_table.parquet` (every field of each road, by its row; the roads' own file has
    their drawing values only). `tile_geojson(src_dir, out, format="pmtiles" | "xyz")` makes the tiles from these files. The tiles
    are the tiles of `export_style` and of `render(tiles=True)`. The Rust engine only.
  - Browser package: `makeSources(...)` (with `fileNames(format)` and `file(name, format, keep)`), `tileSources(sources, prefix, keep)`
    (from memory, with no GeoJSON text) and `tileFiles(fileSet, prefix, keep)` (from the files, in a `FileSet`).
  - Rust: `roadstyle::make_sources`, `save_sources`, `source_file`, `tile_sources`, `tile_files`, `tile_files_with`, `tile_made`,
    `vector_style`; `roadstyle_tiles::stage::TileOptions` (stage 2's rules); `roadstyle_io::write::parquet` (Parquet and GeoParquet)
    and `roadstyle_io::read::features` (a GeoParquet file as GeoJSON).
  - Tartu: all sources 130 MB as GeoJSON files, 22 MB as GeoParquet files; the road table 3.2 MB.
- **`compute_levels(engine="rust")` takes all its keywords**: `band_col`, `order` (`"priority"`, `"class"`, a column or None),
  `band_dist`, `head_m`, `max_level`, `margin`, `min_positions` and `near_rules`. Before, a keyword not at its default went to the Python
  engine. The Rust solver has no time limit, so it does not use `time_limit`.
- **The level editor in Rust**: `roadstyle-levels edit` opens the editor page of `static/level_editor/`. The solver runs in the page
  (roadstyle-wasm `LevelArea`: Monaco loads in 75 ms, solves in 0.1 s), and the Rust program `roadstyle serve <area folder>` (the new
  crate `roadstyle-cli`) gives it the area's files and saves your changes (only `edits.csv`, `heads.csv`, `caps.csv`, `levels.csv`,
  `levels_info.json`). The panel is the same. `--engine python` opens the Python editor. The page's files are in the program (and in the
  Python extension); build the page's WebAssembly package with `rust/roadstyle-wasm/build_editor.sh` before you build them. The server
  answers only to its own address (`Host`, against DNS rebinding), saves only the page's own changes (`Origin`), and takes at most 16 MB. `solve_levels(..., engine="rust")` and `roadstyle-levels solve
  --engine rust` solve the same tables with the Rust solver (no `max_positions`, no time limit).
- **The roadstyle program** (`rust/roadstyle-cli`, docs/rust/cli.md): `roadstyle sources` (stage 1), `roadstyle tiles` (stage 2, PMTiles
  or XYZ), `roadstyle levels make|solve` and `roadstyle serve`, with the option names of the Python keywords.
- **The levels' make in Rust**: `make_area(engine="rust")` and `roadstyle-levels make` (default `--engine rust`) write the same
  roads.parquet and pairs.csv as Python's `level_input`, faster (Tartu 0.7 s, Python 13.2 s).
- Rust: `roadstyle_levels::levels(edges, options)` replaces `compute(edges, method)`. `Options` has the keywords of `compute_levels`, and
  also `fixed` (numbers that stay as they are, as `solve_levels(fixed=...)`) and `edits` (the rows of `visualization.level_edits`, as
  `solve_levels(edits=...)`). `edge_hash(ids)` is public.

### Changed
- Browser package: `roads_sql.js` has `makeRoads(q, catalog, opts)`, one time for each file, and `writeRoads(q, mode)`, which writes
  only `roads.parquet` for each mode. `edge_id` and `osm_id` stay BIGINT, and `source` and `target` (duckOSM's node ids) stay in
  `roads.parquet`. The SQL copy of the tags rule and the JavaScript copy of the edge hash are gone: `makeRoads` returns the look's
  `args.levels`, `"tags"` (the engine computes the levels with the tags rule) or the stored levels' `{edge_hash, n_edges}` (the engine
  checks them).

## [0.25.0] — 2026-10-23

**The Rust engine, as an option.** roadstyle 0.25.0 has a second engine, in Rust, inside the package (the module `roadstyle._rust`). The
default stays the Python engine: a map made with 0.24.3 is the same with 0.25.0, except for the Python fixes below. Select the Rust engine for one call with
`engine="rust"`, or for all calls with the environment variable `ROADSTYLE_ENGINE=rust`.

**The Rust engine is experimental.** The Python API that selects it (`engine="rust"`, `ROADSTYLE_ENGINE`) is stable. The engine's inside
(the crates and the functions of the WebAssembly package), the `roadstyle:*` metadata in the style and the `__rs_*` property names can
change in the next versions.

- **What the Rust engine does:** `render_edges` (the web page, also `tiles=True`, `simple=False`, `views=`, overlays and items),
  `export_inline`, `export_style` (XYZ and PMTiles), `export_look`, `compute_levels` (`method="tags"` and `"solve"`, with the defaults), the
  data colours (`color_by`, `color_table`, `color_options`, the legend) and the look (`palette`, `profile`, `settings`). Its output is the
  Python engine's output: the same style and page byte for byte, and tiles with the same features (`tests/test_engine_parity.py`, and the
  whole test suite runs with `ROADSTYLE_ENGINE=rust`). One known difference: where the two directions of one road have the same line, a
  name or arrow slot can go to the other direction (4 slots on Monaco, 10 on Tartu). The name and the arrow on the map are the same.
- **What stays Python only:** `style=` (a Styler object of Python), the `compute_levels` keywords other than the defaults, the folium and
  lonboard backends, and mapstyle's half of the look. With `engine="rust"` these give an error. With `ROADSTYLE_ENGINE=rust` the Python
  engine makes them, with a warning.
- **Speed** (Tartu, 64,828 roads, the whole web page): 19.1 s with Python and 6.2 s with Rust; with `tiles=True`, 147.5 s and 12.2 s.
- **New metadata in the style:** `roadstyle:color_options` (the legend data), and on the page's style `roadstyle:contract`,
  `roadstyle:state` and `roadstyle:controls` (the interaction contract, `docs/reference/contract.md`).
- **For the users of the Rust engine in the browser** (duckosm-rust's page, the GeoLibre plugin): the engine now follows `labels=False` and
  `arrows=False` in the look's `args`. Before, it always drew the names and the arrows (see "Added").
- **Docs for the Rust engine** (`docs/rust/`, the "Rust engine" part of the site): a first map, how to switch the engine, use it in
  the browser, make tiles and build from source, the keywords of each engine, the crates, how a map is drawn (GeoJSON or tiles, XYZ or PMTiles), and how the
  engine is built, with its parity and speed.
- **Python fixes** (they change the output of the Python engine too): the title of a tiled page, the paint order of a painted road in a
  tiled style, the width of a 3D bridge deck with another class column, the order of `export_look`'s no-casing classes, and the order of
  the bridge shadows. See "Fixed" and "Changed (output)".

### Packaging
- **Wheels for each platform.** roadstyle was a pure-Python wheel. Now each wheel has the Rust module in it, and the release builds one
  wheel for each platform: Linux x86_64 and aarch64 (manylinux), macOS x86_64 and arm64, and Windows x64. The wheels are abi3, so one
  wheel serves every Python from 3.10. `pip install roadstyle` takes the wheel of the platform; nothing else changes for the user.
- **The source distribution needs Rust.** On a platform with no wheel, pip builds the sdist with maturin. If no Rust toolchain is on the
  `PATH`, maturin installs a temporary one for the build (the package puccinialin), and the build takes some minutes. With
  `MATURIN_NO_INSTALL_RUST=1` it does not, and pip stops with "Cargo, the Rust package manager, is not installed or is not on PATH". Then
  install Rust (https://rustup.rs) and run `pip install roadstyle` again.

### Added
- **The Rust engine from Python** (`docs/design/rust_library.md`, phase P5). `export_inline(..., engine="rust")` makes the style with roadstyle's Rust
  engine, the extension `roadstyle._rust` (`rust/roadstyle-py`; a development build: `python rust/roadstyle-py/build.py`). The default stays
  `engine="python"`; `ROADSTYLE_ENGINE` sets it. The Rust engine needs the drawing levels in the roads (`casing_level`, `fill_level`); without them it
  gives an error, and it never goes back to Python without a message. `tests/test_engine_parity.py` checks that the two engines give the same style.
- **`compute_levels(..., engine="rust")`** computes the four level columns with the Rust solver (`roadstyle-levels`), the same as Python for
  `method="tags"` and `"solve"` with the defaults. Other arguments give an error with `engine="rust"`.
- **The Rust engine computes the drawing levels** when the keywords name no level columns, as `render` does (`compute_levels`, method "solve", with
  its defaults). Before, the Rust engine needed `casing_level` and `fill_level` in the roads.
- **The Rust engine takes the column keywords** (`highway_col`, `tunnel_col`, `bridge_col`, `layer_col`, `edge_id_col` and the level, head, cap,
  `directed_col` and `driving_col` columns), with the same style as Python: the user's names in the data and in the road layers.
- **The Rust engine takes more of render's keywords**, with the same style as Python: `labels`, `arrows`, `road_fill`, `road_popup`, `road_tooltip`,
  `hover_delay_ms`, `data_maxzoom`, `data_tolerance`, `select_color` and `hover_color` (also on the overlays), `access_col` (the access colours),
  `head_m`, `offset_zoom`, `minzoom` (true or a table), `cap_col` (the end columns only when they are named, as in Python) and `boundary`.
- **The Rust engine draws metre widths** (`width_m_col`, `width_m_zoom`, `casing_m`, `casing_min_px`), with the mitre ends where a flat end meets another
  metre road, as Python. Before, it stopped with an error on such roads.
- **`export_style(..., engine="rust")`** writes the style and the XYZ tiles with the Rust engine (`Tiler`). The style is the same as Python's byte for
  byte, and the tiles have the same features. `format="pmtiles"` stays Python only for now.
- **The Rust engine draws the 3D bridge decks** (`view_3d=True`, the default of `export_inline` and `export_style`): the same deck features as Python,
  with the same properties. The engine makes the ribbons with its own mitre offsets, not with GEOS, so a corner can differ by the rounding (1e-6 deg).
- **The Rust engine draws the caller's overlays and the road items** (`overlays=`, `items=`): every kind of `Overlay` (fill, line, circle, text), a
  style of the settings, a colour per feature, metre widths, dashes and zoom ranges, overlays on edges, and the line items in metres in the one road
  layer with their mitre ends. The same style as Python, inline and in tiles.
- **`render_edges(..., engine="rust")`** makes the web page with the Rust engine: the roads' style comes from Rust, and Python writes the base map
  and the page. The page is the same as the Python engine's page, byte for byte (with 3D decks: the same page, the decks' corners to the
  rounding). With `tiles=True` the archive has the Rust engine's tiles (the same features as Python's when decoded); the rest of the page is
  the same. `simple=False`, `style=` (a Styler object) and the other backends stay Python only and give an error with `engine="rust"`.
  Time on Tartu (64,828 roads): 19.1 s with Python and 6.2 s with Rust; with `tiles=True`, 147.5 s and 12.2 s.
- **`export_style(..., engine="rust", format="pmtiles")`**: one archive of the Rust engine's tiles.
- **The full look in the Rust engine** (`simple=False`, `full.rs`): a casing and a fill layer for each drawing position with their end-cap
  twins, the dashed classes, the tunnel and bridge looks and the bridge shadows, over the sources `casings`, `halves` and `shadows`. The same
  style as Python byte for byte, inline, in tiles and on the page, with the road-wide end caps of `twin_casing: "each"` (`_twin_ends`).
- **`views=` with `engine="rust"`**: the View menu, and a view's palette (the colours of each palette in the page, as Python's
  `_merge_palettes`, from a Rust style of each palette). Not with `tiles=True` (the tiles have one palette).
- **`ROADSTYLE_ENGINE=rust` runs the whole test suite.** With the Rust engine as the default, a part that the Rust engine does not have
  (folium and lonboard are other renderers; a Styler object, `compute_levels` keywords other than the defaults) is made by the Python
  engine with a warning. With `engine="rust"`
  given, it is an error. The engine's own warnings (a two-way pair whose directions disagree) are Python warnings, and the Rust look takes
  the settings in force (`roadstyle.json`, `$ROADSTYLE_CONFIG`, `use_settings`). CI runs the suite with each engine.
- **`compute_levels(engine="rust")`** gives `levels_given_up` and `levels_orders_not_kept` as Python does.
- **The Rust engine takes `filter_col`** (the class filter: `__rs_cls` on every piece, the filter panel) and the user's own profiles and
  palettes (`./profiles`, `./palettes`, `~/.config/roadstyle/`), as Python does.
- **The page writer in Rust** (`roadstyle::page`, phase P6): render_web's `_page_html` in Rust, with Python's JSON text (its separators, its
  `\uXXXX`, its floats), so `render_edges(engine="rust")` writes the page with it and the page is Python's byte for byte. The browser package
  has it as `makePage` (the duckosm-rust page and the GeoLibre plugin can write a whole page). The page's three scripts (the gzip loader,
  simple mode's recolouring, the tiles' setup) are static files now (`static/page/`), the same text for both writers.
- **`export_look(engine="rust")`** and `exportLook` in the browser package: the simple look for another app's data layer, the same as
  Python's. Python's `export_look` writes the no-casing classes in order now (they came from a set, so the look changed from run to run).
- **The `rs` object** (`static/dashboard/api.js`, the runtime API of the interaction contract): `window.rs` and the value of `rsDashboard`
  have `getState`, `setState`, `can`, `link` (the state in the URL, `#rs=`), `on` and the controls' actions with the roads' edge ids. A page
  opened with `#rs=` applies that state. The `window.rs*` functions and the `rs:*` events do not change.
- **A PMTiles writer in the crate** (`roadstyle_tiles::pmtiles`, `Tiler.archive` in the Python binding and in the browser package): the
  archive of the pmtiles package's Writer (the same header, entries and tiles), with no time in its gzip streams, so the same map gives the
  same archive. The Rust engine's tiled pages and `export_style(format="pmtiles")` use it.
- **The interaction contract in the style** (`docs/design/rust_library.md`, "The interaction contract"). With the look's `args.state = "live"`,
  the Rust engine makes the style of the page: the global state stays in the expressions (MapLibre's `state` block), and the metadata has
  `roadstyle:contract` (1), `roadstyle:state` (the start value of each `rs_*` state) and `roadstyle:controls` (the options of `rsDashboard` that
  come from the style: the filter panel, the overlays, the tunnel look, the road fill, the fill layers, the items, the arrows' rules, the
  select colour). The dashboard reads `roadstyle:controls` for each option that the page does not give, so a page with a Rust style (the
  duckosm-rust page, the GeoLibre plugin) gets the same controls as the Python page.
- **The Rust engine parses floats exactly** (serde_json `float_roundtrip`), so a coordinate from Python has the same last digit.
  **Note for the users of the Rust engine:** the engine now follows `labels=False` and `arrows=False` in the look's `args`, as Python does. Before,
  it always drew the names and the arrows. The looks of the GeoLibre plugin and of duckosm-rust's page have both false (from mapstyle's
  keywords): set them true there, or the maps have no names and no arrows after an update of the engine.

### Changed (output)
- **The bridge shadows in one order** (`simple=False`): each shadow line runs from its lower end, and the lines are in the order of their casing
  number and their first point. Before, the order came from GEOS's line merge. The map does not change.

### Fixed
- **The direction columns in the Rust engine** (`directed_col`, `driving_col`): the engine read the columns `is_directed` and `has_arrows`
  also when the keywords did not name them. Python reads them only when they are named (their default is None). Now the Rust engine does
  the same, so roads with these columns get the same style from the two engines.
- **The title of a tiled page** (`tiles=True`): it was "ends" (a loop of the tiled branch used the name of the title). Now it is the map's name.
- **The width of a 3D bridge deck with another class column** (`highway_col`): the deck read a column named `highway`, so with another class
  column every deck had the fallback width. Now it reads `highway_col`.
- **The paint order of a painted road in a tiled style** (`tiles=True`, `export_style`): `roads-fill` and `roads-highlight` shared one layout, so
  the +500 of a painted road was added two times to each. Now each layer gets it one time. The order on the map does not change.
- **The Street View marker on vector tiles** (simple mode, the Rust engine's tiles). A road clicked on a tile piece had no line in the
  page, so Street View had no spot: no marker, no heading, no steps, and Linked mode did not move the marker. Now the clicked piece's
  own line is used, and the spot has the road's properties from `engine.props`.

### Changed
- **One wheel with the Rust engine in it** (decision 5 of `docs/design/rust_library.md`). The package builds with maturin: each wheel has the
  module `roadstyle._rust` (abi3, one wheel for Linux x86_64 and aarch64, macOS x86_64 and arm64, and Windows), and the release workflow
  builds them. The files of the package do not change. An install from the source needs a Rust toolchain.
- **`export_style` writes the legend data** in `roadstyle:color_options`, as `export_inline` does.
- **`export_inline` writes the legend data** in the style's metadata `roadstyle:color_options` (the page's `COLOR_OPTIONS`), when the map has data
  colours, as the Rust engine does. The dashboard module reads it.
- **The Rust engine is a set of crates** (phase P2): `roadstyle-model`, `roadstyle-io`, `roadstyle-levels`, `roadstyle-engine`, `roadstyle-tiles` and the
  facade `roadstyle`. The crate `roadstyle-rs` stays for one version, as the old name of the facade.
- **The map controls are ES modules** (`static/dashboard/`, `docs/design/dashboard_module.md`). The controls and the road interaction of the web page
  (colour by, legend, road filter, find, panel, Street View, Google 3D, base map, overlays, tunnels, views, arrows, hover and click) were one script in the
  page template. Now each control is a file, and `rsDashboard(map, options)` adds them all to a MapLibre map. The pages that use the Rust engine can
  import the same files. The Python page puts them in the page as one script, so a saved page still works offline. The look, the texts and the
  `window.rs*` API do not change.
- **The dashboard on roads that come later** (`dashboard_module.md`, "Roads that come later"). `rsDashboard` returns an object with
  `setStyle(style)`: a page gives a new roads style after each build, and the controls stay. New options: `prefix` (the page added the
  style's sources and layers with it), `engine: {props}` (one road's properties on request) and `style: null`. In simple mode with
  vector tiles a road glows through its pieces (`promoteId: {simple: "__rs_edge"}` on the `roads` source).

## [0.24.3] — 2026-10-22

### Fixed
- **A short road is cut once** (`short_road_heads.md`). A road shorter than its two heads was cut at `h0` and at `n - h1`. These are the same point only in exact
  arithmetic, so the last bit of `cos` and `hypot` decided whether a middle piece under 2 cm and a second seam and lap came between them. glibc, Pyodide and Rust's
  wasm math library gave three different answers (Monaco: 78 of 8,561 edges differ between native Python and the GeoLibre plugin's Pyodide). Now the road is two
  pieces and one seam on every platform. The map looks the same: the extra piece was less than a pixel wide.

## [0.24.2] — 2026-10-22

### Fixed
- **The glow of a hovered or selected road follows its pieces after an update in place** (simple mode). 0.24.1 kept the list of the pieces of a road once. The level
  editor swaps a road's pieces (`GeoJSONSource.updateData`), so a road could glow through pieces that were gone. The list is made again when the data changes.

## [0.24.1] — 2026-10-21

### Added
- **`max_pitch=` on a render call** (web): the most the map can tilt, in degrees. The default stays 70 (`camera.max_pitch`). `max_pitch=60` keeps the page from the
  views where the one tile zoom (see 0.23.0) loads more tiles: up to 60 degrees MapLibre itself uses one tile zoom.

- **`data_tolerance=` on a render call** (web): how far MapLibre simplifies the road geometry in the tiles it cuts. Default `None` keeps roadstyle's `0.05`. `data_tolerance=1`
  makes a sweep to a new area at zoom 12 about three times faster on a page of 22,000 roads (687 to 226 ms; the first tile 2.4 s to 0.6 s), because zoomed out one
  tile holds a whole district.

### Changed
- **Simple mode with inline data cuts no tiles of the roads source.** The roads source drew nothing in simple mode: it held two layers only, the invisible layer that
  found the road under the cursor and the layer that glowed a hovered or selected road. MapLibre cut it into tiles all the same, and copied the whole page state
  (the colour of each road set by `rsColor`) into each paint expression and back from the worker with each tile. On a page of 22,000 roads one such reply held
  about 2.8 million characters. The page took 40 to 70 ms to read it, and each tile that came in during a zoom froze the page. The two layers are now hidden, so the
  source is cut into no tiles. A road is picked on the fill pieces of the road layer (`roads-simple`). A hovered or selected road glows through the state of its
  pieces: their fill goes toward the highlight colour by the selection opacity, as the old layer drew it. On a Nacka page at zoom 12 to 16 (headless Chromium) the
  frozen time of a scripted zoom fell from 9.2 s to 6.4 s, the frame rate rose from 17-34 to 22-42 frames a second, and with a real graphics card the tasks over 30 ms
  fell from 24 to 12 (1.1 s to 0.5 s). Picks at 380 points gave the same road as before. A highlighted road ends square at its ends, not round.
  `tiles=True` and `simple=False` keep the old layers. The one tile zoom for the whole screen stays: it is what keeps a road at one width in a tilted
  view (no horizontal line where two tile zooms meet), and it costs tiles only above 60 degrees. With one road source cut into tiles, not two, a tilted view
  freezes less than before: in a scripted zoom at 66 degrees the frozen time was 0.8 to 2.3 s, against 2.9 s on the old page.

## [0.24.0] — 2026-10-20

### Added
- **The style in config files: profiles and palettes** (docs/design/style_config.md). A **palette** holds only colors (road
  classes, names, arrows, bridges, tunnels, selection, data maps, overlays, boundary, background): `data/palettes/amber.yaml`,
  `carto`, `highsat`, `mono`. A **profile** holds everything else (widths by zoom, class order and minzoom, zoom ranges, sizes,
  dashes, caps, the tunnel look): `data/profiles/default.yaml`, `highsat`. Python reads them and builds the style; it holds no
  style value (a test checks the colors). `render_edges(profile=..., palette=...)` take names; own files go in `./profiles/` and
  `./palettes/` and state only what they change. `profile="highsat", palette="highsat"` is today's high-saturation look.

- **`rsColorBase` and `access_col` follow the page state.** `rsColorBase(groups)` is the state `rs_base` (under `rs_colors`); the colour of an access kind is baked in the road's
  fill (the palette key `access`, in every colour option), so the page builds no expression for them either.
- **`rs.export_style(edges, out_dir, base_url=...)`: the roads for other map apps.** It writes `style.json` (the style of the
  `tiles=True` page), the road tiles as a `tiles/{z}/{x}/{y}.pbf` folder (`format="pmtiles"`: one `roads.pmtiles`) and a sprite
  with the one-way arrow. GeoLibre, RustGIS, QGIS and MapLibre pages open the style by its URL. Every GeoJSON source goes into
  the tiles, because RustGIS draws none. The page's JavaScript (popups, the `rs*` API, the controls) is not in the style.
  `basemap=None` removes the base map. The arrows follow fixed rules close to the page's (side streets from zoom 17, about
  330 px apart), and `view_3d=True` is the default, so the style has the bridge decks. Design: `docs/design/style_export.md`.
- **`rs.export_look(path)`: the simple look for a data layer in another app.** It writes MapLibre layers with no source that
  read the raw duckOSM columns (`highway`, `oneway`, `tunnel`, `bridge`, `casing_level`, `fill_level`): the class colours and
  widths, a casing, one casing and one fill layer per drawing position, tunnels faded, two-way roads side by side. An app puts them on a data layer, for
  example a duckOSM DuckDB or GeoParquet layer (the GeoLibre plugin, on the branch `geolibre`, does that). Not in the look: names, arrows, 3D decks (they need `export_style`).

### Changed
- **Links are 0.6 of their main class's width everywhere.** The web map drew 0.6 and folium / lonboard used `link_scale` 0.7.
- **Folium's selection colors are the web map's:** select `#7c4dff`, hover `#b388ff` (were `#EE00FF` / `#D000FF`).
- **`defaults.json` holds only the settings that are not a look:** `basemap`, `camera`, `annotations`, `tiles`.
- **`palette="highsat"` alone uses the default widths and dashes.** highsat's own (no casing on minor classes, longer dashes)
  are the profile `highsat`.
- **One-way arrows on side streets from zoom 16.5** (was 17): theme `arrows.main_below`, which the page reads.
- **The page builds no style expression** (docs/design/style_config.md, step 2). The Colour by menu, `rsColor`, `rsSetRoadFill`,
  a view and the Tunnels box set state values (MapLibre `global-state`); the expressions that read them are made in Python, once.
  The page no longer recolours anything when it opens. The functions and events of the JS API are the same. The style has the start
  values in `state`: `rs_co`, `rs_colors`, `rs_fill_on`, `rs_tun_*`, `rs_ov_<n>`.
- **The arrow icon, the arrow placement rules and the Tunnels box lists come from the profile** (`arrows.icon`, `arrows.place`,
  `arrows.main`, `tunnels.steps`, `tunnels.ratios`), and folium's hover look from the palette and the profile.
- **A view can switch the palette:** `views={"Night": {"palette": "mono"}}`. The page holds each view's palette (built once more,
  merged by the state `rs_palette`): the road colors, names, arrows, bridges, tunnels and the Roads panel's swatches change together.

### Deprecated
- Style values in the older settings layout (`palettes`, `selection`, `roads`, and the style keys of `config`) are read for one
  release, each as its profile or palette key, with a `DeprecationWarning` that names it.

## [0.23.0] — 2026-10-20

### Added
- **`find_control=True` and `rsFind(text)`.** A "Search roads…" box on every page, not only in panel mode. `rsFind(text)` is always defined and returns the ids of
  the roads that match (an id or a name).
- **`overlay_control=False`** hides the Layers box. **`Overlay(popup_window=False)`** (or `overlay_popup=False` for the page): the overlay stays clickable and
  fires `rs:select`, but a click shows no popup.
- **`outline` and `width` for circle overlays:** the ring colour and the ring width.
- **`access_col="access"`:** roads with `private`, `bus`, `pedestrian` or `delivery` get the kind's colour and a row each in the Roads box
  (after Bridges and Tunnels), with `rsSetAccess`, `rsGetAccess` and `RS_ACCESS`. mapstyle can use these rows instead of its own copy.
- **`side_panel_html=` and `host_panel_width=`:** a collapsible side panel for the host page, with the docked panel's » handle, « button and `rsPanelShow`.
- **`render_edges(..., levels_db=file)`** reads the stored drawing order (`visualization.edge_levels`) of a duckOSM file for the given edges, which can be
  some of the edges it was solved for. The ids can be int64 or text.
- **`rsColorBase(groups)`:** recolour groups under those of `rsColor`. A host that paints its own roads no longer loses them when another caller uses `rsColor`.

### Fixed
- **Road widths no longer step at a line across a tilted (3D) map.** MapLibre loads the near tiles of a tilted view at a higher zoom than the far tiles,
  and a width that depends on the zoom and on the feature is baked per tile and clamped to that tile's zoom. The page now uses one tile zoom on the
  whole screen. A tilted view loads more tiles (121 against 21 in a test at pitch 72).
- (Not reproduced: an overlay hover that lights every feature with the same number. A test now guards that one feature is lit.)

## [0.22.2] — 2026-10-20

### Added
- **`load_area_levels(con, edges, subset=True)`** reads the stored order for some of the edges it was solved for (a map of one mode of the file).
- **A level area of a database keeps your edits in it.** Each solve copies `edits.csv`, `heads.csv` and `caps.csv` to
  `visualization.level_edits`, `level_heads` and `level_caps`, so the database file holds everything. A new area folder gets
  the files back from there (`make_area(..., db=...)`, `rs.restore_area_inputs`).

### Fixed
- **A solve never deletes the tables of your edits.** A folder without `heads.csv` or `caps.csv` (a new one, or one that lost the file)
  dropped `visualization.level_heads` / `level_caps` of the database at the next solve. The tables are the master: a missing file leaves its table.
- **The arrows of a tilted (3D) map.** They were placed by road length on screen, measured from the vertical pixels, which the tilt squashes
  (8 times at zoom 17): almost every road looked too short and the 3D view kept a few arrows. The scale now comes from the zoom and the latitude.
- **`roadstyle.__version__` from a source checkout** (`PYTHONPATH=.../src`) is the version of its `pyproject.toml`, not of another installed copy.
- A test that needs the optional `mapbox_vector_tile` is skipped without it.

- **The panel search finds a road by its id again when the page sets its own popup fields.** The docked panel's search
  (`popup_mode="panel"`) read only the popup fields, so a page with `road_popup=["name", ...]` and no `edge_id` answered
  "no match" for an edge id. It now always reads the id column (`edge_id_col`) and `edge_ref` as well.

## [0.22.1] — 2026-10-17

### Fixed
- **Google 3D on a hill:** Google's center is in metres above sea level, and roadstyle gave 0 m, so on high ground (Monaco, 120 m)
  the 3D camera came much closer than the map's. The page now reads the ground height under the center from the free Terrain Tiles
  on AWS (Mapzen, Terrarium PNGs, no key) and gives it to Google. The window bar credits them; if they do not load, it shows
  "⚠ no ground heights".

## [0.22.0] — 2026-10-17

### Added
- **`google_3d=True`: a Google 3D window.** A map button opens Google's photorealistic 3D view in a floating window. Its camera and the
  map's move together (center, turn, tilt, zoom), and a clicked road is drawn in it. While it is open, the map's center moves beside it. Where the map cannot follow (its `maxBounds` box, its maximum pitch), the 3D view goes back to the map's camera. It uses the Street View key (`street_view_key`,
  default env `GOOGLE_MAPS_KEY`); without a key it is an error. JS: `rsSetGoogle3D(on)`, event `rs:google3dchange`. Default `False`.
- **A live map in the docs** (`maps/live.html`): Södermalm with every control, Google 3D and a *Colour by* menu (road class, speed limit,
  lanes), kept inside Södermalm. The docs build reads the Google key from the repo secret `GOOGLE_MAPS_KEY`.
  The README, the docs home and the docs header link to it.
- **A guide to set up the Google key** (`docs/guides/google-key.md`): billing, the Maps JavaScript API, the Websites list and the API
  restriction, with the console errors and their causes. The Street View and Google 3D guides link to it.
- **`data_maxzoom=`:** the last zoom MapLibre cuts the page's GeoJSON sources into tiles at. Above it, MapLibre enlarges those tiles and does
  not cut them again at each zoom step. Default `None`: MapLibre's own.

### Changed
- **One loader for Google's script:** the Street View window, the Street View page and the Google 3D window share it, because a page can
  load Google's script only once.

### Fixed
- **A solver stage at its time limit never fails the solve:** there is always an answer, so a stage stopped before it found one keeps
  the answer of the stage before (it holds every rule so far); any stage stopped with an answer keeps it and the next stages go on. A
  warning names the stage, and `levels_info["status"] == "TIME_LIMIT"`. A Monaco all-modes solve failed on GitHub's slower machine.
- **Street View opens empty:** closing the Street View window forgets the last road, so opening it again waits for a road instead of jumping back to the last one.

## [0.21.1] — 2026-10-10

### Added
- **A link to a place in the level editor:** `?at=lon,lat,zoom` opens the editor there (a reload after Apply keeps your own view).

### Changed
- **Hover waits for the mouse to rest:** a road or an overlay item lights up and shows its tooltip only after `hover_delay_ms` (300; 0: at once); leaving clears it at once.

## [0.21.0] — 2026-10-10

### Added
- **`minzoom` on a road item** (`items=`): the item shows from that zoom on (e.g. zebra stripes, a smear of white zoomed out).

## [0.20.0] — 2026-10-09

### Added
- **Items in the level editor.** `roadstyle-levels edit AREA --items module:function` (`serve(..., items=f)`): `f(roads)` gets the table the editor draws (one row per edge, `edge`) and returns `(overlays, render_edges keywords)`, e.g. a lane table's lanes as the roads' own items (`items=`), redrawn in place with their road on Apply; overlays attached to edges draw the whole page again. Without it the page is unchanged.
- **`items=` — a road's own items in the road layer.** `render_edges(..., items=gdf, items_popup=[...])` (simple mode): line items (lanes, lane lines, marks) that name their road in the edge id column, with `width_m` and optional `order`, `offset_m`, `color`, `dash`, `pick`, become pieces of the one road layer above their road's fill, with no source or layer of their own. A `pick` item is clicked and highlighted as itself through the road layer (`rs:select` `detail.item`, popup `items_popup`); the others let a click through to their road. `Overlay` stays for what is not a road.
- **`labels.size` setting:** the street names' size per zoom (`[[zoom, px], ...]`), the same for every class (roads in metres).
- **`casing_min_px`.** A casing in metres (`width_m_col`) is at least this many pixels each side of its fill, so a thin casing (lanestyle's 0.14 m) stays visible zoomed out. Default 0: exact metres, as before.

### Changed
- **An edge with items keeps its fill** under them: its ends (round, flat, square) are the road's own; lanes alone left a round casing end empty.
- **`twin_casing: "each"` with metre widths** shifts each direction by metres too, so each direction's own casing and fill sit side by side.
- **Square ends** are drawn by a 0.5 m piece in the piece's own direction (a 1 cm piece pointed any way after rounding, and a reverse direction's landed on the other half).
- **Round ends too** (simple mode): a round road end on a piece that also ends at a cut (a casing head, a fill half) is drawn by a 5 cm piece at the road end; the piece itself ends flat. A round cap at the cut reached past a short road's flat other end.
- **Level editor: Apply places names and arrows again only for the changed roads' name groups** (their chains numbered by their first road, the same in a part of the map as in the whole): Monaco 1.2 s in place instead of 3.8 s.
- **Level editor: a rule that does not hold says why.** Adding a rule already in edits.csv that the solver cannot keep names the rules of its loop ("not kept: it makes a loop with ..."), in the check and in Apply's message, not only "already in edits.csv"; a click on an order wish not kept (Issues) shows its loop.
- **Level editor with road items: no page reload on Apply.** A change that moves a road's fill number redraws that road and its own items (`items=`: lanes, lines, marks) in place; each item has an id per road and rank. Overlays attached to edges still draw the whole page again.
- **A hover or click finds what is drawn on top** (simple mode): where a road is drawn over another road's picked lanes (a plaza over a tunnel's unseen lanes), the road on top is found, not the lane under it.
- **Faster pages with names:** a class's width at a zoom is kept once read (the name slots asked once per crossing): the level editor's Monaco page with lanes is built in 9 s instead of 30 s.
- **The tunnel look keeps each colour's alpha:** a colour moves toward the tunnel colour but stays as see-through as it was, so an unseen item (`rgba(0,0,0,0)`) stays unseen on a tunnel instead of a see-through strip, darker where two overlapped.
- **Flat ends that go on close the bend** (simple mode): a flat end of a road in metres is pushed on to meet the road that goes on most straight (60 degrees at most) in a mitre, and a line item's end meets the item of its colour that starts within 2 m (two links' lanes), so no wedge of the road under them shows on the outer side of a bend. Dead ends and sharper turns stay as they are.
- **Street View key from the environment.** `street_view_key` defaults to the environment variable `GOOGLE_MAPS_KEY`, so every map built where it is set (the level editor, mapstyle and lanestyle pages included) offers the linked panorama. A passed key wins. The key is written into each page: never publish a page built with an unrestricted key.
- **A two-way pair with metre widths is drawn in metres.** When both directions have a `width_m_col` width, from `width_m_zoom` on the pair's one casing is both directions together (their two inner casings once) and each direction is shifted by half the other direction's fill, so the carriageway is centred on the line. Before, the shift and the pair casing's extra width were class pixels, so lanes drawn as items in metres did not match their casing.

## [0.19.0] — 2026-10-09

Lane items in the fill's place: line items attached to an edge are drawn in the one road layer at their edge's position, each with its own width in metres; the level editor's bus mode.

### Added
- **Line items at their edge's fill position (simple mode).** `Overlay(edge_col=..., order_col=...)` LINE items go into the one ordered
  road layer at their edge's fill position, in order, so a bridge above covers them; an edge that has items draws no fill of its own (its
  items are its fill). Per item: `width_m_col` (metres, exact at every zoom: the layer's width and offset curves are base-2 exponential up
  to zoom 22 on a page with items), `offset_m_col` (metres, + = right), `dash_col`, flat ends; `select="item"` selects one item (picked by its
  own width). At most 38 items per edge (a clear error beyond). Shape and point overlays as before; the full look unchanged.
- **The level editor's bus mode:** a *bus* mode box (a bus line runs on the road, duckOSM `bus.route_edges`) and the road's **bus lines**
  in its card (`bus_lines`, merged over both directions by `level_input`).

### Known
- An overlay's own show/hide switch, `rsFilter(ids, label)` and `rsColor(ids, color, label)` do not yet reach items drawn in the road
  layer; the level editor's in-place update does not rebuild items; a selected item's highlight is drawn above all roads.

## [0.18.1] — 2026-10-09

One-way arrows only on cars' one-ways, the same rule in every page, tiles and the level editor; empty DuckDB columns no longer crash.

### Added
- **`rs.is_directed(edges, driving_col="driving", cycling_col="cycling", highway_col="highway")`**: the one definition of a directed edge
  for `directed_col` (mapstyle's): an edge open to cars or bikes that is not a path class (config `single_line_classes`). A one-way street
  whose reverse is a bus / bike lane is two halves with one arrow, on the car edge; a walking-only reverse is no half (one line).

### Fixed
- **An empty column from DuckDB no longer crashes `render_edges`:** a column with no values comes as a nullable dtype (pandas NA), and
  `v != v` / `v in (...)` raised on it; one test for a missing value (None, NaN, NA) is used everywhere.
- **One-way arrows only on driving roads (`driving_col`).** An edge gets an arrow only if it is one-way and driving: `driving_col="driving"`,
  an edge with false never gets one, even with a copied `oneway`. `driving_col` decides the arrows only; the drawing (two directions or one
  line) is `directed_col`'s. A two-direction pair with one one-way edge has its arrow on that edge, pointing its way, in its own half. A one-way street's
  reverse edge lying on the same line no longer cuts the chain's slots. Also with `tiles=True`. Default `None`: every edge counts as driving.
- **The level editor draws and decides arrows like every page.** It no longer calls a road one-way when it has no reverse edge in any mode:
  each edge carries its own `oneway`, `driving` and `directed` (new `roads.parquet` columns `edges_oneway` / `reversed_oneway`,
  `edges_driving` / `reversed_driving`, `edges_directed` / `reversed_directed`, written by `rs.level_input` / `make_area`; `directed` with
  `rs.is_directed` when the edges have `driving`) and the editor draws with `directed_col="directed"`, `driving_col="driving"`. An area made
  before this must be made again (the editor stops with that message).

## [0.18.0] — 2026-10-09

Simple mode is the default look (one road layer, MapLibre 5.24), a two-way road has one casing, tunnels fade toward Sand at 60, names and
arrows stay off crossings, and the level solver works from the tables with near rules off.

### Added
- **The level editor's guard before a rule is added** (`rs.levels.rule_conflicts`, `POST /api/check`): an exact duplicate, or a loop of the
  solver's own difference rules through the new one (found, yours, and the list waiting to be applied), named in plain words; you may add it anyway.
- **`render_edges(..., simple=True)`** (web): every road piece in ONE line layer instead of a few hundred (Monaco all modes: 310 layers
  to 7), ordered by `line-sort-key` position by position, casings before fills, with each casing cut into its heads as in the full look;
  colour and width per feature. A bridge has a wider casing and a blurred shadow evenly around it. Leaves out twin end caps;
  names, arrows and edge items are drawn above all roads. The full look is unchanged (`simple=False`).
- **The tunnel look moves toward a colour you choose** (`tunnel_toward`, default `Sand`, #d6cfc4): a name in `tunnel_towards` (Slate, Dark, Light, Graphite, Navy, Stone,
  Sand, Teal) or any `#rrggbb`, the same on every base map (Dark or Light on the base map's own theme sinks a tunnel into the map and keeps each class hue).
  `rsSetTunnelStyle({toward})`, `RS_TUNNEL_TOWARDS` and a colour list in the Tunnels box.
- **The level editor's *Start new session* button:** what is in `edits.csv` now moves under *Already in edits.csv* and the list of changes
  starts empty; nothing is deleted.
- **Credits:** a *Built on* section in the README and on the docs home page (MapLibre GL JS, OpenStreetMap and openstreetmap-carto, HiGHS,
  GeoPandas, Shapely, lonboard, folium).

### Changed
- **Street names and one-way arrows stay off crossings:** the annotation slots are cut back by half the crossing road's drawn width plus 2 m
  (at least 2 m + 2 m for a footway, so a zebra too) around every point where another road meets or crosses the street, bridges and tunnels
  over it included; the stretches between are divided into slots on their own. A street through a plain node stays one stretch. Names keep
  `line-center` and the class sort key. An arrow needs a stretch of 8 m, a name 20 m (with `slot_m` 100): a one-way stretch of 8 to 20 m
  is an arrow slot (Monaco: 254 of 394 one-way chains have a piece, 177 when arrows also needed 20 m). See docs/design/arrows_and_names.md.
- **A two-way road's dead end is square by default** in the level area (`level_area.defaults`, `rs.auto_ends`; `levels.dead_end_cap`): an end with no `meet` row on a road that has both directions. With one casing around both directions, two half-width round fill ends left a notch at the tip. One-way roads and ends that meet a road keep their rule; `caps.csv` always wins. `render_edges` does the same without a level area or cap columns (`_mark_twin_dead_ends`): a pair's end that no other edge has an end point at (lines crossing or touching mid-line do not count) is square for the casing and both fills, unless the data gives that end a cap (`cap_col` / `cap_start_col` / `cap_end_col`, `"round"` too); `twin_casing="each"` keeps the blob.
- **A two-way road has one casing around both directions** (setting `twin_casing`, `"one"` by default; `"each"` = the look
  before), with the level columns given or computed by `render_edges` itself (a plain call). The pair's casing is cut once, from the first edge's pieces, unshifted and as wide as both directions together; the other edge has no
  casing piece; each direction keeps its own fill, colour and caps. Ends are caps, no blob (`twin_end_caps` applies to `"each"` only); the
  first edge's start is the second's end, so each cap is the first edge's own at that end. The twins must agree reversed (casing numbers, heads,
  caps), else a warning names the pair. Simple mode, the full look and `tiles=True`; the bridge shadow and the tunnel dashes follow the one
  casing; the pieces name both edges (`__rs_edge2`), so the casing shows while either direction does. A bridge such as Avenue de France
  (Monaco) was two dark bands with square ends.
- **The level editor draws both directions of a two-way road** as the final map does (one edge each, the other direction running the road's line
  backwards with its heads and caps swapped): either direction picks the road, the search finds either edge id or edge_ref, the road card
  lists each direction's edge id and edge_ref (`rs.level_input` now writes `edge_refs` / `reversed_refs`; an area made before shows the
  other direction's id only), and the update in place after an Apply carries both edges' pieces.
- **A two-way footway, path, steps, cycleway ... is one full-width line, not two lanes** (setting `single_line_classes`, default footway, path, steps,
  pedestrian, cycleway, track, bridleway, corridor, platform; `[]` = lanes for all). Of a reverse pair only the first edge is drawn (so two reversed
  dash patterns never overlap); the second is flagged `__rs_dup` and draws nowhere (simple, full look, `tiles=True`, the level editor). Both edges
  keep their data and name each other (`__rs_edge2`): a click, `rsSelect` and the tooltip show "Direction 1" and "Direction 2" with each one's own
  fields, `rs:select` carries `detail.twin`. Filters and colours treat the line as both edges: it shows (and takes a colour) while either edge is in
  the `rsFilter` / `rsColor` set; hiding one direction alone is not possible (the class, bridge and tunnel switches hit both alike). No arrows.
- **The level solver works from the tables only** (`pairs.csv` + `edits.csv`): a stack is written at make (`rs.level_input`, `roadstyle-levels make`,
  `duckosm levels`, and inside `compute_levels`) as one row per part of the upper road that crosses the lower one (`a_end` `start` / `main` / `end`),
  worked out once with the heads of that time (`heads.csv`, else `head_m`); no whole-road stack rows. The solver lifts exactly the named parts of the
  enabled rows, with no geometry and no head lengths, so a head change never solves (the editor's `what_solver_sees` check is gone). Rows union; an
  edit with `enabled=false` switches off that exact row. `solve_levels` loses `parts` and `near_rules`; `near_rules` moved to `level_input` /
  `make --near-rules` (written as `near` rows, kept last). An old `pairs.csv` with whole-road stack rows, or an edit stack with no part, is an error
  that says what to do (make again / name the part). Monaco all modes: 4,918 whole-road rows to 487 part rows; 14.8 s, 0 given up, 22 wishes not kept.
- **The level editor redraws only the roads an Apply changed, in place** (no page reload): the server finds the roads whose levels, heads
  or caps are drawn differently and sends their features (roads, simple pieces, and the names / arrows when a fill number changed), built
  by `render(_edges=...)`; the page swaps them with `GeoJSONSource.updateData`. More than 1,500 changed roads: the whole page again, said
  in the status line. Monaco all modes, one cap: 6.1 s to 0.7 s from Apply to drawn. The roads and simple sources carry feature ids
  (the roads source its index, as `generateId` gave; a piece `16 * edge + k`).
- **A local re-solve keeps the untouched roads' numbers exactly** (`level_area.solve_local`): the result is shifted back when the solver's ground
  moved, so the editor's update in place sees only the roads that really moved (fixed roads that moved by different amounts: an error).
- **Simple mode's line-sort-key has a per-edge tie-breaker** (`+ edge * 1e-8`, under the smallest key step of 0.05; at most 1,000,000 edges, more is
  an error that says to pass `simple=False`): pieces with the same key are drawn by edge, so a road redrawn in place keeps its place.
- **The level editor's stack box**: start head / main / end head, several at once, one row each; *whole road* adds all three. *Switch off all found
  stack rows of this pair* (one switch-off per row) to override a found stack.
- **The level solver's near rules are off by default** (`near_rules=False` in `level_input` and `compute_levels`; CLI `make --near-rules` turns them on).
  A part that only comes near the road under it is not lifted (as if switched off); `attrs["levels_near"]` is empty. Monaco all modes: 14.4 s, 9 positions, 0 given up,
  against 45.9 s, 27 positions with 11,911 near rules, 1,477 of them broken anyway.
- **`tunnel_control=True` works in simple mode:** the *Tunnels* box, with its palette and dash-ratio selects, and `rsSetTunnelStyle({strength, toward, palette, ratio})` recolour the one road layer (and the names, arrows and items that take the tunnel look).
- **Simple mode draws dashes and end shapes (MapLibre 5.24 per-feature `line-dasharray` and `line-cap`):** a tunnel's casing is two pieces in the one layer, a solid one in the palette's gap colour (clear for *One colour*) and the dashes on top, 3 px wider than a casing; a dashed class's fill (footway, path, steps ...) has the full look's dash pattern; each road's end shapes (`cap_col`, `cap_start_col`, `cap_end_col`, the level editor's round / square / flat) are drawn per piece, two different ends as two fill halves and casing heads, as the full look. A casing's main piece stays round.
- **Simple mode: the bridge shadow and the wider bridge casing grow with the zoom:** none below zoom 14 (no shadow, the full look's bridge casing), linearly to the full values at zoom 17 and above (they were too strong zoomed out).
- **`simple=True` is the default** for every web map (`render_edges`, the dashboard, report and street-view pages, the level editor): one road layer (with the dashes and end shapes above),
  a blurred bridge shadow. `simple=False` draws the full look. `tiles=True` works with simple mode: the pieces of the one road layer are a layer
  (`simple`) of the embedded archive, read by `roads-simple` as a vector source layer; the command line (`--tiles`) and the Studio (vector tiles) use simple mode too.
- **One tunnel slider for every colour**: the steps 0, 25, 50, 55, 60, 65, 70, 75, 100, and `tunnel_strength` defaults to 60 (was 35), and the default target is Sand (was slate), so the default tunnel look changes.
- **The level editor does not solve for a head change** (see the first entry: the solver takes no heads).
- **The level editor:** with two roads picked, the rules between them come first, above the road cards; the map's end marks stand beside
  every start / end in the boxes and lists; a local re-solve with more drawing positions is kept (no full solve for that alone), a full solve
  is a note, not a red error, and an error stays until clicked (also in the console and the server log).
- **Casing cuts:** a seam reaches 0.5 m each way from its cut (a quarter of the shorter piece at most; a 2 cm seam lost its direction above
  zoom 18), seams are drawn from zoom 17 in simple mode as in the full look, and below zoom 17 a flat lap lies across each cut, so a bridge's
  outline has no thin gap.

### Fixed
- **Both directions of an unclassed road are a pair:** a missing class (None, NaN, "") is one value when edges are paired or grouped
  (`_cls`: two-way marking, the twin casing, slots), so an edge pair with no `highway` is drawn as a pair, not as two different roads
  (NaN != NaN). `render_edges` warns once when edges have no class, naming how many and up to 5 ids: they are drawn with the default
  style; usually bad data, e.g. an area outline (`area:highway`) taken as a road (Monaco way 1549041737).
- **The notebook preview draws again, with the bundled MapLibre (5.24 from the CDN, was 3.6.2):** 3.6 rejected simple mode's per-feature
  `line-cap` / `line-dasharray`, so the default map was blank. Why the preview had been held at 3.6: it is an `<iframe srcdoc>`, whose
  `location.origin` is `"null"`, while MapLibre's worker reports the notebook server's origin; MapLibre 4.0 to 5.19 drops worker messages
  whose origin differs, so no source ever loaded (style never finished, zero roads). 5.20 accepts the `"null"` origin. Checked headless in
  Jupyter Notebook 7.5 and JupyterLab 4.5: simple, `simple=False` and `tiles=True` draw their roads. A test pins the CDN version to the vendored one.
- **The level editor refuses an exact copy of a rule already in `edits.csv` on Apply** (copies kept a rule working after one copy was deleted).

## [0.17.1] — 2026-10-07

### Fixed
- **pyarrow is a dependency:** a level area writes `roads.parquet` (`roadstyle-levels make`, `duckosm levels`); without pyarrow it failed.
- **The solver's last stage at its time limit keeps its best numbers** (cost and fewest positions; what is over what is fixed by the stages
  before), with a warning and `levels_info["status"] == "TIME_LIMIT"`, instead of failing: an all-modes area failed on a slower machine.

## [0.17.0] — 2026-10-07

### Added
- **`Overlay(select="road" | "item")`** for items attached to a road: `"item"` selects the item itself (its own select and hover highlight,
  its own popup with the road's Street View link, `rs:select` with `item` = `{overlay, id, properties}` next to the road's `id` and
  `properties`); `"road"` (default) selects the road as before. The item still hides with its road. Overlays now take the page's
  `hover_color` / `select_color` for their highlight (they kept the default colours).

### Fixed
- **Each direction of a two-way road selects its own edge:** a click or hover takes the road right under the cursor before the tolerance box
  around it, which reached both directions near the middle and picked the one drawn last.
- **The class filter hides a road's street names and arrows with `filter_col` too:** every piece of a road (fill, casing pieces, fill halves,
  end caps, name and arrow slots) carries `__rs_cls`, its road's `filter_col` value (else `highway_col`), and the class filter reads it; the
  slots carried only the chain's `highway`, so with `filter_col` set the names and arrows of a hidden class stayed.

### Changed
- **One lookup for every piece of a road** (docs/design/edge_items.md, step 2): `rsFilter` on the roads, the class filter and the bridge and tunnel
  switches hide a road's items attached with `Overlay(edge_col=...)` too (they carry `__rs_edge`, the index of their road, and its class and level as
  `__rs_cls` / `__rs_lvl`), and `rsFilter` now hides the bridge shadows and 3D decks of the filtered roads (shown while any of their edges is).
  Hovering an attached item highlights its road; clicking it selects the road (`rs:select` with the road, its panel and Street View; an interactive
  item's fields come along in `overlays`). `rsFilter(ids, label)` on an attached overlay combines with its roads' filters. An overlay that belongs
  to no road is as before.
- **Every piece of a road names its edge** (docs/design/edge_items.md, step 1): `roads` features carry `__rs_edge` (their index), and the casing pieces, seams, fill halves, end caps, name and arrow slots carry `__rs_edge` (and `__rs_edge2` for a two-way pair) in place of `__rs_road` / `__rs_road2`; bridge shadow lines and 3D decks carry `__rs_edges`, the list of their edges (a list, no longer a string). The map looks and behaves as before.
- **The road tooltip waits** until the mouse rests on a road for `hover_delay_ms` (300 ms; `0`: at once): a mouse passing over the map shows none. The hover highlight still follows at once.
- **`roadstyle-levels make | solve | edit FOLDER`**: the level step and its editor come with the package (`roadstyle.level_area`:
  `make_area`, `solve_area`; `roadstyle.level_editor`), in place of `scripts/level_input.py`, `scripts/solve_levels.py` and
  `scripts/edit_levels.py`. The area folder and its files are as before.
- **Lanes pair only within one class:** two edges on one line in opposite directions are a two-way street's two lanes only when they
  are the same class (names, arrows and end caps too): a footway lying on a street the other way round left the street one narrow, shifted lane.
- `rsFilter` (and the editor's mode boxes) hides a filtered road's fill halves too (a road with two different end shapes kept its colour).
- **Fast filters:** `rsFilter`, `rsColor`, the class / bridge / tunnel switches and the editor's mode boxes look ids up (a MapLibre `match`)
  and set the filters without MapLibre's grammar check (~6 ms a layer): a switch on a page of ~500 layers froze it for seconds.
- The level editor shows only the roads of the modes you tick (driving, walking, cycling, private), when the roads have `modes`; display only.
- The level step keeps a `modes` column (who may use a road, e.g. `driving + walking`) and the level editor shows it in the road's card.
- **Roads on the same line join only if they are the same kind** (`highway`, `tunnel`, `bridge`, `layer`): a footway lying exactly on a tunnel's
  piece was joined with it, and the tunnel piece took the footway's tags (solved and drawn as a footway).
- The priority order warns when the edges have no `junction` column: no road is then known as a roundabout (it lost them silently).
- **An area of a database:** `make_area(edges, folder, db=...)` ties the area to a .duckdb file (`area.json`); every solve of it, the editor's
  too, writes the result with each edge's ends into `visualization.edge_levels` (`rs.save_area_levels`), and `rs.load_area_levels(con, edges)`
  reads it back (refusing other edges). duckOSM's `duckosm levels` makes such an area for all modes.
- **The editor's *Apply and solve* re-solves only the roads around the change** (`roadstyle.level_area.solve_local`,
  `rs.solve_levels(fixed=...)`): the roads within three relations of the changed ones are solved again with the same rules, every other road
  keeps its numbers. When the local result breaks a crossing the previous one kept, has more order wishes not kept, near warnings or drawing
  positions, or the solver fails, the whole area is solved instead and the page says so and why. `roadstyle-levels solve` stays a whole solve.
- **Leaner pages:** a road layer is made only where some feature can be drawn by it (a position without a bridge has no bridge layers, none
  without square ends has no square-end layers, ...); the look is the same. The all-modes Monaco page: 485 road layers before, 291 now.

## [0.16.0] — 2026-10-07

### Added
- **The level step on its own** (`docs/design/level_input.md`): `rs.level_input(edges)` (the solver's input from any edges: `roads`, one row per road, and `pairs`,
  `meet` / `stack` / `order`), `rs.solve_levels(roads, pairs, edits=...)`, and `scripts/level_input.py` / `scripts/solve_levels.py` writing `roads.parquet`, `pairs.csv`,
  an `edits.csv` you own, and `levels.csv`. `compute_levels` is the two in one call.
- **The level editor** (`scripts/edit_levels.py AREA_DIR`): a local page to write `edits.csv`: pick two roads, see their pairs, switch one off or add one;
  every change is solved at once and shown, an edit the solver refuses is not saved.
- **A stack edit on one part of A** (`a_end` = `start` / `main` / `end`): added, that part of A's casing is after B's fill even at a junction; switched off,
  only that part of a found pair is left out. The editor has the part chooser.
- The editor warns when a new order (road 1 after road 2) meets an active stack of road 2 over road 1: the stack outranks it, so the order would be given up.
- The editor: you choose which road is on top for an order or a stack (it was always the road clicked first); changes wait in a list until *Apply and solve*,
  one solve for all, with a busy layer over the map until the new map is drawn.
- `level_input` keeps the edges' `lanes` (shown in the editor's cards). A delete in the editor names its row as the page saw it: if edits.csv changed since, nothing is applied.
- **Your own stacks are always real** (never a near warning), and the order wishes let go are named (`attrs["levels_orders_not_kept"]`) and
  listed in the editor's Issues tab.
- **Street names fit their road:** 9/10 of the road's fill width (at most the old 10 to 14 px), and none where that would be under 8 px:
  names on secondary roads from zoom 16, on tertiary and residential streets from 17 (a service road shows none: the name data stops at z18).
- **The casing follows the same line as the fill:** the casing pieces and fill halves are simplified like the roads (`tolerance` 0.05, was MapLibre's 0.375):
  the outline no longer wobbles along curves.
- **A bridge shadow** (`bridge_shadow`, on): a soft dark shadow shifted 2 px down-right, drawn like an extra casing: every part of a bridge
  (start head, main part, end head) at its own casing number, so it lies over what the part crosses and never on its own road at a joint;
  parts at one number joined into one line, lines meeting end to end (flat ends); none over the last 3 m where a bridge comes down.
- Hiding the bridges (`rsSetBridges(false)`, the filter panel's *Bridges* row, a view's `bridges`) hides their shadows too.
- **Bridge casing slate** (`bridge_casing_color` `#64748b`, the colour tunnels fade to; black was too dark).
- **Casing that closes:** a bridge's heavier casing keeps each piece's cap (it was always flat: two bridge pieces could not close at a bend or
  a junction), and a round seam of casing at each cut inside a road closes the outline on a curve (from zoom 17: below it a seam reached past
  a 5 m head and showed as a bump on a flat end). The fill halves of a road with two
  different ends only paint; the road stays clickable in its own (transparent) fill layer. Default caps stay round.
- **Automatic head lengths and caps per road end, as an option** (`rs.auto_ends`, at zoom 18; `solve_levels.py --auto-ends`; the default stays 5 m and round:
  made for one zoom, the heads were too short at the others): heads as long as the drawings overlap at the join (before
  solving), caps round unless the round end would lie over a lower road or out of the joined roads (after solving, from the levels);
  `heads.csv` / `caps.csv` override (empty = automatic), and `levels.csv` carries each edge's ends as drawn. `rs.class_width_px`.
- **Three casing parts for every road; no length in the solver:** `solve_levels(empty_main=...)` (the roads whose main part is drawn with no length,
  from `rs.empty_mains(roads, head_m, heads)`) replaces its `head_m`: an empty main part is never lifted. A short road's heads count one by one,
  so given-up pairs are counted honestly (Monaco 22, was 16 undercounted). Head lengths per road end are the drawing's: `render_edges(head_start_m_col=...,
  head_end_m_col=...)`; the editor's *heads* inputs (`heads.csv`).
- **End shapes:** `cap_col` takes `"square"` (flat, as long as round), and `cap_start_col` / `cap_end_col` set one end each (an edge with two different ends is drawn
  from its casing heads and two fill halves). The editor: *start* / *end* round / square / flat per road (`caps.csv`), and the road's drawn width and lanes in its card.
- **Near rules last:** a stack rule whose part of A does not cross B (only near) is kept after the order wishes and, broken, is a warning
  (`attrs["levels_near"]`), not a given-up pair; `rs.casing_parts` gives the parts (replaces `empty_mains`), `solve_levels(parts=...)`.
- The editor has an **Issues** tab (given up in red, near warnings in amber): the crossing pairs the solver could not keep, A's parts under B's fill in red, each clickable.
- `examples/levels/monaco/`: hand-made level tables for Monaco (`edits.csv`, `heads.csv`, `caps.csv`).
- The editor has a search box: an edge id (either direction of a road) or an edge_ref, or a part of one; a hit is picked and shown.
- **An `amber` palette**: motorway `#f28c28`, trunk `#f5a623`, primary `#f4c542`, secondary `#f7df72`, tertiary `#b8d986`,
  residential `#d7dee8`, living_street `#cbd5e1`, service `#94a3b8`, track `#a3a3a3`; the other classes, the widths and the casings as `carto`.
- **`views=`**: a *View* menu next to *Colour by*. A view is a name and a set of settings applied together: the colour option, the road fill, which overlays show, the road classes,
  bridges, tunnels, 3D and the base map (`{"Lanes": {"road_fill": False, "overlays": {"lanes": True}}}`). The page opens with the first view; `rsSetView(name)` applies one from a host page.
  An unknown setting, or a name the page does not have, is an error. Design: `docs/design/core_model_and_views.md`.
- **`rsSetRoadFill(on)`**: the roads' own fill on or off in the page; with `road_fill=False` it can now be shown again.

### Changed
- **Meet or cross:** roads of different bands that only meet (a tunnel mouth, a bridge end) follow the priority order; roads that cross keep the band. With `band_col`
  the caller's bands decide everywhere. A short road on top keeps its pair on its fill (it was dropped). Monaco: tunnels on top at 223 of 350 mouths, every crossing right.
- **`render_edges` takes no `band_col` and no `order`** (an error says to compute the levels first); without level columns it calls `compute_levels` with its defaults.
  `compute_levels(order=...)` defaults to `"priority"`.
- **One arrow per one-way road in the window** (`docs/design/arrows_and_names.md`): the page puts one arrow in the middle of each one-way road's visible part,
  and keeps it there while it stays in the window; below zoom 17 only the main classes, none on a road shorter than 100 px on screen, and 150 px between arrows; the arrows no longer repeat along every 100 m slot (they crowded zoom 15). A tiled map keeps the old arrows.
- **The *Tunnels* box is off by default** (`tunnel_control=False`): it was the tool for choosing the tunnel look; the look it chose stays the default.
- **The default palette is `amber`** (`palettes.DEFAULT_PALETTE`) in place of `highsat` (too sharp); `carto` was tried first, but its white streets
  vanish on a light base map. `palette="highsat"` keeps the old look.
- **The order where roads meet:** `compute_levels(order="priority")`, now the default of `render_edges`: where roads of one band meet, a roundabout's fill is over a tunnel's,
  a tunnel's over a bridge's, a bridge's over the road class (`junction_col`, default `junction`: `roundabout` or `circular`). The band is unchanged, so a road that crosses over a tunnel
  still covers it. `order="class"` keeps the road class alone.
- **The tunnel look, v2's slider** (`docs/design/tunnel_look.md`): `tunnel_strength` (0-100, 35) moves everything on a tunnel, its fill, street names,
  arrows and attached items, toward slate, opaque (replaces the 72 % see-through fill and its underlay). The casing is two layers with MapLibre's dash, 3 px wider:
  a palette's two colours, dash on gap (`tunnel_palette`, default `Graphite + silver`), or slate dashes with empty gaps (`One colour`), moved toward slate with the rest; dash ratio 1:1 (`tunnel_casing_dash`). The two-tone casing
  (`tunnel_gap_shade`, `tunnel_dash_shade`) is gone. A *Tunnels* box (`tunnel_control`) and `rsSetTunnelStyle({strength, palette, ratio})` move it in the page; the slider has five steps (Normal colors 0, Subtle 20, Balanced 35, Strong 70, Full 100).
- **No light dashes on a tunnel's fill by default** (`tunnel_fill_dash: []`, v2's look); `[1.2, 1.2]` brings them back.
- **An arrow that would touch a street name is left out** (MapLibre places the names first; an arrow never pushes a name away).
- **`road_fill=False`**: the tunnel pattern is drawn over the items of its position, so a tunnel reads as a tunnel on the lanes; a hovered interactive overlay wins over the road under it.
- **Faster page building:** the casing pieces and the arrow and street-name slots are cut with a small numpy cutter instead of shapely's `substring` (the same lines), and a slot of a group of one edge no longer searches for its edge.
  A page of a city of 64,000 roads builds about 40% faster.

## [0.15.0] — 2026-10-04

### Added
- **`render_edges(road_fill=False)`**: the casing of each road, not its fill (the fill layers stay in the page, invisible, for clicks and hovers). The items attached with `Overlay(edge_col=, order_col=)` are then the fill: the use of a library that draws lanes,
  dash lines and connectors itself. Design: `docs/design/edge_overlays.md`, *Three ways to use it*.

- **Overlay styles**: an `Overlay` can name a `style` that a library passes in `settings=` (`config.overlays.styles`; roadstyle ships none) and has new fields: `width_m` (a width in metres, exact from `min_zoom`), `dash`, `min_zoom` / `max_zoom`, and
  the kind `"text"` (`text_col`, `text_size`, `text_color`, `text_halo`), a text along a line or at a point. They work for overlays attached to edges too. Design: `docs/design/overlay_styles.md`.

### Changed
- **A settings file can be YAML** (`.yaml`, `.yml`; PyYAML is now a dependency) as well as JSON. **A settings file that cannot be read is an error**: `settings=` (and `use_settings`, and the files roadstyle finds itself) with a file that is missing, not JSON / YAML or not a mapping raised nothing before and was skipped; it now raises a `ValueError` that names the file, and the settings stay as they were.

## [0.14.0] — 2026-10-04

### Added
- **Overlays attached to edges**: `Overlay(edge_col=, order_col=, color_col=)` and `render_edges(edge_id_col="edge_id")`. A feature is drawn at the position of its edge's fill number, after the fills and before the arrows of that position,
  by `order_col` (global, lower first), so a lane, a marking, a zebra crossing or a sign is over its own road and under every road above it. An edge id that is not among the roads is an error. `rsFilter` on such an overlay keeps each layer's position and order.
  Design: `docs/design/edge_overlays.md`; guide: *Overlays*.
- **The one-way arrows and the street names are connected to the roads**: each piece of road that carries one belongs to the edge under its middle point (`__rs_road`, and `__rs_road2` for the twin of a two-way street) and has that edge's fill number. `rsFilter` on the roads now hides the arrows and names of the edges that are not shown
  (before, only the class filter reached them). Tiles carry the same properties.

## [0.13.1] — 2026-10-04

### Added
- **`compute_levels(min_positions=True)`, on by default**: also minimises the span of the numbers (the highest minus the lowest), so the page has fewer positions, that is fewer layers. It has a lower priority than a stack or an order wish
  and a higher one than compaction, so nothing more is given up; the casings may lie a little farther from their fills. Stage 0 stays a minimum-cost flow. Estonia driving: 9 positions become 5, and the solve takes half the time;
  Vancouver walking: 6 become 5, the solve takes 4.5 times longer; on smaller networks the time is the same. `min_positions=False` leaves it out. The option is stored with the numbers (`min_positions` in `visualization.edge_levels_meta`).
  Numbers saved by 0.13.0 were computed without it: `load_levels` stops with a message that says so, and they must be computed again (or read with `min_positions=False`). Section 7.3.1 of the design.

### Changed
- **A road with no `highway` takes no part in the class order** (`order="class"`): no wish is made for it, with any road, instead of an error. The same for a null number in an `order` column (it was 0.0).

## [0.13.0] — 2026-10-03

### Breaking (0.13.0)
- **Position drawing is the only way the web map draws.** `render_edges(edges)` computes the two positions of every edge itself
  (`compute_levels(method="solve", order="class")`) and draws by them; with `casing_level_col` / `fill_level_col` it draws your own numbers. The three bands
  (below ground, ground, above), the class order as a drawing order, `order_col` (now a `ValueError`) and the separate bridge layers are gone.
  `band_col` stays as an input of the solver. A bridge keeps its heavier black casing, a tunnel its faded, dashed look. See `docs/design/levels_split_casing.md`, section 12.
- **scipy and ortools are core dependencies** (the solver); there is no `levels` extra.
- **`compute_levels(method="solve")` is 2 to 9 times faster:** stage 0 is solved as a minimum-cost flow (OR-tools) instead of an LP with HiGHS; every row of the LP is `x_i - x_j <= c`, the dual of a flow.
  Same optimum on the five reference networks (objectives 130, 1008, 868, 1608, 4786), same number of positions; where several optima exist the numbers can differ in about 2% of the cases. Vancouver driving 29 s to 6 s, Vancouver walking 345 s to 22 s, Estonia driving (738,655 edges) 1,085 s to 352 s; the preparation of the rows is vectorised. `levels_info["solver"]` says `flow` or `highs` (stages 1-3 and an uncertified stage 0 still use HiGHS).
- **`tiles=True` carries the positions**: the archive holds the casing pieces and the twin end caps as tile layers (`casings`, `ends`) next to `roads` and `slots`, and the page reads them
  from the one source (docs/design/levels_split_casing.md, 12.1). Monaco: 3.3 MB tiled against 2.3 MB inline. For a big network compute the positions once (`compute_levels`, `save_levels`).
  Measured: 75,866 edges 6 s, 249,278 edges 22 s, 738,655 edges 352 s (7, 6 and 9 positions).
- `compute_levels(order="class")` raises a `ValueError` for a null road class.

### Added
- **`rs.save_levels(con, levels)` / `rs.load_levels(con, edges, ...)`**: the result of `compute_levels` saved in a duckOSM file, in the new schema `visualization` (`edge_levels`: one row per `edge_id`; `edge_levels_meta`:
  the parameters, the number of edges and a hash of the ids), and read back. Both calls are explicit; reading checks the parameters and the edges and raises an error that says what differs, it never recomputes silently.
- **`rs.compute_levels(edges)`**: the `casing_level_col` / `fill_level_col` positions of every edge. The default `method="solve"` is the optimization (real variables, a margin `margin`, a range `max_level`,
  slack variables for Stack and the order wish; stage 0 as a minimum-cost flow, HiGHS when a wish must be given up). It takes a band (`band_col`, else the tag level), a divided casing (`head_m`) and an order (`order`, a column or `"class"`);
  pairs that cannot be satisfied are reported, not hidden. `method="tags"` is a closed-form rule on `layer` / `bridge` / `tunnel` and the shared nodes.
  It returns `casing_start`, `casing_level` (main), `casing_end` and `fill_level`. The specification is `docs/design/levels_split_casing.md`; the guide is *Which road is on top*.

### Changed
- **The bridge look in position mode** (with `casing_level_col` / `fill_level_col`): a bridge edge is drawn with its heavier black casing and flat ends again, in an extra casing layer of its own casing
  position (`roads-casing-bridge`, `-lv<p>`); the other casing layers leave bridge edges to it.
- **Twin end caps with a divided casing:** the cap's casing ring is painted at the head number of the lane that ends there (`casing_start` / `casing_end`), and is hidden where another road at the node is painted below
  that number; a pair drawn flat with `cap_col` gets no cap.
- **The end caps of two-way pairs follow the positions** (with `casing_level_col` / `fill_level_col`): for each position, the caps' casing is drawn right before that position's casing layers and
  their fill right before its fill layers (they were drawn before all positions and after all positions), and a cap hides its casing where a road at the node is painted below it by position.
- **`casing_start_col` / `casing_end_col` / `head_m`: a divided casing.** The casing of each edge can be drawn as a start head, a main part and an end head, each at its own number, from its own source of pieces;
  the fill stays one line; the main piece ends flat (butt caps, through the `cap_col` twin layers) so that its end cannot reach into the heads, the heads stay round. `compute_levels(method="solve")` returns `casing_start`, `casing_level` (main), `casing_end` and `fill_level`, with the heads swapped for the reversed direction of a road.
- **One-way arrows and street names follow the positions too** (with `casing_level_col` / `fill_level_col`): one layer of each per position, right after
  that position's fill layers, instead of tiers chosen by the `layer` tag and one name layer above everything. A tunnel's arrows were drawn under all road
  layers in this mode; they are now above their own road.
- **With `casing_level_col` / `fill_level_col` the position alone decides the drawing order, with no exception.** The class order
  (`z_order`), the level (`layer`), `band_col` and `order_col` no longer order anything, and a bridge is drawn at its positions like
  any road instead of in its own deck layers (it keeps its colours; the heavier black deck casing is not drawn; the 3D decks of `view_3d` still follow the tags).
  Without the columns nothing changes.

## [0.12.0] — 2026-10-03

### Added
- **`casing_level_col` / `fill_level_col`: the drawing order of each edge** (docs/design/level_columns.md). Two integer columns: the
  position in the drawing order where an edge's casing is drawn and where its fill is drawn. At each position every casing of the
  position is drawn first, then every fill, so edges that share a node merge cleanly and an edge drawn at a higher position is over the
  lower one with its own casing. One casing layer and one fill layer (with the tunnel look and the dashed classes) for each position
  that occurs, in position order; position 0 keeps the layer ids; `rsColor` / colour-by reach every fill layer. They replace the three
  bands for every edge but a bridge. Without the columns nothing changes.
- **`cap_col`: square ends per edge** (docs/design/square_ends.md). A column of true / false: an edge with a true value is
  drawn with butt caps (casing and fill) instead of round ones, by a `-sq` twin of each band's casing and fill layer
  (`roads-casing-sq`, `roads-fill-sq`, `roads-low-*-sq`, `roads-high-*-sq`), because MapLibre sets `line-cap` per layer. For a road
  drawn in pieces (a stretch at another level), so the pieces meet without a ring. Nothing changes without the keyword.
- **A tunnel keeps its look in any band.** With `band_col`, a tunnel put at ground level (or high) now draws its two-tone casing
  dashes (`roads-casing-dash`, `roads-high-casing-dash`), light fill dashes (`roads-fill-pat`, `roads-high-fill-pat`) and faded
  fill there too, as in the low band. Without such a tunnel there are no such layers.

### Changed
- **One drawing rule for every road: levels and looks** (docs/design/levels_and_looks.md). A road's *level* decides its draw
  band, nothing else: three bands, low (below ground), ground, high, from `lvl` (the OSM `layer`, else 1 for a
  bridge, -1 for a tunnel) or a caller's `band_col` (which now also moves a tunnel). A tunnel or a bridge is only a *look* on a
  road of its band, as sublayers and data: the tunnel's two-tone casing (`roads-low-casing-dash`), light fill dashes
  (`roads-low-fill-pat`) and faded fill (a data-driven opacity); the bridge's deck casing and fill, drawn after the plain high
  roads. **Removed:** the stretch cutting (`_stretches`: a tunnel, and a plain-layer road, cut into ground and under
  stretches), the `tpieces` source and every layer made for it (`roads-tunnel-*`, `roads-tunnelgr-*`, `roads-lowp-*`,
  `roads-plaingr-*`, `roads-highp-*`), `__rs_piece` / `__rs_pieced` / `__rs_gstart` / `__rs_gend` / `__rs_tfill`, and the page code
  that followed a stretch to its edge. A tunnel is now drawn whole, under every ground road: at its mouth a street's round end
  can show over the start of the tunnel's casing. The one-way arrows of a tunnel are no longer covered by its ground
  stretches, and anything built on a map follows the band of the road it is on.
- **Colour-by reaches the dashed layers.** A footway, path, steps ... edge is drawn by a `-dash<n>` layer; it now takes the
  active colouring too (`rsSetColorField`, `rsColor`), so a pattern and a colour scheme work together.

## [0.11.0] — 2026-09-30

### Added
- **Line widths in metres** (`width_m_col`, `width_m_zoom=16`, `casing_m=0.15`). A column of real
  widths (lanes, a road's `width` tag, a canal) is drawn exactly that wide from `width_m_zoom` on,
  at every zoom (base-2 exponential interpolation, each line at its own latitude), with its casing
  inside the width, so lines side by side touch with a thin divider. Null widths and maps without
  the column keep the class widths (docs/design/metre_widths.md).

## [0.10.0] — 2026-09-30

### Changed
- **Tunnels get light dashes on their fill** (`tunnel_fill_dash`, default `[1.2, 1.2]`, and
  `tunnel_fill_dash_color`, a translucent white that suits any road colour; `[]` turns it off), on
  top of the dashed casing, so a tunnel reads as one at a glance. A dashed class keeps only its own
  dashes.
- **A tunnel is an ordinary road with a tunnel style** (mapstyle's `docs/design/junctions.md`,
  rule 1). A tunnel was drawn in the lower band along its whole length, so at its mouth the street's
  round end lay across it and the street looked like a dead end. Now it goes to the lower band only
  where it really passes under a road it doesn't join (4 m either side of the crossing; at a shallow
  crossing, the whole stretch within 4 m of the road, but never into a mouth); the rest is drawn
  with the ground roads, in the tunnel's colours (an opaque faded fill, the two-tone dashed casing)
  with butt ends. A path above doesn't make an underpass. The edge stays one feature (clicks,
  filters, `rsColor`); its stretches are drawing pieces (source `tpieces`, `__rs_road` = its id).
  Replaces the tunnel mouth pieces: **`tunnel_portal_m` is removed** (an old settings file that
  sets it still loads; the key is ignored).
- **A road with only a `layer` tag acts the same, in the plain look.** One that passes over or under
  no road is drawn with the ground roads, so a `layer=-1` tunnel approach no longer looks cut off
  from the road it joins. One that does (a raised walkway over a street) is cut into stretches: over
  the road (clearing its drawn width at z17) in its own band with butt ends, the rest with the
  ground roads. A caller's `band_col` value still wins. Bridges keep their band.

### Added
- **Two-way roads end like one road.** A two-way road is drawn as two lanes side by side, each
  with its own round end, so every dead end and junction showed two bumps with a dip between
  them. Now each end of a two-way pair gets one round cap as wide as the whole road, under the two
  lanes (new source `ends`, layers `roads-ends-*` per plain band), except where a road drawn in a
  lower band meets that end (a tunnel mouth: the cap's ring would cross it). The lanes are unchanged, so
  both directions stay separately clickable. A cap draws only where both lanes share a colour, so
  maps coloured per direction keep their ends as before. It follows the class filter, the bridge
  and tunnel toggles, `rsFilter`, `rsColor` and the colour options. Setting: `twin_end_caps`
  (default `true`). Adds about 8–11 % to a page. Design: `docs/design/twin_ends.md`. Where a road
  in a lower band meets the end (a tunnel mouth), the cap is fill only: no ring across that road.
- **`directed_col`: say an edge is undirected.** Two-way roads are found by geometry (the same
  line, reversed), so a footway stored both ways, or a one-way street with a walking-only reverse
  edge, was drawn as two lanes. A pair is now two lanes only when neither edge is false in
  `directed_col`; otherwise it is one line, centred and full width. Null = directed (the geometry
  rule).

### Fixed
- **Dashed classes keep their dashes in tunnel and layer stretches** (each stretch layer gets the
  dashed sibling layers the whole-edge layers have).
- **Roads in the low / high bands can be clicked and hovered again.** Since 0.9.2 a road with a
  non-zero `layer` and no bridge / tunnel tag (a raised walkway) draws in `roads-high-*` /
  `roads-low-*`, and so do edges moved by `band_col`; those layers were missing from the pick
  pattern, so the road couldn't be selected.

### Changed
- **Link roads draw below every street, as in every established map style.** A `*_link` used to
  sort just under its parent class, so a `primary_link` covered the residential street it meets.
  Links now sort below every non-link street and above `service`, in their parents' order
  (`roads.z_order`: motorway_link 1.9 … tertiary_link 1.7), as openstreetmap-carto, OpenMapTiles,
  Mapbox Streets and OSM Americana do. A link the table doesn't list still sits just under its
  parent; settings can override any value. Design: `docs/design/junction_order.md`.

## [0.9.3] — 2026-09-30

### Added
- **A Tunnels row in the roads filter panel**, next to Bridges: switch every tunnel off and on, with
  its street names, arrows and mouth. From your own page: `rsSetTunnels(on)`. Shown only when the
  data has tunnels.
- **Draw order per edge: `band_col` and `order_col`.** Which road draws over which no longer has
  to come from its class and level alone. `band_col` names a column of -1 / 0 / 1 that puts an
  edge, casing included, under (`roads-low-*`) or over (`roads-high-*`) the ground roads: a
  sidewalk under its street, a zebra crossing over it; tunnels and bridges keep their band.
  `order_col` names a numeric column that orders edges inside their band instead of the class's
  `z_order` (clamped to -400 … 400, so `rsColor` still lifts a route over everything on its level).
  Both optional and per edge; without them the style is unchanged. Design:
  `docs/design/draw_order_per_edge.md`.

## [0.9.2] — 2026-09-30

### Changed
- **`rsColor` raises the roads it paints to the top of their level.** A highlighted route is no
  longer covered by a street it crosses: its line-sort-key goes up by 500 (levels are 1000
  apart), so a bridge above it still passes over it. `rsColor(null)` puts the order back.
- **Draw order follows the OSM `layer` tag.** Where roads cross, a tagged `layer` now decides
  which one is drawn on top (untagged: a bridge is 1, a tunnel -1, anything else 0). Before, a
  positive `layer` without a `bridge` tag counted as ground level, so a raised walkway was drawn
  under the street it passes over. The look still comes from the tags: deck styling and 3D decks
  only for `bridge`, the tunnel casing only for `tunnel`. Raised roads that aren't bridges draw
  plain in new layers `roads-high-*` (above the ground roads, below the bridges); lowered roads
  that aren't tunnels in `roads-low-*` (after the tunnels). A negative `layer` without a `tunnel`
  tag no longer gets the tunnel look.
- **Tunnel casings in two tones, never with empty gaps.** The dashed tunnel casing (osm-carto)
  left gaps where you couldn't tell whether two tunnel pieces connect. Now the casing is two dark
  shades of the road's own casing, a solid one with darker dashes on top (new layer
  `roads-tunnel-casing-dash` on top of `roads-tunnel-casing`): it is continuous, and the dash
  still says "tunnel". Settings: `tunnel_casing_dash` (default `[2, 2]`), `tunnel_gap_shade`
  (`0.25`) and `tunnel_dash_shade` (`0.5`): how much darker than the road's casing (an already
  dark casing, as in `mono`, keeps its own tone under the dashes).

### Fixed
- **A road running into a tunnel no longer looks cut off.** Tunnels draw under the surface roads,
  so at a tunnel mouth the surface road's casing and round end were painted across the tunnel's
  start like a wall. Now the first metres of the tunnel draw at street level (a new `portals`
  source and `roads-portal-fill` layer), and the road visibly runs into it. Recolouring
  (`rsColor`, `color_options`) and `rsFilter` reach those pieces too. Length: the
  `tunnel_portal_m` setting (default 8 m; `0` turns it off). A tunnel that passes under a street
  within 12 m of its mouth gets no piece, so that street stays whole. Feature ids and the JS API
  are unchanged.

## [0.9.1] — 2026-09-29

### Added
- **`roadstyle-mcp` on PyPI.** The MCP server under its own name, so the install is
  `claude mcp add roadstyle -- uvx roadstyle-mcp`. It has no code of its own: it installs
  `roadstyle[mcp]` (same version) and provides the command. Released together with roadstyle.
- **A Claude Code plugin.** `/plugin marketplace add Khoshkhah/roadstyle`, then
  `/plugin install roadstyle@roadstyle`: the MCP server and the agent skill in one install.
- **Listed in the MCP Registry** as `io.github.Khoshkhah/roadstyle`, published by the release
  workflow.

### Changed
- The license is declared as an SPDX expression (`license = "MIT"`), which setuptools requires
  from February 2027.

### Fixed
- **Base maps no longer go blank when you zoom in far.** Every base map has a last zoom level with
  real tiles: 16 for Esri's Light Gray and Dark Gray, 19 for Esri Streets, Satellite and
  OpenStreetMap, 20 for CARTO. Past it the map showed grey "Map data not yet available" squares
  (Esri answers with a real image, so nothing could tell) or nothing at all. Each base map now
  carries its `maxzoom`, and the map scales its last level up instead. New `Basemap.maxzoom` field
  (default 19); xyzservices providers bring their own.
- **Switching base maps updates the attribution.** It kept the first map's credit ("© CARTO" on
  an Esri map). Switching now rebuilds the base-map source, in the same place under the roads.
- **Roads appear even when the map starts late.** A map opened off screen (a background tab, a
  notebook output scrolled out of view) builds its sources only once it is shown; the inline data
  loader stopped waiting after 60 s and the map stayed empty. It now keeps waiting, and clears the
  self-check banner if the roads arrive after it appeared.

## [0.9.0] — 2026-09-29

### Added
- **osmnx edges render as they are.** `rs.render_edges(ox.graph_to_gdfs(G, nodes=False))` used to
  fail with `TypeError: unhashable type: 'list'`: osmnx keeps every differing tag of the OSM ways it
  merged as a list (`name=['Götgatan', 'Ringvägen']`). Each list now becomes its first present value
  (a merged `tunnel=[nan, 'yes']` stays a tunnel), and the `(u, v, key)` index becomes columns. New
  notebook `notebooks/10_osmnx.ipynb`.
- **An MCP server: roadstyle as tools for AI agents.** `pip install "roadstyle[mcp]"`, then
  `roadstyle-mcp` (stdio). Tools: `render_place` (any place name, roads downloaded with osmnx),
  `render_file` and `snapshot`. Each saves the map and returns its path, a summary and a PNG
  preview. A misspelt option is an error naming the closest valid keyword, errors reach the agent
  with their message, a download falls back to a second Overpass server, and without a CARTO key
  the map uses the keyless `esri_street` base map instead of watermarked tiles.
- **A warning for edges tagged both bridge and tunnel.** They are drawn as bridges; the usual cause
  is osmnx merging a tunnel with the bridge next to it. The warning names the osmnx setting that
  keeps them apart.

## [0.8.6] — 2026-09-28

### Fixed
- **The Street View window stays inside the map.** It could be dragged anywhere in the browser
  window, so on a page with a side panel it could end up under the panel - most easily by moving it
  while the panel was hidden and then showing the panel - and could not be reached again. Dragging now
  stops at the map's edges, and when the map changes size the window is pulled back inside.

## [0.8.5] — 2026-09-28

### Fixed
- **Classic -> Linked still showed a small panorama in a corner in a real browser** (0.8.4's fix held
  only headless). A panorama now exists only while it is on screen: hiding it (Classic, the window
  closed, a message) drops it, and the next Linked view builds a new one in a visible box.

## [0.8.4] — 2026-09-28

### Fixed
- **Classic -> Linked showed a black Street View panel** (one tile in the corner), on the window
  and on the side-by-side page: the panorama was set while its box was still hidden, so it drew at
  0x0. The box is shown first now, then the panorama is set and told its size.

### Added
- **`rsGetStreetViewSpot()` and the `rs:streetviewspot` event: where the Street View spot is, exactly.**
  The edge (`id`, `properties`), metres along it (`m`) and its length, the point (`lng`, `lat`), where
  the viewer looks (`heading`) and the road's own direction (`roadHeading`) - for placing something
  at a precise spot and direction. `source` says whether it is current: `"panorama"` when Linked put it
  there, `"map"` after a click or step (Classic cannot report the viewer's walk).

## [0.8.3] — 2026-09-28

### Added
- **`street_view_key=` on every map's floating Street View window**, not only on
  `render_street_view`: with a Google Maps JavaScript API key the window's bar offers the same
  **Linked** (a panorama; the map marker walks with the viewer) / **Classic** (the keyless embed)
  switch, remembered in the browser. Without a key the window is unchanged.

## [0.8.2] — 2026-09-28

### Added
- **`street_view_key=` on `render_street_view`: the map marker walks with the viewer.** With a
  Google Maps JavaScript API key the panel is a real panorama instead of the keyless embed: every
  step and turn inside it moves the marker (and pans the map to keep it in view), and only Google's
  own street imagery is shown - the embed also offered people's indoor photos. Without a key the
  page is unchanged. **Both versions stay on the page:** a switch in the panel's bar flips between
  **Linked** (the panorama) and **Classic** (the embed) at the spot the viewer is at, remembered in
  their browser. The walking marker is snapped onto the road as drawn, in its lane.
- **`rsSetStreetViewMarkerAt(lng, lat, heading)`**: the marker at any spot, off the clicked edge if
  need be; the next selection or step returns it to the edge.

## [0.8.1] — 2026-09-28

### Changed
- **The switcher offers Light Gray first, and always a blank map.** The default `basemaps` list is
  `esri_gray`, `positron`, `osm`, `satellite`, `voyager`, `dark_matter`, `blank`.
- **No black text on the web map.** The legend, the filter control, the base-map menu, popups and
  hover tooltips, the map's own buttons (2D/3D, Street View), the scale bar and the attribution use
  soft slate (`#334155`, `#475569`) instead of `#16181d` or the browser's black.

## [0.8.0] — 2026-09-27

### Changed
- **The base-map button is a map control**, last in the top-right column after zoom, 2D/3D and
  Street View, with their size and look; its menu opens to its left. It used to sit on `<body>` at
  the bottom right, so a host page with a side panel had to move it by hand
  (`.bm-icon{right:...}`); now it moves with an inset `#map` like the other controls, and those
  old host rules are outranked and do nothing.

### Added
- **`zoom_readout=`** (default `True`): `False` leaves out the "z 13.2" read-out beside the scale bar.

## [0.7.1] — 2026-09-27

### Added
- **`rs.render_street_view(..., layout="below")`** (CLI `--layout below`): the map on top and
  Street View under it, with a divider dragged up and down; `panel_width` is then its share of the
  height. `"beside"` (next to the map) stays the default.

### Changed
- The side-by-side page's header is one compact row (title · road name, then ◀ ▶) instead of two.
- The Street View pages switch to their phone layout only under 520 px (was 700): a docs page's
  text column (~690 px on a laptop) showed the side-by-side page stacked, without its divider, and
  the floating window as a full-width sheet.
- Docs: a **Street View** page with a live demo of each version (the floating window, beside the
  map, below the map); the Manual's colour-by demo opens on the data, its samples drop the
  default `backend="web"`.

- **Docs redesigned**: by task (Get started; seven short guides, each one screen with a live map;
  Gallery; Reference tables; Studio), roadstyle's colours and logo, cards and tabs. Old URLs
  redirect.

### Fixed (layout)
- `render_edges(backend="lonboard", view_3d=True)` (any web-only keyword) raised a TypeError from
  `lonboard.Map`; web-only keywords are now dropped, as on folium.
- The overlay **Layers** control sat on top of the base-map button; it now sits above it (and
  follows a host page's side panel like the button).

### Fixed
- Stepping Street View along a road (◀ ▶) pans the map when the marker nears its edge, so the
  marker stays in view.
- **A map whose Street View window was left open stopped working (0.7.0).** Reopening the window
  on load ran before the marker's state existed; the error stopped the page before any road was
  drawn, so nothing could be selected. The window now reopens once the map has loaded.
- The window's remembered state (open, place, size) is kept per page, not per site: a window
  enlarged on one map no longer reopens over another page's small embedded map. A reopened
  window is also kept to at most 60% of the map and inside it.
- On a two-way road the Street View marker sat 2.5 m right of the centre line, which is off the
  drawn road when zoomed in. It now sits on its direction's lane as the map draws it (the
  layer's own line-offset at the current zoom); Google still gets the 2.5 m lane point.

## [0.7.0] — 2026-09-26

### Added
- **Street View marker and steps.** While Street View is shown (the window, or the side-by-side
  page), a marker on the map (a dot and a viewing cone) shows where it stands and which way it
  looks. **◀ ▶** buttons walk 15 m back or forward along the edge, so a road can be followed
  without clicking the map again. JS: `rsStreetViewStep(m)` (event `rs:streetviewmove`),
  `rsSetStreetViewMarker(on)`.

### Fixed
- `rsSelect(id)` anchored its popup (and now the Street View spot) at the edge's middle VERTEX,
  which on a two-point edge is its end; it now uses the middle of the length (inline and tiled).

## [0.6.0] — 2026-09-26

### Changed
- **The Street View window is the default** (`street_view="window"`): every map gets a Street View
  button. `street_view=True` keeps the old plain link in the popup, `False` turns it off.
  `render_street_view` pages keep only their own panel.

## [0.5.0] — 2026-09-26

### Added
- **`rs.render_street_view(edges)`**: a page with the map and Google Street View side by side.
  Click a road and Street View shows it, looking the way the edge runs (no new window, no API
  key). A draggable divider shares the width (`panel_width=42`, `resizable=True`); on a phone,
  Street View sits under the map. Google's embed loads only in a served page (http/https);
  opened from disk, the panel says how to serve it and links to Street View instead.
  Live demo in the web-backend docs.
- **`street_view="window"`** (web backend): a Street View button on the map opening a floating
  window that follows each clicked road: drag it by its title bar, resize it by its corner; it
  opens at the map's corner (clear of the host page's own panels) and remembers open state,
  place and size per browser. Nothing is loaded from Google while it is closed. The popup link
  opens it instead of a new tab. JS: `rsSetStreetView(on)`, event `rs:streetviewchange`.
- **CLI `--page dashboard | report | street-view`**: the ready-made pages from the shell, with
  `--panel-width` / `--no-resize` for the street-view one.

### Changed
- The Street View link (and `rs:select`'s `detail.streetView`) now points at the nearest spot on the
  clicked edge's own geometry, the road's centre line, instead of the raw click. Clicks on a
  drawn lane, or at an overview zoom, landed metres off the road, so Google often picked a
  nearby indoor photo (a shop interior) instead of the road's Street View imagery. A two-way
  road's twin edges (one line) then each step 2.5 m right, into the middle of their own lane,
  so the two directions no longer share one spot.

## [0.4.2] — 2026-09-26

### Added
- **`street_view=True`** (web backend): a Google Street View link in the road popup / panel, at
  the clicked point and facing the clicked edge's direction, so a road's two directions get
  opposite headings. A plain maps URL, no API key; `street_view=False` turns it off.
  The URL also rides on `rs:select` as `detail.streetView`, for host pages with their own panel.
- **`skills/roadstyle/SKILL.md`**: an agent skill for code that *uses* roadstyle (the one call,
  the data contract, the JS API, the traps); **`AGENTS.md`** for agents working on the repo;
  **`llms.txt`** at the docs site root.
- **`rs.snapshot(..., scale=)`**: device pixel ratio (default 1); `scale=2` for sharp PNGs on HiDPI screens and in print.

### Changed
- Field names in the click popup and the hover tooltip are **bold**, values plain.
- Docs site merged from 15 pages to 9 (Home, Manual, Gallery, Studio, Web backend, Embedding,
  Parameters & API, Palettes/base maps/settings, Engines); the old URLs redirect. Parameters &
  API is now the one complete keyword reference, per backend.
- PyPI summary rewritten; the CLI's `--palette` accepts `mono`.
- README cut to a one-screen overview with a sharp 2x hero image (`docs/build_gallery.py`);
  the parameter tables live in the docs, base maps & API keys moved into the docs (now the palettes page).

### Fixed
- `rs.snapshot(html_string, ...)` raised `OSError: File name too long` instead of rendering it.
- `render_edges(backend="folium", tiles=True)` (or `view_3d`, `street_view`, … any web-only
  keyword) raised a `TypeError` from `folium.Map`; web-only keywords are now dropped on folium.

## [0.4.1] — 2026-08-29

### Added
- **Base map API key resolution & third-party provider support**:
  - Full API key resolution for commercial tile providers (CARTO, Mapbox, Stadia, Thunderforest, Jawg, MapTiler, etc.).
  - Added `roadstyle.set_api_key(key, provider=None)` and `roadstyle.get_api_key(provider=None)` for session management.
  - Added `api_key` parameter across all rendering backends (`render_edges`, `render_web`, `render_folium`, `render_lonboard`, and `to_spec`).
  - Automatic environment variable resolution (`CARTO_API_KEY`, `MAPBOX_API_KEY`, `STADIA_API_KEY`, `THUNDERFOREST_API_KEY`, `ROADSTYLE_API_KEY`).
  - Persistent config file support in `~/.config/roadstyle/roadstyle.json` and `./roadstyle.json`.
  - Automatic injection of `?key=` parameter for CARTO basemaps to prevent "API KEY REQUIRED" watermark.

### Fixed
- **`name=` shows as the page heading.** `render_dashboard` / `render_report` (and the studio's
  *Title* knob) now put the name in the sidebar's `<h2>` as well as the browser-tab `<title>`;
  before, the heading was stuck on the template's hardcoded text.

## [0.4.0] — 2026-07-24

### Added
- **`roadstyle studio`** — the Streamlit workbench now ships inside the package (`roadstyle/studio/`)
  and launches from one command: `pip install "roadstyle[studio]"`, then `roadstyle studio` (no repo
  checkout). The subcommand forwards every extra argument to `streamlit run`, so
  `roadstyle studio --server.port 8502` behaves as usual. Sample networks download on first use
  (cached under `~/.cache/roadstyle`), or are read straight from the repo when run from a source
  checkout. The `ui/studio/` tree keeps only the shared `samples/`.
- **`roadstyle[all]`** — one extra that pulls every user-facing extra
  (`numeric`, `basemaps`, `lonboard`, `duckdb`, `arrow`, `tiles`, `studio`).
  `[dev]` now builds on it (`roadstyle[all]` + pytest/ruff/mypy) instead of
  hand-listing packages — so it gains `streamlit` and can't drift.

### Fixed
- **Web backend honours `legend=`.** `render_edges(backend="web", color_by=…, cmap=…)` (and the CLI
  `--color-by … -f web`) now render the data styler's legend — a continuous ramp or categorical key,
  drawn as a single legend-only entry (no *Colour by* dropdown) — matching the folium backend.
  Previously a data-coloured web map showed no key unless you used `color_options`. `legend=False`
  opts out; class-styled maps are unchanged (they carry the road-type filter, no legend).

## [0.3.0] — 2026-07-24

### Added
- **`render_dashboard()` / `render_report()`** — one call renders a self-contained page: the styled
  map with the built-in controls off and a bundled sidebar injected (the dashboard's query /
  colour-by / class-filter + legend / table UI, or the report's stats panel), wired through the
  public `window.rs*` API. Returns a `WebMap` (`.save("dashboard.html")`). The sidebar templates now
  **ship inside the package** (`roadstyle/templates/`), so `pip install roadstyle` builds these pages
  with no repo checkout; `sidebar_html("dashboard" | "report")` returns the fragment to copy and
  reshape.

### Changed
- `ui/dashboard/build.py`, `ui/report/build.py` and the studio Dashboard / Report pages now wrap the
  packaged `render_dashboard` / `render_report` — one source of truth for the sidebars.

## [0.2.2] — 2026-07-24

### Changed
- **In-map controls restyled** (web backend, `web_template.html`) — the road-class filter,
  colour-by dropdown, legend, base-map menu and overlay control now share one look: muted
  uppercase headers, an accent for the active/hover state, soft shadows and hairline borders. The
  colour-by dropdown and filter are grouped into a single anchored top-left stack, fixing a stray
  top gap and an overlap with the native zoom controls.
- **Popup and hover tooltip are now translucent**, with a backdrop blur that keeps text legible
  over busy maps.

### Added
- Studio (repo tooling, not on PyPI): the **Map** page gains a multi-column colour-by with an
  in-map dropdown + legend, and a shared `colour_by_section` across Map / Dashboard / Report offers
  numeric **and** low-cardinality categorical columns (`bridge`, `oneway`, `layer`, …), drops
  id/key columns, and picks a discrete `min(5, n)` categorical scale or a continuous p2–p98 ramp
  per column (unmapped edges stay neutral). The **dashboard sidebar** is restyled to match the
  report and gains a road-class legend; Dashboard and Report gain a *Decorations* (labels / arrows)
  section.

## [0.2.1] — 2026-07-23

### Added
- **Report sidebar UI template** (`ui/report/`) — a stats-forward panel over any web map: KPI
  cards (edges / classes / named roads / length), the active colour-by legend, a checkbox filter
  for overlay layers and road types, search, and a selected-road read-out. Wired entirely through
  the public `window.rs*` API; a matching **Report** page joins the studio.
- **`RS_CLASS_COL` / `RS_CLASS_COLORS` JS globals** (web backend) — the column `RS_CLASSES` came
  from, and each class's baked fill colour, so a custom UI can build a by-class legend or filter.
- Studio **Dashboard** and **Report** pages gain a *Hover tooltip* section (`tooltip=`).

### Changed
- **Panel legend and road-class filter collapse by default** in panel mode (`popup_mode="panel"`),
  reclaiming the space above the record read-out; floating maps are unchanged.

### Fixed
- **Panel search matches column names too.** Bridges are `bridge=yes` (no *value* contains the
  string "bridge"), so a value-only search found nothing; the built-in `_sideSearch` and the report
  sidebar now also match the query against the column name when that field is set, so `bridge`,
  `tunnel`, `oneway`, … resolve.

## [0.2.0] — 2026-07-22

First PyPI release.

### Changed
- **`compress` is now on by default** for web maps (3–4× smaller files; sources under 256 KB
  stay inline). `compress=False` / `--no-compress` writes plain JSON. Gzip blobs are stamped
  with `mtime=0`, so the same map now renders byte-identical across runs.
- Version is single-sourced from `pyproject.toml` (`roadstyle.__version__` reads the install
  metadata).

### Added (vector tiles)
- **`tiles=True` (web backend)**: pack the roads — and the street-name/arrow annotation slots —
  as a **PMTiles vector tileset embedded in the single HTML file**, served to MapLibre from
  memory via an in-page `pmtiles://` protocol (vendored pmtiles.js). MapLibre parses only the
  tiles in view: ~10⁵-edge maps boot in a couple of seconds and stay responsive, still offline,
  still one file. Low zooms carry simplified geometry and only the classes the settings
  `minzoom` table shows there. The full JS API, popups and hover/select work unchanged — full
  per-edge attributes travel in a gzipped sidecar table sharing the same index-id space.
  New extra `roadstyle[tiles]` (mapbox-vector-tile + pmtiles), CLI `--tiles`, settings knobs
  under `config.tiles` (zoom range / extent / clip buffer). Class thinning in the tiles
  follows the `minzoom` parameter exactly like the inline version — off by default
  (residential visible at the opening zoom), opt-in with `minzoom=True`. The dashboard builder
  (`ui/dashboard/build.py --tiles`) and both studio pages (a *Vector tiles* toggle) expose it,
  and notebook/studio previews of tiled maps keep the vendored MapLibre v4 (the CDN v3 preview
  predates promise-style `addProtocol`).

### Fixed (grade separation on walking/cycling networks)
- **Solid roads vanished from maps with dashed classes**: `__rs_dash` is baked as null on
  non-dashed edges and MapLibre's `["has"]` counts a present-null as true — the not-dashed
  exclusion filter silently dropped every solid-class road from the fill/casing layers, so
  walking/cycling maps showed the *basemap's* streets instead of roadstyle's (and stacking
  around bridges looked wrong). The filter is now null-safe (`to-boolean`).
- **Stacked structures order by OSM `layer`**: `lvl` now carries the layer value (bridge ≥ +1,
  tunnel ≤ −1), so a layer=3 viaduct draws above a layer=1 footbridge instead of falling back
  to class importance.
- **Dashed-class bridges get a real deck**: the black bridge casing now includes footway /
  cycleway / path bridges, with a solid underlay (the class's light casing colour) beneath the
  dashes — the osm-carto footbridge look. Previously a path bridge drew as bare floating
  dashes, letting whatever passed underneath show through the gaps.
- **Draw-priority review for walking/cycling classes** (aligned with osm-carto's z_order):
  `service` moved BELOW `pedestrian`/`living_street` (was above — a parking alley could cover
  a plaza), `track` slots just above `footway`, `steps` just below (ties used to break
  arbitrarily), and `platform` gets an explicit bottom-of-stack entry (unknown classes default
  to residential priority — railway platforms were drawing at street level). Dashed classes
  (footway/cycleway/path) now honour the table too: their layers draw UNDER the solid
  casing+fill of the same grade, so a street covers a footpath crossing it (osm-carto order —
  they used to ride above everything as a side effect of the sibling-layer construction).
  Bridge-bucket dashes keep their deck sandwich on top: a footbridge is a structure, not a
  surface marking.
- **Overlay click precedence follows the visual stacking**: an `"over"` overlay (POIs) wins
  the click, then the roads, then `"under"` overlays (zone fills) — previously ANY clickable
  overlay ate the click, so a road inside a clickable zone could never be selected and
  dashboards got no `rs:select` for it. A selected road now also reports the interactive
  overlays under the click — the popup/panel appends a section per overlay, `rs:select`
  carries `detail.overlays` (`[{label, fields, properties}]`), and the dashboard sidebar
  renders road + zone together.
- **Overlay hover tooltips** (`Overlay(tooltip=[...])`): overlays get the same split the road
  layer has — `popup` fields on click, `tooltip` fields following the mouse. Direct clicks on
  ANY interactive overlay (sensors/POIs included, not just zones under a road) now dispatch
  `rs:select` (`detail.overlay` = its label), so dashboard sidebars show overlay info without
  extra wiring.
- Studio: every sidebar section is a collapsible expander (Data and Look start open); each
  overlay gets "Click popup columns" and "Hover tooltip columns" pickers.
- Studio: tiled maps preview correctly and show an "embedded vector tiles" badge. Vendored
  MapLibre v4 stalls ANY roads source (GeoJSON or vector) inside sandboxed iframes, so tiled
  previews go through the same CDN v3 slim variant as inline ones — pmtiles.js's Protocol is
  v3-compatible. Verified in a live Streamlit session.

### Added (release engineering)
- CI: lint + tests on Python 3.10–3.13, plus a headless-Chromium smoke test that boots a saved
  map and asserts the data reached MapLibre (`tests/test_web_smoke.py`).
- Tag-triggered PyPI release workflow (trusted publishing).
- The web page template now lives in `static/web_template.html` (was an inline Python string) —
  same output byte-for-byte.
- Docs: kepler.gl comparison + an explicit practical size ceiling for inlined maps.

### Added (2026-07 wave)
- **One settings file** for every styling default (`data/defaults.json`) with the override
  ladder: `~/.config/roadstyle/roadstyle.json` → `./roadstyle.json` → `$ROADSTYLE_CONFIG` →
  `rs.use_settings(...)` → per-call `render_edges(..., settings=...)`. The theme system was
  removed (single light-grey casing; black on bridges; primary base map is a setting).
- **JavaScript API**: `window.rsSetBasemap/rsSetClasses/rsSetColorField/rsSetOverlay/
  rsSetView3D/rsSelect/rsDeselect` — every in-map control scriptable and event-emitting
  (`rs:*` CustomEvents) — plus **id-set queries**: `rsQuery(predicate[, layer])` returns ids;
  `rsFilter/rsColor/rsHighlight/rsGetProps/rsFocus` act on the set, on roads or any overlay.
- **UI templates** (`ui/`): the sidebar dashboard (query box with SQL-style syntax, verb
  buttons, clickable results table → select + fly-to, detail panel, base-map/colour-by selects).
- **3D bridges**: ramped extruded decks with whole-structure hover/select, black side-strip
  casing (`bridge_decks.casing_px`), width trimmed by `bridge_decks.width_scale`, and a 2D LOD —
  flat cased lines below `bridge_decks.flat_below` (default 16) so bridges stay road-width and
  visible at overview zooms.
- **Tile-less base maps** `blank` / `blank_dark` (plain background colour; saved maps make zero
  network requests); `from_duckosm()`; `rs.snapshot()` (headless-browser PNGs); annotation
  slots (alternating names/arrows); `minzoom` class hiding; scale bar + zoom read-out;
  `road_popup="panel"`; overlay styling defaults in settings; compress; the docs gallery.

Goal: generalize roadstyle from an OSM-only tool into a reusable, data-driven road-map
styling library that can also be embedded in a website. The existing OSM styling stays
byte-for-byte unchanged; everything new is additive.

### Added
- **Curated default road popup**: `road_popup=True` (default) now shows a concise field set
  (`DEFAULT_ROAD_POPUP` = name, edge_id, edge_ref, highway, lanes, bridge, tunnel) instead of every
  column — `name` as the bold title (no label), `bridge`/`tunnel` only when the road actually is one,
  and blank / `nan` values dropped. Pass `road_popup=[fields]` for a custom set or `road_popup="all"`
  for every column; `road_popup=False` still disables it.
- **Per-edge colour table**: `render_edges(edges, color_table={edge_id: colour})` paints each edge
  from your own map (dict / `Series` / DataFrame with `color_key`+`color_col`) instead of by road
  class — for clusters, routes, metrics, etc. Edges not in the table get a **gray** fallback; class
  widths + casing are kept so the network still reads as roads. `colors="self"` does the same from
  a colour column already on the data. New `ColorTableStyler`; works on every backend.
- **MapLibre `web` backend is now the default** (`render_edges` `backend="web"`); the CLI's `-f web`
  emits it too and is the default format. The old `-f web` roadstyle.js page moved to **`-f rsjs`**
  (resolving the name clash). Folium-specific features (legends, filter panel) stay on
  `backend="folium"` / `-f folium`.
- **Web-backend UI toggles**: `arrows`, `labels`, `filter_control` (a new collapsible **road-class
  filter panel** — a checkbox per class present, hides that class across every road layer), and
  `basemap_switcher` (the in-map base-layer dropdown). All default `True`; CLI flags `--no-arrows`,
  `--no-labels`, `--no-filter`, `--no-basemap-switcher`.
- **Web-backend boundary overlay**: `render_edges(edges, backend="web", boundary=…)` draws a dashed
  outline on top of the roads (e.g. the area the network was clipped to). Accepts a shapely
  geometry, a `GeoSeries`/`GeoDataFrame` (reprojected to EPSG:4326), or a GeoJSON mapping; `None`
  (default) draws nothing. Rendered as its own `boundary` layer, so it is excluded from the
  road-class filter and from hover/click picking.
- **MapLibre `web` backend** (`render_edges(backend="web")` → a `WebMap` with `.save()`): a
  self-contained, **zoom-correct** vector map matching openstreetmap-carto. Per-zoom road widths
  (osm-carto width-by-zoom curve) instead of fixed pixels; **two-way directional lanes** via a
  pixel-proportional `line-offset` (`offset_frac`/`width_frac`/`offset_zoom`); direction **arrows**
  and curved **street names** (native symbol layers); **hover/select** via `feature-state`; an
  in-map **base-layer switcher**; class-based **draw order**; and **tunnel/bridge grade
  separation** — one baked `lvl` (from optional `tunnel`/`bridge`/`layer` columns) orders tunnels
  underneath (dashed + faded) and bridges on top (heavier, square-capped casing). The saved HTML
  **bundles MapLibre inline and inlines the data**, so it opens offline from disk with no server.
  Distinct from `save`/`-f rsjs` (the roadstyle.js spec page). See `docs/web-backend.md`.
- Command-line interface: a `roadstyle` console script (`roadstyle.cli`) renders any road file
  from the shell — `roadstyle edges.gpkg -o map.html --theme dark`, with `--include/--exclude`
  filtering, data-driven `--color-by/--cmap/--width-by`, and `-f folium|web|spec|geojson` output.
  Every flag mirrors a `render_edges` keyword. No Python required to make a styled map.
- Interactive selection that **returns the result**: clicking a road in `roadstyle.js` fires
  `onSelect(feature, layer)` (and `onDeselect`) with the edge's GeoJSON feature — geometry +
  properties incl. `__rs_class` — plus a `getSelection()` query method, so a custom page UI can
  react (single-select; click again / the map background to deselect). See `docs/embedding.md`.
- Canonical browser renderer: `static/roadstyle.js` (+ `roadstyle.css`) — one drop-in
  `RoadStyleMap` class (headless core: `load`/`setFilter`/`highlightRoad`/`getRoadClasses`, geometry
  sandwich, hover/selection; plus opt-in legend & road-type filter widgets). `to_html` now **inlines
  this same file** instead of a hand-written copy, so the embedded and standalone renderers can't
  drift (enforced by a test). Shipped as package data.
- Packaging/quality: MIT `LICENSE`, `py.typed` marker, richer `pyproject.toml` metadata
  (classifiers, keywords, URLs), optional extras (`numeric`, `basemaps`), and `ruff`/`mypy` config.
- Data-driven styling: color/size roads by any **categorical** (`color_by`+`colors`) or
  **numeric** (`color_by`+`cmap`+`width_by`) column, with auto legends; both folium & lonboard.
- Stack-agnostic JSON output: `to_spec` (canonical data + baked-in style + legend), `to_geojson`,
  `to_html(full=…)`, `to_iframe`, `save`, `save_spec`/`load_spec` — embed maps in any website
  (Leaflet / MapLibre / iframe; see `docs/embedding.md`).
- Canonical input layer: `RoadEdges` + `normalize_edges`/`load_edges` (normalize-at-boundary).
- Input validation with clear error messages; configurable `StyleConfig`; registries for custom
  palettes/themes/basemaps; palette JSON I/O (`save_palette`/`load_palette`).
- Docs: parameter reference, embedding guide, frontend-integration guide (baked HTML / JSON API /
  JS port), comparison vs `.explore()`/prettymaps, and a runnable example notebook.

### Verified by adoption
- `sweden-road-data` (`nvdb_acquirer.viz.aadt_map`): renders NVDB vehicle edges coloured by AADT
  traffic volume via `render_edges(color_by="aadt", cmap="YlOrRd", width_by=…)` — confirmed on
  927 real Nacka edges (AADT 1–37,828), both folium & lonboard.

### Fixed
- **Internal `lvl` is hidden from web popups/tooltips.** The web backend injects `lvl` (grade-
  separation elevation, -1/0/+1) for draw ordering; like `twoway` it's now skipped in the default
  popup/tooltip (still present in the feature data for z-ordering). Data columns such as `lanes`
  and `edge_ref` keep showing.
- **Large integer ids no longer round in web popups/tooltips.** Property integers past
  `Number.MAX_SAFE_INTEGER` (2^53) — e.g. a content-hash `edge_id` — were inlined as JSON numbers
  and silently rounded by the browser's `JSON.parse` (last digits changed). They're now emitted as
  JSON **strings**, so they display exactly. Display-only: feature ids are MapLibre-generated
  (`generateId`), so styling / filtering / feature-state / `color_options` are unaffected.
- **`tooltip=` now works on the `web` backend.** The shared `tooltip=` argument (and CLI
  `--tooltip`) was silently swallowed by the web backend, which only read its own `road_tooltip` —
  so the default backend produced no hover tooltip. `tooltip=` is now accepted as an alias that
  fills `road_tooltip` when unset, so the same call works across `web` / `folium` / CLI.
- `roadstyle.js` edge selection now works: clicking a road visibly highlights it (the
  glow is sized to cover the edge, so the colour changes even on wide roads), clicking it again
  or clicking the map background deselects it, and a filtered-out edge drops its selection. The
  highlight overlay is non-interactive so repeat clicks reach the road underneath.

### Changed
- Repositioned as an opinionated OSM road-cartography layer that **reuses** mature libraries —
  `branca` (colormaps + legends), `mapclassify` (numeric classification), `xyzservices` (basemaps) —
  instead of reinventing them.

## [0.1.0]

### Added
- Initial release: OSM-theme road/edge styling for folium & lonboard.
- Two palettes (`highsat`, `carto`); three themes (`light`, `dark`, `satellite`).
- Geometry-sandwich rendering; interactive folium layer (dynamic casing, hover highlight,
  road-type filter panel); thumbnail base-layer switcher; neon-violet selection overlay.
