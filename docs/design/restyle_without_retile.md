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
| the first zoom of the arrows (`arrows.minzoom`) | different at zoom 14 |
| the wing of a bridge (`bridges.wing_scale`) | different at zooms 9 to 16 |

So a look has two kinds of values. **Structure** changes the pieces or the content of a tile. **Appearance** changes only how the style draws
them. Only the structure needs new tiles.

## The design

### D1. The tiles hold structure only

This is a rule, and a test keeps it (D5). A value of appearance (a colour, a width, an opacity, a dash) is never in a tile, except a colour
that comes from the user's data (`color_by`, `color_table`, `color_options`). That colour is data, and a new data colour needs new tiles.

### D2. A list of the structure values: `Look::tile_key()`

One list in `roadstyle-look` names every value of a look that changes a tile. `Look::tile_key()` is a hash of those values, in a fixed
order. Two looks with the same key make the same tiles for the same roads.

We start the list with what the test above shows (the first zoom of a class, the arrows' first zoom, the bridges), the `tiles` section
(zoom range, extent, buffer), the columns and the levels of `map`, and the data colouring of `map.color`. The guard of D5 finds every value that
is missing from the list, and every value that is on it for no reason.

We do not find the key by comparing outputs. That needs both builds, and the build is the cost that we want to avoid.

### D3. `LiveTiles::set_look(look)`

`set_look` takes a new look. It returns `Restyled { tiles_kept: bool }`.

1. If `look.tile_key()` is the key of the look that made the tiles, `set_look` makes the new layers and the new style, keeps the tile cache
   and the index, and returns `tiles_kept: true`. The tile addresses and the source ids do not change.
2. If the key is not the same, `set_look` changes nothing and returns `tiles_kept: false`. The host makes a new `LiveTiles` as today.
   (A later phase can do this step from the roads that `LiveTiles` already holds, with no read of the file.)

The wasm class `LiveMap` gets `setLook(look, format)`. It returns the new style and `tilesKept`.

### D4. A path that makes the layers and not the pieces

`restyle` (`roadstyle-engine`) takes 0.8 to 1.2 s on Burnaby, nearly as long as stage 1 (1.0 to 1.5 s), because it makes the pieces again. D3
needs a function that makes only the layers and the style from the look and from the facts of the roads that the layers read. Examples of the
facts are the classes that exist, a tunnel or a bridge exists, the names of the columns, the base-map features. Stage 1 keeps them in
`Styled` once.

The base-map layers (land, water, buildings) have colours from the look too, and `restyle` has no base map. The new path must make them from the
features that `Styled` already holds.

### D5. A test that guards the list

The test `tile_key_guard` uses a small area (a Monaco file in `rust/roadstyle/tests/data`) and has two parts.

1. **The list is right.** For each value of the default look (read from the look's own JSON), change the value, and make the tiles at
   some zooms. The tiles change if and only if the value is on the list of D2. A value that changes tiles and is not on the list fails the
   test, and so does a value on the list that changes no tile.
2. **`set_look` is exact.** For each palette and each profile in `data/`, `LiveTiles(A).set_look(B)` gives the same style text as
   `LiveTiles(B)`, and the same tile bytes, when the keys are the same.

A stale map is the worst failure of this design, because it looks right and is wrong. Part 1 and part 2 stop it.

### D6. The host contract

The host keeps its source ids and tile addresses (`prefix`). When `tilesKept` is true, the host gives the new style to MapLibre as a
change of paint and layout, and the tiles that MapLibre holds stay. The host does not start a new worker.

## Phases

| Phase | Work | Done when |
|---|---|---|
| 0 | A spike for D4: the layers and the style from a new look, with no pieces. | On Burnaby it takes less than 100 ms natively, and its style text equals the style of a new `LiveTiles`. If it cannot, this design stops and we look at the cause. |
| 1 | `tile_key`, `set_look`, the guard test. | The two parts of D5 pass for all the palettes. |
| 2 | The wasm `setLook`, the documentation (`docs/rust/browser.md`), the Python binding if it is wanted. | A test in the browser sets a look and the style changes with no new tile request. |
| 3 | The duckOSM page: the Design panel calls `setLook` and uses the old path only when `tilesKept` is false. | A theme change on Burnaby takes less than 1 s in the browser. |
| 4 | The dashboard theme switch and `palettes.rs` can use `set_look` and stop making every palette at the start. Optional. | The decision is a separate document. |

## Risks

- **A wrong key.** A value of structure that is not on the list gives a stale map. D5 part 1 is the guard.
- **The base map.** The layers of the base map come from a YAML file and the features. If they read per-feature data in a way that I did not
  see, phase 0 shows it.
- **The data colour.** A look with `color_by` has colours in the pieces (`__rs_fill` and the places in `ColourTable`). Its key includes the
  data colouring, so a change of the data colouring makes new tiles. This is correct.
- **The Python and CLI paths** write static styles. They do not use `LiveTiles`, and they are not changed.

## Open questions

1. Should `set_look` with a changed key rebuild by itself in phase 1, or only return `tiles_kept: false`? The proposal is to return only.
2. The level editor holds a `LiveTiles` too (`relevel`). Does it call `set_look` when the theme changes? The proposal is yes, after phase 1.
3. The start of the list (D2) comes from a test on Burnaby with a few looks. The first run of the guard in phase 1 completes it.
