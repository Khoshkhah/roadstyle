# Gallery

<p class="lead">Each picture shows one feature, with the line of code that makes it.</p>

The pictures are Södermalm (Stockholm) and Monaco, from OpenStreetMap:

```python
import geopandas as gpd
import roadstyle as rs
edges = gpd.read_file("ui/studio/samples/sodermalm_driving.geojson")   # Södermalm; Monaco is duckOSM's Monaco build
```

## The road map look

The default map has outlines, street names along the roads and one-way arrows.

```python
rs.render_edges(edges)
```

![Södermalm at street zoom: Hornsgatan and the streets around Mariatorget, with their names and one-way arrows](img/gallery/road_look.jpg)

## Bridges and tunnels

A bridge has a slate outline and a soft shadow on the roads under it. A tunnel fades and has a dashed outline. roadstyle works out the drawing order.

```python
rs.render_edges(edges)
```

![Monaco: a bridge with its shadow over a roundabout, a dashed tunnel under both](img/gallery/bridges_tunnels.jpg)

More in [Which road is on top](guides/levels.md).

## Stacked roads

Roads, ramps and tunnels cross at several levels, and each one is drawn in the right order. To fix a place by hand, use the
[level editor](guides/levels.md#edit-the-levels).

```python
rs.render_edges(edges)
```

![Monaco: tunnels, ramps and a roundabout crossing at several levels](img/gallery/stacked_roads.jpg)

## Colour by your data

Any column, with a legend.

```python
rs.render_edges(edges, color_by="maxspeed_kmh", cmap="YlOrRd", legend=True)
```

![Södermalm coloured by speed limit, light yellow to dark red, with the legend](img/gallery/colour_by_data.jpg)

More in [Colour by your data](guides/colour.md).

## 3D bridges

Bridges are raised decks over the roads under them. A map page has a 2D/3D button. A dashboard has the `navigate` button, and its box has a tilt slider.

```python
rs.render_edges(edges, view_3d=True)
```

![Södermalm in 3D: a raised bridge deck over the roads below](img/gallery/bridges_3d.jpg)

## Street View

Click a road, then click the Street View button. A window that you can move shows Google Street View of that road.

```python
rs.render_edges(edges)                # the Street View button is on by default
```

![Ringvägen selected on a satellite base map, with the Street View window showing it](img/gallery/street_view.jpg)

More in [Google Street View](guides/street-view.md).

## Google 3D

A window next to the map shows the photorealistic 3D view of Google. The two cameras move together. A clicked road is drawn in
the 3D view. This needs a [Google key](guides/google-key.md). To try it, use the [live map](maps/live.html).

```python
rs.render_edges(edges, google_3d=True)
```

![Götgatan at Medborgarplatsen: the street selected on the map, and the same street in the Google 3D window](img/gallery/google_3d.jpg)

More in [Google 3D](guides/google-3d.md).

## Ready-made pages

One call makes the standard dashboard: a panel at the left and a toolbox at the right edge (navigate, base map, roads, colour and legend, settings).
The panel starts empty: the call above adds the query box and the road card. The pictures show a road selected. The map starts on the base map that you give. The pictures use OpenFreeMap Positron and OpenFreeMap Fiord (the dark theme).

```python
rs.render_dashboard(
    edges, basemap="ofm_positron",
    color_options={"Class": {}, "Speed": {"color_by": "maxspeed_kmh"}},
    dashboard={"panel": {"sections": [{"id": "q", "part": "query"}, {"id": "road", "part": "road_card"}]}},
)
```

![The dashboard on a desktop: Monaco, a road selected in the panel at the left, and the toolbox at the right edge](img/gallery/dashboard.jpg)

![The dashboard in the dark theme on the OpenFreeMap Fiord base map](img/gallery/dashboard_dark.jpg)

<div style="max-width:300px" markdown>

![The dashboard on a phone: the one-row bar at the top, the map, and the panel as a bottom sheet](img/gallery/dashboard_phone.jpg)

</div>

More in [Dashboards](guides/dashboards.md).

## Mono palette

Shades of grey on a blank canvas: a quiet base under your own data colours. The other palettes are `amber` (the default), `carto` and `highsat`.

```python
rs.render_edges(edges, palette="mono", basemap="blank")
```

![All of Monaco in the mono palette on the blank canvas](img/gallery/palette_mono.jpg)

## Base maps

The same map on another background. The base maps are OpenFreeMap Positron (the default), OpenFreeMap Liberty, OpenStreetMap, Esri Gray, Esri Streets, Esri Satellite and a blank canvas that works offline.

```python
rs.render_edges(edges, basemap="blank")
```

![Monaco in 3D on the blank canvas](img/gallery/basemap_blank.jpg)

More in [Style the roads](guides/style.md).
