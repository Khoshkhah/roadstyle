# Keywords by engine

<p class="lead">The state of each keyword of <code>render_edges</code> and of each public function in the Python engine and in the
Rust engine, at version 0.25.0.</p>

The values in the Rust column:

| Value | Meaning |
|---|---|
| **yes** | The Rust engine makes it. The output is the same as the output of the Python engine. |
| **page** | A keyword of the page, not of the style. The dashboard reads it, and the page is the same with both engines. |
| **first** | Python applies it to the roads before the engine runs, the same for both engines. |
| **Python** | Only the Python engine has it. With `engine="rust"`: a `ValueError`. With `ROADSTYLE_ENGINE=rust`: the Python engine makes the call, with a warning ([Switch the engine](switch-engine.md)). |
| **folium** | A keyword of the folium backend. The Rust engine makes only the web page. |

The default of each keyword and what it does: [Every parameter](../reference/parameters.md). The format of the roads, the level
data and the look that the keywords name: [Inputs and outputs](../reference/formats.md).

## `render_edges`

### Look

| Keyword | Python | Rust |
|---|---|---|
| `backend` | `"web"`, `"folium"`, `"lonboard"` | `"web"` only. `engine="rust"` with another backend is a `ValueError`; with `ROADSTYLE_ENGINE=rust` the other backends use the Python renderer, with no warning |
| `profile`, `palette`, `settings` | yes | yes, also the profiles and the palettes in `./profiles`, `./palettes` and `~/.config/roadstyle/` |
| `basemap`, `basemaps`, `basemap_switcher`, `api_key`, `zoom_readout` | yes | page |
| `arrows`, `labels`, `legend`, `name` | yes | yes |
| `legend_position` | folium | folium |
| `hover_color`, `select_color` | yes | yes, also on the overlays |
| `minzoom` | yes | yes: `True` or a table |
| `offset_frac`, `width_frac`, `offset_zoom` | yes | yes |

### Filtering

| Keyword | Python | Rust |
|---|---|---|
| `include`, `exclude`, `match_links` | yes | first |
| `filter_control`, `find_control`, `overlay_control`, `overlay_popup` | yes | page |
| `filter_col` | yes | yes |
| `access_col` | yes | yes |

### Color by data

| Keyword | Python | Rust |
|---|---|---|
| `color_by`, `colors`, `cmap`, `vmin`, `vmax`, `width_by` | yes | yes |
| `color_table`, `color_key`, `color_col` | yes | yes |
| `color_options`, `color_active` | yes | yes, if each option has the palette of the map. An option with another palette is an error |
| `views` | yes | yes. With `tiles=True`, a view with its own palette is a `ValueError` (the tiles have one palette) |
| `style` (a `Styler` object) | yes | Python |

### Popups and hover

| Keyword | Python | Rust |
|---|---|---|
| `road_popup`, `popup_mode`, `road_tooltip`, `tooltip`, `hover_delay_ms` | yes | yes (in the style's metadata `roadstyle:interaction`) |
| `side_panel_html`, `host_panel_width` | yes | page |
| `data_maxzoom`, `data_tolerance` | yes | yes |
| `selected`, `copy_field` | folium | folium |

### Street View and Google 3D

| Keyword | Python | Rust |
|---|---|---|
| `street_view`, `street_view_key`, `google_3d` | yes | page |

### Camera and 3D

| Keyword | Python | Rust |
|---|---|---|
| `pitch`, `bearing`, `max_pitch` | yes | yes |
| `view_3d` | yes | yes. The engine makes the deck ribbons with its own mitre offsets, not with GEOS, so a corner can differ by the rounding (1e-6 degrees) |

### Output and scale

| Keyword | Python | Rust |
|---|---|---|
| `tiles` | yes | yes: the archive of the Rust engine's tiles. The `tiles` extra is not necessary |
| `simple` | yes | yes: `True` (simple mode) and `False` (the full look) |
| `compress`, `tunnel_control` | yes | page |

### Column mapping and levels

| Keyword | Python | Rust |
|---|---|---|
| `highway_col`, `tunnel_col`, `bridge_col`, `layer_col`, `edge_id_col` | yes | yes |
| `casing_level_col`, `fill_level_col`, `casing_start_col`, `casing_end_col` | yes | yes. Without them, the engine computes the levels (`compute_levels`, method `"solve"`) |
| `head_m`, `head_start_m_col`, `head_end_m_col` | yes | yes |
| `cap_col`, `cap_start_col`, `cap_end_col` | yes | yes |
| `road_fill` | yes | yes |
| `width_m_col`, `width_m_zoom`, `casing_m`, `casing_min_px` | yes | yes |
| `directed_col`, `driving_col` | yes | yes |
| `levels_db` | yes | first: Python reads the stored levels, then the engine draws them |

### Overlays, items and boundary

| Keyword | Python | Rust |
|---|---|---|
| `overlays` | yes | yes: every kind of `Overlay` (fill, line, circle, text), on edges, in metres |
| `items` | yes | yes. A MultiLineString item is an error |
| `items_popup` | yes | page |
| `boundary` | yes | yes |

## Public functions

| Function | Python | Rust (`engine="rust"`) |
|---|---|---|
| `render_edges` | yes | yes, with the keywords above |
| `render_dashboard`, `render_report`, `render_street_view` | yes | yes: the same page (they call `render_edges`) |
| `export_inline` | yes | yes |
| `export_style` | yes | yes: `format="xyz"` and `"pmtiles"` |
| `export_look` | yes | yes |
| `compute_levels` | yes | yes for `method="tags"` and `"solve"` with the default keywords; another keyword (`near_rules=True`, ...) is Python |
| `level_input`, `solve_levels`, the level areas and the level editor | yes | not in the engine (Python only, no `engine` keyword) |
| `save_levels`, `load_levels`, `save_area_levels`, `load_area_levels` | yes | not in the engine |
| `snapshot`, `to_spec`, `to_html`, `save`, the Leaflet output | yes | not in the engine |
| `load_edges`, `from_duckdb`, `from_arrow`, `from_geojson`, `as_edges`, `filter_edges` | yes | not in the engine: Python reads the data, then the engine draws it |
| `register_palette`, `save_palette`, `load_palette`, `palette_to_dict`, `palette_from_dict` | yes | not in the engine. The engine takes a palette by its name (a bundled palette, or a file in `./palettes`) or in `settings` |
| `use_settings` | yes | yes: the engine takes the settings in force (`roadstyle.json`, `$ROADSTYLE_CONFIG`, `use_settings`) |
| the CLI, the MCP server, the studio | yes | not in the engine |

The source of this list is the checklist "What Python roadstyle can do and the crate cannot yet" in
[One Rust engine for roadstyle](../design/rust_engine.md#what-python-roadstyle-can-do-and-the-crate-cannot-yet-2026-10-23).
