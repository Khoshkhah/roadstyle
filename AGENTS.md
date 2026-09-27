# roadstyle — guide for AI coding agents

roadstyle turns a GeoDataFrame of road edges into one self-contained, interactive HTML map
(MapLibre, data inlined, works offline), with a `window.rs*` JavaScript API for host pages.
Humans: start at [README.md](README.md). This file is the short version, plus the traps.

## Setup and tests

```bash
conda activate roadstyle            # or: pip install -e ".[dev]"
pytest                              # ~200 tests, ~20 s; browser tests need `pip install playwright`
```

A consumer project that does not install it runs with `PYTHONPATH=<this repo>/src`.

## The one call

```python
import roadstyle as rs
m = rs.render_edges(gdf, backend="web", palette="mono",
                    color_options={"Road class": {"color_by": "highway"},
                                   "Flow": {"color_by": "flow", "cmap": "turbo"}},
                    basemap="positron", boundary=area_geojson, arrows=True, labels=True)
html = m.html                       # a string; append your own panel before </body>
```

Every keyword with its default: README "Rendering parameters", or `docs/parameters.md`. Styling
(colours, widths, casing) is a *setting*, not a keyword — see README "Settings".

## Data contract

Required: LineString `geometry` (any CRS) and `highway` (OSM class). Optional columns switch
features on: `name` (labels, popup title), `oneway`, `bridge` / `tunnel` / `layer` (grade
separation), `edge_id` (kept exact even past 2**53). Every other column appears in the popup and
is queryable from JavaScript. An edge is DIRECTED: its geometry runs the way traffic flows, and
a two-way road is two edges with reversed geometry (drawn side by side).

## JavaScript API (in the saved page)

| call | does |
|---|---|
| `rsQuery(p => bool)` | features whose properties match -> **roadstyle feature ids** |
| `rsColor(ids, "#hex")` / `rsColor([[idsA, c1], [idsB, c2]])` / `rsColor(null)` | paint sets over the base colours / reset |
| `rsHighlight(ids)` | selection glow (`[]` clears) |
| `rsFocus(ids)` | fit the camera |
| `rsSelect(id)` / `rsDeselect()` | select like a click (glow + popup) |
| `rsFilter(ids)`, `rsGetProps(ids)` | show only these / their rows |
| `rsSetBasemap`, `rsSetClasses`, `rsSetColorField`, `rsSetOverlay`, `rsSetView3D` | drive the built-in controls |

Events on `document`: `rs:select` (`e.detail.properties`), `rs:deselect`, `rs:colorchange`, …
Full table: `docs/web-backend.md`.

## Traps (each one cost a real bug)

- **Ids past 2**53.** `rsSelect` / `rsColor` / `rsFocus` take roadstyle's *feature ids*, never your
  `edge_id`. Get them with `rsQuery(p => String(p.edge_id) === "8121729169906061189")`, or add a
  small integer column (e.g. `pidx = 0..n-1`) and query on that. In Python, a pandas column
  mixing big ints and `None` becomes float64 and silently rounds the ids — use `dtype="Int64"`.
- **Your side panel covers the map controls.** roadstyle appends the base-map button and menu
  to `<body>`, positioned against the viewport. A host page with a fixed side panel must inset
  the map and move them: `#map{right:400px!important} .bm-icon{right:410px} .bm-menu{right:410px}`.
- **Highlight by recolouring, not by drawing.** To show a set of edges, use `rsColor` (or a
  `color_options` entry). Extra lines drawn over the roads double them and hide the road's own
  styling underneath.
- **A selection in the base colour shows nothing.** Pick a highlight colour that no
  `color_options` entry already uses.
- **`palette="mono"` + `color_options`** is the readable combination: neutral roads, data colour.

## Changing the library

- `src/roadstyle/render_web.py` — `render(...)`: Python keywords become `__PLACEHOLDER__`
  replacements in `src/roadstyle/static/web_template.html` (one `.replace` chain near the end).
- A new web option = the keyword + its `.replace` + a `const` in the template + a test in
  `tests/test_render_web.py` + a row in README's table and `docs/web-backend.md` + CHANGELOG.
- The road popup and hover tooltip text: `_rfields` (popup/tooltip) and `_rrows` (docked panel)
  in the template; the Street View link: `_sv` / `_svHeading`.
