# roadstyle

OSM-theme **road/edge map styling** for `folium` and `lonboard`. Turns a GeoDataFrame with a
`highway` column into a styled interactive map — with the proper **casing + fill
"geometry sandwich"**, **light / dark / satellite** themes, **highway-type filtering**, and a
neon-violet **selected-edge** style.

Two palettes:
- **`highsat`** — custom high-saturation theme (cyan motorway, pink trunk, orange primary…)
  with theme-dependent casing. Maximum legibility over any base map.
- **`carto`** — the classic **OSM Carto** palette (muted warm tones).

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
roadstyle edges.gpkg -f spec -o map_data.json               # JSON spec for your own frontend
```

`-f/--format` picks the output: `folium` (default), `web` (standalone roadstyle.js page), `spec`
(JSON), or `geojson`. Run `roadstyle --help` for every flag — each mirrors a `render_edges` keyword.

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
```

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
