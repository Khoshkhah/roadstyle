# Themes

A theme sets the **base map** and which **casing** variant the `highsat` palette uses.
`light` is the **default**.

| theme | base map | casing used | notes |
|---|---|---|---|
| `light` (default) | CartoDB Voyager | light casing (coloured) | for white/light canvases |
| `dark` | CartoDB Dark Matter | dark casing (`#000000`) | for dark canvases |
| `satellite` | Esri World Imagery | dark casing (`#000000`) | high-contrast over imagery |

```python
render_edges(edges, theme="light")
render_edges(edges, theme="dark")
render_edges(edges, theme="satellite")
```

## Base maps

By default the folium map shows a **layers button (FAB, bottom-right)** that opens a popover
with a **2-column grid of thumbnail cards** (each a gradient preview + little road sketch);
click a card to switch the base map live (active card highlighted green). The **satellite**
option also dims the imagery (`saturate .8 brightness .9`). This matches the
osm-traffic-enrichment website's selector (not the default Leaflet box).

| key | tiles |
|---|---|
| `voyager` | CartoDB Voyager |
| `positron` | CartoDB Positron (light) |
| `dark_matter` | CartoDB Dark Matter (dark) |
| `osm` | OpenStreetMap |
| `esri_gray` | Esri Light Gray |
| `satellite` | Esri World Imagery |

```python
# default switcher (voyager / positron / dark_matter / osm / satellite)
render_edges(edges, theme="dark").save("m.html")

# customise the switcher set
render_edges(edges, theme="dark", basemaps=["dark_matter", "osm", "satellite"]).save("m.html")

# a single fixed base map (no switcher)
render_edges(edges, theme="light", basemap="osm").save("m.html")
```

The road network is always drawn (no on/off toggle). The registry is `roadstyle.BASEMAPS`;
add your own `Basemap(...)` entries (with `bg`/`preview` for the thumbnail).

!!! note "Casing & the switcher"
    The road **casing** is baked from the chosen `theme` and does **not** dynamically re-swap
    when you switch base maps in the browser (a static folium map can't re-style on the fly).
    Pick `theme="dark"` if you'll mostly view dark/satellite, `theme="light"` for light tiles.
    (Live casing-swap on base-map change is a possible future enhancement.)

- The **`carto`** palette uses its own coloured casing regardless of theme.
- For `satellite`, the spec recommends a tile filter `saturate(0.80) brightness(0.90)` to calm
  the imagery — it's recorded on the theme (`Theme.tile_filter`) but folium doesn't apply
  per-layer CSS automatically; apply it in your page CSS if you embed the map.
- lonboard maps use the Carto **Positron**/**DarkMatter** basemaps for `light`/`dark`
  (satellite falls back to dark).

## Custom themes

`THEMES` is a dict of `Theme` objects — add your own:

```python
from roadstyle.themes import THEMES, Theme
THEMES["night"] = Theme("night", casing="dark",
                        folium_tiles="CartoDB dark_matter", folium_attr=None,
                        lonboard_basemap="DarkMatter")
```
