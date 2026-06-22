# When to use roadstyle (vs the alternatives)

roadstyle isn't trying to replace the geospatial-viz ecosystem — it's an **opinionated road
cartography layer** on top of it. Here's how it compares to the closest tools, so you can pick
the right one.

## At a glance

| Tool | Interactive? | Road **casing** + per-class widths | Colour by **data** | Web-embeddable output | Best for |
|---|---|---|---|---|---|
| **roadstyle** | ✅ folium + lonboard + MapLibre (`web`) | ✅ built-in (geometry sandwich; per-zoom widths on `web`) | ✅ categorical + numeric | ✅ JSON spec / HTML / iframe | correct interactive road maps, out of the box |
| geopandas `.explore()` | ✅ folium | ❌ single line, no casing/z-order | ✅ (`column`, `cmap`, `scheme`) | ⚠️ folium HTML only | quick data exploration of any geometry |
| prettymaps | ❌ static PNG/SVG | ✅ per-class widths | ❌ class only | ❌ image | poster-quality static art maps |
| osmnx `plot_graph` | ❌ mostly static | ⚠️ basic | ⚠️ manual | ❌ | street-network analysis |
| MapLibre / Mapbox styles | ✅ | ✅ (you author it) | ✅ (you author it) | ✅ | full custom vector basemaps |

## roadstyle vs geopandas `.explore()`

`.explore()` is excellent and the closest neighbour — it already does data-driven colouring
(`column=`, `cmap=`, `scheme=`), legends and tooltips. Reach for **roadstyle** when you want the
**road cartography** it doesn't do:

- the **geometry sandwich** — a casing under every fill, drawn in importance order, so junctions
  read cleanly (`.explore()` draws a single flat line);
- **per-class cartographic widths** (motorway wider than residential) and OSM treatments
  (tunnel fade, bridge casing, `_link` narrowing, dashed paths);
- **theme-aware casing** (light vs dark/satellite) and a thumbnail base-map switcher;
- a **stack-agnostic JSON spec** for embedding in a non-folium website.

Use `.explore()` for a fast look at arbitrary geometry; use roadstyle when the output is a
*road map* you care about the look of, or that ships to a website.

## roadstyle vs prettymaps

prettymaps makes gorgeous **static** maps (osmnx + matplotlib). roadstyle is for **interactive /
web** maps and **data-driven** styling. Different jobs — use prettymaps for a print/poster, use
roadstyle for an interactive or embedded map (and for colouring by traffic/speed/congestion).

## What roadstyle deliberately reuses

roadstyle doesn't reinvent the wheels under it — it builds on
[`branca`](https://python-visualization.github.io/branca/) (colormaps + legends),
[`mapclassify`](https://pysal.org/mapclassify/) (numeric classification schemes), and
[`xyzservices`](https://github.com/geopandas/xyzservices) (tile providers). That keeps it small
and lets your existing knowledge of those libraries carry over.

## Known limitations

- **Fixed-pixel widths on folium/lonboard** — great at city scale, can blob at very wide zoom
  (see [parameters](parameters.md)). The **`web` (MapLibre) backend** is zoom-scaled (osm-carto
  width curve), so reach for it when you need zoom-correct widths — it also adds two-way lanes and
  tunnel/bridge grade separation (see [web backend](web-backend.md)).
- **lonboard legends** aren't rendered yet (folium + the JSON/HTML outputs have them).
