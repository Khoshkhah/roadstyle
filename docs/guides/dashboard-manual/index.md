# Dashboard manual

<p class="lead">A dashboard is a map with a toolbox and a side panel. This manual has two chapters: make the page from Python, then control it from JavaScript.</p>

| Chapter | What you learn | Result on the page |
|---|---|---|
| [Python SDK](python.md) | The call `rs.render_dashboard`, its keywords, and every key of `dashboard=` | Each example shows the page that it makes |
| [JavaScript](javascript.md) | `window.rs`: find roads, select, filter, color, add to the panel and the toolbox, live data, events | Each block has a **Run** button, and the map stays in view |

## What a dashboard has

A dashboard is the map, the toolbox and the panel. The table shows where to set each topic from Python and from JavaScript. The options are in [Dashboard options](../../reference/parameters.md#dashboard-options).

| Topic | What it is | Python | JavaScript |
|---|---|---|---|
| Panel | The side panel. It starts empty; the page adds sections (the query part, the road card part, its own HTML) | `dashboard={"panel": ...}` | `rs.sections` |
| Toolbox | The bar of tools at the edge of the window | `dashboard={"toolbar": ...}` | `rs.tools` |
| Legend | The legend box of the toolbox | `dashboard={"legend": ...}` | `rs.legend`, `rs.colorModes` |
| Credits | The credits box of the toolbox | `dashboard={"credits": ...}` | none |
| Windows | Street View and Google 3D | `street_view=`, `google_3d=`, `dashboard={"windows": ..., "google_3d": ...}` | `rsSetStreetView`, `rsSetGoogle3D` |
| Boundary | The dashed outline of the area, with its shade and its camera limit | `boundary=`, `dashboard={"boundary": ...}` | none |
| Phone form | The bar at the top and the panel as a bottom sheet. The page turns to it by itself | none | `rs.sheet`, `rs.freeArea` |
| Live data | Colors and widths from your own numbers | `live_data=True` | `rs.setData` |
| Events | Messages that the page sends when something changes | none | `rs.on`, `document.addEventListener` |

**See also:** [Dashboard layout](../dashboard-layout.md) · [Add to the panel](../dashboard-panel.md) · [Live data](../live-data.md) · [Every parameter](../../reference/parameters.md) · [JavaScript API](../../reference/javascript.md)
