# Changing the look without making the tiles again

Date: 2026-11-04. Status: proposal, version 3, not built. Versions 1 and 2 are in the history of this file. The section "Review history" at the end
says what changed and why.

## Summary

A host page (the duckOSM page) changes the look of a map that is already drawn: a theme, a colour, a width. Today it must make the whole map
again. On Burnaby (64,221 roads) a theme change takes 7 s in a browser on a normal PC, and 5.7 s of it is the engine.

roadstyle's architecture is the standard one, and it stays: the tiles hold the pieces of the roads and their facts, and the MapLibre style draws them.
Three things in the current design stop a fast theme change:

1. **Some look values go into the tiles by their value, not by their role.** The main case is the colour table: a piece holds the place of its colour
   in a table of the distinct colours, and a theme changes the places. A theme change then changes the tiles.
2. **No API takes a new look.** `LiveTiles` must be made again, and that reads and prepares the roads again.
3. **The style is made together with the pieces.** A new style costs about 700 ms of work that a new look does not need.

This design changes those three things. It does not change the pieces, the levels, the slots, the geometry in the tiles, or the static styles of
the Python and CLI paths.

## The problem, measured

| What | Where | Time |
|---|---|---|
| A theme change in the duckOSM page, Burnaby | Brave, a normal PC | 7.0 s, of which the engine 5.7 s |
| The same | headless Chromium, a fast server | 4.4 s, of which the engine 2.3 s |
| `style_sources` (stage 1) | native, Burnaby | 1.0 to 1.5 s |
| `LiveTiles::new` (the tile index) | native, Burnaby | 1.4 to 1.5 s |
| `restyle` (stage 1 from prepared roads) | native, Burnaby | 0.65 to 1.2 s |

The parts of stage 1 (native, Burnaby, with temporary timers):

| Part | Time | Needed for a new look? |
|---|---|---|
| `mark_roads`: each road's drawing values | 180 to 250 ms | no |
| the slots (arrows and names) | 220 to 270 ms | no |
| the base-map overlays: the data (`feature_tables`, `edge_attach`) | 186 ms | no |
| `simple_source`: the pieces | 44 to 72 ms | no |
| `road_layers`: the layers | 41 to 53 ms | yes |
| the dark colours and the contract | 38 to 44 ms | yes |
| the metadata | 0 to 8 ms | yes |

So a new look needs about 100 ms of the about 800 ms.

## What a tile holds today

A piece of a road in a tile holds **facts** (the class place `__rs_ci`, the grade, the direction, bridge and tunnel, the access kind
`__rs_access`, the metre widths) and, in some cases, **values of the look**. The values of the look in a tile are the problem:

| Value of the look in a tile | Code | When | Effect of a theme change |
|---|---|---|---|
| The place of a fill and a casing colour in a table of distinct colours (`ColourTable`) | `colors.rs`: `Colours::add` numbers each new value in the order of first use; `put_places` | the look has a colour option, a `color_by` or a `color_table`. **The duckOSM page has a colour option ("Road class").** | When the theme makes other colours equal or unequal, the places change, and every tile changes. |
| The access colour, written into each road's fill | `roads.rs` (`look.access`) | `access_col` is set. **The duckOSM page sets it.** | The tile keeps the old colour as text, or as a place. |
| The dash, as a place in the sorted list of all the patterns | `layers/build.rs` (`dash_patterns`) | a class or an item has a dash | A new pattern changes the places of the others. |
| No casing piece for a dashed class | `simple/source.rs` | as above | A theme that gives a class a dash, or takes it away, changes the pieces. This is structure (see D1). |
| The colour of the items | `overlays.rs` (`sections.overlays.color`) | the map has items | The tile keeps the old colour. |

With the class-only path (no colour option, no access column), the colours are already by role: the style has a lookup from the class to its colour
(`class_table` in `layers/build.rs`), and a palette change gives the same tile bytes. We measured this on Burnaby for 4 palettes (`compare_tiles.rs`).
That test passed only because those 4 palettes have the same pattern of equal colours, and it used the class-only colours. It is not evidence for the
duckOSM page.

Other values decide the tiles in a way that is correct and stays (structure): the first zoom of a class, the first zoom of the arrows and the names, the
bridge wing, the order of the classes, the slot look, the base-map layer list, the popup and tooltip fields (they decide the properties that a tile
keeps), and the buffer of each zoom (D2).

## Who uses the tiles

roadstyle's tiles are made in two places, and this design reaches them differently. Read from the call sites on 2026-11-04.

| Consumer | Where the tiles are made | Live data | What this design gives it |
|---|---|---|---|
| The duckOSM page (`duckosm-rust`, `crates/duckosm-wasm/www/map/map_worker.js`) | in the browser, by `LiveMap` (`LiveTiles`) in a worker | not yet | Phase 1: the same tiles for every theme. Phases 3 to 5: a theme change with no new tiles; the live colours (feature state) stay, because the source stays. |
| SonoFlow's daily page (`viz/daily.py`: `rs.render_dashboard(..., live_data=True, tiles=True)`) | in Python, when the page is built; the tiles are in the page file | yes: `rs.setData` writes `rs_c` and `rs_w` as feature state | Phase 1, after a release and a new build of the page: the tiles hold no class or access colour (this page has neither an access kind nor a colour option, so its tiles are probably the same bytes; not checked). `set_look` does not reach it: its tiles are fixed in the file. A page that offers several palettes (`palettes.rs`, the state `rs_palette`) no longer needs a colour copy for each palette in every piece. |
| `export_style`, `roadstyle tiles` (the CLI) | in Rust, once | no | Phase 1 only. |

The live colours (`roadstyle:live`, `rs.setData`) are the first part of the road colour expression (`["coalesce", ["feature-state", "rs_c"], ...]`), and this design does not change that part.

## The design

### D1. A tile holds facts. A colour reaches a piece by its role.

A **role** is what a piece is, made only of facts that the tile already has: the class place, the colour option, the access kind, the piece kind
(fill, casing, shadow, tunnel gap or dash), bridge or tunnel. The style holds the table from a role to a colour. A theme changes the table in the
style, and no tile byte.

1. **Class colours with a colour option.** A colour option that colours by class (the duckOSM page's "Road class") reads the colour from the class
   lookup of the style (`class_table`), as the class-only path does today. The piece holds no colour place.
2. **The access colour.** The style draws a piece with an access kind in the palette's colour of that kind, before the class lookup:
   `["match", ["get", "__rs_access"], "private", <colour>, ..., <class lookup>]`. The bake stops writing the access colour into the fill.
3. **The dash.** The dash pattern of a class comes from the style, by the class place. Whether a class has a dash at all stays structure, because it
   decides if the class has casing pieces.
4. **The colour of the items.** The style reads it from the look. A piece of an item keeps its own colour only when the item gives one (data).
5. **Data colours stay data.** A colour from the user's data (`color_by` on a column, `color_table`) is a fact of the data. It stays as it is now (a
   place in a table), and its colour mode is part of the key (D2), so a change of it makes new tiles.

The test of D1 (D5, part 1): the tiles are the same bytes for every theme and profile of the duckOSM Design panel, and for custom colours that make two
classes the same colour, with the page's own options (`access_col`, the colour option).

**The size of a tile.** A piece holds fewer properties than today (no fill and casing place for a class-coloured option). The style has one more
`match` for the access kinds. Phase 1 measures both against the tile size standard (`docs/design/tile_contract.md` on its branch) on Burnaby.

### D2. The key is derived, not listed

`set_look(look)` decides if the held tiles are still right in two steps. Both must pass.

1. **The part that comes from the style.** Make the new layers and style (D4). Make `TileOptions` from them, as `LiveTiles` does today (this is
   cheap). The held tiles are right only if the new options equal the held options (`read`, `source_reads`, the popups, the codes, `slots_from`,
   `base`, the zooms), and if **each new buffer is not larger than the held buffer** of its zoom. The buffer comes from the stroke widths of the layers
   (`buffer::buffers_px`), so a look with wider roads can need new tiles; a look with narrower roads can keep them. `TileOptions` gets `PartialEq`.
2. **The part that comes from stage 1.** A hash of the stage-1 inputs that are not in the style: the order of `model.classes`; the slot look (with the
   class width at zoom 20, `width_z20`, which places the names) and the deck look; `head_m`, `bridge_shadow`, `single_line`, `twin_casing`,
   `casing.m`; `base_map.layers_yaml`; the overlays, the items, the columns and the levels; the colour mode and the data colours; which classes have a
   dash.

We do not keep a hand-written list of every look value: the review showed that such a list cannot be complete.

**How part 2 is made (phase 3).** The key is a hash of the whole saved look (`Look::to_json`) with only its colours left out, and not in the sections
that hold the user's data colours (`map`, `data`, `overlays`): there a colour can be a place in the colour table of the pieces. Every other value
counts: a width, a dash, a zoom, a palette name. So a change of anything but a colour gives a new map. That costs time, never a wrong map. A value
that is known to be appearance only can leave the key later, with the guard test (D5) as its proof.

### D3. `LiveTiles::set_look(look)` and the frozen state

`set_look` returns `Restyled { tiles_kept: bool }`. When the key of D2 passes, it replaces the style text and nothing else. The rule:

> `set_look` never changes anything that `fill()` or `tile()` reads: `styled`, `options`, the class colours of the pieces and the piece table stay
> as they are.

`LiveTiles` makes the properties of a piece when a tile is first seen (`fill`). With the frozen state, a tile that is made after `set_look` equals a
tile that was made before it. After D1, the pieces hold no colour of the look, so the new style shows the new colours on old and new tiles alike.

When the key fails, `set_look` changes nothing and returns `tiles_kept: false`. The host makes a new `LiveTiles`, as today. The wasm class `LiveMap` gets
`setLook(look, format)`. It returns the new style and `tilesKept`.

### D4. A path that makes the layers and not the pieces

The layers, the dark colours, the contract and the metadata, from the new look, with no pieces, no slots and no per-road bake. The parts that it needs
cost about 100 ms on Burnaby (see the measured table). Three things make it harder than one call:

- `road_layers` reads some marks of the roads (the dash classes, `any_dup` from `single_line`, the controls). The path keeps the road marks from
  stage 1 and runs only the class frame of `colors::bake` for the new look.
- `Overlay` holds the data of a base-map layer and its styling together, and `style.rs` moves it into the sources. `feature_overlays` is split into the
  facts of each layer (name, kind, kinds, attached to the edges), which `Styled` keeps, and the styling from the look (`look.sections.base_map.style`).
  This touches `overlays.rs`, `contract.rs` and `layers/*`.
- After D1, the class colours of the pieces do not depend on the look, so no colour must be compared with the old look's.

The target: **less than 250 ms natively on Burnaby** for `set_look` when the key passes, and the style text equal to the style of a new `LiveTiles` of
the new look.

### D5. The tests

1. **The tiles are facts (D1).** For the duckOSM page's look, its options on, and every theme and profile of the Design panel, plus custom colours that
   make two classes equal: every tile of Monaco at zooms 12 to 18, and the tiles around the centre of Burnaby at zooms 6 to 16, are the same bytes. This
   test runs before `set_look` exists.
2. **`set_look` is exact (D2, D3).** If `set_look` says `tiles_kept`, every tile equals the tile of a new `LiveTiles` of the new look: the tiles made
   before `set_look`, the tiles first made after it, and the tiles made again after the cache drops them. The looks are the themes and profiles, and
   random changes of the look values with the options on that act only when on (`access_col`, `decks_3d`, items, `width_m`, tunnels, dashes). When
   `set_look` says `tiles_kept: false`, the test needs no comparison. A wrong `tiles_kept: true` fails the test. A refusal that was not needed does not
   fail it: it costs time, not a wrong map.
3. **The style is exact.** For each theme, the style of `set_look` equals the style of a new `LiveTiles`.
4. **The browser (D6).** In the page, a theme change sends no new tile request, removes no source, and the map shows the new colours.

### D6. The host contract

The host keeps its source ids and its tile addresses (`prefix`). Today the duckOSM page makes a new prefix (`rs://<generation>/`) for each draw, so
MapLibre requests every tile again. With `tilesKept`, the page keeps the prefix and gives the new style to MapLibre with `setStyle(style, { diff: true })`.
Phase 4 checks in a browser:

- MapLibre keeps a source only when its object is equal, so the style's `sources` must not change.
- The images (`roadstyle:images`) and the controls are in the style's metadata, which the diff does not apply. The host adds the images again and reads
  the controls again.
- The global-state defaults (`state`) must be diffable in the pinned MapLibre. If not, the host sets them with `setGlobalStateProperty`.
- A change of layout or filter makes MapLibre's worker parse the held tiles again, with no new request.
- **The live colours stay.** MapLibre keeps the feature state of a source while the source stays, so the colours and widths that `rs.setData`,
  `rsColor` and `rsColorBase` wrote (`rs_c`, `rs_w`) stay after a theme change, and the host does not write them again. The browser test sets live
  colours, changes the theme, and checks that the roads keep them.

The light and dark switch (`rs_theme`, `dark_theme.md`) already needs no new style. This design is for every other change of the look.

## Phases

| Phase | Work | Done when |
|---|---|---|
| 0 | Measure the parts of stage 1. **Done.** | The table above. |
| 1 | D1: colours by role (the class-coloured option, the access colour). **Done 2026-11-04** for the fill and the casing; the dash pattern and the item colour are not changed (see below). | D5 part 1 passes; the tile size on Burnaby is not larger than today; the page draws as before. |
| 2 | D4: the layers-only path and the split of `feature_overlays`. **Done 2026-11-04.** | Its style equals the style of a new `LiveTiles` for every theme; less than 250 ms natively on Burnaby. |
| 3 | D2 and D3: the derived key, `PartialEq` for `TileOptions`, the stage-1 hash, `set_look`. **Done 2026-11-04.** | D5 parts 2 and 3 pass. |
| 4 | The wasm `setLook`, the documentation (`docs/rust/browser.md`), the browser test of D6. **Done 2026-11-04.** | D5 part 4 passes. |
| 5 | The duckOSM page: the Design panel calls `setLook` and keeps its prefix; the old path only when `tilesKept` is false. | A theme change on Burnaby takes less than 1 s in the browser. |
| 6 | The dashboard and `palettes.rs` can use `set_look` and stop making every palette at the start. Optional. | A separate document. |

Phase 1 alone does not make a theme change faster: the page still makes a new worker and a new prefix. It is the condition for phases 3 to 5.

## Phase 1 result (2026-11-04)

- A piece holds no role colour. `Draw::role` marks, for each road, the colour slots whose fill is a role colour (the class's, or the access
  kind's); the casing is a role colour when it comes from the class styles. `ColourTable` holds only data colours.
- The road layer gives a role colour by `__rs_access` (a `match` on the palette's access colours) and by `__rs_ci` (the class lookup). With no data
  colours, the layer reads no colour of a piece at all, and its expression is shorter than before (the tile budget passes).
- Tests: `tile_roles.rs` (the same tile bytes for 4 bundled palettes, a palette with two classes in one colour, and a palette with other access
  colours, with and without the duckOSM page's options); `tile_colour.rs` (each role colour equals the colour of its road in the road table, also
  for private roads at zoom 15; the colour places of data colours as before; a view's palettes switch the class casing by `rs_palette`).
- Not changed: the dash pattern stays a place in the sorted list of patterns, and a dashed class has no casing (structure). The colour of the items
  stays as it is. Neither changes with a palette today (the dashes are in the profile, not in a palette), so they belong to the stage-1 key (D2).

## Phase 2 result (2026-11-04)

- `roadstyle_engine::restyle_layers(styled, look)` makes the look half of a style (the layers, the dark colours, the contract, the state, the glyphs,
  the metadata, the boundary) from a held stage 1. `style_parts` and `restyle_layers` share one function (`look_half`), so they cannot drift.
- Stage 1 keeps `LookInputs`: the colour bake's result (`Baked`) and the facts of each base-map layer (`LayerFacts`: its name, kinds, heights,
  whether it is on the streets, and the (fill number, order) groups of a layer on the streets). `feature_overlays` is split into the facts and the
  styling (`styled_layers`).
- Two look values were read from data and now come from the look: the legend's swatch of a class (a role colour: `colors::role_fill`) and place 0 of
  a colour table (the fallback colour).
- `LiveTiles::style_for(look)` gives the tiled style of another look; it changes nothing that the map holds. `tiled_style_of` is the style part of
  `tile_stage`.
- Tests (`tests/restyle.rs`, Monaco with its base map and the duckOSM page's options): the same look, every colour changed (two ways), the base map's
  colours, and all class fills in one colour each give the style of a new map, byte for byte; the held map does not change.
- Time on Burnaby (`examples/time_style_for.rs`, every colour changed): `style_for` 89 to 112 ms, a new map 2.8 to 4.3 s; the same style.
- Found: every bundled base-map theme other than `liberty` makes other tiles than `liberty` (it sets the first zoom of the base-map layers and the
  roads' dash patterns too). A change of the base-map theme is structure; a change of colours is not. The key of phase 3 must tell them apart.

## Phase 3 result (2026-11-04)

- `LiveTiles::set_look(look)` keeps the tiles when both parts of the key pass: `stage1_key` (the look's JSON with its colours left out, except in
  `map`, `data` and `overlays`) is the same, and `TileOptions::keeps_tiles` (the same rules, no larger buffer). Then it takes the new style and
  look and changes nothing that `tile` reads (D3); else it changes nothing and answers false.
- The guard test (`tests/set_look.rs`, Monaco with its base map and the duckOSM page's options): a theme-like change of colours keeps the tiles, and
  every tile (made before and after the change) and the style are the new map's; a change of the data colours and a change of the classes' first
  zoom make a new map; 40 random changes of one to three look values: 6 kept the tiles (each checked tile by tile), 34 needed a new map.
- Time on Burnaby (`examples/time_style_for.rs`): `set_look` that keeps the tiles 79 to 111 ms; a refusal 3 ms; a new map 2.3 s.
- Not done: the guard test does not drop the tile cache between the checks; the key is careful on purpose (a width, an opacity, a dash or a
  palette name gives a new map). Values can leave the key later, each with the guard test as its proof.

## Phase 4 result (2026-11-04)

- The wasm `LiveMap.setLook(look, format?)` gives the new style when the map keeps its tiles, and `undefined` when the look needs a new map.
  `docs/rust/browser.md`, "Change the look of a live map", shows the host's code.
- The browser test (`tests/test_set_look_browser.py`, Playwright, the web package of `build_editor.sh`, Monaco's part with the page's options): 20
  roads get a live colour (`rs_c`), a theme-like colour change goes through `setLook` and `setStyle(style, {diff: true})`. The map requests 0 tiles
  again, keeps its one source, keeps all 20 live colours, has the new class colours in its road layer and gives no error; a change of structure
  gives `undefined`.
- Found on the way: a style with no name has `"name": null`, and MapLibre's style check refuses it (the map does not load). The duckOSM page gives a
  name; the docs say so. Not changed here.

## Risks

- **A stale map.** The worst failure, because it looks right. The guards are D1 (no look in a tile), D2 (a derived key), D3 (a frozen state) and D5 part 2
  (all tiles, random changes).
- **The size of a tile and of the style.** Phase 1 changes what a tile holds. It must meet the size standard and its CI budget.
- **The tunnel and bridge colours.** The tunnels have their own palettes (`tunnels.palette`). Phase 1 must find whether their colours reach the pieces,
  and give them roles if they do.
- **The base map.** The split of `Overlay` (D4) is the largest single change.
- **The pinned roadstyle.** The duckOSM page pins a roadstyle commit (`ROADSTYLE_COMMIT` in `crates/duckosm-wasm/build.sh`). Each phase that the page uses
  needs a pushed commit and a new pin. The Design session of the page uses the same pin.

## Open questions

1. Does the dashboard need the colour option "Road class" on the duckOSM page at all? If not, the page can use the class-only path at once. This does
   not remove the need for D1 (the access colour, the dash, other hosts).
2. `set_look` with a failed key returns `tiles_kept: false` and changes nothing. A later phase can rebuild by itself from the held roads.
3. The level editor holds a `LiveTiles` (`relevel`). Does it call `set_look` when the theme changes? The proposal is yes, after phase 3.
4. How wide may a road be before the held buffer is too small? A later phase can raise the buffer in advance, at a cost in tile size.

## Review history

- **Version 1** said that a look's appearance never reaches the tiles, with a hand-written list of structure values. An independent review (Opus,
  2026-11-04) rejected it: the dash, the access colours, the item colour and the popup fields are in the tiles; the buffer comes from the widths (our
  width test did not show it, because those widths fall back to a fixed buffer); the tiles are made late from the held state; and a hand-written list
  cannot be complete. We checked each point in the code.
- **Version 2** answered the review: a derived key, a frozen state, a guard test in one direction, and two small moves (the access colour and the dash).
- **Version 3** found the main case that version 2 missed: with a colour option (the duckOSM page has one), every piece holds the place of its colour in
  a table of distinct colours, numbered in the order of first use. D1 now makes all class colours reach a piece by its role, which covers the colour
  option, the access colour, the dash and the item colour in one rule.
