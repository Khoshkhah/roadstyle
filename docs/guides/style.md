# Style the roads

<p class="lead">Pick a palette and a base map, switch the map's controls on or off, show bridges in 3D, and keep only the road classes you want.</p>

<iframe src="../../maps/first_map.html" loading="lazy" title="A map with the default style" class="rs-demo"></iframe>

=== "Python"

    ```python
    import geopandas as gpd
    import roadstyle as rs

    edges = gpd.read_file("edges.gpkg")
    rs.render_edges(edges, palette="carto", basemap="ofm_positron").save("map.html")   # the default is amber on OpenFreeMap Positron
    ```

=== "Command line"

    ```bash
    roadstyle edges.gpkg --palette carto --basemap ofm_positron -o map.html
    ```

## Palettes

A palette sets each road class's colour, width and casing.

- `amber`: orange, yellow and green main roads, slate-grey streets. The default: every class stands out on a light base map.
- `carto`: the muted colours of the OpenStreetMap standard map.
- `highsat`: bright, high contrast.
- `mono`: shades of grey. Use it under your own data colours.

<div class="grid" markdown>

![amber, the default](../img/gallery/road_look.jpg)

![amber on the blank canvas](../img/gallery/basemap_blank.jpg)

</div>

To change a class's colour or add a palette, see [Settings & palettes](../reference/settings.md).

## Base maps

`basemap=` sets the background, `basemaps=` sets the list in the base-map switcher (bottom-right).

```python
rs.render_edges(edges, basemap="ofm_dark", basemaps=["ofm_dark", "ofm_positron", "satellite"])
rs.render_edges(edges, palette="mono", basemap="blank")      # no tiles: works offline
```

The seven base maps (none needs a key):

- `ofm_liberty` and `ofm_positron` (the default): OpenFreeMap vector styles. Their dark twins are `ofm_fiord` and `ofm_dark`.
- `osm`: OpenStreetMap.
- `esri_gray` (dark twin `esri_dark_gray`) and `esri_street`: Esri.
- `satellite`: Esri World Imagery.
- `blank` (dark twin `blank_dark`): a plain canvas with no network requests, so the file works offline.

A page that asks for a base map that was removed (see the CHANGELOG) gets `ofm_positron` and a warning. See
[Base maps & API keys](../reference/settings.md#base-maps-api-keys).

## Map controls

Labels, one-way arrows and the base-map switcher are all on by
default. Turn any of them off:

```python
rs.render_edges(edges, labels=False, arrows=False, filter_control=False, basemap_switcher=False)
```

On the command line: `--no-labels`, `--no-arrows`, `--no-filter`, `--no-basemap-switcher`.

## 3D bridges

`view_3d=True` tilts the camera and draws bridges as raised decks, so you can see the roads that
pass under them. Every map also has a 2D/3D button. Below zoom 16 bridges draw flat.

```python
rs.render_edges(edges, view_3d=True)                         # CLI: --view-3d
```

![Bridges in 3D](../img/gallery/bridges_3d.jpg)

## Bridges and tunnels in 2D

- A **bridge** has a slate casing (`bridge_casing_color`) and a soft **shadow** (`bridge_shadow`). The shadow is blurred evenly around the bridge. Each part of the bridge casts it at its
  own casing number, so it lies on what the bridge crosses, never on its own road. Hiding the bridges hides it too.
- A **tunnel** fades toward a colour (`tunnel_toward`, default Sand): its fill, names, arrows and attached items. `tunnel_strength`
  (default 60) sets how much: 0 gives the normal colours, 100 the full tunnel colours. Its casing has two dashed colours
  (`tunnel_palette`, default *Graphite + silver*).
- To try other values, `tunnel_control=True` adds a *Tunnels* box with its steps and colour list. `rsSetTunnelStyle({strength, palette,
  ratio})` does the same from your page.

Which road is drawn over which comes from the drawing levels: [Which road is on top](levels.md).

## Keep or drop road classes

```python
rs.highway_types(edges)                                      # the classes in your data
rs.render_edges(edges, include=["motorway", "trunk", "primary", "secondary"])
rs.render_edges(edges, exclude=["service", "footway", "path", "cycleway"])
rs.render_edges(edges, minzoom=True)                         # hide minor classes when zoomed out
```

`include` and `exclude` also keep or drop the `*_link` ramps of each class (`match_links=True`).
`minzoom` can also be a dict such as `{"residential": 14}` to change the zoom for some classes.

## Your own road classes

For a class column that is not OSM `highway` (say NVDB functional classes), give a palette file with a colour and widths for each class and
style by that column: `render_edges(edges, highway_col="functional_road_class", palette="nvdb")`. How a palette file looks:
[Settings & palettes](../reference/settings.md).

**See also:** [Every parameter](../reference/parameters.md) · [Settings & palettes](../reference/settings.md) · [Gallery](../gallery.md) · [JavaScript API](../reference/javascript.md) (`rsSetBasemap`, `rsSetClasses`, `rsSetView3D`)
