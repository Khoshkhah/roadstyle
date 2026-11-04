# Changing the look without making the tiles again

Date: 2026-11-04. Status: proposal, not built. A host page changes the look of a map that is already drawn (a theme, a colour, a width).
Today the host must make the whole map again. On Burnaby (64,221 roads) this takes 2.3 s in the engine on a fast computer and 5.7 s on a
slower one, and the tiles that come out are the same bytes as before.

## The problem

`LiveTiles::new` takes stage 1 (`style_sources`), which has the pieces of the roads, and makes the tile index and the style. There is no
method that takes a new look. A host that wants a new look must read the roads again, run stage 1 again, and build the index again. The
host (the duckOSM page) starts a new worker for each theme change.

## What is already true

The tiles hold the pieces of the roads and the class index of each piece (`__rs_ci`). The colours of a class are in the style (`class_only`
in `colors.rs`; `docs/design/dark_theme.md` says "no new tile: the tiles have the pieces, not their colours").

We tested this on Burnaby (`rust/roadstyle/examples/compare_tiles.rs`): stage 1 and `LiveTiles` for the default look and for a changed
look, and the tiles around the centre at zooms 6, 9, 11, 13, 14, 15 and 16 (9 tiles for each zoom), compared byte by byte.

| Change in the look | Tiles |
|---|---|
| palette `carto`, `highsat`, `mono`, `amber` | all the same |
| the width of each class at each zoom (`roads.width`), `roads.width_zoom_rate`, `roads.casing_ratio` | all the same |
| the width of the links (`roads.links.width`), the end cap (`roads.cap`) | all the same |
| the width and the casing width of the palette, the opacity of the casing (`casing.opacity`), `tunnels.opacity_scale` | all the same |
| the first zoom of each class (`roads.classes.<class>.minzoom`) | different at zooms 6 to 15 |
| the first zoom of the arrows (`arrows.minzoom`) | different at zoom 13 |
| the wing of a bridge (`bridges.wing_scale`) | different at zooms 9 to 16 |

So a look has two kinds of values. **Structure** changes the pieces or the content of a tile. **Appearance** changes only how the style draws
them. Only the structure needs new tiles.

## Review of version 1 (2026-11-04)

An independent review of version 1 found three blockers. We checked each one in the code. Version 2 below answers them.

1. **Some values that version 1 called appearance are in the tiles.**
   - The dash. A dashed class has no casing pieces (`simple/source.rs`, "a dashed class has no casing"). In a tile, `__rs_dash` is a place in the sorted
     list of all the dash patterns of the map (`dash_patterns` in `layers/build.rs`). A new pattern changes the places of the others.
   - The access colours. With `access_col`, `look.access` is written into each road's fill (`roads.rs`). A piece keeps a fill that differs from the class colour
     (`simple/source.rs`), so an old palette's colour stays in the tile.
   - The colour of the items (`sections.overlays.color`), and the popup and tooltip fields, which decide the properties that a tile keeps.
2. **The widths are structure for the tile buffer.** `TileOptions::new` takes the buffer of each zoom from the stroke widths of the style's layers
   (`buffer::buffers_px`). Wider roads need a larger buffer, or the strokes are cut at the tile edges. Our width test showed equal tiles because a width
   that the function cannot bound gets the fallback buffer, so that test was not evidence. The widths also decide the names' room at zoom 20
   (`slots/place.rs`).
3. **The tiles are made late.** `LiveTiles` makes the properties of a piece when a tile is first seen (`fill`), from the held stage-1 data and the held
   `TileOptions`. If `set_look` changed those, a tile that is made after it would carry the new rules over old pieces.

The review also showed that a hand-written list of structure values (D2 of version 1) cannot be complete, and that a guard test which changes one
value at a time cannot find it.

## The design (version 2)

### D1. Tiles hold facts. Each look value has one of three homes.

1. **In the style only.** A colour, an opacity, a width, a blur, a label size, the dark colours. A new look changes the style and nothing else.
2. **In the tile, as a fact.** The class place (`__rs_ci`), the access kind (`__rs_access`), the grade, the direction, the bridge and tunnel flags,
   the metre widths. The style turns a fact into a look.
3. **In the tile, as the result of a rule of the look** (structure): the first zoom of a class, the dash of a class, the order of the classes, the
   metre widths, the bridge wing, the slots' look, the base-map layer list, the colour mode.

The work of this design includes **moving values from home 3 to home 2** where that is cheap and clean. Two cases are known:

- The access colour. A piece keeps `__rs_access` (a fact, already a mark), and the style maps the kind to the palette's colour. The bake stops writing
  the colour into the fill.
- The dash. A piece keeps a number that names its class's dash role, not a place in a sorted list of patterns, and the style holds the patterns.

What stays in home 3 is the key (D2).

### D2. The key is derived, not listed

`set_look(look)` decides if the held tiles are still right in two steps:

1. **The style-derived part.** Make the new layers and style. Make `TileOptions` from them (it is cheap). The held tiles are right only if the new
   options equal the held options (`read`, `source_reads`, the popups, the codes, `slots_from`, `base`, the zooms), and **each new buffer is not
   larger than the held buffer** of its zoom. `TileOptions` gets `PartialEq` for this. A look with narrower roads keeps the tiles. A look with wider
   roads than the buffer allows does not.
2. **The stage-1 part.** A hash of the stage-1 inputs that are not in the style: the order of `model.classes`; the slot look and the deck look;
   `head_m`, `bridge_shadow`, `single_line`, `twin_casing`, `casing.m`; `base_map.layers_yaml`; the overlays, the items, the columns, the levels; the
   colour mode; the dash of each class; the access colours while they are home 3. The held tiles are right only if the hash is the same.

Both steps must pass. If one fails, `set_look` changes nothing and returns `tiles_kept: false`.

### D3. `LiveTiles::set_look(look)` and the frozen state

`set_look` returns `Restyled { tiles_kept: bool }`. When `tiles_kept` is true, it replaces the style text **only**. The rule is:

> `set_look` never changes anything that `fill()` or `tile()` reads: `styled`, `options`, the class colours and the piece table stay as they are.

So a tile that is made after `set_look` equals a tile that was made before it, and the style turns the same facts into the new look. The wasm class
`LiveMap` gets `setLook(look, format)`. It returns the new style and `tilesKept`.

### D4. A path that makes the layers and not the pieces

As in version 1: the layers, the dark colours, the contract and the metadata from the new look, with no pieces, no slots and no per-road bake.
Version 1 left out three things that make it harder:

- `road_layers` reads per-road marks (the dash list, `any_dup` from `single_line`, the controls). The cheapest correct way is to keep the road marks
  from stage 1 and run only the class frame of `colors::bake` for the new look.
- `Overlay` holds the data and the styling together, and `style.rs` moves it into the sources. The split of `feature_overlays` touches
  `overlays.rs`, `contract.rs` and `layers/*`.
- The class colours that the pieces were stripped with (`simple.class_colours`) stay from the old look (D3). The new style does not read them from the
  pieces, so the pieces that kept an explicit fill still show the old colour. This is why the access colour moves to home 2.

### D5. The guard test: one direction, all tiles

The rule that the test guards is: **if `set_look` says `tiles_kept`, then every tile equals the tile of a new `LiveTiles` of the new look**. The test:

1. Makes `LiveTiles(A)` and makes **some tiles**, then calls `set_look(B)`.
2. Compares every tile of the area at every zoom: the tiles made before `set_look`, the tiles first made after it, and the tiles made again after the
   cache dropped them. The reference is `LiveTiles(B)`. When `set_look` says `tiles_kept: false`, the test needs no comparison.
3. Uses the palettes and profiles in `data/`, **and** random changes of the look values, with the options turned on that act only when on (`access_col`,
   `decks_3d`, items, `width_m`, tunnels, dashes). A change that `set_look` accepts and that changes a tile fails the test.
4. Does not test the other direction ("a value that changes no tile must be accepted"). A value that is refused for no reason costs time, not a wrong map.

The oracle of `palettes.rs` (`merge` fails when two palettes make other features) is used to check the options.

### D6. The host contract

The host keeps its source ids and tile addresses (`prefix`). With `tilesKept`, it gives the new style to MapLibre with `setStyle(style, { diff: true })`. We
check these in phase 2, in a browser test:

- MapLibre keeps a source only when its object is deep-equal, so the style's `sources` must not change. The test fails when a source is removed.
- The images (`roadstyle:images`) and the controls are in the style's metadata, which the diff does not apply. The host adds the images again and reads the
  controls again.
- The global-state defaults (`state`) must be diffable in the pinned MapLibre. If not, the host sets them with `setGlobalStateProperty`.
- A change of layout or filter makes the worker parse the held tiles again, with no new request. The test counts the tile requests.

The light and dark switch (`rs_theme`, `dark_theme.md`) already needs no new style. This design is for every other change of the look: the Design panel
of the duckOSM page, a custom colour, a profile.

## Phase 0 result (2026-11-04)

We timed the parts of `style_parts` (the stage that makes the layers and the pieces) on Burnaby, natively, with temporary timers:

| Part | Time | Needed for a new look? |
|---|---|---|
| `mark_roads`: each road's drawing values | 180 to 250 ms | no, for a look with class colours only (`class_only`) |
| the slots (arrows and names) | 220 to 270 ms | no, the slots do not depend on the colours |
| the base-map overlays (`feature_tables`, `edge_attach`) | 186 ms | the data part: no. The styling part: yes, and it is small |
| `simple_source`: the pieces | 44 to 72 ms | no |
| `road_layers`: the layers | 41 to 53 ms | yes |
| the dark colours and the contract (`dark::layers`, `contract`) | 38 to 44 ms | yes |
| the metadata | 0 to 8 ms | yes |

The parts that a new look needs (layers, dark colours, contract, metadata) cost about 100 ms. The parts that it does not need cost about 700 ms. A full
`restyle` costs 650 to 1,200 ms, because it makes all of them again.

What phase 0 did **not** show: a working layers-only function with a style that equals the style of a new `LiveTiles`. The inputs of `road_layers` must be
rebuilt without the data. This needs three changes, which are the work of phase 1:

1. `Styled` keeps the facts of each base-map overlay (its name, kind, kinds and whether it is attached to the edges). `feature_overlays` is split in two: the
   facts, which depend on the data, and the styling, which depends on the look (`look.sections.base_map.style`).
2. The class colours (`ClassColours::of`) are made again from the new look, and the `simple` source keeps its pieces.
3. A look with data colours (`ColourTable`, `color_by`) has no layers-only path: its key includes the data colouring (D2).

So the target of phase 0 changes. The first target (less than 100 ms) is the cost of the parts that are certain, with no margin. The new target for phase 1
is **less than 250 ms natively on Burnaby**, which is about 3 to 5 times less than the 650 to 1,200 ms of today, and the style text must equal the style of a new
`LiveTiles` for every palette.

## Phases (version 2)

| Phase | Work | Done when |
|---|---|---|
| 0 | A measurement for D4: the time of each part of `style_parts`. Done (see above). | The parts that a new look needs cost about 100 ms. |
| 1a | Move the access colour to home 2 (the style maps `__rs_access` to the colour), with the byte test that the tiles of a look with no `access_col` do not change. | The tiles with `access_col` do not carry a palette colour. |
| 1b | Move the dash to a role number (home 2), the same test. | A new dash pattern does not change the other patterns' tiles. |
| 1c | The split of `feature_overlays`, the layers-only path (D4), `PartialEq` for `TileOptions`, the stage-1 hash (D2), `set_look` (D3), the guard test (D5). | Less than 250 ms natively on Burnaby, and the guard test passes for all the palettes and for the random changes. |
| 2 | The wasm `setLook`, the documentation (`docs/rust/browser.md`), the browser test of D6, the Python binding if it is wanted. | The test sets a look, the style changes, and no source is removed and no tile is requested again. |
| 3 | The duckOSM page: the Design panel calls `setLook` and uses the old path only when `tilesKept` is false. | A theme change on Burnaby takes less than 1 s in the browser. |
| 4 | The dashboard theme switch and `palettes.rs` can use `set_look` and stop making every palette at the start. Optional. | The decision is a separate document. |

## Risks

- **A stale map.** The worst failure, because it looks right. D2 (derived key), D3 (frozen state) and D5 (all tiles, random changes) are the guards. A
  value that `set_look` accepts by mistake is a bug that the random test must be able to find.
- **A larger change than the first design.** Phases 1a and 1b change what a tile holds, so they change the tile contract (the size standard and the CI
  budget, `docs/design/tile_contract.md` on its branch). Each one needs the byte test and a check of the tile size on Burnaby.
- **The base map.** The layers of the base map come from a YAML file and the features. The split of `Overlay` (D4) is the largest single change.
- **The data colour.** A look with `color_by` has colours in the pieces. Its colour mode is in the stage-1 hash, so a change of it gives
  `tiles_kept: false`. This is correct.
- **The Python and CLI paths** write static styles. They do not use `LiveTiles`, and they are not changed.

## Open questions

1. Phases 1a and 1b move values into home 2. Are they in scope, or do we accept `tiles_kept: false` when a dash or an access colour changes? The
   proposal is to do them: they are what makes the tiles a set of facts, and they are small.
2. `set_look` with a changed key returns `tiles_kept: false` and changes nothing. A later phase can rebuild by itself from the held roads.
3. The level editor holds a `LiveTiles` (`relevel`). Does it call `set_look` when the theme changes? The proposal is yes, after phase 1c.
4. How wide may a road be before the buffer of the held tiles is too small? D2 refuses the new look, and the host builds the tiles again. A later
   phase can raise the buffer in advance (a larger tile for every zoom has a cost: the tile size standard).
