# roadstyle

<p class="lead">Turn a road network into a styled, interactive HTML map that works offline, with Google Street View and a JavaScript API.</p>

<div class="rs-hero" markdown>
![A roadstyle map of Monaco in 3D: bridges, tunnels and roundabouts drawn in order, Rue de la Colle selected, and the floating Street View window showing it](img/hero.jpg)
</div>

```bash
pip install roadstyle
```

```python
import geopandas as gpd
import roadstyle as rs

edges = gpd.read_file("edges.gpkg")        # road edges with a `highway` column
rs.render_edges(edges).save("roads.html")  # one self-contained file, opens offline
```

## What you can do

<div class="grid cards" markdown>

-   :material-palette:{ .lg .middle } **Style the roads**

    ---

    Palettes, base maps, labels, arrows and 3D bridges.

    [:octicons-arrow-right-24: Style the roads](guides/style.md)

-   :material-chart-line:{ .lg .middle } **Colour by your data**

    ---

    Categorical or numeric columns, legends, switchable colourings.

    [:octicons-arrow-right-24: Colour by your data](guides/colour.md)

-   :material-layers-outline:{ .lg .middle } **Add your own layers**

    ---

    Zones, points and lines under or over the roads.

    [:octicons-arrow-right-24: Add your own layers](guides/overlays.md)

-   :material-google-street-view:{ .lg .middle } **Google Street View**

    ---

    Click a road and see it, in a floating window or beside the map.

    [:octicons-arrow-right-24: Google Street View](guides/street-view.md)

-   :material-map-marker-path:{ .lg .middle } **Big networks**

    ---

    Vector tiles in the file, or the GPU backend for millions of edges.

    [:octicons-arrow-right-24: Big networks](guides/big-networks.md)

-   :material-view-dashboard-outline:{ .lg .middle } **Dashboards & JavaScript**

    ---

    Ready-made pages, and `window.rs*` calls to drive the map.

    [:octicons-arrow-right-24: Dashboards & JavaScript](guides/dashboards.md)

-   :material-web:{ .lg .middle } **Put it on a website**

    ---

    An iframe, a JSON spec, or `roadstyle.js` on your own map.

    [:octicons-arrow-right-24: Put it on a website](guides/website.md)

</div>

## When to use roadstyle

- **Instead of geopandas `.explore()`** when the output is a road map you care about: casings,
  per-class widths, one-way arrows, bridges over tunnels. `.explore()` draws one flat line.
- **Instead of prettymaps** when you need an interactive web map or colour by data (flow, speed).
  prettymaps makes static images.
- **Instead of kepler.gl** for road cartography. kepler.gl is a general exploration GUI; its roads
  are flat strokes with no labels or arrows.
- For a quick look at any geometry, those tools are fine; roadstyle is for roads.

## Built on

- **[MapLibre GL JS](https://maplibre.org/)** (BSD-3-Clause) draws every web map: roadstyle writes its style and
  data, and a copy of MapLibre is inlined in each saved page so it opens offline.
- **[OpenStreetMap](https://www.openstreetmap.org/copyright)** data (© OpenStreetMap contributors, ODbL) and the
  **[openstreetmap-carto](https://github.com/gravitystorm/openstreetmap-carto)** style, whose road classes,
  colours and widths roadstyle follows.
- **[HiGHS](https://highs.dev/)**, through [SciPy](https://scipy.org/), solves which road is drawn on top.
- **[GeoPandas](https://geopandas.org/)** and **[Shapely](https://shapely.readthedocs.io/)** for the geometry;
  **[lonboard](https://developmentseed.org/lonboard/)** (deck.gl) and **[folium](https://python-visualization.github.io/folium/)**
  for the notebook back-ends.

[:material-image-multiple: Gallery](gallery.md) ·
[:material-book-open-variant: Reference](reference/parameters.md) ·
[:material-tune: Studio](studio.md) ·
[:material-github: GitHub](https://github.com/Khoshkhah/roadstyle) ·
[:material-package-variant: PyPI](https://pypi.org/project/roadstyle/) ·
[:material-history: Changelog](https://github.com/Khoshkhah/roadstyle/blob/main/CHANGELOG.md)
