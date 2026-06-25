# Parameter reference

Every parameter roadstyle uses, grouped by where it appears. Types, defaults, allowed
values, and what each one does. Use this as a lookup; for tutorials see [usage](usage.md).

Sections: RoadStyle · render_edges · Stylers · Theme · Basemap · StyleConfig · Palette JSON
(use your browser's find, or the page's table-of-contents sidebar).

---

## 1. `RoadStyle` — one road's look

A `RoadStyle` describes how a **single road class** (e.g. `motorway`) is drawn. A *palette*
is a dictionary of these, one per class. These are also the fields you see in an exported
palette JSON file.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `fill` | hex colour string | *required* | The road's main (centre) line colour, e.g. `"#FF0000"`. The colour you actually see. |
| `width` | number (px) | *required* | Thickness of the fill line in pixels, e.g. `6`. Bigger = more important road. |
| `casing_width` | number (px) | *required* | Thickness of the **casing** (the outline drawn *under* the fill), e.g. `8`. Usually `width + 2`. Set `0` for no casing. |
| `casing_light` | hex string or `null` | `null` | Casing colour on **light** base maps, e.g. `"#007785"`. `null` = no casing on light maps. |
| `casing_dark` | hex string | `"#000000"` | Casing colour on **dark/satellite** base maps. Usually black so roads pop on a dark canvas. |
| `dash` | `[on, off]` or `null` | `null` | Dash pattern in px, e.g. `[4, 4]` = 4px line, 4px gap (used for footpaths/cycleways). `null` = solid line. |
| `opacity` | number 0–1 | `1.0` | Transparency of the fill. `1` = solid, `0` = invisible. (The renderer multiplies this by the theme's fill opacity.) |

> **Casing?** A road is drawn as two stacked lines: a wider **casing** underneath (the border)
> and a narrower **fill** on top (the colour). This is the "geometry sandwich" — it gives every
> road a clean edge. `casing_light`/`casing_dark` are the two variants; the **theme** picks one
> (`casing="light"`/`"dark"`), and every backend draws that — casing is theme-driven and stays put
> when you switch the base map. The built-in themes all use the dark (black) casing.

> **Units & zoom.** `width` and `casing_width` are **fixed screen pixels** on the `folium` and
> `lonboard` backends — a road keeps the same on-screen thickness at every zoom level. This looks
> right at city scale (roadstyle's main use), but when zoomed far out fixed-pixel roads can blob
> together, and when zoomed far in they don't thicken. The **`web` (MapLibre) backend** instead
> varies width with zoom (the osm-carto width-by-zoom curve), so roads widen smoothly as you zoom
> in — use it when you need zoom-correct widths. See [web backend](web-backend.md).

Example (one entry from the `highsat` palette):
```json
"motorway": {
  "fill": "#00E5FF", "width": 6.0, "casing_width": 8.0,
  "casing_light": "#007785", "casing_dark": "#000000",
  "dash": null, "opacity": 1.0
}
```

---

## 2. `render_edges` — the main entry point

`render_edges(gdf, ...)` builds the map. `gdf` is your road data (a `RoadEdges` or a
GeoDataFrame with line geometry + a class column).

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `gdf` | `RoadEdges` / GeoDataFrame | *required* | The road edges to draw. A plain GeoDataFrame is normalised for you (→ EPSG:4326, lines). |
| `backend` | `"web"` / `"folium"` / `"lonboard"` | `"web"` | Renderer. **`web` (default)** = self-contained **MapLibre (vector)** map with per-zoom widths, two-way lanes, arrows/names, hover/select & tunnel/bridge grade separation (see [web backend](web-backend.md)). `folium` = portable interactive HTML (Leaflet) with legends + filter panel. `lonboard` = GPU/WebGL, for very large data. |
| `palette` | str or dict | `"highsat"` | Which colour palette for **class** styling. Built-ins: `"highsat"`, `"carto"`, `"mono"` (grayscale). Add your own via a [data file or override](palettes.md#customising-data-files-and-overrides). Ignored if you use `color_by`/`style`. |
| `theme` | `"light"`/`"dark"`/`"satellite"` | `"light"` | Visual theme: sets the default base map and which casing colour (light/dark) is used. `light` opens on the Voyager base. |
| `highway_col` | str | `"highway"` | Which column holds the road class. Set this if your class column has a different name. |
| `include` | str / list / `None` | `None` | Keep **only** these road classes (e.g. `["motorway","primary"]`). |
| `exclude` | str / list / `None` | `None` | Drop these road classes. Applied after `include`. |
| `match_links` | bool | `True` | If true, `primary` also matches `primary_link` (OSM link variants). |
| `color_by` | str / `None` | `None` | Colour by a **data column** instead of road class. With `colors` → categorical; with `cmap` → numeric. |
| `colors` | dict / `"self"` / `None` | `None` | For categorical `color_by`: a `{value: hexcolour}` map, e.g. `{"low":"#11D68F"}`. `"self"` = use the column's value as the **literal** colour (gray fallback for blank/invalid). |
| `color_table` | dict / Series / DataFrame / `None` | `None` | Per-edge colour keyed by `color_key`: a `{id: colour}` dict, a `Series`, or a DataFrame with `color_key` + `color_col`. Edges not in it get a **gray** fallback; class widths + casing are kept. |
| `color_key` | str | `"edge_id"` | The edges column joined against `color_table`'s keys. |
| `color_col` | str | `"color"` | The colour column name, when `color_table` is a DataFrame. |
| `cmap` | str / list / `None` | `None` | For numeric `color_by`: a colour ramp name (`"viridis"`, `"YlOrRd"`, …) or list of hex stops. |
| `vmin`, `vmax` | number / `None` | `None` | Value range for the numeric ramp. Default = the column's min/max. |
| `width_by` | `(min_px, max_px)` / `None` | `None` | For numeric styling: scale line width with the value, from `min_px` (low) to `max_px` (high). |
| `style` | `Styler` / `None` | `None` | Pass a styler object directly (advanced). Overrides `palette`/`color_by`. |
| `tooltip` | list / `None` | `None` | Which columns to show on hover. `None` = all columns. |
| `selected` | GeoDataFrame / `None` | `None` | Highlight these edges with a neon-violet overlay. |
| `basemap` | str / `None` | `None` | Use a single fixed base map (a key in `BASEMAPS`), instead of the theme default + switcher. |
| `basemaps` | list / `None` | `None` | (folium) The set of base maps offered in the switcher control. |
| `filter_control` | bool | `True` | Show the in-map road-type filter panel (checkboxes). On `folium` and the `web` backend. |
| `name` | str | `"roads"` | Layer name. |

**Returns:** a `WebMap` (default, `backend="web"`), a `folium.Map` (`backend="folium"`), or a
`lonboard.Map` (`backend="lonboard"`). Save with `.save("map.html")` (web / folium) or
`.to_html("map.html")` (lonboard); all three also display inline in a notebook.

> **Legends & the default backend.** Data-driven **legends** and the in-map **filter panel** are
> drawn by the `folium` (and JSON) outputs, *not* the MapLibre `web` backend. So
> `render_edges(color_by=…, cmap=…, legend=True)` only shows a legend on `backend="folium"` (or via
> `to_html`/`to_spec`). Use `backend="folium"` when you need the legend; use the default `web`
> backend for the zoom-correct interactive map.

### `backend="web"` — extra parameters

Only used by the MapLibre web backend; ignored by the others. See [web backend](web-backend.md).

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `arrows` | bool | `True` | Show one-way direction chevrons (CLI: `--no-arrows`). |
| `labels` | bool | `True` | Show curved street-name labels (CLI: `--no-labels`). |
| `filter_control` | bool | `True` | Show the collapsible road-class filter panel (CLI: `--no-filter`). |
| `basemap_switcher` | bool | `True` | Show the in-map base-layer dropdown (CLI: `--no-basemap-switcher`). |
| `offset_frac` | float | `0.28` | Two-way lane offset as a fraction of the road's **pixel** width (constant overlap at every zoom). `0` = no lane split. |
| `width_frac` | float | `0.6` | Each two-way lane's width as a fraction of the full width once the directions fan apart (a little over `0.5` so the lanes overlap rather than gap). |
| `offset_zoom` | int | `15` | Zoom at which the two directions start fanning into parallel lanes (ramped over ~2 levels; coincident below). |
| `tunnel_col` | str | `"tunnel"` | Column marking tunnels — drawn underneath, dashed + faded. |
| `bridge_col` | str | `"bridge"` | Column marking bridges — drawn on top with a heavier, square-capped casing. |
| `layer_col` | str | `"layer"` | OSM `layer` tag column; its sign sets elevation when `tunnel`/`bridge` are absent. |
| `boundary` | geometry / GeoDataFrame / GeoJSON | `None` | Overlay a dashed outline on top of the roads (e.g. the area the network was clipped to). Accepts a shapely geometry, a `GeoSeries`/`GeoDataFrame` (reprojected to EPSG:4326), or a GeoJSON mapping (assumed lon/lat). `None` = no overlay. |
| `color_options` | mapping / list / `None` | `None` | Bake several **"colour by" options** + a *Colour by* dropdown that recolours client-side (no re-render). An ordered `{name: {styler kwargs}}` mapping (or list of `{"name": ..., **kwargs}`); option 0 is active. Blank edges fall back to the base fill. See [web backend](web-backend.md#dynamic-recolouring-color_options). |
| `overlays` | list of `Overlay` / `None` | `None` | Extra layers the caller brings — zone polygons, POI circles, any geometry — drawn under/over the roads, clickable, with a *Layers* toggle. See [`Overlay`](#8-overlay-extra-layers). |

> **Direction arrows.** `arrows=True` (web backend) places one-way chevrons along each one-way edge
> using a native MapLibre symbol layer (`symbol-placement: line`). Geometry direction is the edge's
> coordinate order, so on a directed routing graph each one-way edge points the legal way.

---

## 3. Stylers — how colours are chosen

A **Styler** decides each edge's colour/width. `render_edges` builds one for you from the
arguments above, but you can construct them directly for full control.

### `ClassStyler` — colour by road class (the OSM default)
| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `column` | str | `"highway"` | Column holding the road class. |
| `palette` | str or dict | `"highsat"` | Palette name, or a `{class: RoadStyle}` dict. |
| `normalize_links` | bool | `True` | Strip the OSM `_link` suffix (`primary_link`→`primary`) and render links narrower. Turn off for non-OSM data. |
| `fallback` | str | `"unclassified"` | Class used when a value isn't in the palette. |
| `tunnel_col` | str / `None` | `None` | Column marking tunnels (faded + dashed). |
| `bridge_col` | str / `None` | `None` | Column marking bridges (solid black casing, a bit wider). |
| `config` | `StyleConfig` | defaults | Opacity/width knobs (see §6). |

### `CategoricalStyler` — colour by a discrete column
| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `column` | str | — | The column to read the category from (e.g. `"congestion"`). |
| `colors` | dict | `{}` | `{value: hexcolour}` map, e.g. `{"low":"#11D68F","heavy":"#F24E42"}`. |
| `fallback_color` | hex str | `"#cccccc"` | Colour for values not in `colors` (and missing data). Inside `color_options`, unmapped edges fall back to the **base option's fill** instead, not this colour. |
| `width` | number or str | `2.0` | Constant line width, or the name of a column to read width from. |
| `casing` | hex str / `None` | `None` | Optional constant casing colour. |
| `opacity` | 0–1 | `0.9` | Line opacity. |
| `dash` | `(on, off)` / `None` | `None` | Optional dash pattern. |

### `NumericStyler` — colour by a numeric column
| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `column` | str | — | The numeric column (e.g. `"aadt"`, `"maxspeed_kmh"`). |
| `cmap` | str / list | `"viridis"` | Colour ramp: a name (`"viridis"`, `"magma"`, `"YlOrRd"`, …) or a list of hex stops. |
| `vmin`, `vmax` | number / `None` | `None` | Value range mapped across the ramp. Default = data min/max. |
| `width` | number | `2.0` | Constant width (when `width_by` is not set). |
| `width_by` | `(min_px, max_px)` / `None` | `None` | Scale width with the value. |
| `width_column` | str / `None` | `None` | Column driving the width ramp (defaults to `column`). |
| `opacity` | 0–1 | `0.9` | Line opacity. |
| `nan_color` | hex str | `"#cccccc"` | Colour for missing/non-numeric values. Inside `color_options`, missing edges fall back to the **base option's fill** instead. |

---

## 4. `Theme`

A theme bundles the casing variant + a default base map.

| Field | Type | Meaning |
|---|---|---|
| `name` | str | Theme name (`"light"`, `"dark"`, `"satellite"`). |
| `casing` | `"light"` / `"dark"` | Which casing colour to use (`casing_light` vs `casing_dark`). |
| `default_basemap` | str | Base map shown by default for this theme. |

Built-ins: `light` (**Voyager** base, the default theme), `dark` (Dark Matter base), `satellite` (Esri imagery).

---

## 5. `Basemap`

A tile provider (the background map under the roads).

| Field | Type | Default | Meaning |
|---|---|---|---|
| `key` | str | — | Short id, e.g. `"dark_matter"`. |
| `label` | str | — | Human name shown in the switcher. |
| `url` | str | — | Leaflet tile-URL template (`{z}/{x}/{y}`). |
| `attr` | str | — | Attribution text (credit the tile source). |
| `is_dark` | bool | `False` | Dark canvas? Drives which casing colour is used. |
| `satellite` | bool | `False` | Apply the satellite saturation/brightness filter. |
| `lonboard` | str / `None` | `None` | Matching basemap name for the lonboard backend. |
| `bg`, `preview`, `subdomains` | — | Thumbnail styling + tile subdomains for the switcher. |

Built-ins: `voyager`, `positron`, `dark_matter`, `osm`, `esri_gray`, `satellite`.

---

## 6. `StyleConfig`

Global styling knobs. Defaults reproduce the calibrated v0.1 look — change them only to tweak
the overall feel. Pass via `ClassStyler(config=StyleConfig(...))`.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `fill_opacity` | 0–1 | `0.9` | Base opacity of every fill line. |
| `casing_opacity` | 0–1 | `0.75` | Base opacity of every casing line. |
| `casing_extra` | px | `2.0` | Reserved: casing = fill + this (palettes currently set casing widths directly). |
| `link_scale` | 0–1 | `0.7` | How much narrower `_link` roads are vs their parent. |
| `tunnel_opacity_scale` | 0–1 | `0.45` | Tunnels fade to this fraction of opacity. |
| `bridge_casing_extra` | px | `1.5` | Bridges get a casing this many px wider. |
| `minor_no_casing` | set of str | service, living_street, … | Classes drawn fill-only (no casing). |

---

## 7. Palette JSON file

What `save_palette()` writes / `load_palette()` reads. One file fully describes a palette and
can be hand-edited or read by a web frontend.

```json
{
  "name": "highsat",
  "roads": {
    "motorway": { "fill": "#00E5FF", "width": 6.0, "casing_width": 8.0,
                  "casing_light": "#007785", "casing_dark": "#000000",
                  "dash": null, "opacity": 1.0 },
    "primary":  { "fill": "#FF9100", "width": 4.5, "casing_width": 6.5,
                  "casing_light": "#A86000", "casing_dark": "#000000",
                  "dash": null, "opacity": 1.0 }
  }
}
```

| Key | Meaning |
|---|---|
| `name` | Palette name. On load it's registered under this name, so `render_edges(palette=name)` works. |
| `roads` | A map of `class → RoadStyle fields` (see §1 for each field). |

A minimal entry needs only `fill`, `width`, `casing_width`; the rest fall back to defaults.

---

## 8. `Overlay` — extra layers

Extra geometry the caller brings — zone polygons, POI circles, any lines — drawn alongside the
roads on the **`web` backend** via `render_edges(..., overlays=[Overlay(...), ...])`. Each `Overlay`
is *passthrough* data (your geometry, your style); it does **not** go through the road-styling
compiler. See [web backend → Overlay layers](web-backend.md#overlay-layers-overlays).

| Field | Type | Default | Meaning |
|---|---|---|---|
| `data` | GeoDataFrame / GeoSeries / GeoJSON | *required* | The overlay geometry (any CRS → EPSG:4326). Feature `properties` are kept and shown in the click popup. |
| `kind` | `"fill"` / `"line"` / `"circle"` / `None` | `None` | Draw kind. `None` = auto-detect (polygon → `fill`, line → `line`, point → `circle`). |
| `placement` | `"under"` / `"over"` | `"over"` | Draw beneath the roads (e.g. zone fills) or on top (e.g. POIs). |
| `color` | hex str | `"#6aa9ff"` | Paint colour (fill / circle / line). |
| `opacity` | 0–1 / `None` | `None` | Layer opacity; `None` = a kind-appropriate default (fill `0.15`, circle `0.85`, line `0.9`). |
| `outline` | hex str / `None` | `None` | Polygon outline colour (`fill` only; default = `color`). |
| `radius` | px | `6.0` | Circle radius (`circle` only). |
| `width` | px | `2.0` | Line / fill-outline width. |
| `label` | str / `None` | `None` | Name shown in the *Layers* toggle (default `"Layer N"`). |
| `popup` | list / `None` | `None` | Fields shown when a feature is clicked (makes the layer interactive). `None` = show all fields; `[]` = non-interactive (decoration only). |

```python
from shapely.geometry import box
zones = gpd.GeoDataFrame({"taz_id": ["Z0"], "weight": [0.7]},
                         geometry=[box(18.04, 59.31, 18.07, 59.33)], crs=4326)
rs.render_edges(edges, backend="web",
    overlays=[rs.Overlay(zones, placement="under", color="#6aa9ff",
                         opacity=0.14, label="Zones", popup=["taz_id", "weight"])])
```
