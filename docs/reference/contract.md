# The interaction contract

<p class="lead">What roadstyle's engine, the dashboard and the page share: the style's metadata keys, the dashboard's options, the global
state, the feature properties, the page's placeholders and the browser storage keys.</p>

The design is in [the Rust library plan](../design/rust_library.md#the-interaction-contract). This page is the inventory.
`tests/test_contract_names.py` searches the code for each kind of name below and fails when the code has a name that this page does
not have, or the reverse. The names in the section "Planned names" are not in the code yet.

## The style's metadata

A style that the Rust engine makes with `state: "live"` (a page with the dashboard; `render_edges`) has the contract.
The export's style (`export_style`, `export_inline`: `state` baked) has `roadstyle:interaction`, `roadstyle:images` and
`roadstyle:color_options` only.

| Key | Content |
|---|---|
| `roadstyle:contract` | the version of the contract: 2 (version 2: the road's row is the feature id of the pieces and the slots, not a property; the sort key is `r * 2^32 + id`). The dashboard reads it (`core.js`, `CONTRACT`): a newer version is an error (the console, `rs.error`), and the dashboard adds no road interaction for that style; a style with `roadstyle:*` keys and no version is read as version 1, with a note |
| `roadstyle:state` | each global state `rs_*` and its start value |
| `roadstyle:controls` | the options of `rsDashboard` that come from the style (the next table), and `dashes`: the sorted dash patterns of the road layer's features, for the page's simple-mode script (not an option) |
| `roadstyle:interaction` | `{popup, tooltip, hover_delay_ms}`: the road popup's fields, the hover tooltip, the hover delay |
| `roadstyle:color_options` | `[{name, prop, legend}]`: the colour options and their legends |
| `roadstyle:live` | with `live_data=True` only: `{color, width, types, ramp, nodata}`: the feature states that the road layer reads on the road's row (`rs_c` a colour, `rs_w` a width factor), the default ramp (9 colours of `cmap`) and the no-data colour; a page gives it to the dashboard as the option `live` (null without `live_data`) |
| `roadstyle:images` | the images that the host adds (`oneway`) |
| `roadstyle:planner`, `roadstyle:planner_skipped` | the route planner's graphs, or the number of roads past its limit |
| layer `roadstyle:group` | the group of a layer: `roads`, or an overlay's label |
| layer `roadstyle:over` | a base-map layer that goes over the roads (the 3D buildings) |
| layer `roadstyle:position` | the drawing position of a layer of `export_look` |
| `roadstyle:sources` | each road role of the style (`simple`, `slots`, `arrows`, `decks`, `shadows`) with its source and its source layer (null for GeoJSON), from its final layers (`contract::describe`; after tiling the tile layers); the page gives it to the dashboard as the option `sources` |
| `roadstyle:arrows` | `"points"` (the page's own arrows, the source `arrows`), `"line"` (along the slots) or null, from the final layers; the page's option `arrows` |
| `roadstyle:tiles` | in stage 1's saved `style.json` only: the tile settings that stage 2 reads (`minzoom`, `maxzoom`, `buffer_px`, `extent`) |
| `roadstyle:columns` | in stage 1's saved `style.json` only: the user's class, filter and metre width columns (`class`, `filter`, `width`) |
| `roadstyle:generation` | the generation of the road set: the first 16 hex characters of the hash of the sorted edge ids (`edge_hash`). A row is valid in one generation only. The tile URL (`?g=`) and the PMTiles metadata carry it. The dashboard compares it with the generation of the tiles (the option `tiles_generation`, the document event `rs:tiles-generation` with the generation as `detail`, else the `?g=` of the style's tile URLs). If they differ, it shows one message on the map, hides the layers of the vector sources, adds no road interaction and sets `rs.error`; it checks again when the generation arrives or `setStyle` runs |
| `roadstyle:popups` | the popup fields of each overlay that has some, by its source: `{source: [field]}`. They are not in the overlay's tiles: its props file (`props/<source>.json`, named in `roadstyle:interaction.base_props`) holds them by row, which is the feature id |
| `roadstyle:base` | the names of the base-map layers, if the map has any. The tiles of such a layer keep only the properties that its style layers and the popup read |
| Parquet field `roadstyle:json` | stage 1's Parquet files (`write_sources`): a column whose values are JSON text (values of more than one type, lists or objects) |

## The dashboard's options from the style

`roadstyle:controls` has these options, with the values that `render_web.render` gives the page (`render(_parts=True)` returns them).
The dashboard (`static/dashboard/index.js`, `fromStyle`) takes each one that the page does not give. The overlays' sources and layers
get the page's prefix.

The rule (rule 5 of the plan): `roadstyle:controls` has the facts of the look and of the roads that a host's dashboard needs. The
caller's page keywords (`tiles`, `views`, the base maps, Street View, ...) stay in `RS_OPTIONS`: the page writer gives them, and a
host gives them to `rsDashboard` itself.

| Option | Content |
|---|---|
| `simple` | the id of the one road layer of simple mode (`roads-simple`) |
| `pitch_3d` | the camera's tilt in 3D |
| `select_color` | the colour of a selected road (also the Google 3D line) |
| `filter` | the road filter (the facts that `rsSetClasses` and the colour box's class legend read): `{col, classes, access, swatches, bridges, tunnels, minzoom}`, and `palettes` with a view's palette. `minzoom`: `{class: zoom}`, the first zoom of each class of `classes` that the class minzoom hides below a zoom; null when the minzoom is off (`minzoom=False`) |
| `color_active` | the colour option at the start |
| `overlays` | the Layers box: `[{label, source, layers, hit, visible, color, popup, popup_window, tooltip, under, base, select, interactive}]`; a base-map layer also has `kinds` (`[[kind, count], ...]`, most first) and, with a 3D layer, `extrude` (that layer's id) |
| `tunnel` | the tunnel look: `{layers, dash, casing, strength, palette, palettes, ratio, bg, steps, ratios, toward, towards, to, control}` |
| `fill_layers` | the road fill layers that the page recolours |
| `pick` | the layers that a road is picked on (clicked, hovered): `roads-simple` and the 3D decks' tops (`roads-bridge-decks`), not their casing. A caller's items are in `overlays` |
| `road_fill` | `{on, paint}`: the road fill switch and each fill layer's opacity without it |
| `items` | `{label, popup, layer}` of render's `items=`, or null |
| `edge_id_col` | the roads' id column |
| `arrow_icon`, `arrow_color`, `arrow_rules` | the one-way arrow: its image, its colour and the page's rules for where it goes |

## The page and control variables

"Run time" says whether a page can change the value after it opens. "Gap" marks a value that a page cannot change today and that the
contract makes changeable (or a value that is not used).

| Variable | Type, default | Set in | Read by | Run time | API |
|---|---|---|---|---|---|
| `name` (title) | text, `"roadstyle"` | `render` keyword; look `args.name`; style `name` | page title, host panel | no | |
| `style` | the style object, or null (the roads come later) | `rsDashboard` option | every control | yes | `setStyle`; `restyle` (planned) |
| `prefix` | text, `""` | `rsDashboard` option | every control that finds a roads layer or source | no | |
| `engine.props` | `(row) => Promise<props>` | `rsDashboard` option | `select.js` (click, `rsSelect`, the tooltip, the twin `__rs_edge2`) | | the engine port |
| `engine.restyle` | `(change) => Promise<StylePatch>` | `rsDashboard` option | the controls that need the engine | | the engine port (planned) |
| `basemaps`, `basemap` | keys, `DEFAULT_SWITCHER`, `"voyager"` | `render`; `rsDashboard` option (`BASEMAPS`) | `basemap.js` | yes | `rsSetBasemap`; `rs:basemapchange`; `window.RS_BASEMAPS` |
| `basemap_switcher` | bool, true | `render`; option | `basemap.js` | no | |
| `api_key` | text | `render`, `set_api_key` | the base-map URL | no | |
| `zoom_readout` | bool, true | `render`; option | `zoom.js` | no | |
| `pitch`, `bearing`, `max_pitch` | numbers, none, none, 70 | `render`; `defaults.json` camera | the map | the camera: yes; `max_pitch`: no | gap: no getter or setter of the camera (only `rsFocus`) |
| `pitch_3d` | number, 55 | `defaults.json`; option | `view3d.js` | yes | `rsSetView3D`; `rs:viewchange` |
| `view_3d` (bridge decks) | bool, false | `render`; look `args.view_3d` | engine (deck layers) | no: the decks are in the style or not | |
| 3D buildings | the layer that a base-map overlay names in `extrude`, hidden | engine (mapstyle features) | `features.js` | yes: a button and a row under the buildings | `rsSetBuildings3D`; `rs:buildings3dchange` |
| `find_control` | bool, false | `render`; option | `find.js` | no | `rsFind` |
| find fields | the popup fields, and `edge_id_col` and `edge_ref` (`_ID_KEYS`) | `road_popup`, `edge_id_col` | `find.js` | no | `rsFind` |
| `edge_id_col` | text, `"edge_id"` | `render`; option | `find.js`, `select.js` | no | |
| `road_popup` | false, null (every field) or fields; `DEFAULT_ROAD_POPUP` | `render`; `roadstyle:interaction.popup`; option | `select.js`, `find.js` | gap | |
| `popup_mode` | `"popup"` or `"panel"` | `render`; option | `panel.js` and every docked control | no | |
| `road_tooltip`, `tooltip` | false, true or fields | `render`; look `args.tooltip`; `roadstyle:interaction.tooltip` | `select.js` | gap | |
| `hover_delay_ms` | ms, 300 | `render` (a page key); `roadstyle:interaction` (the look's default); option; `_TIP_DELAY` | `select.js`, `overlays.js` | gap | |
| `copy_field` | text, `"edge_id"` | look `args.copy_field` (mapstyle passes it) | folium only | gap: not used by the web page | |
| `hover_color` | color, `selection.hover` (`#b388ff`) | `render`; the palette | engine: a literal in each highlight expression | gap: fixed in the style | planned (see below) |
| `select_color` | color, `selection.select` (`#7c4dff`) | `render`; the palette; option (Google 3D line) | engine (literal), `google3d.js` | gap: fixed in the style | planned (see below) |
| the glow | `selection.opacity` 0.85, `glow_opacity` 0.35 (palette); the width of the fill (simple mode) | the palette | engine (`_simple_color(glow=...)`) | gap: fixed | planned (see below) |
| `filter` | `{col, classes, swatches, palettes, bridges, tunnels, access, minzoom}` | `render` (`filter_col`, `access_col`); option | `filter.js`, `views.js` | yes | `rsSetClasses`, `rsSetBridges`, `rsSetTunnels`, `rsSetAccess`, `rsGetAccess`, `rsFilter`; `rs:filterchange`; `window.RS_CLASSES`, `RS_CLASS_COL`, `RS_CLASS_COLORS`, `RS_ACCESS` |
| access colors | `access.private`, `bus`, `pedestrian`, `delivery` (palette) | the palette | engine (`__rs_access` colors) | no | |
| `color_options` | `[{name, prop, legend}]` | `render`; `roadstyle:color_options`; option | `color.js`, `legend.js`, `views.js` | the choice: yes; a new option: `restyle` | `rsSetColorField`; `rs:colorchange`; `window.RS_COLOR_OPTIONS` |
| the legend | `{title, kind, entries}` or `{title, kind, ramp, vmin, vmax}` | the data styler (`bake_color_options`); the page shows it when its option `legend` is true (the default) | `legend.js` | follows the option | gap: the metadata does not give the active option |
| `color_active` | index or name, 0 | `render`; option | `color.js` | yes | `rs_co` |
| host colors | `[{color, ids}]` | the host page | the fill and item expressions | yes | `rsColor`, `rsColorBase`; `rs:colorchange` |
| `road_fill` | `{on, paint}`, on | `render`; option | `color.js` | yes | `rsSetRoadFill`; `rs:roadfillchange` |
| `overlays` | `[{label, source, layers, popup, tooltip, interactive, under, base, select, color, visible, popup_window}]` | `render` (`Overlay`); option | `core.js`, `overlays.js`, `filter.js`, `select.js` | visibility, color: yes | `rsSetOverlay`; `rs:overlaychange`; `window.RS_OVERLAYS` |
| `overlay_control`, `overlay_popup` | bool, true | `render`; option | `overlays.js` | no | |
| `items`, `items_popup` | `{label, popup, layer}` or null | `render`; option | `select.js` | no | |
| `tunnel` | `{layers, control, strength, palette, palettes, ratio, ratios, toward, towards, to, steps}` | `render` (`tunnel_control`) and the look (`tunnels`) | `tunnel.js`, `arrows.js` | yes | `rsSetTunnelStyle`; `rs:tunnelchange`; `window.RS_TUNNEL_PALETTES`, `RS_TUNNEL_TOWARDS` |
| the bridge look | casing color and width, shadow, deck (look `bridges`) | the look | engine | no | |
| `views` | `{name: {setting: value}}` | `render`; option | `views.js` | yes | `rsSetView`; `rs:viewselect`; `window.RS_VIEWS` |
| `palette` (views) | text | `render`; views | engine (`rs_palette`) | yes, among the palettes that the views name | `rsSetView` |
| `arrows`, `labels` | bool, true | `render`; the map options (`arrows.on`, `labels.on`) | engine | gap: no switch at run time (a visibility change is enough) | |
| `arrow_icon`, `arrow_color`, `arrow_rules` | the look (`arrows`, `labels.base_size`) | option | `arrows.js` | no | |
| `street_view` | `"window"`, true, false | `render`; option | `streetview.js`, `svspot.js` | yes | `rsSetStreetView`; `rs:streetviewchange` |
| Street View mode | `"linked"` or classic | `localStorage` `rs-street-view-mode` | `streetview.js` | yes | the window's buttons |
| `street_view_key` | text, `GOOGLE_MAPS_KEY` | `render`; option | `streetview.js`, `google3d.js` | no | |
| Street View spot and marker | `{edge, m}` | the click; the host | `svspot.js` | yes | `rsSetStreetViewMarkerAt`, `rsSetStreetViewMarker`, `rsStreetViewStep`, `rsGetStreetViewSpot`; `rs:streetviewmove`, `rs:streetviewspot` |
| `google_3d` | bool, false | `render`; option | `google3d.js` | yes | `rsSetGoogle3D`; `rs:google3dchange` |
| the place of the two windows | `{left, top, width, height}` | `localStorage` `rs-street-view-window:<path>`, `rs-google-3d-window:<path>` | `float.js` | yes | |
| `side_panel_html`, `host_panel_width` | HTML, 320 px | `render` | the page, `panel.js` | open or closed: yes | `rsPanelShow`; `localStorage` `rs-host-panel:<path>` |
| `--rs-side` | CSS length | `panel.js` | `dashboard.css` (the controls on the right move with the panel) | yes | |
| the theme of the page (light, dark) | none on the map page; `data-theme` on the sidebars of `render_dashboard` | `templates/*.html` | the sidebars | the sidebars: yes | gap: `dashboard.css` and `popup.css` have literal colors and one CSS variable (`--rs-side`) |
| `simple`, `tiles`, `fill_layers` | the mode and the road fill layer ids | `render`; option | `core.js`, `select.js`, `svspot.js` | no | |
| `compress`, `data_maxzoom`, `data_tolerance` | | `render` | engine | no | |
| `boundary` | the outline | `render` | engine | no | |
| page self-checks | `window.__rs_gz`, `window.__rs_tiles`, `window.__rs_side` | `_INFLATE_JS`, `_TILES_JS`, `_SIDE_JS` | the page's banner | | |
| `window.map` | the map | the page | the level editor, host scripts | | |
| URL parameters | none today | | | | new: `#rs=` (`getState`, `setState`) |

## The global state `rs_*`

The style reads each one with `["global-state", name]` (`_gs()` in `render_web.py`, `gs()` in `layers.rs`). A live style (`state: "live"`)
declares each one in MapLibre's `state` block and lists its start value in `roadstyle:state`. The dashboard sets the style's global
state: at the start and in `setStyle`, it sets each name of `roadstyle:state` that the map does not have to its start value, and keeps
a value that the map has (the host's or the user's). So a host that adds a live style's layers to its own map (whose style has no
such `state` block) has no step of its own (`core.js`, `_useState`).

| Name | Type | Start value | Values | Read by | Set by | API |
|---|---|---|---|---|---|---|
| `rs_co` | integer | `color_active` | 0 to the number of options - 1 | the fill pieces and items (`match` on the option) | Colour by menu, views | `rsSetColorField`; `rs:colorchange` |
| `rs_top` | list of rows | `[]` | the rows that `rsColor` painted | the simple look's sort key: a painted road is drawn over the others of its level (the colour is the feature state `rs_c` of the row) | host page | `rsColor` |
| `rs_fill_on` | bool | `road_fill` | | the fill pieces' opacity | road fill switch, views | `rsSetRoadFill`; `rs:roadfillchange` |
| `rs_ov_<i>` | object: feature id to color | `{}` | colors | the paint of overlay `i` | host page | `rsColor(..., overlay)` |
| `rs_palette` | text | the start palette | the palettes that the views name | each color that differs between these palettes (`__rs_fill@<palette>` and the paint values) | View menu | `rsSetView`; `rs:viewselect` |
| `rs_tun_strength` | number | `tunnel_strength` (60) | 0 to 100 (`steps`) | each tunnel color | Tunnels box | `rsSetTunnelStyle`; `rs:tunnelchange` |
| `rs_tun_toward` | color | `tunnel_toward` (Sand `#d6cfc4`) | `towards`, or any `#rrggbb` | the same | Tunnels box | the same |
| `rs_tun_two` | bool | the palette has two colors | | the tunnel casing | Tunnels box | the same |
| `rs_tun_c0`, `rs_tun_c1` | colors | `tunnel_palettes[tunnel_palette]` | the palettes | the tunnel casing dash and gap | Tunnels box | the same |
| `rs_tun_ratio` | `[dash, gap]` | `tunnel_casing_dash` (`[1, 1]`) | `ratios` | the tunnel casing dash layer | Tunnels box | the same |

With `state: baked` (the export, RustGIS), the engine writes the start values in place of these expressions.

## The feature properties `__rs_*`

67 names. None is public for a host page: a host reads the data columns and the API. "Dashboard" marks the names that the dashboard
reads (the internal contract between the engine and the dashboard of the same version). "Leaflet" marks the names of the Leaflet spec
Each one goes into a typed field of the render model, and the engine writes the property only
when a layer reads it.

| Names | Meaning | Written by | Read by | Kind | Replaced by |
|---|---|---|---|---|---|
| `__rs_fill`, `__rs_w`, `__rs_op`, `__rs_dash`, `__rs_casing`, `__rs_cw`, `__rs_cop`, `__rs_class` | the class style of the edge: fill color, width, opacity, dash, casing color, casing width, casing opacity, class | `stylers.bake_props`, `roads.rs` | engine layers, `color.js` (`__rs_fill`), Leaflet | dashboard (`__rs_fill`), Leaflet | `RoadDraw.class` + the look; the layer expressions read the class |
| `__rs_fill__<i>` (`__rs_fill__1`, ...), `__rs_fill@<palette>`, `__rs_color` | the fill of color option `i`, of a palette of a view, the `color_table` column | `simple.rs`, `render.py` | engine, `color.js` | dashboard (`__rs_fill__<i>`) | `RoadDraw.look` paint columns (task 1) |
| `__rs_cl`, `__rs_fl`, `__rs_cs`, `__rs_ce` | the casing (main), fill, casing start and casing end numbers | `_mark_levels`, `roads.rs` | engine | internal | `RoadDraw.levels` |
| `__rs_hs`, `__rs_he`, `__rs_cap`, `__rs_cap0`, `__rs_cap1`, `__rs_split` | the head lengths, the cap of both ends, of each end, two different ends | `render` (the head columns), `_mark_caps` | engine | internal | `RoadDraw.ends` |
| `__rs_band` | always 0 since the positions | `_mark_levels` | engine | internal | removed |
| `__rs_twoway`, `__rs_oneway`, `__rs_dup`, `__rs_twin`, `__rs_pair` | two directions, the arrow, the second edge of a single-line pair, the edge of the shared casing, the shared casing | `_mark_twoway`, `_mark_single_line`, `_mark_twin_casing` | engine, `arrows.js`, `svspot.js` (`__rs_twoway`), `select.js` (`__rs_dup`) | dashboard (`__rs_twoway`, `__rs_dup`) | `RoadDraw.direction` and the derived `twin`, `single_line` |
| `__rs_bridge`, `__rs_tunnel`, `__rs_access`, `__rs_lvl` | the bridge look, the tunnel look, the access kind, the tag level of an attached item | `_mark_lvl`, `access_col`, `_edge_overlay` | engine, `filter.js` (`__rs_access`, `__rs_lvl`) | dashboard (`__rs_access`, `__rs_lvl`) | `RoadDraw.structure`, `RoadDraw.look.access` |
| `__rs_ci` | the class index of every feature of `simple` (R8): its class's place in the profile's class list, else the list's length; the road layer reads its width and offset tables with `["at", ["get", "__rs_ci"], ["literal", [...]]]` | `layers::class_index`, `simple.rs`, `_class_index` | the layers | engine | |
| `__rs_cls` | the class column of the edge on every piece, name and arrow of a GeoJSON source (for the class filter); the road table has it too | `_mark_cls`, `roads.rs`, `slots.rs` | `filter.js` | dashboard | the edge label: the dashboard reads the class through the edge |
| `__rs_cc` | the class as a number in a tile: the index of the class in `roadstyle:controls.filter.classes` (a tile has no `__rs_cls`; a page with no filter panel has no class key) | `tiles/src/layer.rs` (`Builder`) | `filter.js` | dashboard | the tile cut makes it; one rule for every path (docs/design/tiling.md) |
| `__rs_kept_` (the prefix of `__rs_kept_<column>`) | the output name of an input column with one of the four level names (casing_start, casing_level, casing_end, fill_level) when the engine computes the levels: the computed ones take the four names | `road.rs` (`Roads::new`, `kept`) | the outputs | internal | |
| `__rs_edge`, `__rs_edge2`, `__rs_edges` | `__rs_edge`: the carrier of a road's key in the engine and on an overlay's item (not a property of a piece or a slot in a style or a tile). `__rs_edge2`: the key of the twin of a road drawn as one line, a field of the road table only (a piece and a slot do not have it since contract 2: `rsFilter` takes the twin from the road table). `__rs_edges`: the keys of a shadow or a deck. A road's key (`RoadKey`, `table << 32 \| row`; the row for one table) is the feature id of its pieces and slots | every generator | `core.js`, `filter.js`, `select.js`, `arrows.js`, the level editor | dashboard | the edge label of each piece (render model) |
| `__rs_k`, `r` | the kind of piece (0 casing, 1 fill, 2 shadow, 3 tunnel gap, 4 tunnel dash, 5 item) and its rank (an integer; the line-sort-key adds the road's key as `r * 2^32 + id`) | `_simple_pieces`, `simple.rs` | engine, `core.js`, `svspot.js` (`__rs_k`) | dashboard (`__rs_k`) | `DrawKey` |
| `__rs_main`, `__rs_seam`, `__rs_lap`, `__rs_stub` | the main casing piece, a seam, a lap, an end stub | `simple.rs` | engine | internal | the piece generators |
| `__rs_wm`, `__rs_cm`, `__rs_twm` | the width, the casing and the pair width in metres (over cos of the latitude) | `_mark_width_m` | engine | internal | `RoadDraw.look.width_m` |
| `__rs_ord`, `__rs_ov`, `__rs_item`, `__rs_ic`, `__rs_iwm`, `__rs_iom`, `__rs_imz`, `__rs_pick` | an attached object's order, its overlay, its row, color, width and offset in metres, minzoom, and "pick it as itself" | `_edge_overlay`, `_item_pieces`, `_road_items` | engine, `select.js` (`__rs_pick`) | dashboard (`__rs_pick`) | `Attachment` |
| `__rs_arw` | the number of an arrow slot (for the export's thinning) | `_annotation_slots`, `slots.rs` | engine | internal | the slot attachments |
| `__rs_base`, `__rs_height`, `__rs_casing_slab`, `__rs_chain` | a 3D deck's base and height, its casing slab, its chain | `_bridge_decks` | engine, `select.js` (`__rs_casing_slab`) | dashboard (`__rs_casing_slab`) | the deck generator |
| `__rs_gz`, `__rs_tiles`, `__rs_side` | not properties: the page's self-check globals (`window.__rs_gz`, `window.__rs_tiles`, `window.__rs_side`: the road table did not load) | `_INFLATE_JS`, `_TILES_JS`, `_SIDE_JS` | the page's banner | page | the page writer |
| `__rs_fill__` | the prefix of `__rs_fill__<i>` in the code | | | | |

## What a page reads

The page's dashboard modules and page scripts declare the feature properties that they read, in
`rust/roadstyle-assets/files/static/dashboard/reads.json`. The file is made from the engine's list of marks
(`roadstyle_model::mark::Mark`, with the features on which the page reads each, and `PAGE_COLUMNS`): `rust/roadstyle-rs/tests/marks.rs`
fails when it differs, and `ROADSTYLE_BLESS=1` writes it again. A new property that the page reads is a line in `mark.rs`, not an edit of
the file.

- `pieces`: the properties of a feature of the road layer (a road piece or an item); `decks`: of a 3D deck or shadow; `slots`: of a
  name or arrow slot.
- `table`: the properties of a row of the road table. A row also has the fields of the popup and the tooltip
  (`roadstyle:interaction`; every public field when the popup list is null), the `edge_id_col` and the road's line.

The layers' own expressions read the properties that they name in `["get", name]` and `["has", name]`. The Rust engine collects these
(`props::drawn`), with the declaration, the popup and tooltip fields, `name` and `kind`. `tests/test_contract_names.py` fails when a module
reads a `__rs_*` property that is not declared, and `rust/roadstyle-rs/tests/sources.rs` fails when a layer reads a property whose name is
not a literal. A change to a module that reads a new property adds the property to `reads.json`.

Both engines write only what is read (R1, 2026-10-24), in the GeoJSON, the GeoParquet files and the tiles:

- A piece keeps what the road layer (the layers on `simple`) and `pieces` read (`props::piece_reads`). An item (`__rs_k` 5) also keeps
  its own fields (a picked item's popup fields).
- A road of the `roads` source keeps all its fields and only the stage values (`__rs_*`) of that set.
- A row of the road table keeps all its fields, the stage values of `table`, and the fills (`__rs_fill*`, which the filter's swatches of
  a view's palette read).

## The drawing positions

The positions of a road (its casing numbers at the start, in the middle and at the end, and its fill number) come from, in this order:

1. the columns that `casing_level_col` and `fill_level_col` (and `casing_start_col`, `casing_end_col`) name;
2. else the input's columns `casing_level`, `fill_level`, `casing_start` and `casing_end` (the ones it has): duckOSM's stored levels. An
   input column with one of these names is the level input;
3. else the solver (`compute_levels(method="solve")` with its defaults).

The browser's keyword `levels` (`"tags"` or `"solve"`, Rust engine) computes them whatever the input has. Then an input column with one
of the four names goes to the outputs as `__rs_kept_<name>`, and a warning names it. Computed positions are not written into the
caller's table: the roads source and the road table give them under the four names, after the road's own columns, as before (2026-10-25).
The table is not renamed: the column keywords (`highway_col`, `bridge_col`, ...) resolve one time to the roles of the columns
(`roadstyle_model::Roles`), and a keyword that names a column the roads do not have is an error that gives the nearest column names.

## The page's placeholders

`static/web_template.html` has these placeholders:

- `__TITLE__`, `__STYLE__` (the style, as `const style = ...`), `__RS_OPTIONS__` and `__HOST_PANEL_HTML__`. The page writer
  (`roadstyle::page::page_html`) fills in these four in one pass, so it does not read a value again.
- `__RS_OPTIONS__` is one JSON object: the options of `rsDashboard` (each with the name of a `render` keyword) and `camera`
  (`center`, `pitch`, `bearing`, `max_pitch`, `bounds`), which the page's own script reads. The template calls
  `rsDashboard(map, {...RS_OPTIONS, style})`.
- `__DASHBOARD_CSS__`, `__DASHBOARD_JS__`, `__POPUP_CSS__` and `__POPUP_JS__`: the frame (`render_web._HTML`, `page::frame`).
- `__RS_TILES__`: the tiled page's scripts. `__MAPLIBRE_CSS__` and `__MAPLIBRE_JS__`: `WebMap` puts in MapLibre when it saves the page.

## The browser's storage and the CSS variables

| Name | Content | Set by |
|---|---|---|
| `rs-street-view-mode` | the Street View mode (`linked` or classic) | `streetview.js` |
| `rs-street-view-window:<path>`, `rs-google-3d-window:<path>` | the place of the two windows | `float.js` |
| `rs-host-panel:<path>` | the host panel open or closed | `panel.js` |
| `--rs-side` | the width of the side panel (the controls on the right move with it) | `panel.js` |

## Planned names

Names of the plan that the code does not have yet (`test_contract_names.py` does not read this section): the global states
`rs_hover`, `rs_select` and `rs_glow` (`setSelectionStyle`), the metadata key `roadstyle:levels` (the source of the drawing positions)
and the layer key `roadstyle:role` (`casing`, `fill`, `item`, `arrows`, `labels`, `highlight`, `deck`, `base`).
