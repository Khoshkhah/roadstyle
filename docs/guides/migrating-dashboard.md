# Move a dashboard to the new version

<p class="lead">Use this page when a script calls `render_dashboard` or `render_report` from an older version, or when you move from roadstyle 0.25 to 0.26 or 0.27. Each old keyword has one new place. This page lists only what changed. The current options are in [Dashboard options](../reference/parameters.md#dashboard-options).</p>

## From an older version

| Before | Now |
|---|---|
| `render_report(...)`, `--page report` | Removed. Use `render_dashboard(...)` |
| `template="classic"` | `render_dashboard(..., layout="dock")` |
| `layout="overlay"` | The default. You can leave it out |
| `toolbar="right"` | `dashboard={"toolbar": {"position": "right"}}` |
| `edit=function` | Removed. Add sections with `dashboard={"panel": {"sections": [...]}}` ([Add to the panel](dashboard-panel.md)), and the page's JavaScript with `page_script=` |
| panel width (a string replace in the HTML) | `dashboard={"panel": {"width_px": 480}}` |
| `window.rsG3dSelectionStyle = {...}` | `dashboard={"google_3d": {"selection_style": {...}}}` |
| `window.rsG3dMeshAltitude = 1.5` | `dashboard={"google_3d": {"mesh_altitude_m": 1.5}}` |
| `window.rsToolbarHold = true` | `dashboard={"toolbar": {"hold": True}}`, then `rs.tools.ready()` |
| `google_3d_layers=[...]` | The same keyword. A wrong key is now an error |
| the panel and the toolbox at the right, the scale box shown | The panel is at the **left** and **empty** (since 0.27.0), the toolbox is at the **right edge** (on a phone, at the top), and the scale box is **hidden**. The base map, color and legend are tools of the toolbox. To get the old place: `dashboard={"panel": {"side": "right"}, "scale_box": True}`. `dashboard={"toolbar": {"position": "left"}}` puts the toolbox at the left |

An old keyword that no longer exists stops with an error that says where it went.

## From 0.25 to 0.26

| Before (0.25.0) | Now (0.26.0) |
|---|---|
| `simple=True` (the default) or `simple=False` | Removed. The simple look is the only look. `simple=` is an error: delete it from your calls |
| `engine="python"` (the default) or `engine="rust"` in `render_edges`, `export_style`, `export_inline`, `export_look`; `ROADSTYLE_ENGINE` for them | Removed. There is one engine, in Rust. `engine=` is an error. The drawing-order solver (`compute_levels`, `solve_levels`, `make_area`) keeps `engine=`, and its default is `"rust"` |
| `backend="folium"`, `backend="lonboard"`, `to_html`, `to_iframe`, `rs.save`, `roadstyle -f spec` and the other formats, a `Styler` as `style=` | Removed. The only backend is `"web"`. Use `color_by`, `colors`, `cmap`, `vmin`, `vmax` or `width_by` in place of a `Styler`. The extras `numeric`, `lonboard` and `tiles` are gone |
| The Python level editor (`roadstyle-levels edit --engine python`, `--items`) | Removed. `roadstyle-levels edit` runs the Rust editor. `--engine` stays on `make` and `solve` |
| The floating Roads box, with a row for each road class (`filter_control=True`) | Removed. The `roads` tool of the bar is the road filter. `filter_control=False` and `--no-filter` have no effect. The filter calls stay: `rsSetClasses`, `rsSetBridges`, `rsSetTunnels`, `rsSetAccess`, `rsFilter`, `rsSetModes`, `rs.setFilter` |
| The floating Layers box, with a row for each base-map layer | A page with a bar has no Layers box. The base-map box has one switch for the style's own base-map layers (`overlays_label`, default "Map layers"; `rsSetOverlays(on)`), and the legend box lists them with their colours. A page with no bar, or with no base-map box, keeps the Layers box. The Tunnels box and the View menu are hidden on a page with a bar |
| `tiles=False` (the default): the roads are GeoJSON | `tiles=True` is the default: every page embeds its roads as tiles. To get GeoJSON roads, use `tiles=False`. A page with a palette in a view needs `tiles=False` |
| MVT tiles, last tile zoom 15, the extra `roadstyle[tiles]` | MLT tiles, last tile zoom 16 (MapLibre scales the tiles of zoom 16 up). To get MVT tiles, use `tile_format="mvt"`. The extra is gone |
| Road layers in zoom bands, with a `minzoom` and a `maxzoom` (builds between 0.25.0 and 0.26.0) | Removed. One road layer (`roads-simple`) and its dash layer (`roads-simple-dash`) draw every zoom. A script that read the ids or the zoom range of the bands must read the road layer without a range |
| A road feature in a tile has text keys (`highway`, `__rs_cls`, the dash text) | A road feature has no text, except the street name of a name slot. The class is the number `__rs_ci`. A script that read `highway` from a tile feature must read the road table: `rs.props(id)`, or `engine.props` in a page that makes its own tiles |
| `minzoom=None` shows every class at every zoom | `minzoom=None` hides the minor classes below their class's zoom, on a map page and on a dashboard alike (the profile's table, `minzoom` in [Every parameter](../reference/parameters.md)). `minzoom=False` shows all classes at every zoom |
| A dashboard with a docked panel and the map's control column: +, -, the compass and 2D/3D | The standard dashboard: the panel and the toolbox, with one `navigate` button (a box with a zoom, a turn and a tilt slider; Ctrl + drag on the map turns and tilts it). `dashboard={"toolbar": {"navigation": "buttons"}}` brings the buttons back |
| The credits button in the column of the map's controls | The credits button is in a corner box with the scale and the zoom number. On a phone it is in the bar. `dashboard={"credits": [...]}` sets your own credits |
| The base-map list with CARTO maps and OpenFreeMap Bright | The list has Liberty, Positron, OpenStreetMap, Esri Gray, Esri Streets, Satellite and Blank. `basemap="ofm_bright"` still works by key |
| A panel of 340 px, and the card behind the text at 75 % | A wider panel (`panel.width_px`: [Dashboard options](../reference/parameters.md#dashboard-options)), and new transparency defaults ([Settings](dashboard-layout.md#settings)). Fit your content to the panel |
| A host page that adapted the dashboard to a style that came later | `rsDashboard(map, {style: null, prefix, ...})` and `rs.setStyle(style)` after each build. Every control that a style gives follows each `rs.setStyle`. The file `data/host_options.json` has the typed options for a host that writes its own HTML (`rsFirstPaint(first)`) |

If a keyword no longer exists, the call stops with an error that names the new place. An unknown keyword of `render_edges` is a `ValueError` that names the nearest known keyword.

A page that uses the level editor in a dashboard: [Edit the levels in a dashboard](levels.md#edit-the-levels-in-a-dashboard).

## From 0.26 to 0.27: the empty panel

| 0.26 | 0.27 |
|---|---|
| the panel had the query box and the selected road, and `hide` took blocks away | the panel is empty; add `{"id": "q", "part": "query"}` and `{"id": "road", "part": "road_card"}` to `panel.sections` |
| `dashboard={"panel": {"hide": [...]}}` | an error: leave it out, and add only the parts that you want ([Add to the panel](dashboard-panel.md)) |
| the ids `bm`, `co`, `sb-legend`, `q`, `tbl`, `count`, `detail` | gone: the parts have classes (`.rs-q`, `.rs-q-list`, `.rs-road-card`) and are found with `rs.sections.get(id)` |
| `basemap="blank"`, `road_popup=False`, a `minzoom` table, `name="Roads dashboard"` set by the template | the template sets no map keyword: the map has the defaults of a map page. Give any of them yourself |
| a click showed the road in the panel only | a click opens the popup; add the road card for the panel, and `road_popup=False` for the card only ([Add to the panel](dashboard-panel.md#a-click-on-a-road-the-popup-the-card-or-both)) |
