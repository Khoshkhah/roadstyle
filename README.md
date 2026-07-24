# roadstyle

[![Tests](https://github.com/Khoshkhah/roadstyle/actions/workflows/test.yml/badge.svg)](https://github.com/Khoshkhah/roadstyle/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/Khoshkhah/roadstyle/blob/main/LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://pypi.org/project/roadstyle/)

Turn a GeoDataFrame of road edges into a **styled, interactive, self-contained map** — proper
road cartography (the casing + fill "geometry sandwich", per-zoom widths, street names, one-way
arrows, tunnel/bridge grade separation, optional 3D bridge decks) in one offline HTML file, with
a scriptable JavaScript API.

![3D bridges over Södermalm](https://raw.githubusercontent.com/Khoshkhah/roadstyle/main/docs/img/gallery/bridges_3d.png)

**Contents:**
[Features](#features) ·
[Installation](#installation) ·
[Quickstart](#quickstart) ·
[The studio (no code)](#the-studio--the-library-behind-knobs-no-code) ·
[Rendering parameters](#rendering-parameters) ·
[Data contract](#data-contract--which-column-powers-what) ·
[Recipes](#recipes) ·
[JavaScript API](#drive-the-map-from-javascript) ·
[Settings](#settings--one-defaults-file-your-overrides-on-top) ·
[Command line](#command-line) ·
[Documentation](#documentation)

## Features

- **Real road cartography** — casing + fill sandwich, importance-ordered junctions, per-zoom
  widths (openstreetmap-carto model), two-way lanes, curved street names, one-way arrows.
- **Grade separation** — tunnels faded + dashed underneath, bridges on decks on top (stacked
  structures ordered by their OSM `layer`), and an optional **3D view** with extruded bridge decks.
- **One offline file** — MapLibre and the data are bundled into the saved HTML; it opens by
  double-click, no server, no internet (with the `blank` basemap: zero network requests).
- **Data-driven styling** — colour/width by any column (categorical or numeric ramps), per-edge
  colour tables, and multiple colour layers switchable client-side.
- **Big networks** — `tiles=True` packs the roads as an embedded vector tileset (PMTiles):
  ~10⁵-edge maps open in seconds and stay responsive, still one offline file.
- **A JavaScript API** — every control is scriptable (`rsQuery`, `rsFilter`, `rsColor`,
  `rsSelect`, …) with `rs:*` events, so the saved map can power your own dashboard.
- **Three backends** — `web` (MapLibre, the flagship), `folium` (Leaflet, legends), `lonboard`
  (GPU, millions of edges).

## Installation

Python ≥ 3.10. Two ways in, depending on who you are:

### Using the library (pip, no clone)

```bash
pip install roadstyle                 # the library — geopandas, shapely, folium, branca come along
pip install "roadstyle[studio]"       # + the no-code Streamlit workbench: `roadstyle studio`
```

Every optional feature is an extra — combine what you need (e.g. `pip install "roadstyle[numeric,tiles]"`),
or take everything at once with `pip install "roadstyle[all]"`:

| Extra | Enables | Pulls in |
|---|---|---|
| `studio` | `roadstyle studio` — the interactive Streamlit workbench | streamlit |
| `numeric` | continuous colour ramps + classification (`color_by` on numbers) | mapclassify, matplotlib |
| `tiles` | `tiles=True` — embedded vector tiles for big networks | mapbox-vector-tile, pmtiles |
| `lonboard` | the GPU backend for very large edge sets | lonboard |
| `duckdb` | `from_duckdb()` — read edges straight from DuckDB | duckdb |
| `arrow` | read edges from a pyarrow Table | pyarrow |
| `basemaps` | any XYZ provider from the xyzservices registry | xyzservices |
| `all` | every extra above in one go | all of the above |

To try the latest unreleased state — still no clone:
`pip install "roadstyle @ git+https://github.com/Khoshkhah/roadstyle.git"`

### Developing on it (clone + editable install)

```bash
git clone https://github.com/Khoshkhah/roadstyle.git && cd roadstyle
pip install -e ".[dev]"              # editable + test/lint tools (pytest, ruff, mypy, all backends)
# or with conda: conda env create -f environment.yml && conda activate roadstyle && pip install -e ".[dev]"
pytest                               # the full suite; browser tests need `pip install playwright`
```

From a checkout the studio runs against your working tree (`roadstyle studio`, needs
`pip install streamlit`) and uses the repo's sample data in `ui/studio/samples/` directly.

**Uninstall:** `pip uninstall roadstyle`. Your personal settings overrides
(`~/.config/roadstyle/roadstyle.json`, project-local `roadstyle.json`) are your files — pip
leaves them in place; delete them yourself if you want a clean slate.

## Quickstart

```python
import geopandas as gpd
import roadstyle as rs

edges = gpd.read_file("edges.gpkg")          # any CRS; needs a `highway` class column

rs.render_edges(edges).save("map.html")                          # done — open map.html
```

That one line gives you the full treatment: per-zoom widths, two-way lanes, arrows, street
names, hover/select with popups, a base-map switcher, a class filter panel, grade separation.
Common variations:

```python
rs.render_edges(edges, basemap="dark_matter", view_3d=True).save("map3d.html")   # dark + 3D bridges
rs.render_edges(edges, palette="carto", basemap="positron").save("carto.html")   # the classic OSM look
rs.render_edges(edges, include=["motorway", "trunk", "primary"]).save("major.html")
rs.render_edges(edges, color_by="aadt", cmap="viridis").save("traffic.html")     # colour by your data
rs.render_edges(edges, tiles=True).save("big.html")                              # 10⁵-edge networks

rs.render_dashboard(edges).save("dashboard.html")   # a full query-sidebar dashboard page, one call
rs.render_report(edges).save("report.html")         # a stats-sidebar report page
```

Palettes: **`highsat`** (high-saturation, maximum legibility), **`carto`** (the muted
openstreetmap-carto look), **`mono`** (grayscale — quiet backdrop for data overlays).

## The studio — the library behind knobs, no code

The gentlest way in. The studio is a small Streamlit app that ships with the package — install the
`studio` extra and run it (the sample networks, ~12 MB, download on first run):

```bash
pip install "roadstyle[studio]"
roadstyle studio                 # add streamlit args as usual: roadstyle studio --server.port 8502
```

![roadstyle studio](https://raw.githubusercontent.com/Khoshkhah/roadstyle/main/docs/img/gallery/studio.png)

Three pages, same idea — every knob updates the live map **and** the exact Python code that
reproduces it:

- **Map** — upload a road file (`.gpkg` / `.geojson`) or pick a bundled Södermalm sample, then
  click through palette, base map, 3D, vector tiles, colour-by-data, class filter, minzoom,
  labels/arrows, popups and overlays. Copy the generated `render_edges(...)` code out, or
  download the self-contained `map.html`.
- **Dashboard** — the same knobs, but the product is a **sidebar dashboard** (query box, verb
  buttons, results table, detail panel) built on the JavaScript API. Preview it live, download
  `dashboard.html`. The generated code is a one-liner: `rs.render_dashboard(edges, ...)`.
- **Report** — a **stats sidebar** instead (KPI cards, the colour-by legend, a checkbox filter,
  search, a selected-road read-out). Generated as `rs.render_report(edges, ...)`.

Both sidebar pages are shipped in the library — `rs.render_dashboard(edges).save("dashboard.html")`
and `rs.render_report(edges)` build them in one call, no repo checkout needed (see below).

## Rendering parameters

The keywords of `rs.render_edges(gdf, ...)` — the ones you'll actually reach for. Full
reference with every type and edge case: [docs/parameters.md](https://khoshkhah.github.io/roadstyle/parameters/).

**Core**

| Parameter | Default | What it does |
|---|---|---|
| `backend` | `"web"` | `"web"` (MapLibre, the flagship) / `"folium"` (Leaflet + legends) / `"lonboard"` (GPU) |
| `palette` | `"highsat"` | Class colour palette: `"highsat"` / `"carto"` / `"mono"`, or your own |
| `basemap` | `"voyager"` | Background map: `voyager`, `positron`, `dark_matter`, `osm`, `satellite`, `blank`, `blank_dark` |
| `basemaps` | all built-ins | The set offered in the in-map base-layer dropdown |
| `name` | `"roadstyle"` | Page / layer title |
| `settings` | `None` | Per-call settings override (dict or path) — see [Settings](#settings--one-defaults-file-your-overrides-on-top) |

**Filtering**

| Parameter | Default | What it does |
|---|---|---|
| `include` / `exclude` | `None` | Keep / drop road classes (`include=["motorway","primary"]`); `_link` variants follow automatically |
| `filter_col` | `None` | Let the filter panel list a different column than the one that drives styling |
| `minzoom` | `None` (off) | Hide minor classes when zoomed out: `True` for the built-in table, or a `{class: zoom}` dict. Applies to the vector tiles too |

**Colour by data**

| Parameter | Default | What it does |
|---|---|---|
| `color_by` | `None` | Colour by a column instead of road class |
| `colors` | `None` | Categorical `{value: "#hex"}` map, or `"self"` to use the column's value as the literal colour |
| `cmap` / `vmin` / `vmax` | `None` | Numeric colour ramp (`"viridis"`, …) and its value range |
| `width_by` | `None` | `(min_px, max_px)` — scale line width with the numeric value |
| `color_table` | `None` | Per-edge colours: `{edge_id: "#hex"}` dict / Series / DataFrame (gray fallback, class widths kept) |
| `color_options` | `None` | Bake **several** colour layers + a client-side *Colour by* dropdown: `{"Traffic": {"color_by": "aadt", "cmap": "viridis"}, ...}` |

**Camera & 3D** (web backend)

| Parameter | Default | What it does |
|---|---|---|
| `view_3d` | `False` | Tilted camera + extruded, ramped, cased 3D bridge decks + an on-map 2D/3D toggle |
| `pitch` / `bearing` | settings | Starting camera tilt / rotation |

**UI toggles** (web backend)

| Parameter | Default | What it does |
|---|---|---|
| `arrows` | `True` | One-way direction chevrons |
| `labels` | `True` | Curved street-name labels |
| `filter_control` | `True` | The collapsible road-class filter panel (doubles as a colour legend) |
| `basemap_switcher` | `True` | The base-layer dropdown |
| `road_popup` | `True` | Click popup: `True` (curated fields) / `[fields]` / `"all"` / `"panel"` (docked read-out) / `False` |
| `tooltip` | `None` (off) | Hover tooltip fields (list of columns) |
| `hover_color` / `select_color` | violet | Highlight colours for hovered / selected roads |

**Extra content** (web backend)

| Parameter | Default | What it does |
|---|---|---|
| `overlays` | `None` | Your own layers (`Overlay(...)`) — zones under the roads, POIs on top, clickable, with a Layers toggle |
| `boundary` | `None` | Dashed outline of the clip area, drawn on top |
| `selected` | `None` | Pre-highlighted edges (folium backend) |

**Output & scale**

| Parameter | Default | What it does |
|---|---|---|
| `compress` | `True` | Gzip the inlined data (3–4× smaller files; `compress=False` for plain JSON) |
| `tiles` | `False` | Embedded-PMTiles vector tileset — for ~10⁵-edge networks (needs the `tiles` extra) |

**Column mapping**

| Parameter | Default | What it does |
|---|---|---|
| `highway_col` | `"highway"` | The road-class column that drives styling |
| `tunnel_col` / `bridge_col` / `layer_col` | `"tunnel"` / `"bridge"` / `"layer"` | Grade-separation columns |

Everything *stylistic* — the actual colours, widths, casing, label/arrow cosmetics, camera
defaults, bridge-deck geometry — is deliberately **not** a keyword but a
[setting](#settings--one-defaults-file-your-overrides-on-top).

## Data contract — which column powers what

Only two things are required; every other column lights up a feature when present and is
skipped when absent:

| Column | Values | Powers |
|---|---|---|
| *geometry* | LineString (any CRS) | **required** — the edges themselves |
| `highway` | OSM class (`motorway`…`service`) | **required** — colour, width, casing, draw order |
| `name` | text | street-name labels + the popup title |
| `oneway` | `True`/`False` / `yes`/`no` | direction arrows (without it, one-way is inferred from reverse-geometry twins) |
| `bridge` / `tunnel` | truthy | grade separation: tunnels below, bridges on decks above, 3D decks in `view_3d` |
| `layer` | int | stacking order of bridges/tunnels; negative → below ground even without `tunnel` |
| `edge_id` | id (64-bit safe) | popups + click-to-copy; ids > 2⁵³ are kept exact as strings |
| anything else | anything | shown in the click popup / hover tooltip, queryable from JavaScript |

Networks exported by [duckOSM](https://github.com/Khoshkhah/duckOSM) (`duckosm export-gis`)
carry exactly this column set.

## Recipes

Each of these is one call — details behind the links.

```python
# colour each edge from your own table (cluster / route / metric per edge)
rs.render_edges(edges, color_table={"4897…": "#e6194B", "5193…": "#3cb44b"})

# several colour layers in one map, switchable client-side (no re-render)
rs.render_edges(edges, palette="mono", color_options={
    "Road class": {},
    "Traffic":    {"color_by": "aadt", "cmap": "viridis"},
    "Speed":      {"color_by": "maxspeed_kmh", "cmap": "magma"}})

# your own layers under/over the roads
rs.render_edges(edges, overlays=[
    rs.Overlay(zones,   placement="under", color="#2d6cdf", opacity=0.25, label="Zones",
               popup=["taz_id", "population"]),
    rs.Overlay(sensors, placement="over",  color="#ffd166", radius=6, label="Sensors")])

# your own tile server as a base map
rs.register_basemap(rs.Basemap(key="lm", label="Lantmäteriet",
                               url="https://tiles.example.se/{z}/{x}/{y}.png", attr="© LM"))

# a static PNG for a paper, through a real headless browser (pip install playwright)
rs.snapshot(rs.render_edges(edges, view_3d=True), "fig.png",
            center=(18.076, 59.303), zoom=16, pitch=60)

# roads straight from DuckDB
edges = rs.from_duckdb(con, "SELECT edge_id, highway, name, ST_AsWKB(geom) AS geometry FROM edges")
```

More: [the gallery](https://khoshkhah.github.io/roadstyle/gallery/) — one screenshot + recipe per look.

## Drive the map from JavaScript

Every in-map control is a thin UI over a `window.rs*` function, and the baked features are a
queryable table — so a saved map can power your own dashboard with plain HTML:

```js
const ids = rsQuery(p => p.lanes >= 2 && p.maxspeed_kmh > 30);   // WHERE clause → id set
rsFilter(ids);                 // show only these         rsFilter(null) resets
rsColor(ids, "#ff00aa");       // paint them one colour   rsColor(null) resets
rsHighlight(ids);              // selection glow
rsGetProps(ids);               // the rows behind the ids — table-ready
rsFocus(ids);                  // fly the camera to fit them
rsSelect(id);                  // select + popup, like a click

rsSetBasemap("dark_matter");   rsSetClasses(["primary","secondary"]);
rsSetColorField("Traffic");    rsSetOverlay("Zones", false);      rsSetView3D(true);

document.addEventListener("rs:select", e => showSidebar(e.detail.properties));
```

Everything works the same on overlays (pass the overlay's label as the last argument) and on
tiled maps. Full API table: [docs/web-backend.md](https://khoshkhah.github.io/roadstyle/web-backend/#the-javascript-api-windowrs).

Two ready-made sidebars ship **inside the package**, built entirely on this API — one call each:

```python
rs.render_dashboard(edges).save("dashboard.html")   # query box, colour-by, class filter + legend, table
rs.render_report(edges).save("report.html")          # KPI cards, colour-by legend, filter, search
```

`color_options={...}` populates their *Colour by* picker; every `render_edges` keyword passes
through. To reshape one, `rs.sidebar_html("dashboard")` (or `"report"`) returns the HTML/CSS/JS
fragment — edit it and re-inject before `</body>`. The same fragments live in
[`ui/`](https://github.com/Khoshkhah/roadstyle/tree/main/ui) with a `build.py` per template.

## Settings — one defaults file, your overrides on top

EVERY styling default — palettes, opacities, casing, the width/draw-order model, base map,
camera, labels, arrows, bridge decks — ships in one file, `roadstyle/data/defaults.json`. You
never edit it; you state only what changes, at any of five levels (later wins):

1. `~/.config/roadstyle/roadstyle.json` — personal defaults
2. `./roadstyle.json` — project-local
3. `$ROADSTYLE_CONFIG=/path/to/file.json` — per run
4. `rs.use_settings({...})` — from code, applies immediately
5. `render_edges(..., settings={...})` — this one call only

```jsonc
{
  "palettes":  { "highsat": { "service": { "fill": "#E0E0E0" } } },   // retint one class
  "config":    { "basemap": "dark_matter", "labels": { "color": "#8899aa" } },
  "roads":     { "z_order": { "service": 5 }, "width": { "secondary": { "18": 14 } } }
}
```

Details: [docs/palettes.md](https://khoshkhah.github.io/roadstyle/palettes/).

## Command line

No Python required — point the `roadstyle` command at any road file:

```bash
roadstyle edges.gpkg -o map.html --basemap dark_matter        # styled interactive map
roadstyle edges.gpkg --view-3d --tiles                        # 3D + embedded vector tiles
roadstyle edges.gpkg --include motorway trunk primary
roadstyle edges.gpkg --color-by aadt --cmap viridis --width-by 1 6
roadstyle edges.gpkg -f spec -o map_data.json                 # JSON spec for your own frontend

roadstyle studio                                              # the interactive workbench (needs the studio extra)
roadstyle studio --server.port 8502                           # any streamlit flag is forwarded
```

Every flag mirrors a `render_edges` keyword; `roadstyle --help` lists them all. `roadstyle studio`
launches the [Streamlit workbench](#the-studio--the-library-behind-knobs-no-code) (install it with
`pip install "roadstyle[studio]"`) and passes any extra arguments straight to `streamlit run`.

## Documentation

| | |
|---|---|
| [Gallery](https://khoshkhah.github.io/roadstyle/gallery/) | one screenshot + recipe per look |
| [Parameter reference](https://khoshkhah.github.io/roadstyle/parameters/) | every keyword, type, and default |
| [Web backend](https://khoshkhah.github.io/roadstyle/web-backend/) | grade separation, 3D, vector tiles, colour options, the full JS API |
| [Choosing an engine](https://khoshkhah.github.io/roadstyle/engines/) | web vs folium vs lonboard, data-size guidance |
| [Palettes & settings](https://khoshkhah.github.io/roadstyle/palettes/) | the built-in palettes and the override system |
| [When to use roadstyle](https://khoshkhah.github.io/roadstyle/comparison/) | vs `.explore()`, prettymaps, kepler.gl, raw MapLibre |
| [Notebooks](https://github.com/Khoshkhah/roadstyle/tree/main/notebooks) | a runnable manual, one topic per notebook |
| [UI templates](https://github.com/Khoshkhah/roadstyle/tree/main/ui) | the dashboard / report scaffolding + the studio's sample data (the studio itself ships in the package — `roadstyle studio`) |

Full MkDocs site: [khoshkhah.github.io/roadstyle](https://khoshkhah.github.io/roadstyle/)
(`mkdocs serve` locally).

## License

[MIT](https://github.com/Khoshkhah/roadstyle/blob/main/LICENSE). Base-map tiles are third-party services (CARTO, OSM, Esri) with their own
attribution and terms; the styling spec is transcribed from the cartographic design docs in the
osm-traffic-enrichment project.
