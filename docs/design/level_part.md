# The level-edit part

**Status:** a design, 2026-11-08. Not built. It needs a sign-off before the code.

## What and why

A host page (duckOSM Studio, the page of `roadstyle levels edit`) must have the level editor with **one call** and a small **data adapter**. The host must not write code for the editor itself. A new version of roadstyle must give a better editor with **no change in the host**: the host only moves its roadstyle version.

Today `levelEditor(...)` is only the panel and the solver. Studio has about 180 lines of glue around it: the area, the store, the busy veil, the open and the close, the limit for many roads, the notes, the redraw, and the write into DuckDB. This design moves all of this glue into roadstyle. Only the code that reads or writes the host's own data stays in the host.

## The part

One function in `dashboard/editor/level_part.js`:

```js
const part = levelEditPart({dashboard: rs, map, data, card: {...}, ...options});   // gives an EventTarget
```

It does all of this by itself:

- **The card.** It adds a card with `rs.sections.add` that opens the editor (a card that opens something, like Ask). The card has a line of status (`note`): how many roads, how long the open took, "Changed: ← Steps applies the new drawing order", the number of rules, heads and line ends after an Apply, and the text about files that the browser could not keep (`lostBytes`).
- **The store.** `browserStore` with `memoryFallback`, one for each area name.
- **The area.** `ensureArea`: it makes the area only when the edge hash changed, and makes it again once when the browser lost the files.
- **The open.** It asks `data.roadsStyle()` and draws the page's roads when they are not on the map, shows the dashboard busy veil (`rs.mapBusy`), takes off the page's selection and popups, and starts the engine in the background before the first open (`prepareEditor`).
- **The limit.** `maxRoads` (default: the limit of the engine, 200 000). A larger area gives a clear note in the card, and the editor does not open.
- **The redraw.** After each change it calls `data.relevel(rows)`, reloads the tiles of the changed roads and waits for `idle`. If the answer has a style, it swaps the style with `roadLayers`.
- **The layout.** The editor frame hides the host's steps and shows them again. The part sets `document.body.dataset.rsEditing = "levels"` while it is open and gives the map its padding back at the close. A host can style by this attribute.
- **The close.** "← Steps" with changes waiting asks *Apply*, *Discard* or *Stay* (the editor's own bar). After an Apply, the part calls `data.saveLevels(files)` and draws the roads again only when the host asks for it.

## The adapter (the host's data)

An object with **five async functions**. All of them read or write the host's data and nothing else.

| Function | Gives or does |
|---|---|
| `edges()` | the roads of the area as GeoParquet bytes (Studio: a DuckDB SQL query). |
| `storedLevels()` | `{csv, edge_hash}` of the levels in the host's tables, or `null`. |
| `saveLevels(files)` | writes `levels.csv`, `edits.csv`, `heads.csv`, `caps.csv` (texts) into the host's tables. |
| `relevel(rows)` | draws the changed edges again in the host's map worker; gives `{style?, counts}`. |
| `roadsStyle()` | the style of the page's roads (Studio: its map worker). |

Optional: `roadCount()` (for `maxRoads`), `after(style)` (Studio: its overview layers and the boundary), `useStyle(style)` (only a host that swaps the style itself).

The page of `roadstyle levels edit` uses the **same part**. Its adapter reads `roads.parquet` and the CSV files with `fetch` and writes with `PUT`: `httpData(base)`. It has no code of its own either.

## Events

`open`, `close`, `applied` (`{files}`), `error` (`{message, fatal}`), and `dirty` as a property. A host uses `applied` to refresh its own steps, and `close` to refresh its layout.

## What the host keeps (Studio)

The adapter (five functions, about 25 lines of DuckDB-wasm calls) and one call (`levelEditPart({dashboard: rs, map, data, card: {id: "level", label: "Edit levels"}, maxRoads: window.mapMaxRoads})`, about 3 lines). **At most 30 lines.** Studio keeps no store, no area, no veil, no limit text, no note, no layout code and no listener for the worker.

## The rules for a host contract

1. **Compatible.** Each new option has a default. A change that breaks a host needs a CHANGELOG line under *Host changes* and the migration text in the same PR.
2. **A Studio-shaped test host.** The browser tests use a host like Studio: vector-tile sources that many overlays share (`rs-roads`, `rs-low`), a data adapter, and an area restored from the browser storage. The tests cover the part, the design panel and `roadLayers`. A real DuckDB-wasm test runs only when the network is there; the fake adapter uses the engine's own `makeArea` and `relevel`.
3. **Each PR says what the host must do.** For example: "Studio: only move the pin".

## The PRs

| PR | What | Status |
|---|---|---|
| a | `browserStore` `memoryFallback`, `lostBytes()` | merged |
| b | editor `error` event, `dirty`, `exportFiles()`, deselect at the open | built, in review |
| c | `ensureArea` and the stale-area retry | next |
| d | `roadLayers` (show, remove, reload tiles) | next |
| e | `levelEditPart` and `httpData`; Studio and `roadstyle levels edit` use it | last |

## Which test covers which behaviour

| Behaviour that leaves the host | Test (roadstyle) |
|---|---|
| store in memory, the lost-bytes note | `test_level_editor_page.py` (a), the note in `test_level_part_browser.py` (e) |
| worker stopped, `error` | `test_level_editor_page.py` (b) |
| area made once, made again after a loss | `test_level_editor_page.py` (c) |
| deselect and popups at the open | `test_level_editor_page.py` (b) |
| style swap, images, tile reload | `test_design_panel_browser.py`, `test_design_edit_browser.py`, `test_level_part_browser.py` (d) |
| the limit `maxRoads`, the note | `test_level_part_browser.py` (e) |
| the card, the status line, the layout attribute | `test_level_part_browser.py` (e) |
| `applied`, `saveLevels(files)`, `relevel` calls | `test_level_part_browser.py` (e), with the Studio-shaped host |
| the same part in the page of `roadstyle levels edit` | `test_levels_edit_browser.py` (e) |

## Not decided

- The name of the part (`levelEditPart` is the working name).
- Whether `roadsStyle()` is needed in a host that always has its roads on the map when the card opens.
