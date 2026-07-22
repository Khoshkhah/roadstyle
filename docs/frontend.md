# Frontend integration

roadstyle is a **Python (backend) library**: you run it in Python and it produces maps or JSON.
There are three ways to get a roadstyle map onto a web frontend, from "zero JavaScript" to a
"full JS port". This page explains the options so you can pick the right one — see
[Embedding in a website](embedding.md) for the copy-paste snippets.

## The three paths

| Path | Who computes the style | Python at runtime? | Effort | Use when |
|---|---|---|---|---|
| **1. Baked HTML / iframe** | Python (once, ahead of time) | No (pre-generated file) | none | a static site, a report, a quick embed |
| **2. JSON API** | Python (per request) | Yes (a server) | small | a live app whose data changes |
| **3. `roadstyle.js` (JS port)** | The browser (JavaScript) | No | large | fully client-side, no Python anywhere |

All three already share one thing: roadstyle bakes each road's resolved style into per-feature
`__rs_*` properties (see [embedding](embedding.md)), so the browser side never needs roadstyle's
styling logic — *except* path 3, which reimplements that logic in JS on purpose.

---

## Path 1 — Baked HTML / iframe (no JavaScript)

Python writes a finished, self-contained map; you drop it into a page. **No frontend code, no
server.** Best for static sites, dashboards exported ahead of time, or a quick share.

```python
import roadstyle as rs
rs.save(edges, "roads.html", color_by="aadt", cmap="viridis")     # standalone page
html = rs.to_iframe(edges, color_by="aadt", cmap="viridis")        # <iframe> string
```
```html
<iframe src="roads.html" style="width:100%;height:600px;border:0;"></iframe>
```

Trade-off: the map is a snapshot — to reflect new data you re-run Python and regenerate the file.

> **Want a finished MapLibre map instead of a spec page?** `render_edges(backend="web").save(...)`
> writes a self-contained, zoom-correct MapLibre map (two-way lanes, grade separation, 3D
> bridges, offline) — also Path 1 (no server), but a rendered map rather than a `roadstyle.js`
> spec page. Its saved page is itself scriptable: a `window.rs*` API (setters for every control,
> id-set queries, `rs:*` events) lets your own HTML drive it, with copyable scaffolding in
> [`ui/`](https://github.com/Khoshkhah/roadstyle/tree/main/ui). See
> [MapLibre web backend](web-backend.md).

---

## Path 2 — JSON API (Python serves, JavaScript draws)

A small web endpoint calls `to_spec()` and returns the styled JSON; your browser map fetches it
and draws it. **Python still computes the styling; the browser only renders.** Best for a live
app where the data changes (filters, new uploads, fresh traffic).

```
Browser  ──GET /roads.json──▶  Python API  ──▶  roadstyle.to_spec(edges, ...)
Browser  ◀──── styled JSON ───  (a dict with geojson + __rs_* props + legend + basemap)
Leaflet / MapLibre / deck.gl draws it
```

Minimal example with FastAPI (Flask/Django are equivalent — just return the dict as JSON):

```python
# server.py
from fastapi import FastAPI
import geopandas as gpd
import roadstyle as rs

app = FastAPI()
edges = gpd.read_file("edges.gpkg")          # or load per request / from a DB

@app.get("/roads.json")
def roads(color_by: str = "aadt", cmap: str = "viridis"):
    return rs.to_spec(edges, color_by=color_by, cmap=cmap, basemap="dark_matter")
```

The browser then `fetch("/roads.json")` and renders with the Leaflet or MapLibre snippet from
[Embedding in a website](embedding.md). This is usually the **most practical** path: little code,
and roadstyle stays the single source of truth for the cartography.

---

## Path 3 — a true JavaScript *styling* port

> **Not to be confused with the bundled `roadstyle.js`.** roadstyle already ships a
> `roadstyle.js` — the renderer that `to_html` / `save` inline — but it *reads the baked `__rs_*`
> props* (it does **not** recompute styling), and it exposes a real JS API (`RoadStyleMap`: events,
> `setColorField`, `addPanel`). That's part of **Path 1** — see
> [Embedding → the RoadStyleMap JS API](embedding.md#the-roadstylemap-js-api-events-recolour-custom-panels).
> *This* Path 3 is the heavier, hypothetical thing below: porting the **styling logic** itself.

Reimplement the styling *logic* (palettes, the geometry sandwich, class→colour / numeric ramp
resolution) in JavaScript, so the browser computes styles itself with **no Python at runtime**.
This is a separate, standalone sub-project (e.g. an npm package), not something the Python library
emits.

```js
// hypothetical roadstyle.js
import { renderEdges, loadPalette } from "roadstyle";
const palette = await loadPalette("highsat.json");   // same JSON Python exports
renderEdges(map, geojson, { colorBy: "aadt", cmap: "viridis", palette });
```

What already makes this feasible (groundwork laid by the Python side):

- **Palette JSON** (`save_palette`) is a portable, language-neutral colour source — a JS port can
  load the *same* `highsat.json` and stay pixel-identical to Python.
- The **spec format** (`spec/1`) and the `__rs_*` property contract are documented and stable.
- The styling rules are small and self-contained (a palette lookup + the geometry sandwich + a
  numeric ramp), so a faithful port is tractable.

Trade-off: it's real, ongoing work to build and keep in sync with the Python library. Only worth
it if you need a fully client-side experience with no Python server at all.

---

## Recommendation

- **No frontend experience / static site** → **Path 1** (iframe). Zero JS.
- **A live app, data changes** → **Path 2** (JSON API). Small, practical, Python stays in charge.
- **Must be 100% client-side, no Python** → **Path 3** (`roadstyle.js`). A separate project to
  scope on its own.

Most projects should start at Path 1 or 2; reach for Path 3 only when a JS-only runtime is a hard
requirement.
