![roadstyle — opinionated road cartography and interactive map styling for Python](https://raw.githubusercontent.com/Khoshkhah/roadstyle/main/assets/roadstyle-banner.svg)

[![PyPI](https://img.shields.io/pypi/v/roadstyle.svg)](https://pypi.org/project/roadstyle/)
[![Tests](https://github.com/Khoshkhah/roadstyle/actions/workflows/test.yml/badge.svg)](https://github.com/Khoshkhah/roadstyle/actions/workflows/test.yml)
[![Docs](https://img.shields.io/badge/docs-khoshkhah.github.io%2Froadstyle-indigo.svg)](https://khoshkhah.github.io/roadstyle/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/Khoshkhah/roadstyle/blob/main/LICENSE)

Turn a GeoDataFrame of road edges into **one styled, interactive, offline HTML map**, with real
road cartography (casing and fill, per-zoom widths, street names, one-way arrows, tunnels and
bridges, optional 3D) and a JavaScript API for your own dashboard.

![A roadstyle map of Södermalm, Stockholm, in 3D: bridge decks lifted above the streets, roads coloured by class](https://raw.githubusercontent.com/Khoshkhah/roadstyle/main/docs/img/hero.jpg)

## Install

```bash
pip install roadstyle              # core
pip install "roadstyle[all]"       # + studio, numeric ramps, vector tiles, lonboard, DuckDB, …
```

Python ≥ 3.10. Individual extras and the dev setup: [Usage → Install](https://khoshkhah.github.io/roadstyle/usage/#install).

## Quickstart

```python
import geopandas as gpd
import roadstyle as rs

edges = gpd.read_file("edges.gpkg")        # LineStrings + a `highway` column, any CRS
rs.render_edges(edges).save("map.html")    # open map.html, no server needed
```

```python
rs.render_edges(edges, basemap="dark_matter", view_3d=True)            # dark, 3D bridge decks
rs.render_edges(edges, palette="carto", basemap="positron")            # the classic OSM look
rs.render_edges(edges, color_by="aadt", cmap="viridis")                # colour by your data
rs.render_edges(edges, palette="mono", color_options={                 # several colourings,
    "Traffic": {"color_by": "aadt", "cmap": "viridis"},                #   switched in the browser
    "Speed":   {"color_by": "maxspeed_kmh", "cmap": "magma"}})
rs.render_edges(edges, tiles=True)                                     # 100k+ edges
rs.render_dashboard(edges).save("dashboard.html")                      # map + query sidebar
```

No Python? `roadstyle edges.gpkg -o map.html --basemap dark_matter`, or click through it in the
workbench: `pip install "roadstyle[studio]" && roadstyle studio`.

## What goes in

Only `geometry` and `highway` are required. Other columns switch features on:

| Column | Powers |
|---|---|
| `geometry` (LineString, any CRS) | the edges. Each edge is **directed**: a two-way road is two edges with reversed geometry |
| `highway` (OSM class) | colour, width, casing, draw order |
| `name` | street labels, popup title |
| `oneway` | direction arrows |
| `bridge` / `tunnel` / `layer` | grade separation: tunnels below, bridges on decks above |
| `edge_id` | popups; 64-bit ids stay exact |
| anything else | shown in the popup, queryable from JavaScript |

[duckOSM](https://github.com/Khoshkhah/duckOSM) (`duckosm export-gis`) exports exactly this.

## Drive it from JavaScript

The saved page exposes `window.rs*` functions and `rs:*` events:

```js
const ids = rsQuery(p => p.maxspeed_kmh > 30); // feature ids whose properties match
rsColor(ids, "#ff00aa");  rsFocus(ids);       // paint them, fit the camera
document.addEventListener("rs:select", e => console.log(e.detail.properties));
```

Full API: [web backend → JavaScript API](https://khoshkhah.github.io/roadstyle/web-backend/#the-javascript-api-windowrs).

## For AI coding agents

- [`skills/roadstyle/SKILL.md`](https://github.com/Khoshkhah/roadstyle/blob/main/skills/roadstyle/SKILL.md): a
  skill for agents that *use* roadstyle (the one call, the data contract, the JS API, the traps).
  Install it for Claude Code:
  ```bash
  mkdir -p ~/.claude/skills/roadstyle && curl -fsSL -o ~/.claude/skills/roadstyle/SKILL.md \
    https://raw.githubusercontent.com/Khoshkhah/roadstyle/main/skills/roadstyle/SKILL.md
  ```
- [`AGENTS.md`](https://github.com/Khoshkhah/roadstyle/blob/main/AGENTS.md): for agents working *on* this repo.
- [`llms.txt`](https://khoshkhah.github.io/roadstyle/llms.txt): the docs site as a link list for LLMs.

## Documentation

**[khoshkhah.github.io/roadstyle](https://khoshkhah.github.io/roadstyle/)**:
[gallery](https://khoshkhah.github.io/roadstyle/gallery/) ·
[every parameter](https://khoshkhah.github.io/roadstyle/parameters/) ·
[web backend & JS API](https://khoshkhah.github.io/roadstyle/web-backend/) ·
[palettes & settings](https://khoshkhah.github.io/roadstyle/palettes/) ·
[base maps & API keys](https://khoshkhah.github.io/roadstyle/usage/#base-maps-api-keys) ·
[web vs folium vs lonboard](https://khoshkhah.github.io/roadstyle/engines/) ·
[vs .explore() / kepler.gl](https://khoshkhah.github.io/roadstyle/comparison/) ·
[changelog](https://github.com/Khoshkhah/roadstyle/blob/main/CHANGELOG.md)

## License

[MIT](https://github.com/Khoshkhah/roadstyle/blob/main/LICENSE). Base-map tiles come from
third-party services (CARTO, OSM, Esri) with their own attribution and terms.
