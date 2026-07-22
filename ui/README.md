# UI templates

Copyable starting points for building your own frontend over a roadstyle web map. The library
keeps **data and logic** (the baked features, the `window.rs*` API, the `rs:*` events); the UI
layer is deliberately yours — these templates are scaffolding, not part of the package.

Each template is a plain **HTML/CSS/JS fragment** (no frameworks, no build step, no server)
that gets injected before `</body>` of a saved map and talks to it only through the public API:

| template | what it shows |
|---|---|
| [`dashboard/`](dashboard/) | A sidebar dashboard: query box (`rsQuery`), verb buttons (`rsFilter` / `rsColor` / `rsHighlight`), a clickable results table (`rsGetProps` + `rsSelect`), a detail panel fed by `rs:select`, and a base-map select built from `RS_BASEMAPS`. |
| [`studio/`](studio/) | **roadstyle studio** — a Streamlit workbench (`pip install streamlit`, then `streamlit run ui/studio/app.py`), two pages: **Map** (the whole library behind a few knobs, with the live map next to the exact `render_edges` code it represents) and **Dashboard** (the same knobs, but the product is the `dashboard/` sidebar page — pick the base maps and colour-by columns, preview it live, download `dashboard.html`). Both have a download button for the self-contained HTML and a **Vector tiles** toggle (embedded-PMTiles roads for big networks, when the `tiles` extra is installed). The gentlest way to work with — and demo — the library. |

## Using a template

```bash
python ui/dashboard/build.py path/to/edges.gpkg     # default: the bundled Södermalm sample
# -> ui/dashboard/dashboard.html — self-contained, double-click to open
python ui/dashboard/build.py big_network.gpkg --tiles   # ~10⁵ edges: embedded-PMTiles roads
```

`--tiles` needs `pip install "roadstyle[tiles]"`; the sidebar is unchanged — it only talks
through the `rs*` API, which works identically over inline or tiled roads.

Or inject the fragment yourself around any map you render:

```python
m = rs.render_edges(edges, basemap_switcher=False, filter_control=False, road_popup=False)
page = m.html.replace("</body>", open("ui/dashboard/sidebar.html").read() + "</body>", 1)
```

The fragment file is the template — edit its CSS/HTML freely; as long as you only call the
documented `rs*` functions and listen to `rs:*` events, library upgrades won't break it.
The full API reference lives in [`docs/web-backend.md`](../docs/web-backend.md).
