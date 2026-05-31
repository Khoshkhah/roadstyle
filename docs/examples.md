# Examples

Prefer reading in the browser? The **[Tutorial](tutorial.md)** walks through everything below on one
page. The notebooks here are the same material, runnable.

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
