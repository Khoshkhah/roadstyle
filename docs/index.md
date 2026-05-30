# roadstyle

**roadstyle** turns a GeoDataFrame of road edges into a beautifully styled interactive map —
an OSM-style "geometry sandwich" (coloured fills over casings) with palettes, themes, and base
maps — and can colour roads by **your own data**, on **folium** / **lonboard**, or as a
**stack-agnostic JSON spec** you embed in any website.

```python
import geopandas as gpd
from roadstyle import render_edges

edges = gpd.read_file("edges.gpkg")            # any CRS; needs a road-class column
render_edges(edges, theme="dark").save("roads.html")          # classic OSM styling

render_edges(edges, color_by="aadt", cmap="viridis",          # colour by a data value
             width_by=(1, 6), legend=True).save("traffic.html")
```

## Why roadstyle?

- **Geometry sandwich** — every road is a coloured fill over a wider casing, so junctions and
  overlaps read cleanly (just like the OSM "Standard" style).
- **Class styling** — built-in `highsat` (high-saturation) and `carto` (classic OSM) palettes;
  bring your own vocabulary with `register_palette` / palette JSON.
- **Data-driven styling** — colour/size roads by any **categorical** column (`color_by`+`colors`)
  or **numeric** column (`color_by`+`cmap`+`width_by`), with automatic legends.
- **Themes & base maps** — light / dark / satellite, with a thumbnail base-map switcher.
- **Backends + web output** — folium (portable HTML), lonboard (WebGL), and `to_spec`/`to_html`/
  `to_iframe` for embedding in your own site (Leaflet / MapLibre / iframe).
- **Canonical input** — `normalize_edges` reprojects, drops non-lines, and maps your column names.

## Where to next

- **[Usage](usage.md)** — install, quick start, recipes.
- **[Parameter reference](parameters.md)** — every parameter explained.
- **[Embedding in a website](embedding.md)** — the JSON spec + Leaflet/MapLibre/iframe snippets.
- **[Palettes](palettes.md)** / **[Themes](themes.md)** — styling reference.
- **[Comparison](comparison.md)** — roadstyle vs geopandas `.explore()` / prettymaps.
