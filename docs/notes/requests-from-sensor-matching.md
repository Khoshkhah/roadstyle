# Requests from sensor-matching (2026-10-21)

The sensor-matching review pages (`~/projects/sensor-matching/viz/matches.py`, `viz/priors.py`)
use roadstyle. Each item below is a gap that those pages work around today. Each item gives the
workaround and its file, so you can see the real use. When roadstyle has an item, tell the
sensor-matching session, and it removes the workaround.

**Status (2026-10-21): done.** roadstyle 0.23.0 has items 1 to 8. sensor-matching uses them
(sensor-matching PR #4) and deleted its workarounds, except item 5: the cameras keep their own
colour. Item 9 is not needed any more, because sensor-matching now uses the PyPI release, not a
source checkout.

## 1. Road widths change at a tile boundary in a tilted (3D) view

**Done** on branch `requests-sensor-matching` (not released): the page uses one tile zoom on the whole screen. Cause: MapLibre bakes a width that depends on zoom and feature per tile for `[tile zoom, +1]` and clamps it; tilted views load near tiles at a higher zoom.

The most visible issue. Fix this one first.

- **What you see:** in a tilted view, a horizontal line crosses the map, and every road changes
  width at that line. The line stays at the same place on the screen while the map moves, so it
  is not in the data.
- **Where:** in a normal browser between zoom 18 and 20, reported by Kaveh with a screenshot. In
  headless Chromium (no GPU), at zoom 17.6 and pitch 72°.
- **Both looks:** `simple=True` and `simple=False` both show it at the same line. So the
  per-feature width expression of the simple look is not the cause.
- **Suspects:**
  - how the line widths are calculated for tiles of different zoom when the map is tilted
  - the enlarged tiles above the GeoJSON source's maximum zoom (`data_maxzoom`)

  A test at zoom 19 with `data_maxzoom=22` did not show the step, but the test at zoom 19
  without it did not show the step either. So that test does not prove anything.
- **To reproduce:**
  - network: `~/projects/sensor-matching/areas/norrmalm/network.parquet` (`geom_wkb` is WKB,
    EPSG:4326)
  - camera: center 18.0508, 59.3336; zoom 17.6 to 19.5; pitch 72°; bearing −25°
  - check with a real GPU, not only headless

## 2. A find box on every page, not only in panel mode

**Done** on `requests-sensor-matching`: `find_control=True`, `rsFind(text)`.

- **Gap:** the "Search roads…" box exists only with `popup_mode="panel"`. A normal page has no
  search, so a host page builds its own.
- **Workaround:** `_findEdge` in `sensor-matching/viz/matches.py` (an edge id or a street name →
  `rsQuery` → `rsSelect` + `rsFocus`).
- **Idea:** `find_control=True`, and a JS function `rsFind(text)` that returns the matching ids.

## 3. A switch to turn off the Layers box

**Done** on `requests-sensor-matching`: `overlay_control=False`.

- **Gap:** `filter_control` exists, but the Layers box (`.ov-ctrl`) has no switch. A page that
  shows its layers in its own legend must hide the box with CSS.
- **Workaround:** `.ov-ctrl{display:none}`, and checkboxes that call `rsSetOverlay`.
- **Idea:** `overlay_control=False`.

## 4. Clickable overlays without a floating popup

**Done** on `requests-sensor-matching`: `Overlay(popup_window=False)`, `overlay_popup=False`.

- **Gap:** `Overlay(popup=[])` makes a layer not clickable. There is no setting for "clickable,
  fire `rs:select`, but show no popup". A page that shows its records in its own panel must
  hide the popup with CSS. Without that, the hover card and the click popup show the same thing
  twice.
- **Workaround:** `.maplibregl-popup:not(.rs-tip){display:none}`.
- **Idea:** `Overlay(..., popup_window=False)`, or `overlay_popup=False` for the whole page.

## 5. An outline for circle overlays

**Done** on `requests-sensor-matching`: `outline` and `width` for circles.

- **Gap:** `Overlay.outline` and `width` work only for polygons. Circles get one global
  `circle_stroke`. The cameras needed a dark ring, so they now use a different color instead.
- **Idea:** `outline` and `width` also for `kind="circle"`.

## 6. Rows for restricted roads in the Roads box

**Done** on `requests-sensor-matching`: `access_col`, `rsSetAccess`, `rsGetAccess`, `RS_ACCESS`. mapstyle can drop its copy later.

- **Gap:** mapstyle (`layers.js`, `ACCESS`) adds the rows "Private roads", "Bus lanes",
  "Pedestrian streets" and "Delivery only" after Bridges and Tunnels, with their colors.
  roadstyle pages that show duckOSM's `private_edges` need the same rows.
- **Workaround:** `_ACCESS_JS` in `viz/matches.py`, copied from mapstyle.
- **Idea:** `access_col="access"` in roadstyle; mapstyle then uses roadstyle's rows.

## 7. A collapsible side panel for host pages

**Done** on `requests-sensor-matching`: `side_panel_html=`, `host_panel_width=`.

- **Gap:** `rsPanelShow` and the » / « handle work only for roadstyle's own docked panel.
- **Workaround:** `sensor-matching/viz/_side.py`. It sets `--rs-side`, adds the handle and keeps
  the open or closed state per page.
- **Idea:** a host-panel option, for example `side_panel_html=` or `host_panel_width=`, that
  uses the same handle and `rsPanelShow`.

## 8. Stored levels for part of a network, read from the DuckDB

**Done** on `requests-sensor-matching`: `render_edges(..., levels_db=path)`.

- **Gap:** `load_area_levels` refuses an edge set that differs from the edges the level area was
  solved for. A page that draws only the driving edges needs mapstyle's
  `stored_levels(only=True)`, string ids, and mapstyle on `PYTHONPATH`.
- **Workaround:** `viz/_levels.py`.
- **Idea:** `render_edges(..., levels_db=path)`. It reads `visualization.edge_levels` for the
  given edges, with int64 or string ids.

## 9. `__version__` is wrong from a source checkout

**Done** in 0.22.2.

- **Gap:** with `PYTHONPATH=~/projects/roadstyle/src`, `roadstyle.__version__` gave `0.17.1`,
  while `pyproject.toml` says `0.22.1`. It reads the metadata of an old installed package.

## Also fixed on `requests-sensor-matching` (not in the list above)

- `rsColorBase(groups)`: colour groups under `rsColor`'s own (duckOSM's level editor wraps `rsColor` today for this).
- An overlay hover that lights every feature with the same number: not reproduced (also in the real level-editor page on Monaco); a test guards it.
