# Gallery

Every look below is the bundled **Södermalm driving sample**
(`ui/studio/samples/sodermalm_driving.geojson`) — one `gpd.read_file(...)` call, then
`render_edges` with the keywords shown. Thumbnails are real `rs.snapshot()` screenshots
(regenerate with `python docs/build_gallery.py`).

```python
import geopandas as gpd
import roadstyle as rs
edges = gpd.read_file("ui/studio/samples/sodermalm_driving.geojson")
```

## The defaults

`highsat` palette on the Voyager base — what you get with no arguments.

```python
rs.render_edges(edges)
```

![highsat on voyager](img/gallery/highsat_voyager.png)

## OSM-Carto on Positron

The classic muted openstreetmap-carto tones.

```python
rs.render_edges(edges, palette="carto", basemap="positron")
```

![carto on positron](img/gallery/carto_positron.png)

## Dark

```python
rs.render_edges(edges, basemap="dark_matter")
```

![dark matter](img/gallery/highsat_dark.png)

## Blank canvas (offline)

`mono` palette on the tile-less `blank` base map — zero network requests, print-clean.

```python
rs.render_edges(edges, palette="mono", basemap="blank", basemap_switcher=False)
```

![mono on blank](img/gallery/mono_blank.png)

## Satellite

```python
rs.render_edges(edges, basemap="satellite")
```

![satellite](img/gallery/satellite.png)

## Data-driven colour

Any numeric column → a colormap + legend (categorical mappings work too, see
[Palettes](palettes.md)).

```python
rs.render_edges(edges, color_by="maxspeed_kmh", cmap="plasma", legend=True, basemap="positron")
```

![coloured by maxspeed](img/gallery/speed_datadriven.png)

## 3D bridges

`view_3d=True`: tilted camera and extruded, ramped, black-cased bridge decks — look *under* a
bridge and see the roads passing beneath. Below zoom 16 bridges draw as classic flat cased lines
(`bridge_decks.flat_below`).

```python
rs.render_edges(edges, view_3d=True)
```

![3d bridges](img/gallery/bridges_3d.png)

## The sidebar dashboard (UI template)

Every built-in control replaced by plain HTML driving the [JS API](web-backend.md#the-javascript-api-windowrs) —
query box, verb buttons, clickable results table, detail panel. Copy it from
[`ui/dashboard/`](https://github.com/Khoshkhah/roadstyle/tree/main/ui/dashboard).

```bash
python ui/dashboard/build.py your_edges.gpkg            # add --tiles for ~10⁵-edge networks
```

![dashboard](img/gallery/dashboard.png)

## roadstyle studio (Streamlit workbench)

The whole library behind a few knobs — live map on the right, the exact `render_edges` code for
the current state below it, and a download button for the self-contained HTML. Three pages — **Map**,
**Dashboard**, **Report** — the gentlest introduction to the library. See the
[Studio](studio.md) page for the full walkthrough.

```bash
pip install "roadstyle[studio]" && roadstyle studio
```

![roadstyle studio](img/gallery/studio.png)
