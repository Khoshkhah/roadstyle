# One Rust engine for roadstyle

Status: step 1 is done (2026-10-23). The crate is in `rust/`. The Python code of roadstyle did not change.

## Why

Before this step, the style engine had three copies. Python roadstyle is the reference. geolibre-roadstyle has a Rust port in `wasm/` (the GeoLibre plugin and the browser page of duckosm-rust). duckosm-rust has a Rust port of roadstyle's level solver. The copies already differ. For example, the `roads_sql.js` file of duckosm-rust and the file of geolibre-roadstyle differ in 33 lines.

The plan has one Rust crate in this repository with three front-ends: WebAssembly, native Rust and a Python binding. Python roadstyle keeps its API and its folium and lonboard drawing. Later, it calls Rust for the heavy parts.

## What is in the crate

`rust/` is a cargo workspace with two members:

| Member | Type | Content |
|---|---|---|
| `roadstyle-rs` | library and native program | The engine and `src/main.rs` (the native front-end) |
| `roadstyle-wasm` | `cdylib` | The browser front-end: `makeStyle`, `Tiler` and `memoryBytes` through wasm-bindgen, and the `grow` allocator. Natively the crate is empty. |

The modules of `roadstyle-rs`, and where they come from:

| Module | Content | From |
|---|---|---|
| `read` | The roads from GeoParquet (WKB lines), any Parquet table | geolibre-roadstyle `wasm/src/`, commit `eea9f49` (branch `vector-tiles`), then the building heights of `0806ac2` |
| `roads`, `simple`, `slots` | The `roads` source, the casing pieces, the names and arrows | the same |
| `features`, `overlays`, `geom` | The base-map layers, `edge_attach`, WKB, GEOS's area and centroid | the same |
| `layers` | The road tables, the expression builders and the passes on the layer list | the same |
| `planner` | `metadata["roadstyle:planner"]` | the same |
| `tiles` | The vector tiles on request (`Tiles`, `props`) | the same |
| `levels` | roadstyle's `compute_levels`: the tags rule, and the solver (least span first, then a push-relabel min-cost flow) | duckosm-rust `crates/duckosm-core/src/levels/`, commit `60dbede` (branch `browser-b4`) |

The code moved without changes, with two exceptions:

- `levels` has its own input type, `LevelEdge`: `edge_id`, `highway`, `tunnel`, `bridge`, `layer`, `junction` and the line. In duckosm-core, the solver read `Edge` and `Mode`. Now the caller gives each edge a rank (`LevelEdges::add(rank, edge)`), and the edge with the lowest rank wins. duckOSM's ranks are: driving 0, walking 1, cycling 2, then their private edges 3, 4 and 5. Thus the crate does not depend on duckosm-core.
- The `lib.rs` of the engine has no wasm code. The allocator and the wasm-bindgen API are in `roadstyle-wasm`.

The Python binding (maturin and PyO3) will be a third member, `roadstyle-py`. It is not in this step.

## Tests

```bash
cd rust
cargo test --offline
```

| Test | What it compares |
|---|---|
| The unit tests of both ports (11) | The flow, the solver, the input geometry, the tiles |
| `tests/style.rs`, Monaco | The SHA-256 of `make_style` against the style of `0806ac2` from the same inputs, with rule C for the building heights |
| `tests/style.rs`, Tartu (`--ignored`) | The same for Tartu. The inputs are not in git. `tests/get_goldens.sh` gets them, with the large goldens, from the GitHub pre-release `rust-test-data` |
| `tests/levels.rs` | The tags rows and the solve rows of Monaco against duckosm-rust's own `edge_levels_visualization.parquet`, the edge hash and the solve summary |

The reference styles are too large for git (Monaco 26 MB, Tartu 151 MB), so the test keeps only their hashes. To see a difference, make the old style again with `rust/roadstyle-rs/tests/old_style.sh`. It builds `0806ac2` from a geolibre-roadstyle checkout. Then compare the two files.

The test data in `rust/roadstyle-rs/tests/data/`:

| File | Made by |
|---|---|
| `look.json`, `monaco/roads.parquet`, `monaco/features.parquet` | geolibre-roadstyle's fixture (`tools/make_spike_fixture.py`); `look.json` and `features.parquet` from `0806ac2` (`m_per_level` 3.66, the columns `roof_levels`, `min_height`, `min_level`) |
| `tartu/` (from the pre-release, file `tartu-inputs-2.tar`) | The same fixture before `0806ac2`. Its `features.parquet` has the three new columns, but they are empty: the case of a database without these tags |
| `monaco/level_edges.parquet` | The edges and private edges of the three modes from duckosm-rust's test `duckosm-build/tests/levels.rs`, with a `rank` column |
| `monaco/levels_tags.parquet`, `monaco/levels_solve.parquet` | The same duckosm-rust test, as it wrote them (zstd: the tests read zstd, the library does not) |

Result on 2026-10-23: all tests pass, Tartu too. The style of Monaco and the style of Tartu are byte for byte the same as the style of `eea9f49`. After the move, geolibre-roadstyle's `0806ac2` changed the building heights in its copy. The crate has that change too, and its style is byte for byte the same as the style of `0806ac2`. Then Kaveh chose rule C for the building height: the higher of the `height` tag and (`building:levels` + `roof:levels`) x `m_per_level`. In Tartu the `height` tag is often an ETAK code (0 to 9), and levels first makes the buildings of Monaco lower than OpenFreeMap's. With rule C, the style differs from the style of `0806ac2` only in the `height` of 15 buildings of Monaco and 355 of Tartu, and the test has the hashes of the new style. The levels are the same rows as duckosm-rust's.

## Step 3: less memory (2026-10-23)

Kaveh chose to do this step before step 2, because the limit of 100,000 roads stops larger areas, for example Stockholm county. The work is on the branch `rust-memory`. The style and the tiles did not change: the SHA-256 tests of the style and of the tiles (`tests/style.rs`, Monaco and Tartu) give the same hashes as before the step.

Two changes:

1. **The source `roads` takes the roads.** Before, it made a copy of the properties of each road. Now `make_parts` makes it last, after all stages that read the roads, and the properties move into it.
2. **Typed sources `roads` and `simple`** (module `props`). `Props` keeps the properties as a list, with one copy of each key name for the whole program. It has the methods of serde_json's `Map`, so the stages did not change much. A `Feat` keeps its line as numbers, not as JSON arrays. `Source::write_json` writes the same text as the JSON tree, and a unit test compares the two. The layers read typed and JSON properties through the trait `Get`. The base map and the slots stay JSON.

The peak memory, natively (`/usr/bin/time`, the peak resident memory):

| Area | Output | Before | After |
|---|---|---|---|
| Tartu (63,965 roads) | Style | 2.13 GB | 1.13 GB |
| Tartu | Tiles (`make_tiled`) | 2.13 GB | 1.01 GB |
| Monaco (13,298 roads) | Style | 387 MB | 196 MB |

It is also faster: Tartu's style 5.8 s to 5.1 s, Monaco's style 1.1 s to 0.7 s.

`MAX_ROADS` is now 200,000, not 100,000. This number is an estimate, not a measurement. In the earlier measurements, the WebAssembly module used 0.65 to 0.77 times the native peak. Thus Tartu needs about 14 KB for each road, and 200,000 roads need about 2.8 GB of the 4 GB that a browser gives. Before the limit goes higher, measure a larger area in a browser.

What is left: each text value in the properties (colors, classes) is its own string. A value type with one copy of each text would cut more, but the layers read `serde_json::Value`, so that change is larger.

## Data-driven colour and width (2026-10-23)

The engine reads the colour options of `render_edges` from `look["args"]`: `color_by`, `colors`, `cmap`, `vmin`, `vmax`, `width_by`, `color_table` with `color_key`, `color_options`, `color_active` and `legend`. The module `colors` ports roadstyle's `stylers.py` (the class, categorical, numeric and colour-table stylers, `bake_props`, `bake_color_options`, `build_styler`), the `color_table` step of `render_edges` and the colouring of `render_web.render`.

| Part | In the engine |
|---|---|
| Ramps (`cmap`) | branca's `LinearColormap`: the same lookup (an exact branca name, then the first name in order that is the same without case or starts with `<name>_`, then matplotlib at 9 stops) and the same arithmetic (`int(u * 255.9999)` for each channel). The schemes, the matplotlib stops and the colour names are data, `src/cmaps.json` (branca 0.8.2, matplotlib 3.10.9) |
| Values given by the caller | Keep their JSON form, as in Python: `vmin: 1` stays an integer in the legend, a computed one is a float |
| Missing values | A missing categorical value is the key `"nan"`, as pandas 3 gives it (a text column holds NaN) |
| The layers | The fill expression of each colour option and the state `rs_co` (the active option) |
| The legend data | `metadata["roadstyle:color_options"]`: the page's `COLOR_OPTIONS`, a list of `{name, prop, legend}`. Only when the map has data colours. Python's `export_inline` does not write it; its page has it in the HTML |

Not in the engine: `style=` (a Styler object of Python), and an option with another palette than the look's (the look has the class styles of one palette). Both stop with an error message.

**Check.** `tests/colors.rs` compares the engine's style with Python's `export_inline` for 1,373 roads of Monaco (Monte Carlo) and seven cases: no options, a numeric `color_by` with `cmap`, `vmin` and `vmax`, `width_by`, a categorical `color_by`, a `color_table`, three `color_options` with `color_active` and `missing="self"`, and `legend=False`. Below the top level, all must be the same, key order included; the legend data must equal the page's `COLOR_OPTIONS`. `tests/make_goldens.py` makes the goldens and `cmaps.json` (in the conda environment `roadstyle`).

**A change in the bytes of the style.** The first case found one difference that the spike's compare script did not see, because it ignored the key order: Python writes `__rs_cls` before `__rs_arw` in the slots. The engine now does the same. The Monaco and Tartu styles are the same data as before, with other bytes, so their hashes in `tests/style.rs` changed.

## The look in Rust (2026-10-23)

Before, Python made the look (`look.json`: the resolved palette, profile, settings and render keywords) for the engine. The module `look` makes it now: `make_look(options)`, in the browser `makeLook(options)`. `options` holds render_edges' `palette` (default `amber`), `profile`, `settings` (a mapping or a list of them), `args` (the other keywords) and `features` (mapstyle's base-map part, as given).

It ports:

- the `pick` of `render_edges`: a profile, and a bundled palette, other than the default, is a settings source after `settings`;
- `_settings.theme()`: the profile and the palette merged, the road classes of every palette at the profile's widths, the settings in the older layout (`_old_style_keys`: `palettes`, `config`, `selection`, `roads`), and `active`;
- `_settings.style()` and `StyleConfig` (its fields in order, as `dataclasses.asdict` writes them), and `_settings.roads()`;
- the class styles (`RoadStyle.from_dict`, then `style._apply`, plain and as a link), the slots' tables (the draw order, each class's width at zoom 20, with the engine's own width curve), the arrow image and the popup fields, as geolibre-roadstyle's `look_of` adds them.

The data is roadstyle's own: the crate reads `src/roadstyle/data/` (the profiles, the palettes, `defaults.json`, `sprite.png`) when it is built, so there is one copy of it. The settings are given; the engine does not read `roadstyle.json` files or `$ROADSTYLE_CONFIG`, because the browser has none.

**Check.** `tests/look.rs`: the look of the fixture's palette, settings and args (with its `features` given) is `tests/data/look.json`, byte for byte; and the ten looks of `tests/make_looks.py` (each built-in profile x palette, a settings source in the older layout with its own palette, and one in the newer layout) are equal to Python's, key order included.

**Not in the engine: mapstyle's part of the look.** mapstyle turns its mode, theme and paths into the palette name, the settings and the args, and makes `features` (layers.yaml, the 3D buildings, the theme's feature style, the textures and icons as data URLs) from its own data in the mapstyle repository. geolibre-roadstyle's `build.py` still makes that part with mapstyle. A port of it is a separate decision: it needs mapstyle's data in this repository or a mapstyle crate.

## What Python roadstyle can do and the crate cannot yet (2026-10-23)

The crate makes the style of `export_inline` for simple mode with stored levels (with mapstyle's base map, the planner data, the names and arrows), its vector tiles, the colours of data (`color_by`, `color_table`, `color_options`, legend), the look from `palette`, `profile` and `settings`, and the levels (`compute_levels`, tags and solve). This list is what is left, by the Python function or option. "Fixed" means the crate has one value where Python has an option.

**Keywords of `render_edges` / `render_web.render` that change the style**

- [x] Column names (`ColumnMap`, 2026-10-23), `filter_col` and `cap_col`. Before, fixed in the crate: `highway_col` (highway), `filter_col`, `tunnel_col`, `bridge_col`, `layer_col`, `edge_id_col` (edge_id), `cap_col` / `cap_start_col` / `cap_end_col`, `casing_level_col`, `fill_level_col`, `casing_start_col`, `casing_end_col`, `head_start_m_col`, `head_end_m_col`, `directed_col` (is_directed), `driving_col` (has_arrows).
- [x] `access_col`: the access colours (`__rs_access`, the theme's `access`; 2026-10-23).
- [x] No stored levels: `render` computes them (`compute_levels(method="solve")`), and so does the engine (`roadstyle-engine`, `compute_levels`; the same style on the parity fixture). Only `head_m=5`.
- [x] `head_m`, `road_fill`, `offset_zoom`, `offset_frac`, `width_frac` (2026-10-23).
- [x] Metre widths: `width_m_col`, `width_m_zoom`, `casing_m`, `casing_min_px` (`_mark_width_m`, `_width_m_expr`, the roads' part of `_mitre_ends`; 2026-10-23).
- [x] `simple=False`: the full look (`full.rs`, 2026-10-23): the layer set of casings and fills for each position, the end caps, the dashed
  classes, the bridge look and its shadows, and the road-wide end caps of `twin_casing: "each"` (`_twin_ends`).
- [x] `arrows`, `labels`, `minzoom` (true or a table; 2026-10-23).
- [x] `view_3d`: the 3D bridge decks (`decks.rs`, 2026-10-23). The engine makes the ribbons with its own mitre offsets, not GEOS: the same properties, the same shapes to the rounding (1e-6 deg).
- [x] `items`: edge items and lanes (`__rs_k` 5, `__rs_ic`, the items' mitre ends; 2026-10-23). `items_popup` is a page keyword. A MultiLineString item is an error in the engine.
- [x] `overlays=`: the caller's own `Overlay` layers (`_build_overlays`, `overlays.py`; every kind, a style of the settings, on edges, in metres as items; 2026-10-23).
- [x] `boundary` (the dashed outline), `hover_color`, `select_color` (2026-10-23).
- [x] `data_maxzoom`, `data_tolerance`, `pitch`, `bearing`, `max_pitch` (2026-10-23).
- [x] `road_popup`, `popup_mode`, `road_tooltip`, `tooltip`, `hover_delay_ms` (2026-10-23).
- [x] `views`: named presets of colour option, palette and filters (`_check_views`, `_merge_palettes`; 2026-10-23, the page of `render_edges`).
- [ ] `style=`: a Python `Styler` object (an error in the crate); a colour option with another palette than the look's.
- [x] `tiles=True`: the page's PMTiles archive with the sidecar table (2026-10-23: the Python binding writes the archive of the crate's `Tiler`
  tiles with the `pmtiles` package). A PMTiles writer in the crate (for the browser) is P6.

**Keywords of the HTML page, not of the style** (the dashboard JS module of task 2): `filter_control`, `find_control`, `overlay_control`, `overlay_popup`, `side_panel_html`, `host_panel_width`, `basemap_switcher`, `basemap`, `basemaps`, `api_key`, `zoom_readout`, `street_view`, `street_view_key`, `google_3d`, `tunnel_control`, `compress`.

**Public functions**

- [ ] Backends: `render_edges(backend="folium")` (`render_folium.py`), `backend="lonboard"` (`render_lonboard.py`).
- [x] `export_style`: the tile folder and one PMTiles file (`engine="rust"`, 2026-10-23).
- [ ] `export_look`: the simple look for another app's data layer.
- [ ] Pages: `render_dashboard`, `render_report`, `sidebar_html`, `make_legend`, `to_html`, `to_iframe`, `save`, `render_street_view`, `snapshot` (a PNG through a browser).
- [ ] Specs: `to_spec`, `save_spec`, `load_spec`.
- [ ] Input: `load_edges`, `from_duckdb`, `from_arrow`, `from_geojson`, `as_edges`, `normalize_edges`, `filter_edges` (`include`, `exclude`, `match_links`), `highway_types`, `is_directed`. The crate reads GeoParquet with fixed column names only.
- [ ] Levels: the level areas and their editor (`save_area_levels`, `load_area_levels`, `restore_area_inputs`, `level_area.py`, `level_editor.py`), and the stored levels in a duckOSM file (`load_levels`, `save_levels`, `levels_store.py`). The crate has `compute_levels` with `level_input`, `solve_levels` and `auto_ends` inside it.
- [ ] Palettes and settings (the engine reads own profile and palette files and settings files through the binding, 2026-10-23): `register_palette`, `save_palette`, `load_palette`, `palette_to_dict`, `palette_from_dict` (the crate takes a palette only through `settings`); `use_settings` with a file path (the crate takes mappings).
- [ ] Base maps: `BASEMAPS`, `get_basemap`, `register_basemap`, `get_api_key`, `set_api_key`.
- [ ] The other tools: `cli.py`, `mcp_server.py`, the studio (`ui/studio`).
- [ ] mapstyle's half of the look (mode, theme and paths; `features`): its own task after the plan, with Kaveh's OK.

## Step 2: the tiles follow `tiles.py` (2026-10-23)

`make_tiled` and `Tiles` (module `tiles`) now use the rules of roadstyle's `tiles.py`:

| Rule | Before | Now |
|---|---|---|
| Sources | One vector source for each style source | One vector source `roads`. Each old source is a layer in its tiles, and each style layer has that name as its `source-layer` |
| Name and arrow slots | Clipped to the tile | Whole in each tile that they touch, from the first zoom of their layers (14) |
| Zooms and buffer | Zoom 0 to 16, buffer 512 units | `look["config"]["tiles"]`: zoom 6 to 15, buffer 80 units. The look must have these values, else `make_tiled` stops with an error |
| Lines below the last zoom | All points | Simplified to half a tile unit (Douglas-Peucker). A line shorter than half a unit is not in the tile |

The browser API did not change. A page asks for `tile("roads", z, x, y)` and gets all layers in one tile. `props("roads", id)` gives the properties of a road. Polygons are clipped and not simplified, as before. `tiles.py` does not simplify polygons either.

The simplification has no topology check. GEOS's `simplify` (with `preserve_topology`) also keeps a line from crossing itself.

Sizes and times natively (`main.rs --tiles`, the tiles around the center):

| Area, zoom | Before | Now |
|---|---|---|
| Monaco, 12 | 2.8 MB, 575 ms a tile | 2.7 MB, 222 ms a tile |
| Tartu, 12 | 26.4 MB | 16.8 MB |
| Tartu, 14 | 26.5 MB | 18.1 MB |
| Tartu, last zoom (16 before, 15 now) | 29.0 MB in 1,008 tiles | 18.8 MB in 313 tiles |

## Next steps

1. geolibre-roadstyle and duckosm-rust use the crate at a fixed commit and delete their copies. The duckosm-rust session does this step.
2. The tiles follow `tiles.py`: done (see above). duckosm-rust's page must show the map again with the new tiles.
3. Typed pieces in place of JSON trees, to use less memory: done (see above).
4. The Python binding. Then Python roadstyle calls Rust part by part, and its golden tests check each part.
