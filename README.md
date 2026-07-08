# roadstyle

OSM-theme **road/edge map styling** for `folium`, `lonboard`, and a self-contained **MapLibre
(vector)** backend. Turns a GeoDataFrame with a `highway` column into a styled interactive map —
with the proper **casing + fill "geometry sandwich"**, **light / dark / satellite** themes,
**highway-type filtering**, and a neon-violet **selected-edge** style.

The **`web` backend** (`backend="web"`) goes further, matching the *openstreetmap-carto* look with
**per-zoom widths**, **two-way directional lanes**, direction **arrows**, curved **street names**,
**hover/select**, a base-layer switcher, **tunnel/bridge grade separation**, and an optional
**boundary overlay** — all in one **offline, self-contained HTML** file (MapLibre and the data
bundled in; no server needed). See [`docs/web-backend.md`](docs/web-backend.md).

Three palettes (data files you can [override](#customising-palettes--config-data-files-no-code-edit)):
- **`highsat`** — custom high-saturation theme (cyan motorway, pink trunk, orange primary…)
  with theme-dependent casing. Maximum legibility over any base map.
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
roadstyle edges.gpkg -o map.html --theme dark               # styled interactive map
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

render_edges(edges, theme="dark").save("map.html")                  # high-sat, dark
render_edges(edges, palette="carto", theme="light").save("c.html")  # OSM Carto, light

# filter by type + satellite + highlight a selection
sel = edges[edges.highway == "motorway"]
render_edges(edges, theme="satellite",
             include=["motorway", "trunk", "primary"],
             selected=sel).save("major.html")

# big data: GPU backend
render_edges(edges, backend="lonboard", theme="dark")

# self-contained MapLibre map: per-zoom widths, two-way lanes, arrows, names,
# hover/select, base switcher, tunnel/bridge grade separation — opens offline, no server
render_edges(edges, backend="web", theme="dark").save("roads.html")
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

## Customising palettes & config (data files, no code edit)

The built-in palettes and styling knobs are **data, not code** — JSON files shipped in the
package (`roadstyle/data/palettes/*.json` and `roadstyle/data/style.json`). To change a colour or
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
| `render_edges(gdf, *, backend, palette, theme, include/exclude, selected, …)` | filter + render |
| `filter_edges(gdf, include, exclude, …)` / `highway_types(gdf)` | type filtering |
| `resolve(highway, palette, theme, tunnel, bridge)` | resolve one edge's concrete style |
| `selection_style(theme, base_width)` | neon-violet selected-edge layers |
| `PALETTES`, `THEMES` | the palette/theme tables |

Full docs: see [`docs/`](docs/index.md) (MkDocs — `mkdocs serve`). Styling spec is transcribed
from the cartographic design docs in the `osm-traffic-enrichment` project.
