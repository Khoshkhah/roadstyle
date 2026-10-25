# T3: the typed map options and the typed look (design, no code yet)

The target architecture (section (d), approved on 2026-10-24) gives three option types, one for each consumer: the `Look` (the resolved
style), `MapOptions` (what a caller chooses for one map, which changes stage 1) and `PageOptions` (the page's keys, `page.rs`). Stage 2
has `TileOptions`, and the style writer has `SourceMode`. This note is the design of `MapOptions` (audit N32) and of the typed `LookData`
sections (audit R16), for the look lane. The engine's and the facade's readers change to the typed fields after it (N32 step 2,
roadstyle-rs).

## Today (rust-engine f1ee2ea)

- `LookData` has 10 JSON values: `settings`, `args`, `theme` (14 sections), `config` (37 keys), `styles`, `slots`, `roads_model`,
  `features`, `oneway_image`, `interaction`. The typed parts are made from them (`RoadModel`, `RoadLook`, `SlotLook`, `DeckLook`).
- `config` is StyleConfig's flat view: most of its keys are a copy of a theme section (`config.arrows` = `theme.arrows`, the
  `bridge_*` keys = `theme.bridges`, the `tunnel_*` keys = `theme.tunnels`, ...).
- The engine and the facade read about 60 option names from `args` as text (with the 15 column keywords of `ColumnMap`). A misspelt
  name is ignored.

## The rules

1. **One type for each consumer.** A key that changes the stage-1 output (the style, its sources, the road table) is in `MapOptions`; a
   key that changes only what the page does with that output is in `PageOptions` (the coordinator's rule, 2026-10-24).
2. **Rust names.** No `_col` suffix inside `Columns`; no Python-only key; no key that names a host (no `_export`, no
   `resolved_basemaps` in `MapOptions`).
3. **Defaults.** Each struct is `Default`. A value that the profile gives is `Option<T>`: `None` means "the profile's value".
4. **Unknown key: an error** (`deny_unknown_fields`) of kind `roadstyle_look::Error::Options`, with the key's path and the nearest known
   key (`"color.by_column": unknown key; did you mean "color.by"?`). The same helper as the MCP's option check, if it has one.
5. **JSON in and out.** `MapOptions::from_json(text)` and `serde_json::to_string`. The bindings pass JSON text. The Python binding maps
   `render_edges`' keywords to the JSON form (the old names as aliases in `roadstyle-py` only).

## MapOptions

```rust
#[non_exhaustive]
pub struct MapOptions {
    pub columns: Columns,
    pub levels: Levels,
    pub color: Color,          // the data colours
    pub width: Width,
    pub roads: Roads,
    pub interaction: Interaction,
    pub labels: Labels,
    pub arrows: Arrows,
    pub tunnels: Tunnels,
    pub bridges: Bridges,
    pub overlays: Vec<Overlay>,
    pub items: Option<Items>,
    pub boundary: Option<serde_json::Value>,      // GeoJSON: a geometry, a Feature or a FeatureCollection
    pub base_map: Option<BaseMapOptions>,
    pub output: Output,
}
```

| Group | Field: type (default) | Today's key | Reader |
|---|---|---|---|
| `columns` | `class: String ("highway")`, `tunnel`, `bridge`, `layer`, `edge_id`, `directed`, `driving`, `access`, `filter`, `width_m`, `cap`: `Option<String>` | `highway_col`, `tunnel_col`, `bridge_col`, `layer_col`, `edge_id_col`, `directed_col`, `driving_col`, `access_col`, `filter_col`, `width_m_col`, `cap_col` | engine (ColumnMap), colours, roads |
| `columns.levels` | `Option<LevelColumns>`: `casing_start`, `casing_level`, `casing_end`, `fill_level`, `head_start_m`, `head_end_m`, `cap_start`, `cap_end` | the 8 `*_col` keys | engine (compute_levels skips) |
| `levels` | `enum Levels { Solve (default), Tags, Stored { edge_hash: String, n_edges: u64 }, Given }` | `levels` (object or `"tags"`), the presence of `casing_level_col` / `fill_level_col` | engine compute_levels |
| `color` | `by: Option<String>`, `colors: Option<Map<String, Color>>`, `cmap: Option<Cmap>` (a name or a list of colours), `vmin`, `vmax: Option<f64>`, `missing: Missing (Nodata)`, `table: Option<ColorTable { colors: Map<String, Color>, key: String ("edge_id") }>`, `options: Vec<ColorOption>`, `active: Option<usize>` | `color_by`, `colors`, `cmap`, `vmin`, `vmax`, `missing`, `color_table` + `color_key` (the column that the table joins on: stage 1 writes each road's colour from it, so it stays), `color_options`, `color_active` | engine colors.rs |
| `width` | `by: Option<String>`, `range: Option<(f64, f64)>` (px), `m_zoom: Option<f64>` | `width_by`, `width_m_zoom` | engine colors.rs, roads |
| `roads` | `fill: bool (true)`, `head_m: Option<f64>`, `casing_m: Option<f64>`, `casing_min_px: Option<f64>`, `offset_frac`, `width_frac`, `offset_zoom: Option<f64>`, `minzoom: ClassMinzoom { Profile (default), Off, Table(Map<String, f64>) }` (the keyword: `True` or `None` = Profile, `False` = Off, a dict = the profile's table with these changes; the default is the standard map convention, 2026-10-25) | `road_fill`, `head_m`, `casing_m`, `casing_min_px`, `offset_frac`, `width_frac`, `offset_zoom`, `minzoom` | engine, RoadModel |
| `interaction` | `popup: Popup (Default)` (`enum Popup { Default, Fields(Vec<String>), Panel, Off }`), `tooltip: Option<Vec<String>>`, `hover_color`, `select_color: Option<Color>` | `road_popup`, `road_tooltip` / `tooltip`, `hover_color`, `select_color` | engine (metadata, highlight paint) |
| `labels` | `on: bool (true)` | `labels` | engine slots |
| `arrows` | `on: bool (true)` | `arrows` | engine slots |
| `tunnels` | `control: bool (false)` | `tunnel_control` | engine contract |
| `bridges` | `decks_3d: bool (false)` | `view_3d` | engine decks |
| `overlays` | `Vec<Overlay>`: `label`, `data` (a FeatureCollection value), `kind: Option<OverlayKind>`, `color`, `outline: Option<Color>`, `opacity`, `width`, `radius: Option<f64>`, `placement: Placement`, `popup: Option<Vec<String>>`, `popup_window: bool`, `tooltip`, `visible: bool`, `edge: Option<EdgeLink { column, order_column }>`, `select: Select`, `width_m`, `min_zoom`, `max_zoom`, `dash`, `text: Option<TextStyle>`, `color_column` | `overlays` (rs.Overlay's fields) | engine overlays.rs |
| `items` | `Option<Items>`: `data` (a FeatureCollection value), `popup: Option<Vec<String>>` | `items`, `items_popup` | engine overlays.rs |
| `boundary` | `Option<serde_json::Value>` (GeoJSON) | `boundary` | engine |
| `base_map` | `Option<BaseMapOptions>`: `modes: Vec<Mode>` (driving, walking, cycling), `layers: Map<String, LayerStart { clickable, tooltip, popup: Option<bool> }>` | `modes`, `interaction` | engine contract, overlays |
| `output` | `name: Option<String>`, `state: State (Static)` (`enum State { Static, Live }`), `live_data: bool (false)` | `name`, `state`, `live_data` | engine |

### What leaves `MapOptions` (the target's changes)

| Key | Goes to | Why |
|---|---|---|
| `simple` | nowhere | Simple mode is the one drawing approach. Only the Python binding keeps `simple=False` as an error until 0.27.0. |
| `export`, `data_maxzoom`, `data_tolerance` | `SourceMode::Inline { export, maxzoom, tolerance }` of the style writer | choices of the writer, not of stage 1 |
| `tile_keep`, `tile_layers` | `TileOptions` (roadstyle-tiles) | stage 2 |
| `hover_delay_ms`, `box_layout`, `copy_field` (the popup's copy button), `legend` (show the legend or not; its data is stage 1 and always written) | `PageOptions` | page keys (the coordinator's answers, 2026-10-24); `copy_field` leaves the style's interaction metadata, and the page takes it from RS_OPTIONS or the host's options |
| `basemap`, `basemaps`, `api_key`, `basemap_switcher`, `sidebar`, `side_panel_html`, `host_panel_width`, `street_view`, `street_view_key`, `popup_mode`, `filter_control`, `views` | `PageOptions` (they are there already, R3) | page keys |
| `resolved_basemaps`, `_export`, `_palette_copy`, `_read`, ... | nowhere in the core | host-private keys: the Python binding keeps them in Python |

`filter_control` stays a page key (the coordinator's answer, 2026-10-25; R3 rule 5: the controls are the facts of the look, and the page's
keywords stay in RS_OPTIONS). Whether the dashboard shows its filter panel is the page's choice. The facts of the filter (the classes, the
access kinds, the modes) stay in `roadstyle:controls`, because they are the output of stage 1. Step 4 removes the read of the flag in
`contract.rs` (the `on` of the filter entry); the dashboard reads `on` from RS_OPTIONS or from the host's options.

The base map's look (`BaseMapLook`, from `look::Options.base_map`) gives `box_layout` and its `basemap` / `basemaps` to the page through
`PageOptions` defaults, not through `MapOptions`.

## The typed look

`LookData` keeps one JSON value: `settings` (the sources as given, for the record). Each other part becomes a struct. `config` goes: each
of its keys is a field of a section (or a field of `RoadModel`), and the resolution writes the sections only.

| Section | Fields (today's theme / config keys) |
|---|---|
| `RoadLook` | `classes: Map<String, ClassStyle>`, `fallback: ClassStyle`, `width`, `width_zoom_rate`, `casing_ratio`, `zoom_stops`, `links`, `split`, `cap`, `join`, `fill_opacity`, `twin_casing`, `twin_end_caps`, `single_line_classes`, `minor_no_casing`, `link_scale`, `minzoom`; with today's `styles` (the resolved class styles) and `roads_model` |
| `CasingLook` | `extra`, `m`, `min_px`, `drop_below_px` (default 1.0: no casing where it is narrower than this many pixels at a zoom; 0 = always a casing), `opacity` |
| `LabelLook` | `base_size`, `color: Color`, `font`, `fraction`, `glyphs`, `halo_color: Color`, `halo_width`, `max_angle`, `min_px`, `minor_minzoom`, `minzoom`, `padding`; with today's `slots` (`z_order`, `width_z20`, `width_z20_fallback`) and `annotations.slot_m` |
| `ArrowLook` | `color: Color`, `icon`, `main`, `main_below`, `minor_minzoom`, `minzoom`, `opacity`, `place`, `size`, `spacing`, `image` (today's `oneway_image`) |
| `BridgeLook` | `cap`, `casing_color: Color`, `casing_extra`, `casing_m`, `casing_px`, `ramp`, `shadow { color, blur, offset, trim_m, on }`, `wing_scale`, `decks: DeckLook` (`base_m`, `casing_px`, `flat_below`, `match_zoom`, `opacity`, `ramp_m`, `step_m`, `thickness_m`, `underlay`, `width_scale`) |
| `TunnelLook` | `cap`, `casing_dash`, `dash_extra_px`, `fill_dash`, `fill_dash_color: Color`, `opacity_scale`, `palette`, `palettes`, `ratios`, `steps`, `strength`, `to`, `toward`, `towards` (today's `folium_dash` goes with folium at P7) |
| `SelectionLook` | `casing`, `hover`, `select: Color`, `glow_opacity`, `opacity` (today's `folium`, `folium_hover` go with folium at P7) |
| `DataLook` | `casing_opacity`, `casing_width`, `color_table`, `nodata: Color`, `opacity`, `width` |
| `OverlayLook` | today's `overlays` (both copies are the same) |
| `BaseMapLook` | today's `features` (`layers_yaml`, `buildings_3d`, `style`, `images`), typed in the same way; `None` with no base map |
| `TileLook` | `buffer_px`, `extent`, `maxzoom`, `minzoom` (today's `config.tiles`) |
| `CameraLook` | `bearing`, `max_pitch`, `pitch`, `pitch_3d` |
| others | `access: Map<AccessKind, Color>`, `background { light, dark: Color }`, `boundary { color: Color, dash, opacity, width }`, `palette: String` (the name), `interaction.popup` (the road popup's default fields) |

- **`Color`**: one type (`roadstyle_look::color`, D4): it reads `"#rrggbb"`, `"#rgb"` and a CSS colour name, and writes `"#rrggbb"`. A
  colour that MapLibre takes but this does not (`rgba(...)`, `hsl(...)`) stays a text in a `ColorOrText` enum, so that no look loses a
  value. A bad colour is an error that names it, at resolution.
- **Versions.** `schema_version` becomes 2 (the typed sections). The engine reads 2 (N) and 1 (N-1: today's look, converted by one
  function `v1_to_v2`). Version 0 (0.25.0's `look.json`) stays readable (`v0_to_v1`, then `v1_to_v2`) until the frozen hosts move in T6
  (GeoLibre's worker and duckosm-rust read saved `look.json` files); then `v0_to_v1` goes with P7, and the reader takes 2 and 1 only. A
  rename or removal of a key increments the version.
- **`look.schema.json`** is made from the types (`schemars`, feature `schema` of roadstyle-look), by a test that writes it and fails
  when it differs from the file in the repository (so a change of the types shows in the review).

## Steps (each a commit with its tests; the goldens compare structure and pictures)

1. **`MapOptions` and its JSON** in roadstyle-look (no reader changes): the types, `from_json`, the unknown-key error with the nearest
   key, `Look` keeps `args` beside a `map: MapOptions` made from them. Tests: every key of today's `args` in the goldens' looks parses;
   a misspelt key is an error with the nearest key; the Python binding's keywords map to it (a table test in roadstyle-py).
2. **The typed sections** with `Color`, `v1_to_v2`, `schema_version` 2, `look.schema.json`. `Look` keeps the old JSON views as a
   function (`theme_value(path)`) for the readers that have not moved. Tests: the looks of the goldens give the same sections as the
   JSON views; `v1_to_v2` of each golden look; a bad colour.
3. **The look crate's own readers** (`RoadModel`, `RoadLook`, `SlotLook`, `DeckLook`, `basemap.rs`) read the sections.
4. **N32 step 2 (roadstyle-rs)**: the engine's and the facade's readers move to `look.map.*` and the sections, file by file; at the end
   `args`, `theme`, `config` and the JSON views go. Notes from steps 1 to 3:
   - `Look::other_args` has the keywords of `args` that are not map options. The facade checks them against the keys of `PageOptions`
     and the host's keys: an unknown one is an error with the nearest key (`roadstyle_look::options::nearest`).
   - `contract.rs` does not read `filter_control` (see above).
   - The flat reader `MapOptions::from_args` stays while the engine reads looks of version 1.

## Answers (the coordinator, 2026-10-24)

1. Version 0: kept until T6, removed with P7 (see Versions).
2. `copy_field`: a page key (`PageOptions`).
3. `legend`: a page key. `color_key`: stays in `MapOptions` as `color.table.key`, because stage 1 reads it (colors.rs: the colour table's
   join column, which writes each road's colour into the style's data).
