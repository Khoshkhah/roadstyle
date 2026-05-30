# roadstyle

OSM-theme **road/edge map styling** for `folium` and `lonboard`.

Give it a GeoDataFrame with a `highway` column and it renders a styled interactive map:
the proper **casing + fill "geometry sandwich"**, **light / dark / satellite** themes,
**highway-type filtering**, and a neon-violet **selected-edge** style.

```python
import geopandas as gpd
from roadstyle import render_edges

edges = gpd.read_file("edges.gpkg")          # needs a `highway` column
render_edges(edges, theme="dark").save("map.html")
```

## Concepts

- **Palette** — the colour set keyed by `highway` tag. Two ship in the box:
  [`highsat`](palettes.md#highsat) (high-saturation) and [`carto`](palettes.md#carto) (OSM Carto).
- **Theme** — the base map + casing variant: `light`, `dark`, `satellite`
  (see [Themes](themes.md)).
- **Geometry sandwich** — all road *casings* are drawn first (one layer), then all *fills*
  on top, so borders never slice through higher-importance roads.
- **Overrides** — `*_link` render narrower; `tunnel` fades + dashes; `bridge` forces a black
  casing; `footway`/`path`/`cycleway`/`track` get dashed styles.
- **Selection** — a neon-violet glow/casing/core stack highlights selected edges.

## Design source

The palettes, casing widths, theme casing-swap and selection profile are transcribed from the
cartographic spec docs (`map_road_color.md`, `osm_highway_styles.md`, `selected_edge_color.md`).

See [Usage](usage.md) for the full API and recipes.
