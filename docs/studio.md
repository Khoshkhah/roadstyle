# Studio

<p class="lead">A no-code workbench: load a road file, turn the knobs, and see the live map next to the exact code that makes it.</p>

```bash
pip install "roadstyle[studio]"   # adds streamlit
roadstyle studio                  # Streamlit flags pass through: roadstyle studio --server.port 8502
```

No clone needed: the studio ships in the package. The Södermalm sample networks (about 13 MB)
download on first run; in a git checkout it uses `ui/studio/samples/` directly.

![roadstyle studio: knobs on the left, the live map and the exact render_edges code on the right](img/gallery/studio.png)

## Three pages

| Page | Makes | Same as |
|---|---|---|
| **Map** | a map with its built-in controls | `rs.render_edges(edges, ...)` |
| **Dashboard** | the map with a query sidebar: query box, filter and colour buttons, results table, detail panel | `rs.render_dashboard(edges, ...)` |
| **Report** | the map with a stats sidebar: KPI cards, colour legend, layer and road-type filter, search, selected-road read-out | `rs.render_report(edges, ...)` |

Each page has a download button for the self-contained HTML, and shows the Python call so you can
copy it out when you outgrow the knobs.

## The Map knobs

- **Look**: palette, base map, 3D bridges, vector tiles (with the `tiles` extra).
- **Colour by data**: any column with a colour map.
- **Filter**: keep some road classes; hide minor ones when zoomed out.
- **Decorations**: street labels, one-way arrows.
- **Popup & hover**: the click popup (curated, chosen columns, side panel, all, off) and a hover tooltip.
- **Overlays**: zones, points or lines as extra layers.

![The report sidebar: KPI cards, colour legend, and a layer and road-type filter over a live map](img/gallery/report.png)

**See also:** [Dashboards & JavaScript](guides/dashboards.md) · [Every parameter](reference/parameters.md)
