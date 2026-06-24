# Examples

Prefer reading in the browser? The **[Manual](manual.md)** walks through the core workflow with the
**live map embedded after each step**, and the **[Tutorial](tutorial.md)** covers everything below on
one page. The notebooks here are the same material, runnable.

A set of small, focused, runnable notebooks in [`notebooks/`](https://github.com/Khoshkhah/roadstyle/tree/main/notebooks).
Each teaches one topic and is self-contained — open it in Jupyter and run top to bottom. They use the
bundled sample data (`notebooks/data/sundbyberg_edges.gpkg`, ~4,000 real road edges) and write any
output to `notebooks/output/` (git-ignored).

| Notebook | What you'll learn |
|---|---|
| **01 · Quickstart** | Load edges → `render_edges` → `.save()`. Themes (`light`/`dark`/`satellite`) and palettes (`highsat`/`carto`). |
| **02 · Data-driven styling** | Colour roads by your own data — categorical (`color_by` + `colors`) and numeric (`color_by` + `cmap` + `width_by`) with legends. |
| **03 · Filtering & highlighting** | `highway_types`, `include`/`exclude`, and a neon `selected=` highlight. |
| **04 · Outputs for the web** | The canonical JSON spec (`to_spec`), `to_geojson`, `save_spec`/`load_spec`, `to_html`, `to_iframe`, `save`. |
| **05 · Embedding with `roadstyle.js`** | The decoupled path: Python bakes a JSON spec; the bundled `roadstyle.js` draws it in your own page with a custom sidebar. Generates a self-contained `output/web/` folder. |
| **06 · Customizing the look** | Base maps + switcher, and custom colour vocabularies via `color_by` + `colors`. |
| **07 · Large datasets (lonboard)** | The same API on the GPU/WebGL backend for big edge sets. |
| **08 · Loading data** | Every input `render_edges`/`to_spec` accept: GeoDataFrame, file path, GeoJSON (+ spec), pyarrow Table, DuckDB. |

Start at **01** if you're new; jump to **05** if your goal is embedding a roadstyle map in a website.

## Example scripts

Self-contained scripts in [`examples/`](https://github.com/Khoshkhah/roadstyle/tree/main/examples) —
run any of them to write an HTML file you can open. They use the same bundled sample edges (with a
couple of seeded columns where the demo needs data).

| Script | What it shows |
|---|---|
| **`recolor_web_backend.py`** | Switchable data-driven colouring on the **`web` backend** (`color_options` + a *Colour by* dropdown), plus a **custom panel** wired through `window.rsSetColorField` / the `rs:colorchange` event. |
| **`overlays_web.py`** | Extra **overlay layers** — synthetic TAZ zones (under the roads) + POI circles (on top), both clickable, with a *Layers* toggle. |
| **`recolor_custom_panel.py`** | The same switchable colouring on the **roadstyle.js spec page**, driven by a custom `addPanel` + the `setColorField` / event-bus API. |

The generated pages used in the [Manual](manual.md) are built by
[`docs/build_maps.py`](https://github.com/Khoshkhah/roadstyle/blob/main/docs/build_maps.py).
