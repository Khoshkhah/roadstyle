<p align="center">
  <img src="https://raw.githubusercontent.com/Khoshkhah/roadstyle/main/assets/roadstyle-logo.svg" alt="roadstyle logo" width="96">
</p>

<h1 align="center">roadstyle</h1>

<p align="center">Road maps for Python: styled, interactive, offline HTML maps of road networks, with Google Street View.</p>

<p align="center">
  <a href="https://pypi.org/project/roadstyle/"><img src="https://img.shields.io/pypi/v/roadstyle.svg" alt="PyPI"></a>
  <a href="https://github.com/Khoshkhah/roadstyle/actions/workflows/test.yml"><img src="https://github.com/Khoshkhah/roadstyle/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <a href="https://khoshkhah.github.io/roadstyle/"><img src="https://img.shields.io/badge/docs-khoshkhah.github.io%2Froadstyle-ff6b35.svg" alt="Docs"></a>
  <a href="https://github.com/Khoshkhah/roadstyle/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
</p>

Turn a GeoDataFrame of road edges into **one styled, interactive, offline HTML map**, with real
road cartography (casing and fill, per-zoom widths, street names, one-way arrows, tunnels and
bridges, optional 3D) and a JavaScript API for your own dashboard. Every map has a Street View
button: click any road to see it in Google Street View, looking the way it runs.

![A roadstyle map of Södermalm, Stockholm: Hornsgatan selected on the map, and the floating Street View window showing it](https://raw.githubusercontent.com/Khoshkhah/roadstyle/main/docs/img/hero.jpg)

## Install

```bash
pip install roadstyle              # core
pip install "roadstyle[all]"       # + studio, numeric ramps, vector tiles, lonboard, DuckDB, …
```

Python ≥ 3.10. Individual extras and the dev setup: [Install](https://khoshkhah.github.io/roadstyle/get-started/#install).

## Quickstart

```python
import geopandas as gpd
import roadstyle as rs

edges = gpd.read_file("edges.gpkg")        # LineStrings + a `highway` column, any CRS
rs.render_edges(edges).save("map.html")    # open map.html: no server (Street View needs one)
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
rs.render_street_view(edges).save("street_view.html")                  # map and Street View side by side
```

No Python? `roadstyle edges.gpkg -o map.html --basemap dark_matter`, or click through it in the
workbench: `pip install "roadstyle[studio]" && roadstyle studio`.

## API keys

Both keys are optional. roadstyle works without them, just with less.

**CARTO, for the base map.** The default base map (`voyager`) and `positron` and `dark_matter` come
from CARTO. Without a key, their tiles are stamped *API KEY REQUIRED*. Get a free key at
[carto.com/basemaps/apikey](https://carto.com/basemaps/apikey), then use any one of these:

```bash
export CARTO_API_KEY="…"                                          # environment variable
```
```json
{ "config": { "api_keys": { "carto": "…" } } }
```
Save that JSON as `~/.config/roadstyle/roadstyle.json`, or as `roadstyle.json` in the folder you run
from. In Python you can pass `rs.render_edges(edges, api_key="…")` instead. With no key at all, use
a keyless base map: `esri_street`, `esri_dark_gray`, `osm` or `blank`.

**Google Maps, for Street View.** Street View works with no key: the keyless Google embed. With a
Google **Maps JavaScript API** key, the Street View panel and window get a **Linked / Classic**
switch. Linked is a real panorama: the map marker walks and turns with you, and only Google's own
street photos are shown. Classic is the keyless embed. To get a key:

1. In the [Google Cloud console](https://console.cloud.google.com/), create a project and enable
   **Maps JavaScript API** (Google asks for a billing account on the project).
2. Under *APIs & Services > Credentials*, create an **API key**.
3. Restrict it: *Application restrictions* = **Websites**, listing your site's addresses
   (e.g. `https://example.com/*`); *API restrictions* = **Maps JavaScript API** only.

Then pass it in:

```python
rs.render_edges(edges, street_view_key="AIza…")         # the floating Street View window
rs.render_street_view(edges, street_view_key="AIza…")   # the side-by-side page
```

The key is written into the page, as every browser key is, so the site restriction in step 3 is
what protects it. It also means Linked works only on the addresses you listed: to try it on
`localhost`, add `http://localhost:*/*` to the list. Keep the key out of git, for example in an
environment variable.

More: [settings & base maps](https://khoshkhah.github.io/roadstyle/reference/settings/#base-maps-api-keys) ·
[Google Street View](https://khoshkhah.github.io/roadstyle/guides/street-view/).

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

Every function and event: [JavaScript API](https://khoshkhah.github.io/roadstyle/reference/javascript/).

## For AI agents

**MCP server.** Lets any MCP-capable AI app (Claude Code, Claude Desktop, Cursor, …) draw road maps
without writing code: `render_place("Tartu, Estonia")`, `render_file("roads.gpkg")` and `snapshot`.
Each saves an HTML map and returns its path plus a PNG preview the agent can look at.
```bash
claude mcp add roadstyle -- uvx --from "roadstyle[mcp]" roadstyle-mcp
```
Claude Desktop (`claude_desktop_config.json`):
```json
{"mcpServers": {"roadstyle": {"command": "uvx", "args": ["--from", "roadstyle[mcp]", "roadstyle-mcp"]}}}
```
Maps go to `~/roadstyle-maps/`. The preview needs Chromium once: `uvx --from "roadstyle[mcp]" playwright install chromium`.

**For agents that write code:**

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

**[khoshkhah.github.io/roadstyle](https://khoshkhah.github.io/roadstyle/)**, with live maps on every page.

| Where | What you find |
|---|---|
| **[Get started](https://khoshkhah.github.io/roadstyle/get-started/)** | install, a first map, what your data needs |
| **Guides** | [style the roads](https://khoshkhah.github.io/roadstyle/guides/style/) · [colour by your data](https://khoshkhah.github.io/roadstyle/guides/colour/) · [your own layers](https://khoshkhah.github.io/roadstyle/guides/overlays/) · [Google Street View](https://khoshkhah.github.io/roadstyle/guides/street-view/) · [big networks](https://khoshkhah.github.io/roadstyle/guides/big-networks/) · [dashboards & JavaScript](https://khoshkhah.github.io/roadstyle/guides/dashboards/) · [on a website](https://khoshkhah.github.io/roadstyle/guides/website/) |
| **[Gallery](https://khoshkhah.github.io/roadstyle/gallery/)** | a picture and one line of code per look |
| **Reference** | [every parameter](https://khoshkhah.github.io/roadstyle/reference/parameters/) · [JavaScript API](https://khoshkhah.github.io/roadstyle/reference/javascript/) · [settings & base maps](https://khoshkhah.github.io/roadstyle/reference/settings/) · [command line](https://khoshkhah.github.io/roadstyle/reference/cli/) |
| **[Changelog](https://github.com/Khoshkhah/roadstyle/blob/main/CHANGELOG.md)** | what changed in each release |

## License

[MIT](https://github.com/Khoshkhah/roadstyle/blob/main/LICENSE). Base-map tiles come from
third-party services (CARTO, OSM, Esri) with their own attribution and terms.
