# The design-edit part

**Status:** a design, 2026-11-08. Not built. It needs a sign-off before the code. It follows [the level-edit part](level_part.md).

## What and why

The design panel (`designPanel`) is the editor of the map's style. A host page (duckOSM Studio) must have it with **one call** and a small **data adapter**, as it has the level editor. The host must not write code for the card, the layout, the restore, the save or the redraw. A new roadstyle version must give a better design editor with **no change in the host**: the host only moves its roadstyle version.

Today Studio has about 80 lines around `designPanel`: the call, the card with its note, `closeDesign`, `designSaved`, the restore, `setDesignLook`, `redrawDesign`, and the link to the Export card. Only the reads and writes of the host's own data and the Tiles tab are the host's.

## The part

One function in `dashboard/design/design_part.js`:

```js
const part = designEditPart({dashboard: rs, map, data, roads, card: {id: "design", label: "Edit design"}, link: {label: "Export →", card: "export"},
                             tabs: [tilesTab], boundary, storageKey});   // gives an EventTarget
```

It does all of this by itself:

- **The card** (`rs.sections.add`, a card that opens something). Its line of state: the name of the design, ` (changed)` when the style differs from the base design, and the summary lines of the host tabs.
- **The layout.** `open()` and `close()`; "← Steps" closes the panel, gives the map its size and padding back, and sets `document.body.dataset.rsEditing = "design"` while it is open.
- **The restore.** At the start it asks `data.loadDesign()` and loads the text with `panel.load(text, {draw: false})`, before the first draw of the host.
- **The save.** After each change, and after 800 ms of quiet, it calls `data.saveDesign(text)`. A failed save is a warning, not an error.
- **The redraw.** `setLook(text)` and `redraw(text, draw)` go to the adapter. When the host cannot redraw now (the level editor is open, the map is not drawn), the adapter gives a reason and the part shows it in the panel. The part makes `restyle: {also, imagePrefix}` from `roads` (the `roadLayers` of the host), so the host does not repeat them.
- **The link.** `link: {label, card}` shows the button in the panel's bar. A click closes the panel, opens the card `card` and scrolls to it.
- **The events.** `change` (`{design, text, edited}`), `close`. `part.edited`, `part.panel` (the `designPanel`: `get`, `setHost`, `text`, `base`).

## The adapter

An object with five functions. All of them are the host's own data or worker.

| Function | Gives or does |
|---|---|
| `loadDesign()` | the saved design text of the area, or `null` |
| `saveDesign(text)` | keeps the design text with the area |
| `look()` | the look of the map as an object (the page's own look) |
| `setLook(text)` | the host's map worker shows the look on the same tiles; gives a style, or `undefined` when new tiles are necessary |
| `redraw(text, draw)` | remembers the look text; with `draw`, draws the map again (new tiles) and gives a note |

Optional: `redrawReason()`, a text when the host cannot redraw now.

## The host tab (the one hook)

A host tab is `{id, name, key, make, normalize, draw, keep, summary}`. `summary(value)` is new: it gives the text that the card line shows after the name (Studio: `Tile profile: Analysis.`). The panel already keeps the value of the tab in the design (`design.profile`). The value is not part of "(changed)".

## What stays in Studio

- **The Tiles tab** and the tile profile: `app/profile.js` (the limits, `EDGE_COLUMNS`, `CLASS_FROM`, the presets, `normalizeProfile`), `drawTiles` and its event handlers (about 40 lines), and everything in `export.js` that reads the profile (`profile()`, `patchProfile`, `profileZooms`, `fullMaxZoom`, the tile count, the zoom row of the Export card, the link "Edit the tile profile" that opens the tab). This is Studio's feature: **only Studio makes tile files** of the layer `edges` of duckOSM. It is not glue.
- The adapter: `loadDesign`/`saveDesign` (`areaStore`), `setLook`/`redraw` (the map worker and the draw), `look` (`duck.pageLookText`).
- `boundary` (the host paints its own boundary).

**Lines in Studio: at most 25** (the adapter about 12, the call about 6, the wiring of the Tiles tab about 5). The Tiles tab and the profile are counted apart: they are Studio's own feature.

## Could the Tiles tab be a general roadstyle tab?

Only a small part. What roadstyle itself has for tiles is the format (`tile_format`: `mlt` or `mvt`) and the tile zoom range of the page. A general tab **Tiles** with these two values could be in the design editor of roadstyle (`roadstyle design edit` makes tiles in a worker too). The rest of Studio's profile is not general: the layer `edges` and its columns, the zoom where each class starts, the limit of tiles and the extent are for the files that duckOSM Studio exports. So: a later, optional step (the tab **Tiles** with the format and the range in roadstyle), and Studio keeps its own tab for the profile. This does not change the part.

## The rules for a host contract

1. **Compatible.** Each new option has a default. A change that breaks a host needs a CHANGELOG line under *Host changes* and the migration text in the same PR.
2. **A Studio-shaped test host.** The browser test uses a host like Studio: the roads as vector tiles with the prefix and an overview source (`rs-roads`, `rs-low`), an adapter with its own storage, a design restored from the storage, and a host tab with `summary`.
3. **Each PR says what the host must do.** For this part: "Studio: only move the pin, then replace its call and its `designSaved`, `closeDesign` and restore code with `designEditPart`".

## The PRs

| PR | What |
|---|---|
| g | `roadLayers` gives `prefix` and `also` (the part reads them); `designPanel` takes `summary` in a host tab |
| h | `designEditPart`, its docs and its test with a Studio-shaped host |

## Which test covers which behaviour

| Behaviour that leaves the host | Test (roadstyle) |
|---|---|
| the card, its line, "(changed)", the summary of a host tab | `test_design_part_browser.py` (h) |
| the restore before the first draw | `test_design_part_browser.py` (h) |
| the save after 800 ms of quiet, a failed save | `test_design_part_browser.py` (h) |
| the layout: open, "← Steps", the attribute, the map size | `test_design_part_browser.py` (h) |
| `setLook` and `redraw`, the reason of the host | `test_design_part_browser.py` (h) |
| the link to another card | `test_design_part_browser.py` (h) |
| `restyle` from `roadLayers` | `test_design_part_browser.py` (h), `test_road_layers_browser.py` (g) |
