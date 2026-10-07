# Gallery

<p class="lead">One look per entry: the keywords that make it, and a real screenshot.</p>

Every entry uses the bundled Södermalm sample:

```python
import geopandas as gpd
import roadstyle as rs
edges = gpd.read_file("ui/studio/samples/sodermalm_driving.geojson")
```

## The defaults

```python
rs.render_edges(edges)                # amber palette on Voyager
```

![amber on voyager](img/gallery/amber_voyager.png)

## High saturation

```python
rs.render_edges(edges, palette="highsat")
```

![highsat on voyager](img/gallery/highsat_voyager.png)

## OSM-Carto on Positron

```python
rs.render_edges(edges, palette="carto", basemap="positron")
```

![carto on positron](img/gallery/carto_positron.png)

## Dark

```python
rs.render_edges(edges, basemap="dark_matter")
```

![dark matter](img/gallery/amber_dark.png)

## Blank canvas (offline)

```python
rs.render_edges(edges, palette="mono", basemap="blank", basemap_switcher=False)
```

![mono on blank](img/gallery/mono_blank.png)

## Satellite

```python
rs.render_edges(edges, basemap="satellite")
```

![satellite](img/gallery/satellite.png)

## Colour by data

```python
rs.render_edges(edges, color_by="maxspeed_kmh", cmap="plasma", basemap="positron")
```

![coloured by maxspeed](img/gallery/speed_datadriven.png)

More in [Colour by your data](guides/colour.md).

## 3D bridges

```python
rs.render_edges(edges, view_3d=True)
```

![3d bridges](img/gallery/bridges_3d.png)

## Street View window

```python
rs.render_edges(edges)                # the Street View button is on by default
```

![street view window](img/gallery/street_view_window.png)

## Street View beside the map

```python
rs.render_street_view(edges)          # CLI: roadstyle edges.gpkg --page street-view
```

![map and street view side by side](img/gallery/street_view_side.png)

## Street View below the map

```python
rs.render_street_view(edges, layout="below")
```

![map with street view under it](img/gallery/street_view_below.png)

More in [Google Street View](guides/street-view.md).

## Dashboard

```python
rs.render_dashboard(edges).save("dashboard.html")   # CLI: --page dashboard
```

![dashboard](img/gallery/dashboard.png)

More in [Dashboards & JavaScript](guides/dashboards.md).

## Studio

```bash
pip install "roadstyle[studio]" && roadstyle studio
```

![roadstyle studio](img/gallery/studio.png)

More in [Studio](studio.md).
