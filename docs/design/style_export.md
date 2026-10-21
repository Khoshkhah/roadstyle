# duckOSM roads in GeoLibre and RustGIS: data and look

**Status:** version 2 is **agreed** and partly built (2026-10-19, local branch `geolibre`): duckOSM writes the GeoParquet file
(branch `geoparquet-export`), `rs.export_style` reads it (roads only, every column, the page state baked), and the GeoLibre plugin
(`geolibre-plugin/`, on the branch `geolibre`) shows it with a popup and hover; checked in web.geolibre.app and web.rustgis.app. Not yet: the page's own arrows
in the plugin, mapstyle. Its open points were decided 2026-10-19, as proposed. Version 1 (further down) was the first try; version 2
replaces it.

## Version 2: data and look from one duckOSM database

### Why version 1 is not enough

The first look in the two apps (2026-10-19) found these faults:

- In GeoLibre, the export was one Background item: the base map and the roads together. You could not hide or change
  the base map, and you could not click a road. It was a picture, not a layer.
- The tiles had no data: only the properties that the style needs to draw.
- The 3D view showed no bridge decks (`view_3d` was off), and the arrows repeated on every one-way street.
- duckOSM was not part of it. A duckOSM database holds the data (`<mode>.edges`) and the visualization
  (`visualization.edge_levels`). Version 1 used neither.
- The test checked only that the style loads, not what a person does with the layer in the app.

### What you do in each app (the checks)

These are the acceptance checks. I run each one in the real app before I give a link.

**GeoLibre** (web and desktop, MapLibre renderer):

1. The roads are their own row in the Layers panel. You can hide them, show them and change their opacity.
2. GeoLibre's base map stays separate. You can change it or hide it, and the roads stay.
3. A click on a road shows a popup with every duckOSM column of that edge.
4. A tilt shows the bridge decks in 3D. GeoLibre's Cesium globe is a different renderer: the plugin does not support
   it (`engines: ["maplibre"]`), and GeoLibre then suspends the plugin.
5. One-way streets get roadstyle's own arrows: one arrow per street, moved into view after each pan.
6. The look is the same as in roadstyle's page: casings, drawing positions, tunnels, bridges, names.

**RustGIS** (web and desktop):

1. The roads are a layer over RustGIS's own base map. You can change or hide the base map.
2. Identify on a road shows every duckOSM column.
3. The roads show with their colors and casings. The limits of RustGIS's renderer (no `line-sort-key`, no
   `line-offset`, no names or arrows along lines, flat `fill-extrusion`) are listed, not hidden.

### One input: the duckOSM database

| Layer | Table | Content |
|---|---|---|
| Data | `<mode>.edges` (for example `driving.edges`) | every column of each edge: `edge_id`, name, highway, oneway, lanes, maxspeed_kmh, ... |
| Visualization | `visualization.edge_levels` (+ `edge_levels_meta`) | how roadstyle draws each edge: casing and fill positions, caps, heads (`rs.save_levels`) |

The two layers are joined by `edge_id` (BIGINT). The levels are read, not computed again. If a database has no
`visualization.edge_levels`, the export stops with a message that gives the `rs.save_levels` command. It does not
compute them by itself (no silent fallback). Today `norrmalm` and `sundbyberg` have the table; Södermalm does not.

### What each project does

```text
duckOSM db ──► duckOSM: export-gis --format geoparquet ──► edges_<mode>.parquet (data + visualization)
                                                                  │
                                                                  ├──► GeoLibre / RustGIS: a data layer (click, Identify)
                                                                  ▼
                                    roadstyle: rs.export_style ──► style.json + tiles + sprite (roads only)
                                                                  │
                                                                  └──► GeoLibre plugin: look + data over any base map
                                                                       RustGIS: tile layer over its base map
```

**1. duckOSM: the data file.** `duckosm export-gis --format geoparquet` writes `edges_<mode>.parquet` for each mode:
every column of `<mode>.edges`, and the columns of `visualization.edge_levels` when the table is there (a LEFT JOIN
on `edge_id`). DuckDB 1.5 writes the GeoParquet 1.0 metadata by itself (checked 2026-10-19: Södermalm `driving`,
450 KB). duckOSM only reads the visualization table; it does not import roadstyle. Both apps open this file as a data
layer with their own simple style: GeoLibre with `?data=<URL>` (its DuckDB reader), RustGIS in place by range reads.

**2. roadstyle: the look, from the same file.** `rs.export_style` reads `edges_<mode>.parquet`, so the look and the
data come from the same rows. Changes from version 1:

- **Roads only, always.** No background layer and no base map in the style. The `basemap` keyword goes. The base
  map always comes from the app.
- **Every column in the tiles.** The road tile layer keeps all the edge columns, so a click or Identify on the
  tiles shows the data too. Södermalm's tiles get larger (to be measured).
- **The levels from the file.** The position columns of `visualization.edge_levels` go to `render_edges` as
  `casing_level_col`, `fill_level_col`, ... The minimum-cost flow does not run again.
- **RustGIS fixes.** The road layer with the tunnel dash splits into two layers: solid pieces with no
  `line-dasharray`, and tunnel dash pieces with the dash. The tunnel color becomes a plain `interpolate` without
  `let` (RustGIS draws `let` / `to-rgba` as black).
- **Arrows.** The thinned arrows of version 1 stay in the style for plain MapLibre apps. In GeoLibre the plugin
  replaces them with the page's own arrows (below).
- `view_3d=True` stays the default: the style has the bridge decks.

**3. The GeoLibre plugin: look and data together.** A TypeScript plugin, made from
[opengeos/geolibre-plugin-template](https://github.com/opengeos/geolibre-plugin-template), with `engines: ["maplibre"]`.

- **Open:** a Plugins menu item asks for the URL of a roadstyle export (`style.json`). The plugin adds the style's
  sources and layers to GeoLibre's map (`getMap()`), over the base map.
- **One row in the Layers panel:** `registerExternalNativeLayer` with `nativeLayerIds` = the road layers and a
  `paintBridge` for opacity and visibility. Hide, show, reorder and remove work from the Layers panel.
- **Click and hover:** a click shows roadstyle's popup with every column; hover highlights the road
  (feature-state, the `roads-highlight` layer, which the plugin keeps). Both stop while a GeoLibre tool owns the
  pointer (`getActiveMapTool()`).
- **Arrows:** the page's `_rsArrows`, which fills an `arrows` source from the `slots` tile layer after each move.
  To keep one rule in one place, `_rsArrows` and the popup text (`_rfields`) move from `web_template.html` into one
  JavaScript file in roadstyle (`static/arrows.js`). The page and the plugin build both include it.
- **3D:** the bridge decks, with MapLibre's tilt.
- **Project:** the export URL goes into the plugin's project state, so a saved GeoLibre project opens with the roads.
- **Install:** Manage Plugins › Settings › Install from file (the zip), or a `plugin.json` URL (`localhost` is
  allowed without https). Later: a request to list it in [opengeos/geolibre-plugins](https://github.com/opengeos/geolibre-plugins).

**4. RustGIS.** No plugin: RustGIS plugins are sandboxed WebAssembly and cannot run roadstyle's JavaScript. The roads
open as a tile layer (`?style=<URL>` or Home › Add › Basemap › Add Tile Layer), over RustGIS's base map. The GeoParquet
file is the data layer for Identify, if Identify does not read the tile layer (to be checked).

### How to serve the files for a check

The web apps are https pages. They can read `http://localhost` only after you allow Chrome's local network access
(the icon left of the address bar › Site settings › Local network access › Allow). The server must send
`Access-Control-Allow-Origin: *`. RustGIS also puts a new layer under its World Atlas sample, so clear those
checkboxes first.

### Steps

1. duckOSM: `export-gis --format geoparquet` with the visualization columns, and its test. Save the levels of
   Södermalm into its database (`rs.save_levels`), so the check area has both layers.
2. roadstyle: `rs.export_style` from the GeoParquet file; roads only; every column in the tiles; the RustGIS fixes;
   `static/arrows.js` shared by the page.
3. The GeoLibre plugin.
4. The checks above in GeoLibre and RustGIS, by me. Then the links for you.

### Decisions (2026-10-19)

1. **The plugin lives in roadstyle's repository, on its own branch `geolibre`** (changed 2026-10-20; not on `main`, not in the PyPI package): it is built for one app, and its
   `py/pkgs.zip` is a generated copy of roadstyle's and mapstyle's Python. `main` has the export (`export_style`, `export_look`); the plugin branch follows `main`.
2. **A database with no levels stops the export** with a message that gives the `rs.save_levels` command.

### Approach 2: roadstyle's look on a GeoLibre data layer (built 2026-10-19)

A GeoLibre user can add the duckOSM data directly (a `.duckdb` or GeoParquet layer). Approach 2 gives that layer roadstyle's
look, with no export of tiles:

- `rs.export_look(path)` writes MapLibre layers with no source, from the profile and the palette. They read only the raw
  duckOSM columns: `highway`, `oneway`, `tunnel`, `bridge`, `casing_level`, `fill_level`.
- The plugin item "Style a layer with roadstyle" adds these layers on the source of the data layer (`source-<id>`), under the
  data layer's position, and makes GeoLibre's own line transparent with `importLayerStyle`. GeoLibre keeps the layer, so
  Identify and the attribute table still work.
- The look has one row in the Layers panel. It skips the positions that the layer does not have.
- Not in the look: the casing pieces at the ends, names, arrows, 3D decks. For these, use the full export (approach 1).

### Next: mapstyle (after the roadstyle path passes the checks)

mapstyle's layers (water, landcover, buildings, rail, ...) are roadstyle overlays, and the export puts every overlay
into the tiles. Two things are necessary:

- mapstyle's extra styling in `layers.js` (color by `kind`, zoom ranges, dashes, textures, icons) moves to Python
  style rules, so that the style has it. Styling in page JavaScript is a design fault (2026-10-19): every path that
  cannot run that JavaScript (the export, RustGIS, other apps) loses it. The rule: styling is data, made in Python as
  plain MapLibre style rules; JavaScript does only interaction (click, hover, toggles, arrow placement).
- roadstyle has one small case of the same fault: the page sets the tunnel casing colors of `simple=False` at load
  (`rsSetTunnelStyle`), and the export copies that rule in Python (`_tun_hex`). The page must read the colors from
  the style that Python makes, so that there is one rule.
- In GeoLibre, each mapstyle layer is its own row in the Layers panel (one `registerExternalNativeLayer` per layer),
  so that water or buildings can be hidden one by one.

---

Everything below this line is **version 1**.

## Problem

roadstyle makes one HTML page. Other map apps cannot open that page as a layer. Two apps from opengeos
read MapLibre styles:

- **GeoLibre** ([repo](https://github.com/opengeos/GeoLibre), [web](https://web.geolibre.app)), MIT, TypeScript on
  MapLibre GL JS 6.15. A project's `basemapStyleUrl` is the URL of a MapLibre style JSON (UI: double-click the
  Background row, then the custom style URL field; or the link parameter `?style=<url>`). GeoLibre gives that URL to
  MapLibre's `setStyle`, so the full style spec applies. It takes a URL only, not a local file. Its own layer style
  has only fill, stroke, width and opacity, and `importLayerStyle` maps a style onto these with loss. Thus
  roadstyle's look gets into GeoLibre only as a complete style.
- **RustGIS** ([repo](https://github.com/opengeos/RustGIS), [web](https://web.rustgis.app)), Apache-2.0, Rust
  (a native desktop app, and the same code in WebAssembly in the browser). It does not use MapLibre GL JS: it has its
  own renderer for a subset of the style spec (`crates/tiles/src/style.rs`). Home › Add › Basemap › Add Tile Layer
  takes a style.json URL (http or https only); the web app also takes `?style=<url>`.

Facts from the two repos (GeoLibre `a6c1765`, RustGIS `bfb7ce8`), read 2026-10-19 from the code and docs. Neither
app was run.

The same files also open in every MapLibre page, and in QGIS, which converts a MapLibre style with some loss. One export serves
all of them. mapstyle and lanestyle draw through `rs.render_edges`, so they get the export too.

## What roadstyle already has

Most of the work exists. The export collects it into files.

1. **The style is a Python dict.** `render_edges` (`render_web.py`) builds a complete MapLibre style (`version 8`,
   `sources`, `layers`) and writes it into the page as `__STYLE__`. The casing and fill layers, the grade separation,
   the drawing positions (`line-sort-key`, filters on the position), the tunnel look, the bridge decks
   (`fill-extrusion`), the street names and the arrows are all layers in this dict.
2. **The tiles exist.** `tiles=True` writes the roads into a PMTiles archive with `tiles.build_pmtiles`
   (pure Python: `mapbox-vector-tile` + `pmtiles`, the `tiles` extra). The casing pieces, simple mode's pieces,
   the end caps and the label slots go into the same archive as tile layers. The style then points at
   `pmtiles://roads`, which the page serves from memory.
3. **The tiled path already uses static arrows.** With `tiles=True` the arrows repeat along the label slots
   (`symbol-placement: line`). The page's one-arrow-per-road placement (`_rsArrows`) is not used. A static style
   needs exactly this.

## Proposal

### The call

```python
import roadstyle as rs

rs.export_style(edges, "out/sodermalm", base_url="https://example.org/sodermalm",
                theme="light", **render_kwargs)
```

It writes:

| File | Content |
|---|---|
| `style.json` | the MapLibre style, every URL absolute (below) |
| `tiles/{z}/{x}/{y}.pbf` | every road tile layer: the tiles of the `tiles=True` archive, one file each |
| `sprite.json`, `sprite.png`, `sprite@2x.json`, `sprite@2x.png` | one icon, `oneway` |

**A tile folder, not PMTiles, by default.** PMTiles was the first choice, but neither app reads it from inside a
style today:

- RustGIS fetches a vector source's `url` as TileJSON over http or https only, so `pmtiles://...` fails ("only
  http:// and https:// addresses are fetched", `crates/tiles/src/address.rs`). It reads PMTiles only as a layer of
  its own, without the style.
- GeoLibre registers the `pmtiles://` protocol only when the project has a PMTiles layer or a PMTiles base map
  (`pmtiles-archive.ts`, `layer-sync.ts`). A plain style URL does not do this, so the source can fail.

A `tiles: ["<base_url>/tiles/{z}/{x}/{y}.pbf"]` source works in both apps, in QGIS and in every MapLibre page, and
any static server serves it (no range requests). `format="pmtiles"` writes `roads.pmtiles` and a
`pmtiles://` source for MapLibre pages that register the protocol. Both formats come from the same archive:
for the folder, the export reads each tile back out of it (`pmtiles.reader.all_tiles`) and writes it without gzip,
because a static server sends a file with no `Content-Encoding`. `tiles.py` does not change.

`render_kwargs` are the keywords of `render_edges` (palette, settings, levels, `overlays`, `items`, ...). The
export calls `render_edges(..., tiles=True)` with a private keyword `_export=True`, and `render_edges` returns
`{style, pmtiles, bounds}` after it builds the archive, before it makes the HTML. The private `_edges` keyword
already returns early in the same way. Thus the page and the export use one set of rules (one rule, every path).

### Changes to the style before it is written

1. **Absolute URLs.** The source gets `tiles: ["<base_url>/tiles/{z}/{x}/{y}.pbf"]` and the sprite
   `<base_url>/sprite`. MapLibre does not document how it resolves a relative URL in a style, so `base_url` is a
   necessary keyword.
2. **No GeoJSON sources.** RustGIS ignores GeoJSON sources (`Source::Other`, "ignored by the renderer"). Each
   GeoJSON source that `tiles=True` keeps inline (the halves, the bridge shadows, the decks, the overlays) goes into
   the archive as one more tile layer: lines with `line_layers`, points and polygons with `extra_layers`. The
   empty `arrows` source and its layers go out, because the slot arrows replace them. The source of the roads gets
   `bounds`, so an app asks for no tile outside the roads.
3. **The tunnel look is fixed.** With `simple=False`, the page sets the gap color and the dashes of the tunnel
   casings at load (`rsSetTunnelStyle`). The export bakes them with the palette and strength of the settings, with
   `_tun_hex`, a Python copy of `_tunHex`. Simple mode (the default) has them in Python already (`_simple_color`).
4. **The arrow icon.** The page makes the icon with `addImage`. The export writes a sprite with one SDF icon
   (`"sdf": true`), and the arrow layers get `icon-color`. Because the icon is SDF, the PNG files do not change
   with the arrow color: one fixed file, `src/roadstyle/data/sprite.png` (96 x 40, `pixelRatio` 4, as the page's
   `addImage`), made once. It is written as `sprite.png` and as `sprite@2x.png`. No image library is necessary.
5. **Glyphs.** The street names use `Noto Sans Regular` from `demotiles.maplibre.org`, as the page does. The
   style keeps that URL, so the names need a network connection.
6. **The hover and select layer goes out** (`roads-highlight`). It shows only with feature-state, which a
   static style never sets. The `feature-state` cases in other colors stay: they are valid and do nothing.
7. **The camera.** The style gets `center` and `zoom` from the bounds of the edges, as the page's `fitBounds`.
8. **Page-only keywords are refused.** `views=` (the page applies the first view at load) and `color_active=`
   (the page picks that option at load) raise `ValueError`, because the style cannot do what the page does.
9. **A keyed base map keeps its key.** CARTO's tile URL has the API key in it, so `style.json` has the key too.
   The guide says this. For files that other people can see, use a keyless base map or `basemap=None`.

`basemap` not given means the base map of `render_edges`. Because `render_edges` reads `basemap=None` as "the
default", the export uses its own marker for "not given" and gives `render_edges` only a named base map.

### The tiles: reuse `tiles.build_pmtiles`

| Option | New dependencies | Decision |
|---|---|---|
| `tiles.build_pmtiles` (exists) | none (the `tiles` extra) | **use it** |
| tippecanoe | a C++ program, not on PyPI | no |
| DuckDB `ST_AsMVT` | `duckdb` (an extra) | no: a second copy of the tile rules (simplification per zoom, class minzoom, the slot layer) |

The speed is the speed of `tiles=True`: about one minute for 100 000 edges. The tiles stop at zoom 15
(`CONFIG.tiles`), and the apps enlarge zoom 15 for the streets.

## What you lose outside roadstyle's page

The page's JavaScript does these things. A style file cannot do them:

- popups, the hover tooltip, hover and select highlight, the docked panel (the sidecar table is not exported);
- the `window.rs*` API: `rsColor`, `rsFilter`, `rsSelect`, `rsFocus`, `rsQuery` and the others;
- the controls: Colour by menu, legend, class filter panel, views, base-map switcher, tunnel slider,
  `rsSetRoadFill`. Only the active color option and the default tunnel look are in the style;
- Street View, Google 3D and the level editor;
- one arrow per one-way road, moved into view after each pan. The export thins the arrows with fixed rules
  (2026-10-19, after the first look: the repeat of `tiles=True` put an arrow on every 100 m slot). Side streets get
  arrows from zoom 17, as in the page. Python numbers the arrow slots of each one-way chain (`__rs_arw`: the odd
  slots, 200 m apart, else the chain's only slot), and the arrow layers keep every 4th at zoom 15, every 2nd at 16
  and each from 17, one arrow in the middle of its slot (`line-center`): about 330 px apart at each zoom;
- the 3D button: an app has only its own tilt. The export sets `view_3d=True` by default (2026-10-19, after the
  first look), so the style has the bridge decks;
- mapstyle's `layers.js` styling (color by `kind`, zoom ranges, textures, icons): only the plain overlays
  are exported until mapstyle moves these rules to Python.

The casing and fill, the grade separation, the drawing positions, the bridge decks, the names and the themes stay,
because they are style layers. In MapLibre GL JS (GeoLibre, a page) they show as in roadstyle's page.

**RustGIS shows much less.** Its renderer draws a subset of the spec (`style.rs`, `docs/user-guide/maps.md`):

| roadstyle uses | RustGIS | Result in RustGIS |
|---|---|---|
| `line-sort-key` (the drawing positions in simple mode) | not read | at a bridge, the lower road can show on top; the layer order (low band, ground, high band, bridges) stays |
| `line-offset` (the two halves of a two-way road, lanes, casing pieces) | parsed, not drawn | the halves and lanes lie on the center line |
| `symbol-placement: line` (street names, arrows) | line labels not drawn | no street names and no arrows |
| `glyphs` | not fetched, the app's own font | other font on point labels |
| `fill-extrusion` (bridge decks) | drawn flat | no 3D decks |
| `feature-state` | no value | nothing (the export has no hover) |

Thus RustGIS shows the colored casing and fill and the layer order, and not much more. Two later steps can help:
one layer per position for the export (`simple=False` already makes one copy of each layer per position), and
offset geometry in the tiles in place of `line-offset`. The note proposes to do neither now: first see the result.
GeoLibre and MapLibre pages need no such change.

## mapstyle and lanestyle

Both call `rs.render_edges(**kw)`. Each one adds a three-line `export_style` that calls `rs.export_style` with the
same keywords that it gives `render_edges` now. lanestyle's lanes are `items` (Python), so they export with no
change. mapstyle exports its overlays now, and its `layers.js` styling after it moves to Python.

## Test

1. **Unit test** (`tests/test_export_style.py`, Södermalm fixture):
   - each layer's `source` is in `sources`, and each `source-layer` is in the archive's `vector_layers`;
   - no GeoJSON source and no `__PLACEHOLDER__` text is in `style.json`;
   - every URL starts with `base_url`;
   - the sprite files exist and `sprite.json` has `oneway` with `"sdf": true`.
2. **Browser test** (Playwright, as the other page tests): a plain MapLibre page with the vendored `maplibre-gl`
   loads `style.json` from a local server. `querySourceFeatures("roads", {sourceLayer: "roads"})` must not be empty.
3. **By hand, in the two apps.** Export Södermalm and serve the folder with CORS headers
   (`Access-Control-Allow-Origin: *`). Python's `http.server` does not send them. Both web apps are https pages, so
   the files must also be on https, or on `http://localhost` if the browser allows it from an https page (browsers
   differ; neither app documents it). RustGIS also refuses a style from a public host that points into the local
   network, so keep the style and the tiles on one host. GitHub Pages does all of this, but nothing goes to main
   before review: use a local server first, and a branch preview after that.
   - GeoLibre web: Background row › custom style URL, or `https://web.geolibre.app/?style=<style.json URL>`.
   - RustGIS web: Home › Add › Basemap › Add Tile Layer with the `style.json` URL, or `?style=<url>`.
   - Look at a bridge (Skanstull), a tunnel (Söderledstunneln), the names and the arrows. In RustGIS, compare with
     the table above.

## Decisions (2026-10-19)

1. **Tiles: a tile folder by default.** PMTiles does not work in a style in either app today (see above). The
   export writes `tiles/{z}/{x}/{y}.pbf` by default, and `format="pmtiles"` writes `roads.pmtiles`.
2. **Base map: kept by default.** The style keeps the base map of `render_edges`, so it opens alone anywhere.
   `basemap=None` drops the background and the raster layer. The style is then a layer over the app's own
   base map.

## Later, not in this work

- A GeoLibre plugin (a TypeScript bundle and `plugin.json`; `activate(app)` with `getMap()`,
  `addVectorTileLayer`, `importLayerStyle`, `registerRightPanel`). It can add the popups and the
  Colour by menu back in GeoLibre. It is larger, and it needs the export first.
- One style per color option (`style-<option>.json`).
- A command line flag: `roadstyle edges.gpkg --export-style out/`.
