# What is new

This page lists the changes of each version in short. The [CHANGELOG](https://github.com/Khoshkhah/roadstyle/blob/main/CHANGELOG.md) has every change with its details. To move a script to a new version, see [Move a dashboard to the new version](guides/migrating-dashboard.md).

## What is new in 0.28.0

- **The design panel is a dashboard part.** Any page with a dashboard can hold the panel that edits the look of a map, with the tabs Theme, Roads, Text and Layers. [Edit the design of a map](guides/design-panel.md)
- **An *Opacity* slider for the 3D buildings** of a vector base map, and the page keyword `buildings_opacity`. The buildings are solid by default, so a road does not show through a roof. The far buildings of a tilted map now show.
- **`rs.restyle(style)`** gives a map a new look on the same tiles. The event `rs:stylechange` follows each new style.
- **`export_look` has the colours of the map.** It read the palette and missed the colours of a design and of a link class.

## What is new in 0.27.1

- **A page can add a row to the base-map box** (`rsAddTopRow`), a day picker (`rs.days.use`), and a card that opens something (`rs.sections.add({..., open: fn})`).
- **Elevation:** the base-map box has a *3D terrain* row next to *Hillshade* (`hillshade=True` and `terrain=True` start them on), and a switch for the one-way arrows. Page keywords: `terrain_tunnels` and `terrain_exaggeration`.
- **A new look on a live map needs no new tile** when the roads keep their shape: a colour reaches a road piece by its role, and `LiveMap.setLook` keeps the tiles.
- **The "?" of a card that folds is before the chevron.** The chevron is last.
- **A select box on a card looks like a field.**

## What is new in 0.27.0

- **The dashboard's panel starts empty, and a page adds what it needs**: its own HTML, the query box or the road card, with `dashboard={"panel": {"sections": [...]}}` or `rs.sections.add`. The map of a dashboard has the defaults of a map page. `dashboard={"phone": ...}` is gone: the page turns to its phone form when the window is 700 px wide or less. This is a breaking change: see [Migrate a dashboard](guides/migrating-dashboard.md).
- **Cards: one standard for the panel.** A section with a `label` is a card, with or without a background (`background: False`), that folds or not (`fold: True`). Every card has the same width, gap, padding and title row, and the "?" of `rs.help.button` is at the end of the title row (before the chevron since 0.27.1).
- **Every part of the dashboard follows the dark theme, and every scroll area scrolls the same way as the panel.**
- **Street View:** Coverage is an icon after the provider switch, and the close button stays at the top right.

## What is new in 0.26.3

- **A dashboard manual.** Two pages with maps that run: [Dashboards](guides/dashboards.md) for Python and [JavaScript](guides/dashboard-manual/javascript.md). Each JavaScript example has a Run button.
- **The two directions of a two-way road are two halves of the road at every zoom.** A colour on one direction does not hide the other.
- **Fewer arrows on a tiled page, and correct arrows on a page with a vector base map.** Monaco, zoom 16.5: 9 arrows, not 85.
- **Street View:** the coverage shows on any road, and the header of the window keeps the name of the road. `duckosm.page` draws the base map's textures and icons, and `dashboard=False` gives the dashboard without a panel.

## What is new in 0.26.2

- **The level editor follows its page.** In a page with a dashboard, the editor's map has the same base map, the same layers of the area with their switch, and the same light or dark theme. A theme change inside the editor applies. The Base map box has the same rows as the page's. [Edit the levels](guides/levels.md#edit-the-levels-in-a-dashboard)

## What is new in 0.26.1

- **One accent colour.** The dashboard uses the Sonocount teal everywhere, in the light and the dark theme, defined once. The corner box has the shape of the bar, a button with a text shows no tooltip box, and every tool of a phone's one-row bar can be reached. [Dashboard layout](guides/dashboard-layout.md)
- **Help in the level editor.** A **?** button opens a help window with two links to the levels guide. [Edit the levels](guides/levels.md#edit-the-levels-in-a-dashboard)
- **Street View docked, a dashboard with no panel.** `street_view="dock"` and `dashboard={"panel": None}`. [Dashboard layout](guides/dashboard-layout.md)
- **Help buttons and folding.** `rs.help.button` adds a "?" button with its own words; a **Collapse all / Expand all** control folds the panel's sections; a page that starts in the dark theme no longer fails with "Style is not done loading". [Dashboards](guides/dashboards.md)

## What is new in 0.26.0

- **A standard dashboard and toolbox.** `render_dashboard` has one panel and one bar of tools. The bar has one `navigate` button
  (zoom, turn and tilt, with Ctrl + drag), the `roads` filter, one base-map tool, the legend, the settings and the credits.
  A tool that the page cannot use is greyed out, with a reason. On a phone the bar folds and the panel is a bottom sheet.
  [Dashboard layout](guides/dashboard-layout.md) · [Dashboards](guides/dashboards.md)
- **Seven base maps, no key.** OpenFreeMap Liberty and Positron, OpenStreetMap, Esri Gray, Esri Streets, Esri Satellite and Blank, each with its dark twin when it has
  one. The CARTO maps and OpenFreeMap Bright are gone, and a page that asks for one gets `ofm_positron` and a warning. The default base map of `render_edges` is `ofm_positron`.
  [Style the roads](guides/style.md#base-maps)
- **A dark theme for the style's own layers.** The theme switch turns the land, water, buildings and the casing of the roads dark with no new style and no new tile.
  [Dashboard layout](guides/dashboard-layout.md#the-dark-theme)
- **The toolbox is at the right edge** on a desktop, and the panel at the left. On a phone the bar is one row at the top that you move sideways, a fold button hides it,
  there is no hover tooltip on a touch screen, and the Google 3D window has a one-row header.
- **One zoom table.** The dashboard shows service roads and living streets from zoom 14, and steps, platforms, corridors, roads and
  private roads from zoom 15. `minzoom=False` shows all. (Since 0.27.0 a dashboard uses the table of a map page.)
- **Tiles are the default.** Every page embeds its roads as MLT tiles to zoom 16, with one road layer for every zoom. `tiles=False`
  gives GeoJSON roads, and `tile_format="mvt"` gives MVT. One tiling rule serves the page, the browser worker, `export_style` and
  `roadstyle tiles`. [Big networks](guides/big-networks.md) · [Make tiles and PMTiles](rust/tiles.md) ·
  [Tiling](https://github.com/Khoshkhah/roadstyle/blob/main/docs/design/tiling.md)
- **The level editor is in the dashboard.** `roadstyle levels edit AREA_DIR` opens it from the Rust program, with no Python. It draws into the page's one
  standard panel, with the base-map box, red and blue picks, segmented tabs and the area boundary (`levels make --boundary`). The History tab has `edits.csv`.
  [Edit the levels](guides/levels.md#edit-the-levels) · [in a dashboard](guides/levels.md#edit-the-levels-in-a-dashboard)
- **Parts for a dashboard page.** The panel has shared parts: a help window (`rs.help`), a hover box (`rs.hover`), tabs (`rs.tabs`), number tiles (`rs.kpi`),
  scroll areas and tables, chart colours (`rs.svg`), chips and text boxes. `rs.classify` makes discrete colour classes for roads.
  [Dashboard parts](guides/dashboard-parts.md)
- **Live data.** Colours by natural breaks, a legend with the number of roads, and a guide for a new day.
  [Live data](guides/dashboard-manual/javascript.md#live-data-a-new-day)
- **Move a script.** [Move a dashboard to the new version](guides/migrating-dashboard.md) lists each change from 0.25.
