# roadstyle

OSM-style **road/edge map styling** for a self-contained **MapLibre (vector)** backend, plus
`folium` and `lonboard`. Turns a GeoDataFrame with a `highway` column into a styled interactive
map — the proper **casing + fill "geometry sandwich"**, **highway-type filtering**, a neon-violet
**selected-edge** style, and **every styling default in one settings file**
(`data/defaults.json`, overridable via a `roadstyle.json` or `rs.use_settings()`).

The **`web` backend** (`backend="web"`) goes further, matching the *openstreetmap-carto* look with
**per-zoom widths**, **two-way directional lanes**, direction **arrows**, curved **street names**,
**hover/select**, a base-layer switcher, a **scale bar**, a road-class filter panel that
**doubles as a colour legend**, **tunnel/bridge grade separation**, slot-based
**street names + one-way arrows** (alternating along each road, never stacked), an optional
**3D view** (`view_3d=True`: tilted camera, extruded ramped **bridge decks**, an on-map 2D/3D
toggle), and an optional **boundary overlay** — all in one **offline, self-contained HTML** file
(MapLibre and the data bundled in; no server needed). See
[`docs/web-backend.md`](docs/web-backend.md), and **[the gallery](docs/gallery.md)** for one
screenshot + recipe per look.

Three palettes (data files you can [override](#customising-palettes--config-data-files-no-code-edit)):
- **`highsat`** — custom high-saturation palette (cyan motorway, pink trunk, orange primary…)
  with a light-grey casing. Maximum legibility over any base map.
- **`carto`** — the classic **OSM Carto** palette (muted warm tones).
- **`mono`** — neutral grayscale (no hues); importance by shade + width. Good for print or as a
  quiet backdrop for data overlays.

## Install

```bash
pip install git+https://github.com/Khoshkhah/roadstyle.git
```

`folium` is the only hard renderer dependency. Optional extras pull in heavier backends/inputs as
you need them — `lonboard` (WebGL), `numeric` (continuous data-driven styling), `basemaps`,
`duckdb`, `arrow`:

```bash
pip install "roadstyle[numeric,duckdb] @ git+https://github.com/Khoshkhah/roadstyle.git"
```

**Develop locally** (editable install + dev tools):

```bash
git clone https://github.com/Khoshkhah/roadstyle.git && cd roadstyle
pip install -e ".[dev]"
# or a conda env: conda env create -f environment.yml && conda activate roadstyle && pip install -e ".[dev]"
```

## Command line

No Python required — point the `roadstyle` command at any road file (GPKG, GeoJSON, Shapefile, …):

```bash
roadstyle edges.gpkg -o map.html --basemap dark_matter               # styled interactive map
roadstyle edges.gpkg -o map3d.html --basemap dark_matter --view-3d   # tilted camera + 3D bridges
roadstyle edges.gpkg --include motorway trunk primary       # keep only major roads
roadstyle edges.gpkg --color-by aadt --cmap viridis --width-by 1 6   # colour by your data
roadstyle edges.gpkg --tooltip name highway maxspeed         # hover tooltip fields (all backends)
roadstyle edges.gpkg -f spec -o map_data.json               # JSON spec for your own frontend
```

`-f/--format` picks the output: `web` (self-contained MapLibre map, **default**), `folium`
(interactive folium HTML), `rsjs` (standalone roadstyle.js page), `spec` (JSON), or `geojson`. The
`web` map takes `--no-arrows` / `--no-labels` / `--no-filter` / `--no-basemap-switcher`. Run
`roadstyle --help` for every flag — each mirrors a `render_edges` keyword.

## Quickstart (Python)

```python
import geopandas as gpd
from roadstyle import render_edges

edges = gpd.read_file("edges.gpkg")          # needs a `highway` column (any CRS)

render_edges(edges, basemap="dark_matter").save("map.html")                  # high-sat, dark

# straight from a duckOSM database (grade separation, oneway, lanes — the right columns, always)
# edges = rs.from_duckosm("sodermalm.duckdb")
render_edges(edges, palette="carto").save("c.html")  # OSM Carto, light
render_edges(edges, basemap="dark_matter", view_3d=True).save("map3d.html")  # tilted + 3D bridges

# filter by type + satellite + highlight a selection
sel = edges[edges.highway == "motorway"]
render_edges(edges, basemap="satellite",
             include=["motorway", "trunk", "primary"],
             selected=sel).save("major.html")

# big data: GPU backend
render_edges(edges, backend="lonboard", basemap="dark_matter")

# self-contained MapLibre map: per-zoom widths, two-way lanes, arrows, names,
# hover/select, base switcher, tunnel/bridge grade separation — opens offline, no server
render_edges(edges, backend="web", basemap="dark_matter").save("roads.html")
```

### Colour each edge from your own table

Instead of colouring by road class, paint each edge by a per-edge colour — a `{edge_id: colour}`
table (dict, `Series`, or a DataFrame with `edge_id` + `color` columns). Edges not in the table get
a **gray** fallback; class widths + casing are kept, so the network still reads as roads.

```python
colors = {"4897…": "#e6194B", "5193…": "#3cb44b", ...}     # e.g. cluster / path / metric per edge
render_edges(edges, color_table=colors).save("by_edge.html")

# or, if the colour is already a column in your data, use it literally:
render_edges(edges, color_by="color", colors="self").save("by_edge.html")
```

### Base maps & the layer selection box

Every web map carries a **base-layer dropdown** (top-left) by default. You pick what it offers,
which one starts active, and you can register your own tile source:

```python
render_edges(edges,
             basemap="dark_matter",                                        # active
             basemaps=["dark_matter", "positron", "voyager", "satellite"]) # the dropdown

from roadstyle import Basemap, register_basemap
register_basemap(Basemap(key="lantmateriet", label="Lantmäteriet",
                         url="https://tiles.example.se/{z}/{x}/{y}.png",
                         attr="© Lantmäteriet"))
render_edges(edges, basemaps=["dark_matter", "lantmateriet"])
```

Built-ins: `voyager` (the settings default), `positron`, `dark_matter`, `osm`, `satellite`,
plus two **tile-less** ones — `blank` and `blank_dark` — that draw no base layer at all, just a
plain background colour. A map saved with `basemap="blank"` makes **zero network requests**
(fully offline) and gives a distraction-free canvas for print/figures.
Switching is purely client-side — the baked road styling never changes.

- **Turn the box off** (single fixed backdrop): `basemap_switcher=False` in Python,
  `--no-basemap-switcher` on the CLI.
- The box also hides itself automatically when only one base map is offered.

### Add extra layers (zones, POIs, any geometry)

Bring your own layers with `Overlay` — each one gets its own colour, a click popup, a spot in the
in-map **Layers** toggle, and a place **under** the roads (e.g. zone fills) or **over** them
(e.g. POIs). Geometry kind (fill / line / circle) is auto-detected:

```python
from roadstyle import Overlay

render_edges(
    edges, basemap="dark_matter",
    overlays=[
        Overlay(zones, placement="under", color="#2d6cdf", opacity=0.25,
                label="Traffic zones", popup=["taz_id", "population"]),
        Overlay(sensors, placement="over", color="#ffd166", radius=6,
                label="Sensors", popup=["sensor_id", "status"]),
    ],
).save("with_layers.html")
```

**Roads vs. overlays:** the road layer is the *subject* (full cartographic engine — widths,
casing, labels, arrows, grade separation, data-driven colour); overlays are *annotations* (one
flat paint each, popup + Layers toggle). An overlay never grows casings or labels — if a second
linear network deserves road-grade treatment, render it **as** the main layer with a custom
class vocabulary instead. Full comparison: [`docs/web-backend.md`](docs/web-backend.md#roads-vs-overlays--the-architecture).

### Several colour layers on one map (client-side switch)

`color_options` bakes **multiple fill sets** into a single map and adds a *Colour by* dropdown —
the viewer recolours every road (bridge decks included) instantly, with no re-render and no
server. A neutral base palette (`mono`) lets the data ramps stand out:

```python
render_edges(
    edges, palette="mono",
    color_options={
        "Road class": {},                                    # the class colours
        "Traffic":    {"color_by": "aadt", "cmap": "viridis"},
        "Speed":      {"color_by": "maxspeed_kmh", "cmap": "magma"},
    },
).save("switchable.html")
```

Each option carries its own legend; `window.rsSetColorField("Traffic")` drives the same switch
from your own UI.

### Filter by a different class than you style by

By default the web **road-type filter panel** lists whatever column drives styling (`highway_col`).
When width/casing should follow one scheme but the filter should list *another*, source-native
class, set `filter_col` — e.g. size roads by an OSM-highway proxy while the panel filters by the
source's own road class:

```python
render_edges(edges, highway_col="highway",       # widths/casing from the OSM-highway proxy
             filter_col="road_class").save("m.html")   # filter panel lists the source's real classes
```

### Static images for papers & reports

`rs.snapshot` renders any map to a PNG through a real headless browser (so tiles, labels, 3D
decks — everything — look exactly as on screen). Optional dependency:
`pip install playwright && playwright install chromium`.

```python
wm = render_edges(edges, basemap="dark_matter", view_3d=True)
rs.snapshot(wm, "skanstull.png", center=(18.076, 59.303), zoom=16, pitch=60, bearing=-25)
```

## Data contract — which column powers what

roadstyle reads plain columns; only two things are required. Everything else lights up a feature
when present (and is simply skipped when absent):

| Column | Values | Powers |
|---|---|---|
| *geometry* | LineString (any CRS) | **required** — the edges themselves |
| `highway` | OSM class (`motorway`…`service`) | **required** — colour, width, casing, draw order, minzoom (another column via `highway_col`) |
| `name` | text | street-name **labels** along the road + the popup title |
| `oneway` | `True`/`False` (or `yes`/`no`) | direction **arrows** on one-way edges. Without this column, one-way is inferred: an edge with no reverse-geometry twin (directed networks, e.g. duckOSM) |
| `bridge` / `tunnel` | truthy | **grade separation** — tunnels draw faded + dashed *below*, bridges on top with a black deck casing, and as extruded 3D decks in `view_3d` (column names via `bridge_col` / `tunnel_col`) |
| `layer` | int | grade fallback where `bridge`/`tunnel` are absent (sign decides above/below) |
| `lanes`, `maxspeed_kmh`, `edge_ref`, … | anything | shown in the click **popup** (curated set by default; `road_popup="all"` for every column) |
| `edge_id` | id (64-bit safe) | popups + click-to-copy; values > 2⁵³ should be strings so JavaScript can't corrupt them (`from_duckosm` handles this) |

`rs.from_duckosm(db)` selects exactly this set from a duckOSM database.

### Hover tooltip vs. click popup — what shows where

Two different read-outs, configured independently:

- **Click popup** (`road_popup`, web backend) — opens when you click an edge (or a 3D bridge
  deck). **On by default** with a curated field set: `name` (bold title), `edge_id`, `edge_ref`,
  `highway`, `lanes`, `bridge`, `tunnel`. Blank/NaN values are dropped, and `bridge`/`tunnel`
  rows appear only when the road actually is one.
- **Hover tooltip** (`tooltip`, every backend) — follows the mouse. **Off by default** on the web
  backend (hover just highlights); pass a field list to enable it. On the folium backend it's on
  by default (all columns), and clicking **pins** it + copies `edge_id` to the clipboard.

```python
render_edges(
    edges,
    road_popup=["name", "highway", "maxspeed_kmh", "aadt"],  # your click fields
    tooltip=["name", "aadt"],                                # hover read-out (any backend)
)
render_edges(edges, road_popup="all")     # click shows every column
render_edges(edges, road_popup="panel")   # docked side PANEL instead of a floating popup
render_edges(edges, road_popup=False)     # no popup (click still selects/highlights)
```

`road_popup="panel"` docks the read-out bottom-right — it never covers the road you clicked and
stays put at tilted 3D angles. For your own sidebar/dashboard: every click dispatches a
`rs:select` CustomEvent (`event.detail.properties` = the edge's columns; `rs:deselect` on clear),
in every mode — `road_popup=False` + your own listener is a clean custom UI:

```js
document.addEventListener("rs:select",   e => showSidebar(e.detail.properties));
document.addEventListener("rs:deselect", () => hideSidebar());
```

Internal `__rs_*`/`twoway`/`lvl` fields never show. Anything you select into the GeoDataFrame is
available — the popup/tooltip read the columns of *your* data.

## Drive the map from JavaScript

Every in-map control is a thin UI over a `window.rs*` function — so anything you can click, your
own HTML/JS can call. Each setter updates the map **and** keeps the built-in control in sync, and
dispatches a `rs:*` CustomEvent on `document` so outside code can react:

```js
rsSetBasemap("dark_matter");                // by key, label, or index   → rs:basemapchange
rsSetClasses(["primary", "secondary"]);     // show exactly these classes → rs:filterchange
rsSetColorField("Traffic");                 // switch the colour layer    → rs:colorchange
rsSetOverlay("Zones", false);               // hide/show one overlay      → rs:overlaychange
rsSetView3D(true);                          // tilt to the settings' 3D pitch → rs:viewchange
rsSelect(id); rsDeselect();                 // select an edge like a click (popup/panel + glow)
map.easeTo({pitch: 60, bearing: 30});       // camera: window.map is the MapLibre Map itself

document.addEventListener("rs:basemapchange", e => console.log(e.detail.basemap));
document.addEventListener("rs:filterchange",  e => console.log(e.detail.visible));
```

And the baked features are a **queryable table**: `rsQuery` takes a predicate over your data's
columns (a WHERE clause, written in JS) and returns an **id set** — then independent verbs act
on that set, composably:

```js
const ids = rsQuery(p => p.lanes >= 2 && p.maxspeed_kmh > 30);   // → [7, 12, 95, …]
rsFilter(ids);                 // show only these edges (rsFilter(null) resets)  → rs:filterchange
rsColor(ids, "#ff00aa");       // paint the set one colour (rsColor(null) resets) → rs:colorchange
rsHighlight(ids);              // selection glow (rsHighlight([]) clears)      → rs:highlightchange
rsGetProps(ids);               // → the rows behind the ids (internals stripped) — table-ready
rsFocus(ids);                  // fly the camera to fit the set (or one id) — pairs with rsSelect
```

Every verb also takes an **optional layer argument** — omitted it queries the roads; an
overlay's label treats *that* overlay as the table (`rsQuery(p => p.status === 'offline',
"Sensors")`, then `rsHighlight(ids, "Sensors")`, `rsGetProps(ids, "Sensors")`, `rsFilter(ids,
"Sensors")`, `rsColor(ids, "#ff1744", "Sensors")` — reset with `rsColor(null, null, "Sensors")`
— and `rsFocus(ids, null, "Sensors")`). Each layer is its own id space: never mix ids across
layers. The road ids are the same id space as `rs:select` events (`e.detail.id`), so
click-selection and queries interoperate. `rsColor` layers *over* the active `color_options` choice and survives
switching it. One ceiling: street-name labels, arrows, and 3D bridge deck ribbons live on merged
helper sources, so `rsFilter` prunes the road geometry but not those decorations (the class
filter from `rsSetClasses` prunes everything).

**Ready-made scaffolding:** [`ui/`](ui/) holds copyable UI templates built purely on this API —
`python ui/dashboard/build.py your.duckdb` produces a sidebar dashboard (query box, verb
buttons, clickable results table, detail panel, base-map select) with every built-in control
replaced by plain HTML you own.

What's available to enumerate: `RS_BASEMAPS` (key/label per entry), `RS_CLASSES` (road classes in
the data), `RS_COLOR_OPTIONS`, `RS_OVERLAYS`. Selection events are above (`rs:select` /
`rs:deselect`). The setters work **even with the built-in control hidden** — e.g.
`basemaps=["voyager", "blank"], basemap_switcher=False` bakes both entries with no dropdown, so
your own buttons can call `rsSetBasemap("blank")`; only the no-`basemaps=` +
`basemap_switcher=False` combination bakes just the one fixed backdrop.

## All options at a glance

Every keyword of `render_edges` (full reference: [`docs/parameters.md`](docs/parameters.md)):

| Group | Options |
|---|---|
| **Rendering** | `backend` (`"web"` default / `"folium"` / `"lonboard"`) · `palette` (`highsat`/`carto`/`mono`) · `basemap` / `basemaps` (active base map / switcher set) · `name` (page title) · `settings` (per-call settings override, dict or path) |
| **Camera & 3D** | `pitch` / `bearing` (starting camera) · `view_3d` (tilted camera + extruded ramped bridge decks + on-map 2D/3D toggle) |
| **Colour by data** | `color_by` + `colors`/`cmap`/`vmin`/`vmax` (categorical / continuous ramps) · `width_by` (scale width by value) · `color_table` (per-edge `{edge_id: colour}`) · `color_options` (several fill sets + client-side *Colour by* dropdown) |
| **Filtering** | `include` / `exclude` (road classes) · `filter_col` (panel filters by another column) · `minzoom` (hide minor classes when zoomed out — `True` for the built-in table, or a dict) |
| **UI toggles (web)** | `arrows` · `labels` · `filter_control` · `basemap_switcher` · `road_popup` (`True`/field list/`"all"`/`"panel"`/`False`) · `tooltip` (hover fields) · `hover_color` / `select_color` |
| **Extra content** | `overlays` (your own layers, under/over the roads) · `boundary` (dashed outline of the clip area) · `selected` (pre-highlighted edges, folium backend) |
| **Data columns** | `highway_col` (class column) · `tunnel_col` / `bridge_col` / `layer_col` (grade separation) |
| **Output size** | `compress=True` — gzip the inlined GeoJSON (typically 3–4× smaller files; the page inflates it on load; also keeps inline notebook previews under output-size limits) |

Everything *stylistic* (colours, widths, casing, labels, arrows, annotation slots, camera
defaults, bridge decks…) is not a keyword but a **setting** — see the next section.

## Giving the library your settings

EVERY styling default — palettes, opacities, casing, the width/draw-order model, base map,
camera, labels, arrows, annotation slots, bridge decks — ships in **one file**,
`roadstyle/data/defaults.json`. You never edit it: you hand roadstyle a **settings override**
stating only what changes, in any of four ways (later wins):

1. `~/.config/roadstyle/roadstyle.json` — your personal defaults, every project
2. `./roadstyle.json` — project-local (next to where you run)
3. `$ROADSTYLE_CONFIG=/path/to/file.json` — explicit, per run
4. **from code, at any time**: `rs.use_settings("my.json")` or `rs.use_settings({...})` —
   highest precedence, applies immediately (no restart), and `rs.use_settings()` with no
   argument drops it again.
5. **per call** — no files, no global state:
   `render_edges(edges, settings={"config": {"labels": {"color": "#8899aa"}}})` applies the
   override for that one render and restores everything after. Two looks in one script is just
   two calls with two `settings=` values.

The file layout mirrors `defaults.json` — four sections, all optional, merged per entry
(a single zoom stop of one width row is a valid complete override):

```jsonc
{
  "palettes": {
    "highsat": { "service": { "fill": "#E0E0E0" } }    // retint one class; rest inherited
  },
  "config": {
    "basemap": "dark_matter",                          // the primary base map layer
    "labels": { "color": "#8899aa" },                  // street-name paint
    "camera": { "pitch_3d": 65, "max_pitch": 85 },     // 3D tilt targets
    "bridge_decks": { "opacity": 0.6, "step_m": 0.5 }, // 3D deck look
    "annotations": { "slot_m": 120 },                  // name/arrow slot length
    "overlays": { "color": "#2d6cdf", "radius": 8 }    // overlay layer defaults
  },
  "selection": { "core": "#FF0000" },                  // click-highlight colours
  "roads": {
    "z_order": { "service": 5 },                       // draw priority of one class
    "width":   { "secondary": { "18": 14 } }           // one zoom stop of one width row
  }
}
```

Files 1–3 are read **at import** (exist before `import roadstyle`); `use_settings` is the
**runtime** path and also rebuilds the already-loaded tables, so it works mid-notebook.
Programmatic palette APIs still exist too: `register_palette(name, table)`, `load_palette(path)`.

## API at a glance

| Function | Purpose |
|---|---|
| `render_edges(gdf, *, backend, palette, basemap, view_3d, include/exclude, …)` | filter + render |
| `filter_edges(gdf, include, exclude, …)` / `highway_types(gdf)` | type filtering |
| `resolve(highway, palette, tunnel, bridge)` | resolve one edge's concrete style |
| `selection_style(base_width)` | neon-violet selected-edge layers |
| `PALETTES`, `BASEMAPS` | the palette / base-map tables |
| `use_settings(path_or_dict)` | apply a settings override from code |
| `snapshot(map_or_html, "fig.png", center=…, zoom=…, pitch=…)` | static PNG via headless browser (optional `playwright`) |

Full docs: see [`docs/`](docs/index.md) (MkDocs — `mkdocs serve`). Styling spec is transcribed
from the cartographic design docs in the `osm-traffic-enrichment` project.
