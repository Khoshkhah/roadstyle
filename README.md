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
# into an existing env
pip install -e /home/kaveh/projects/roadstyle
# or a standalone dev env
conda env create -f environment.yml && conda activate roadstyle && pip install -e .
```

Requirements are in [`requirements.txt`](requirements.txt) / [`environment.yml`](environment.yml).
`folium` is the only hard renderer dependency; `lonboard` is optional (WebGL backend).

## Quickstart

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
