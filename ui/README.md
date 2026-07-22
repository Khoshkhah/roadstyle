# UI templates

Copyable starting points for building your own frontend over a roadstyle web map. The library
keeps **data and logic** (the baked features, the `window.rs*` API, the `rs:*` events); the UI
layer is deliberately yours — these templates are scaffolding, not part of the package.

Each template is a plain **HTML/CSS/JS fragment** (no frameworks, no build step, no server)
that gets injected before `</body>` of a saved map and talks to it only through the public API:

| template | what it shows |
|---|---|
| [`dashboard/`](dashboard/) | A sidebar dashboard: query box (`rsQuery`), verb buttons (`rsFilter` / `rsColor` / `rsHighlight`), a clickable results table (`rsGetProps` + `rsSelect`), a detail panel fed by `rs:select`, and a base-map select built from `RS_BASEMAPS`. |
| [`studio/`](studio/) | **roadstyle studio** — a Streamlit workbench (`pip install streamlit`, then `streamlit run ui/studio/app.py`): the whole library behind eight knobs, with the live map next to the exact `render_edges` code it represents and a download button for the self-contained HTML. The gentlest way to work with — and demo — the library. |

## Using a template

```bash
python ui/dashboard/build.py path/to/your.duckdb    # or an edges .gpkg
# -> ui/dashboard/dashboard.html — self-contained, double-click to open
```

Or inject the fragment yourself around any map you render:

```python
m = rs.render_edges(edges, basemap_switcher=False, filter_control=False, road_popup=False)
page = m.html.replace("</body>", open("ui/dashboard/sidebar.html").read() + "</body>", 1)
```

The fragment file is the template — edit its CSS/HTML freely; as long as you only call the
documented `rs*` functions and listen to `rs:*` events, library upgrades won't break it.
The full API reference lives in [`docs/web-backend.md`](../docs/web-backend.md).
