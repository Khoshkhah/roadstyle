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
> road a clean edge. `casing_light`/`casing_dark` exist so the border can switch colour to suit
> a light vs dark base map.

> **Units & zoom (known limitation).** `width` and `casing_width` are **fixed screen pixels** —
> a road keeps the same on-screen thickness at every zoom level. This looks right at city scale
> (roadstyle's main use). It is *not* yet zoom-dependent: when zoomed far out, fixed-pixel roads
> can blob together; when zoomed far in they don't thicken. Professional vector maps instead vary
> width with zoom (a Mapbox-style `interpolate` curve) or use ground-meter widths with min/max
> pixel clamps. A zoom→width curve is a planned opt-in; fixed pixels will remain the default.

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
| `backend` | `"folium"` / `"lonboard"` | `"folium"` | Renderer. `folium` = portable interactive HTML (Leaflet). `lonboard` = GPU/WebGL, for very large data. |
| `palette` | str or dict | `"highsat"` | Which colour palette for **class** styling. Built-ins: `"highsat"`, `"carto"`. Ignored if you use `color_by`/`style`. |
| `theme` | `"light"`/`"dark"`/`"satellite"` | `"dark"` | Visual theme: sets the default base map and which casing colour (light/dark) is used. |
| `highway_col` | str | `"highway"` | Which column holds the road class. Set this if your class column has a different name. |
| `include` | str / list / `None` | `None` | Keep **only** these road classes (e.g. `["motorway","primary"]`). |
| `exclude` | str / list / `None` | `None` | Drop these road classes. Applied after `include`. |
| `match_links` | bool | `True` | If true, `primary` also matches `primary_link` (OSM link variants). |
| `color_by` | str / `None` | `None` | Colour by a **data column** instead of road class. With `colors` → categorical; with `cmap` → numeric. |
| `colors` | dict / `None` | `None` | For categorical `color_by`: a `{value: hexcolour}` map, e.g. `{"low":"#11D68F"}`. |
| `cmap` | str / list / `None` | `None` | For numeric `color_by`: a colour ramp name (`"viridis"`, `"YlOrRd"`, …) or list of hex stops. |
| `vmin`, `vmax` | number / `None` | `None` | Value range for the numeric ramp. Default = the column's min/max. |
| `width_by` | `(min_px, max_px)` / `None` | `None` | For numeric styling: scale line width with the value, from `min_px` (low) to `max_px` (high). |
| `style` | `Styler` / `None` | `None` | Pass a styler object directly (advanced). Overrides `palette`/`color_by`. |
| `tooltip` | list / `None` | `None` | Which columns to show on hover. `None` = all columns. |
| `selected` | GeoDataFrame / `None` | `None` | Highlight these edges with a neon-violet overlay. |
| `basemap` | str / `None` | `None` | Use a single fixed base map (a key in `BASEMAPS`), instead of the theme default + switcher. |
| `basemaps` | list / `None` | `None` | (folium) The set of base maps offered in the switcher control. |
| `filter_control` | bool | `True` | (folium) Show the in-map road-type filter panel (checkboxes). |
| `name` | str | `"roads"` | Layer name. |

**Returns:** a `folium.Map` (default) or a `lonboard.Map`. Save with `.save("map.html")` (folium)
or `.to_html("map.html")` (lonboard); both also display inline in a notebook.

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
| `fallback_color` | hex str | `"#cccccc"` | Colour for values not in `colors` (and missing data). |
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
| `nan_color` | hex str | `"#cccccc"` | Colour for missing/non-numeric values. |

---

## 4. `Theme`

A theme bundles the casing variant + a default base map.

| Field | Type | Meaning |
|---|---|---|
| `name` | str | Theme name (`"light"`, `"dark"`, `"satellite"`). |
| `casing` | `"light"` / `"dark"` | Which casing colour to use (`casing_light` vs `casing_dark`). |
| `default_basemap` | str | Base map shown by default for this theme. |

Built-ins: `light` (Positron base), `dark` (Dark Matter base), `satellite` (Esri imagery).

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
