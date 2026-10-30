# Gallery

<p class="lead">What roadstyle can do, one thing per picture, with the line of code that makes it.</p>

The pictures are Södermalm (Stockholm) and Monaco, from OpenStreetMap:

```python
import geopandas as gpd
import roadstyle as rs
edges = gpd.read_file("ui/studio/samples/sodermalm_driving.geojson")   # Södermalm; Monaco is duckOSM's Monaco build
```

## The road map look

Outlines, street names along the roads and one-way arrows, out of the box.

```python
rs.render_edges(edges)
```

![Södermalm at street zoom: Hornsgatan and the streets around Mariatorget, with their names and one-way arrows](img/gallery/road_look.jpg)

## Bridges and tunnels

A bridge has a slate outline and a soft shadow on what it crosses; a tunnel fades and has a dashed outline. The order is worked out for you.

```python
rs.render_edges(edges)
```

![Monaco: a bridge with its shadow over a roundabout, a dashed tunnel under both](img/gallery/bridges_tunnels.jpg)

More in [Which road is on top](guides/levels.md).

## Stacked roads

Roads, ramps and tunnels crossing each other at several levels, each drawn in the right order. Any place can be fixed by hand in the
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

Bridges as raised decks over the roads that pass under them. A map page has a 2D/3D button. A dashboard has the `navigate` button, whose box has a tilt slider.

```python
rs.render_edges(edges, view_3d=True)
```

![Södermalm in 3D: a raised bridge deck over the roads below](img/gallery/bridges_3d.jpg)

## Street View

Click a road, then the Street View button: Google Street View of that road, in a window you can move.

```python
rs.render_edges(edges)                # the Street View button is on by default
```

![Ringvägen selected on a satellite base map, with the Street View window showing it](img/gallery/street_view.jpg)

More in [Google Street View](guides/street-view.md).

## Google 3D

Google's photorealistic 3D view in a window next to the map. The two cameras move together, and a clicked road is drawn in
the 3D view. Needs a [Google key](guides/google-key.md). Try it on the [live map](maps/live.html).

```python
rs.render_edges(edges, google_3d=True)
```

![Götgatan at Medborgarplatsen: the street selected on the map, and the same street in the Google 3D window](img/gallery/google_3d.jpg)

More in [Google 3D](guides/google-3d.md).

## Ready-made pages

A dashboard with a query panel and a toolbox (navigate, base map, roads, colour and legend, settings), in one call.

```python
rs.render_dashboard(edges, color_options={"Class": {}, "Speed": {"color_by": "maxspeed_kmh"}})
```

![The dashboard page: Monaco's roads, the panel at the left with the selected road, and the toolbox next to it](img/gallery/dashboard.jpg)

More in [Dashboards & JavaScript](guides/dashboards.md).

## Mono palette

Shades of grey on a blank canvas: a quiet base under your own data colours. Other palettes: `amber` (the default), `carto`, `highsat`.

```python
rs.render_edges(edges, palette="mono", basemap="blank")
```

![All of Monaco in the mono palette on the blank canvas](img/gallery/palette_mono.jpg)

## Base maps

The same map on another background: Voyager (the default), Positron, Dark Matter, satellite, or a blank canvas that works offline.

```python
rs.render_edges(edges, basemap="blank")
```

<div class="grid" markdown>

![Monaco in 3D on Voyager](img/gallery/basemap_voyager.jpg)

![Monaco in 3D on the blank canvas](img/gallery/basemap_blank.jpg)

</div>

More in [Style the roads](guides/style.md).
