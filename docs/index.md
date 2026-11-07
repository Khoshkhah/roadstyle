# roadstyle

<p class="lead">roadstyle draws a road network as an interactive web map, from one Python call.</p>

- **One file.** The map is one HTML file with all its data in it. It opens from disk, offline, or from your website.
- **Roads that read like a real map.** Each road class has its own colour and width, with outlines, street names and one-way arrows.
  Bridges, tunnels and junctions are drawn in the correct order.
- **More than a map.** Add Street View, a dashboard with your own parts, SQL on your data, and questions to an AI in words.

<div class="rs-hero" markdown>
![A roadstyle map of Monaco in 3D: bridges, tunnels and roundabouts drawn in order, Rue de la Colle selected, and the floating Street View window showing it](img/hero.jpg)
</div>

[:material-map: Open the live map](maps/live.html){ .md-button .md-button--primary }

```bash
pip install roadstyle
```

```python
import geopandas as gpd
import roadstyle as rs

edges = gpd.read_file("edges.gpkg")        # road edges with a `highway` column
rs.render_edges(edges).save("roads.html")  # one file with all its data: it opens offline
```

## What you can do

<div class="grid cards" markdown>

-   :material-palette:{ .lg .middle } **Maps**

    ---

    Style the roads, colour them by your data, put bridges and tunnels in the correct order, add your own layers.

    [:octicons-arrow-right-24: Style the roads](guides/style.md)

-   :material-google-street-view:{ .lg .middle } **Street View and 3D**

    ---

    Click a road to see it in Google Street View, Panoramax or Mapillary, or in the 3D view of Google.

    [:octicons-arrow-right-24: Street View](guides/street-view.md)

-   :material-view-dashboard-outline:{ .lg .middle } **Dashboards**

    ---

    A map with a toolbox and a panel, from one Python call. Add parts to the panel, and control it from JavaScript.

    [:octicons-arrow-right-24: Dashboards](guides/dashboards.md)

-   :material-web:{ .lg .middle } **Use it elsewhere**

    ---

    Put the map on a website, or open its roads in another map app.

    [:octicons-arrow-right-24: On a website or in a map app](guides/website.md)

-   :material-brush-variant:{ .lg .middle } **Design**

    ---

    Change the look of a map in the page: a ready theme, the colours and widths of the road classes, the names and the base map.
    You see each change on the map at once.

    [:octicons-arrow-right-24: Edit the design of a map](guides/design-panel.md)

-   :material-robot-outline:{ .lg .middle } **AI**

    ---

    Ask questions about your data in words, in a dashboard, with a free key of your own. Or let an AI agent make maps for you, with no code.

    [:octicons-arrow-right-24: Ask](guides/ask.md) · [With AI agents](guides/agents.md)

-   :material-image-multiple-outline:{ .lg .middle } **Gallery**

    ---

    Pictures of each look, and a live map to try.

    [:octicons-arrow-right-24: Gallery](gallery.md)

-   :material-language-rust:{ .lg .middle } **Rust engine**

    ---

    The engine of the Python library: in the browser, as tiles and PMTiles, and on the command line.

    [:octicons-arrow-right-24: Rust engine](rust/index.md)

</div>

What changed in each version: [What is new](whats-new.md).

## When to use roadstyle

| In place of | Use roadstyle when |
|---|---|
| geopandas `.explore()` | you want a road map: outlines, a width for each class, one-way arrows, bridges over tunnels. `.explore()` draws one flat line. |
| prettymaps | you want a web map that you can click, or colours from your data. prettymaps makes pictures. |
| kepler.gl | you want a road map with names and arrows. kepler.gl draws roads as flat lines. |

For a quick look at other shapes, those tools are good. roadstyle is for roads.

## Built on

- **[MapLibre GL JS](https://maplibre.org/)** (BSD-3-Clause) draws each web map. roadstyle writes the style and the
  data, and each saved page has its own copy of MapLibre, so it opens offline.
- **[OpenStreetMap](https://www.openstreetmap.org/copyright)** data (© OpenStreetMap contributors, ODbL) and the
  **[openstreetmap-carto](https://github.com/gravitystorm/openstreetmap-carto)** style, whose road classes,
  colours and widths roadstyle follows.
- **[HiGHS](https://highs.dev/)**, through [SciPy](https://scipy.org/), is the optional Python solver of which road is on top. The default solver is in Rust.
- **[GeoPandas](https://geopandas.org/)** and **[Shapely](https://shapely.readthedocs.io/)** read and change the geometry.

[:material-image-multiple: Gallery](gallery.md) ·
[:material-book-open-variant: Reference](reference/parameters.md) ·
[:material-tune: Studio](studio.md) ·
[:material-github: GitHub](https://github.com/Khoshkhah/roadstyle) ·
[:material-package-variant: PyPI](https://pypi.org/project/roadstyle/) ·
[:material-history: Changelog](https://github.com/Khoshkhah/roadstyle/blob/main/CHANGELOG.md)
