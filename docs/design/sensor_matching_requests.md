# Requests from sensor-matching (items 1–8)

**Status:** written 2026-10-20, before the code. Source: `docs/notes/requests-from-sensor-matching.md`
(a local note in the roadstyle folder; the item numbers are the note's).

Each item is a `render_edges` keyword or an `Overlay` field. Each has a test in
`tests/test_requests_browser.py` (a headless browser) or `tests/test_render_web.py` (the page text).

## 1. Road widths step in a tilted view (a fix, no new API)

MapLibre 5 loads the near tiles of a tilted view at a higher zoom than the far tiles. A width that
depends on the zoom and on the feature (every road width here) is baked per tile for the zooms
`[tile zoom, tile zoom + 1]` and clamped outside them. So the roads changed width where two tile
zooms met. The page now sets `calculateTileZoom = z => z` on every non-raster source: one tile zoom
on the whole screen, and the bake is exact. Cost: a tilted view loads more tiles (121 at pitch 72
against 21 in the test map). Test: all tiles of `roads` have one zoom at pitch 72.

## 2. `find_control` and `rsFind(text)`

- `rsFind(text)` is always defined. It returns the ids (as `rsQuery` does) of the roads that match
  the text. The match is the one of the docked panel's search box: a part of a value of the popup
  fields, of the id fields, or a column name.
- `find_control=True` adds a "Search roads…" box to the top-left stack. A click on a result calls
  `rsSelect` and `rsFocus`. The docked panel (`popup_mode="panel"`) keeps its own box and uses the
  same code. Default `False`.

## 3. `overlay_control=False`

Hides the Layers box (and, in panel mode, the overlay rows in the Roads box). `rsSetOverlay` still
works. Default `True`.

## 4. `Overlay(popup_window=False)` and `overlay_popup=False`

The overlay stays clickable: it is highlighted, and `rs:select` fires with its fields. The floating
popup (and, in panel mode, the docked read-out) does not show. `overlay_popup=False` is the same for
every overlay of the page. The hover tooltip does not change. Default `True`.

## 5. `outline` and `width` for circle overlays

`Overlay(kind="circle", outline=..., width=...)` sets the circle's ring colour and ring width in px.
Without them the ring is the `circle_stroke` setting, 1 px, as before.

## 6. `access_col`

`render_edges(..., access_col="access")`: the column holds `private`, `bus`, `pedestrian`,
`delivery` or nothing. For each of these values that occurs:

- the road fill has the colour of the value: `#c8c8c8`, `#9db8d9`, `#dddde8`, `#e8d2b0`. The colour
  is under `rsColor` and over the "colour by" option (the rule of mapstyle's `layers.js`);
- the Roads box has a row after Bridges and Tunnels: "Private roads", "Bus lanes", "Pedestrian
  streets", "Delivery only". A row switches the edges of its value on and off, together with the
  class, bridge, tunnel and `rsFilter` switches;
- `rsSetAccess(kind, on)`, `rsGetAccess()` and `RS_ACCESS` (kind → count) are defined;
- the class row `pedestrian` goes away when every road of that class has `access="pedestrian"`.

Python bakes `__rs_access` on every piece, as it does `__rs_cls`. mapstyle can use these rows
later and drop its copy.

## 7. `side_panel_html` and `host_panel_width`

`render_edges(..., side_panel_html="<div id=mp>…</div>", host_panel_width=360)`. The page puts the
HTML in a full-height panel on the right, with the same » handle in its header, the same « button
on the map and the same `rsPanelShow(on)` as the docked panel. `--rs-side` follows the panel, so
the controls and windows that are anchored on the right move with it. The open or closed state is
kept per page in `localStorage`. It is an error to use it with `popup_mode="panel"`.

## 8. `levels_db`

`render_edges(..., levels_db="area.duckdb")` reads `visualization.edge_levels` of that file for the
given edges (`load_area_levels(subset=True)`). The ids of the edges can be int64 or strings. The
numbers go in the `render_edges` level columns. An explicit level column or `levels_db=None` leaves
the call as it was. A `ValueError` says so when the file has no stored levels or an edge has no row.

## Known issues that are fixed with them

- **(a)** An overlay hover lights every feature that has the same number: see the test in
  `tests/test_requests_browser.py` for the cause and the fix.
- **(b)** `rsColor` is one slot. A host that wraps it to add its own colour removes the colours of
  other callers: see `rsColor(ids, color, layer)` with a key (described in CHANGELOG when done).
