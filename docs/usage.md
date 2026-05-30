# Usage

## `render_edges`

```python
render_edges(
    gdf, *,
    backend="folium",     # "folium" (portable HTML) | "lonboard" (WebGL)
    palette="highsat",    # "highsat" | "carto"
    theme="dark",         # "light" | "dark" | "satellite"
    highway_col="highway",
    include=None,         # keep only these highway types (str or iterable)
    exclude=None,         # drop these types
    match_links=True,     # treat primary_link as primary, etc.
    # folium-only extras:
    tooltip=None,         # list of columns for hover (default: all non-geometry)
    selected=None,        # a GeoDataFrame subset to highlight (neon-violet)
    tunnel_col="tunnel",  # bool/'yes' column -> tunnel styling (ignored if absent)
    bridge_col="bridge",
    name="roads",
)
```

Input: any GeoDataFrame with a `highway` column (any CRS — it's reprojected to 4326 for
display). Returns a `folium.Map` (call `.save("map.html")`) or a `lonboard.Map`.

The folium map is **interactive**:

- **Dynamic casing** — the road casing re-styles when you switch base maps (coloured casing
  on light tiles, black on dark/satellite), like the OSM project's website.
- **Hover highlight** — hovering an edge turns it white and brings it to front.
- **Type filter panel** (top-right) — checkboxes per `highway` type, plus *All*/*None*, to
  show/hide road classes live. Disable with `filter_control=False`.
- **Base-map switcher** (bottom-right) — thumbnail cards; see [Themes › Base maps](themes.md#base-maps).

## Recipes

```python
# high-saturation, dark base
render_edges(edges, theme="dark").save("dark.html")

# OSM Carto, light base
render_edges(edges, palette="carto", theme="light").save("carto.html")

# satellite, only the major network
render_edges(edges, theme="satellite",
             include=["motorway", "trunk", "primary", "secondary"]).save("major.html")

# drop service roads + alleys
render_edges(edges, exclude=["service", "footway", "path"]).save("drive.html")

# highlight a selection (e.g. a matched/queried subset)
sel = edges[edges.name == "Rissneleden"]
render_edges(edges, selected=sel).save("selected.html")

# big data -> GPU
render_edges(edges, backend="lonboard", theme="dark")

# choose a base map, or offer several toggleable ones (see Themes > Base maps)
render_edges(edges, theme="dark", basemap="voyager").save("voyager.html")
render_edges(edges, theme="dark",
             basemaps=["dark_matter", "positron", "satellite"]).save("switch.html")
```

## Filtering on its own

```python
from roadstyle import filter_edges, highway_types

highway_types(edges)                       # ['motorway', 'residential', 'service', ...]
major = filter_edges(edges, include=["motorway", "trunk", "primary"])
no_service = filter_edges(edges, exclude="service")
```

## Inspecting / reusing the style

```python
from roadstyle import resolve, base_style, selection_style

resolve("primary", palette="highsat", theme="dark")
# ResolvedStyle(fill='#FF9100', width=4.5, casing='#000000', casing_width=7.5, dash=None, opacity=1.0)

base_style("motorway", "carto").fill        # '#e892a2'
selection_style("dark", base_width=4.0)     # {'glow': {...}, 'casing': {...}, 'core': {...}}
```

Use `resolve()` to drive any other renderer (Mapbox GL, QGIS, deck.gl) from the same palette.
