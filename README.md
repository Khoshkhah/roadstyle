# roadstyle

OSM-style **road/edge map styling** for a self-contained **MapLibre (vector)** backend, plus
`folium` and `lonboard`. Turns a GeoDataFrame with a `highway` column into a styled interactive
map — the proper **casing + fill "geometry sandwich"**, **highway-type filtering**, a neon-violet
**selected-edge** style, and **every styling default in one settings file**
(`data/defaults.json`, overridable via a `roadstyle.json` or `rs.use_settings()`).

The **`web` backend** (`backend="web"`) goes further, matching the *openstreetmap-carto* look with
**per-zoom widths**, **two-way directional lanes**, direction **arrows**, curved **street names**,
**hover/select**, a base-layer switcher, **tunnel/bridge grade separation**, slot-based
**street names + one-way arrows** (alternating along each road, never stacked), an optional
**3D view** (`view_3d=True`: tilted camera, extruded ramped **bridge decks**, an on-map 2D/3D
toggle), and an optional **boundary overlay** — all in one **offline, self-contained HTML** file
(MapLibre and the data bundled in; no server needed). See
[`docs/web-backend.md`](docs/web-backend.md).

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

## Customising palettes & config (data files, no code edit)

The built-in palettes and styling knobs are **data, not code** — one JSON file shipped in the
package (`roadstyle/data/defaults.json`: palettes, config, selection, and the road width/draw-order
model). To change a colour or
a knob, edit those files, or — without touching the package — drop a `roadstyle.json` override
that is read at import time. Override sources, lowest precedence first (later wins):

1. `~/.config/roadstyle/roadstyle.json` (or `$XDG_CONFIG_HOME/roadstyle/roadstyle.json`)
2. `./roadstyle.json` (project-local, current working dir)
3. `$ROADSTYLE_CONFIG` (explicit file path)

```jsonc
{
  "palettes": {
    "highsat": { "service": { "fill": "#E0E0E0" } },   // retint one class; rest is inherited
    "mytheme": { "roads": { "motorway": { "fill": "#f00", "width": 6, "casing_width": 8 } } }
  },
  "config":    { "fill_opacity": 0.95 },
  "selection": { "core": "#FF0000" }
}
```

Palette overrides are deep-merged **per road class** (change just `service.fill` and keep its
width/casing); `config`/`selection` override individual keys. Programmatic paths still work too:
`register_palette(name, table)`, `load_palette(path)`, or `render_edges(palette=…)`.

## API at a glance

| Function | Purpose |
|---|---|
| `render_edges(gdf, *, backend, palette, basemap, view_3d, include/exclude, …)` | filter + render |
| `filter_edges(gdf, include, exclude, …)` / `highway_types(gdf)` | type filtering |
| `resolve(highway, palette, tunnel, bridge)` | resolve one edge's concrete style |
| `selection_style(base_width)` | neon-violet selected-edge layers |
| `PALETTES`, `BASEMAPS` | the palette / base-map tables |
| `use_settings(path_or_dict)` | apply a settings override from code |

Full docs: see [`docs/`](docs/index.md) (MkDocs — `mkdocs serve`). Styling spec is transcribed
from the cartographic design docs in the `osm-traffic-enrichment` project.
