# T4: the Python binding on the public API

Status: plan, 2026-10-25. It starts after the stage-2 API of roadstyle-rs's T4 lands (target_architecture.md, (f)).

This plan changes `rust/roadstyle-py` (the module `roadstyle._rust`) and its Python callers so that each binding entry calls one
facade function. The rules come from target_architecture.md:

- **(g) item 1, pattern 9.** A binding entry converts its arguments (JSON text, an Arrow C stream, bytes), calls one facade function,
  and converts the result. It has no `if` on an option.
- **(e) item 1.** The error variant is the contract. Python maps each facade error kind to a subclass of `ValueError`.
- **(f).** The public API is `style` → `Styled`, `tile` → `Tiled` and `page`, with the readers and the levels.

## 1. The facade calls that the binding uses

These are the names of (f). An item in *italics* does not exist yet; roadstyle-rs's T4 makes it.

| Facade call | What it gives | Exists today as |
|---|---|---|
| `Look::resolve(&Options)`, `Look::from_json`, `look.with_arg` | a resolved look | the same |
| *`style(roads, look, opts, Inputs)`* → `Styled` | stage 1 in memory | `sources_of`, `make_sources` |
| *`Styled::write_style(w, SourceMode)`* | the style text: data inline, file names or tile URLs | `Sources::write_style`, `make_style` |
| *`Styled::write_files(dir, Format)`* | stage 1's files | `save_sources` |
| `write_road_table(styled, fields, w)` | the road table text | the same (lean table, 2026-10-25) |
| *`Styled::restyle(look)`* | a view's palette | `palettes::add` |
| *`tile(TileInput, &TileOptions)`* → `Tiled` | stage 2 | `tiled_of`, `make_tiled`, `tile_files`, `tile_made`, `tile_stage` |
| `Tiled::tile(z, x, y)` | one tile | `Tiles::tile` |
| *`Tiled::write_pmtiles(w)`*, *`Tiled::write_xyz(dir)`* | the archive, the tile folder (every tile, with the empty ones of the bounds) | `Tiles::archive`; the folder walk is in Python |
| *`Tiled::write_style(w)`* | the tiled style | the first item of `tiled_of` |
| *`page(PageInput, look, page, given)`* | the HTML page | `page_from`, `make_page` |
| `levels::levels`, `levels::solve_rules` | the drawing levels | the same |
| `level_area::make_area`, `serve` | the level area, the editor server | the same |
| *`duckosm::plan`*, `duckosm::catalog_sql`, `duckosm::levels_sql` | duckOSM's SQL | in roadstyle-io, wrapped by the binding |
| *`base_map::theme`*, *`base_map::recolor`* | the base-map colours | in the facade, wrapped by the binding |
| `assets::get(name)`, `assets::names()` | the files that Rust owns | the same |

## 2. Each Python entry and what it becomes

"Callers" are the Python package's callers in `src/roadstyle/` (the tests are listed only when they are the only callers).

### Stage 1, stage 2 and the page

| Entry today | Callers | It becomes | The Python code that goes |
|---|---|---|---|
| `resolve_look(options)`, `Look.from_json`, `Look.json`, `Look.with_arg` | `_engine.py`, `duckosm.py` | no change (one facade call each) | none |
| `Look.part(key)` (7 keys, a `match`) | `_engine.py` (`sections`, `other`), `duckosm.py` (`map`, `base_map_page`, `palette`, `settings`, `features`) | one getter for each part: `Look.map()`, `Look.sections()`, `Look.other()`, `Look.base_map_page()`, ... Each returns the JSON text of one typed field, so the binding has no `match` on a key (pattern 9) | the `part("…")` calls take the getter names |
| `make_style(roads, look, features, planner, name)` | `_engine.py` (export_inline), `duckosm.py` | `style(...)` then `Styled.write_style(SourceMode::Inline)`: one entry `Styled.style_text(mode)` on the class below | `make_style` goes |
| `make_sources(...)` → `Sources` | `_engine.py` (export_geojson) | `style(...)` → `Styled` (the class `Sources` takes the name `Styled`) | none |
| `Sources.save(dir, format, keep)` | `_engine.py` | `Styled.write_files(dir, format)`. `format` is parsed by `Format::parse` in the facade, not by the binding's `format()` | the binding's `fn format` goes |
| `Sources.style()`, `Sources.road_table(fields)` | tests only | `Styled.style_text(SourceMode)`, `Styled.road_table(fields)` | none |
| `Sources.metadata()` | tests only | `Styled.metadata()` (a part of `MapFacts`, (b) item 7) | none |
| `Sources.add_palettes(base, looks)` | none | `Styled.restyle(look)` (one view a call) | the entry goes, if no caller comes before T4 |
| `Sources.file_names`, `Sources.file` | none | they go | none |
| `Sources.tile_stage(only, exact, keep, at)`, `Sources.page_arrows()` | tests only (`test_stages.py`, `test_engine_parity.py`) | `tile(TileInput::Styled(&styled), &TileOptions)` → `Tiled`; the page arrows are inside `page` | both entries go; the tests call `tile` and `page` |
| `tile_files(dir, keep, prefix)` → `Tiler` | `_engine.py` (`tile_geojson`) | `tile(TileInput::Files([dir]), &TileOptions)` → `Tiled` | see "Tiled" below |
| `Tiler(roads, look, features, name, prefix, keep)` | `_engine.py` (export with tiles), `duckosm.py` | `style(...)` then `tile(TileInput::Styled)`: one entry `tiled(roads, look, ..., options)` that calls the two in the facade, or two calls from Python (`Styled` then `Styled.tile(options)`) | none |
| `Tiler.tile`, `Tiler.props`, `Tiler.bounds`, `Tiler.layers`, `Tiler.zooms` | `_engine.py`, `duckosm.py` | `Tiled.tile`, `Tiled.props`, `Tiled.bounds`, `Tiled.layers`, `Tiled.zooms` (the class `Tiler` takes the name `Tiled`) | none |
| `Tiler.archive(bounds, layers)` | `_engine.py` (`tile_geojson`, `_pmtiles`) | `Tiled.write_pmtiles(path)` (the bounds and the layers come from the tiles; the facade writes the file) | the bounds and layer arguments in Python |
| (none: a Python loop) | `_engine.py` `tile_geojson` (format "xyz"), `_write_export` | `Tiled.write_xyz(dir)` | the two z/x/y loops of `_engine.py` (about 40 lines) and their `_merc` / `_tile_range` imports. This is (f)'s "`_engine.py` loses its tile walk" |
| `page_from(roads, look, options, given, features)` | `_engine.py` (render), `duckosm.py` | `page(PageInput, look, page, given)`. `page_from` stays as the one-call helper of (f) item 4 | none |
| `make_page(style, page, parts, pmtiles)`, `page_defaults()`, `sidebar_defaults()` | tests only (`test_engine_parity.py`) | they go: the page writer takes `Styled` or `Tiled` (f), and the defaults are the facade's `PageOptions::default()` | the parity test reads the defaults through `page` |
| `export_look(look, cols, positions)` | `export.py` | no change (one facade call) | none |

### The levels, the level area and duckOSM

| Entry today | Callers | It becomes | The Python code that goes |
|---|---|---|---|
| `compute_levels(roads, method, cols, band_col, order, ...)` | `_engine.py`, through `levels.py`, `export.py`, `render_web.py` | no change: it calls `level_edges` (one rule with the engine's `compute_levels`) and `levels::levels` | none |
| `solve_rules(...)` | `_engine.py` | no change | none |
| `make_area(edges, folder, id_col, ...)` (11 keyword arguments) | `level_area.py` | `level_area::make_area(table, &MakeOptions, folder)`, with `MakeOptions` from one JSON text (`MakeOptions::from_json`), so the binding has one argument for the options, not 11 | none |
| `serve(area, port, page)` | `level_area.py` | no change | none |
| `duckosm_catalog_sql`, `duckosm_levels`, `duckosm_subset_levels`, `duckosm_features_select` | `duckosm.py` | no change (one facade call each) | none |
| `duckosm_plan(tables, columns, mode, tags, specs, only, ...)` | `duckosm.py` | `duckosm::plan(&Catalog, &PlanOptions)`: one facade function for the binding, the wasm binding and the CLI (D7). The wasm `duckosmPlan` gives the same keys (today they differ) | none |
| `base_map_theme(theme)`, `base_map_recolor(colour, saturation, lighten)` | `duckosm.py` | no change (one facade call each) | none |
| `asset(name)`, `asset_names()` | `_assets.py` | no change | none |
| `take_warnings()` | `_engine.py` | no change (the binding's warning queue) | none |

## 3. The errors

Today `py_err` gives a `ValueError` for every error and adds the advice "use engine='python'" to an unsupported part. After T4:

| Facade error (also when the engine wraps it) | Python exception (each a subclass of `ValueError`) | A caller does |
|---|---|---|
| `Model` (all kinds, also `MissingColumn`), `Io::Format`, `Io::Data`, `Engine::Column`, `Engine::Data`, `Engine::Limit`, `Tiles::Empty` | `roadstyle.DataError` | skips the input or fixes the data |
| `Look` (all kinds), `Options`, `Io::Options`, `Engine::Options`, `Tiles::Options` | `roadstyle.OptionsError` | fixes the call |
| `Levels` (all kinds), `Io::Levels`, `Edits` | `roadstyle.LevelsError` | fixes the edits or solves again |
| `File`, `Io::Crs`, `Io::Write` | `roadstyle.FileError` | fixes the path or the file |
| `Engine::Unsupported` | `roadstyle.UnsupportedError` (with the binding's advice) | uses another engine or option |

`py_err` is one `match` on the variant, the only `match` in the binding. It is a type conversion, not an option (pattern 9). The
message text stays the facade's. The classes go in `src/roadstyle/errors.py`, and `roadstyle/__init__.py` exports them. The variants
are `#[non_exhaustive]`, so the `match` ends with `_ => ValueError`.

## 4. The order of the work

1. After roadstyle-rs's `style`/`Styled` lands: rename `Sources` to `Styled`, add `Styled.style_text(mode)` and
   `Styled.write_files`, remove `make_style`, `Sources.file_names`, `Sources.file` and the binding's `format()`.
2. After `tile`/`Tiled` lands: `Tiler` becomes `Tiled`, `tile_files` and `Tiler(...)` call `tile`, add `Tiled.write_pmtiles` and
   `Tiled.write_xyz`, remove the two tile walks of `_engine.py`, `Sources.tile_stage` and `Sources.page_arrows`.
3. After `page` lands: remove `make_page`, `page_defaults` and `sidebar_defaults`; `test_engine_parity.py` reads them through `page`.
4. Any time after 1: `Look.part` becomes one getter for each part; `make_area` and `duckosm_plan` take one options text; the error
   classes.
5. Each step: `tests/test_binding.py` checks the binding's texts against the Rust goldens (byte for byte), the cross-language test
   gives the same hash, and pytest runs with each engine.

## 5. The checks of the finished binding

- Every `#[pyfunction]` and `#[pymethods]` body has one facade call and no `if` or `match` on an option (a review item, pattern 9).
- No entry has no caller in `src/roadstyle/` or in the tests.
- `src/roadstyle/_engine.py` has no z/x/y loop and imports no `tiles._merc` or `tiles._tile_range`.
- Each facade error kind gives its Python class (a test with one bad input for each class).
- The Tartu tiled export (`export_style(..., tiles=True)`) has the same files as before, and its peak memory is not above today's.

## 6. Open points for roadstyle-rs

1. `Tiler(roads, look, ...)` in one call: one binding entry `tiled(...)` (the facade composes `style` and `tile`), or two calls from
   Python (`style` then `Styled.tile`)? Pattern 9 allows both. The second gives Python the `Styled` for the page too.
2. `Styled.metadata()`: a part of `MapFacts`, or the saved style's metadata as today?
