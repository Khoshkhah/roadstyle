# Changelog

All notable changes to **roadstyle** are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **`cap_col`: square ends per edge** (docs/design/square_ends.md). A column of true / false: an edge with a true value is
  drawn with butt caps (casing and fill) instead of round ones, by a `-sq` twin of each band's casing and fill layer
  (`roads-casing-sq`, `roads-fill-sq`, `roads-low-*-sq`, `roads-high-*-sq`), because MapLibre sets `line-cap` per layer. For a road
  drawn in pieces (a stretch at another level), so the pieces meet without a ring. Nothing changes without the keyword.
- **A tunnel keeps its look in any band.** With `band_col`, a tunnel put at ground level (or high) now draws its two-tone casing
  dashes (`roads-casing-dash`, `roads-high-casing-dash`), light fill dashes (`roads-fill-pat`, `roads-high-fill-pat`) and faded
  fill there too, as in the low band. Without such a tunnel there are no such layers.

### Changed
- **One drawing rule for every road: levels and looks** (docs/design/levels_and_looks.md). A road's *level* decides its draw
  band, nothing else: three bands, low (below ground), ground, high, from `lvl` (the OSM `layer`, else 1 for a
  bridge, -1 for a tunnel) or a caller's `band_col` (which now also moves a tunnel). A tunnel or a bridge is only a *look* on a
  road of its band, as sublayers and data: the tunnel's two-tone casing (`roads-low-casing-dash`), light fill dashes
  (`roads-low-fill-pat`) and faded fill (a data-driven opacity); the bridge's deck casing and fill, drawn after the plain high
  roads. **Removed:** the stretch cutting (`_stretches`: a tunnel, and a plain-layer road, cut into ground and under
  stretches), the `tpieces` source and every layer made for it (`roads-tunnel-*`, `roads-tunnelgr-*`, `roads-lowp-*`,
  `roads-plaingr-*`, `roads-highp-*`), `__rs_piece` / `__rs_pieced` / `__rs_gstart` / `__rs_gend` / `__rs_tfill`, and the page code
  that followed a stretch to its edge. A tunnel is now drawn whole, under every ground road: at its mouth a street's round end
  can show over the start of the tunnel's casing. The one-way arrows of a tunnel are no longer covered by its ground
  stretches, and anything built on a map follows the band of the road it is on.
- **Colour-by reaches the dashed layers.** A footway, path, steps ... edge is drawn by a `-dash<n>` layer; it now takes the
  active colouring too (`rsSetColorField`, `rsColor`), so a pattern and a colour scheme work together.

## [0.11.0] — 2026-09-30

### Added
- **Line widths in metres** (`width_m_col`, `width_m_zoom=16`, `casing_m=0.15`). A column of real
  widths (lanes, a road's `width` tag, a canal) is drawn exactly that wide from `width_m_zoom` on,
  at every zoom (base-2 exponential interpolation, each line at its own latitude), with its casing
  inside the width, so lines side by side touch with a thin divider. Null widths and maps without
  the column keep the class widths (docs/design/metre_widths.md).

## [0.10.0] — 2026-09-30

### Changed
- **Tunnels get light dashes on their fill** (`tunnel_fill_dash`, default `[1.2, 1.2]`, and
  `tunnel_fill_dash_color`, a translucent white that suits any road colour; `[]` turns it off), on
  top of the dashed casing, so a tunnel reads as one at a glance. A dashed class keeps only its own
  dashes.
- **A tunnel is an ordinary road with a tunnel style** (mapstyle's `docs/design/junctions.md`,
  rule 1). A tunnel was drawn in the lower band along its whole length, so at its mouth the street's
  round end lay across it and the street looked like a dead end. Now it goes to the lower band only
  where it really passes under a road it doesn't join (4 m either side of the crossing; at a shallow
  crossing, the whole stretch within 4 m of the road, but never into a mouth); the rest is drawn
  with the ground roads, in the tunnel's colours (an opaque faded fill, the two-tone dashed casing)
  with butt ends. A path above doesn't make an underpass. The edge stays one feature (clicks,
  filters, `rsColor`); its stretches are drawing pieces (source `tpieces`, `__rs_road` = its id).
  Replaces the tunnel mouth pieces: **`tunnel_portal_m` is removed** (an old settings file that
  sets it still loads; the key is ignored).
- **A road with only a `layer` tag acts the same, in the plain look.** One that passes over or under
  no road is drawn with the ground roads, so a `layer=-1` tunnel approach no longer looks cut off
  from the road it joins. One that does (a raised walkway over a street) is cut into stretches: over
  the road (clearing its drawn width at z17) in its own band with butt ends, the rest with the
  ground roads. A caller's `band_col` value still wins. Bridges keep their band.

### Added
- **Two-way roads end like one road.** A two-way road is drawn as two lanes side by side, each
  with its own round end, so every dead end and junction showed two bumps with a dip between
  them. Now each end of a two-way pair gets one round cap as wide as the whole road, under the two
  lanes (new source `ends`, layers `roads-ends-*` per plain band), except where a road drawn in a
  lower band meets that end (a tunnel mouth: the cap's ring would cross it). The lanes are unchanged, so
  both directions stay separately clickable. A cap draws only where both lanes share a colour, so
  maps coloured per direction keep their ends as before. It follows the class filter, the bridge
  and tunnel toggles, `rsFilter`, `rsColor` and the colour options. Setting: `twin_end_caps`
  (default `true`). Adds about 8–11 % to a page. Design: `docs/design/twin_ends.md`. Where a road
  in a lower band meets the end (a tunnel mouth), the cap is fill only: no ring across that road.
- **`directed_col`: say an edge is undirected.** Two-way roads are found by geometry (the same
  line, reversed), so a footway stored both ways, or a one-way street with a walking-only reverse
  edge, was drawn as two lanes. A pair is now two lanes only when neither edge is false in
  `directed_col`; otherwise it is one line, centred and full width. Null = directed (the geometry
  rule).

### Fixed
- **Dashed classes keep their dashes in tunnel and layer stretches** (each stretch layer gets the
  dashed sibling layers the whole-edge layers have).
- **Roads in the low / high bands can be clicked and hovered again.** Since 0.9.2 a road with a
  non-zero `layer` and no bridge / tunnel tag (a raised walkway) draws in `roads-high-*` /
  `roads-low-*`, and so do edges moved by `band_col`; those layers were missing from the pick
  pattern, so the road couldn't be selected.

### Changed
- **Link roads draw below every street, as in every established map style.** A `*_link` used to
  sort just under its parent class, so a `primary_link` covered the residential street it meets.
  Links now sort below every non-link street and above `service`, in their parents' order
  (`roads.z_order`: motorway_link 1.9 … tertiary_link 1.7), as openstreetmap-carto, OpenMapTiles,
  Mapbox Streets and OSM Americana do. A link the table doesn't list still sits just under its
  parent; settings can override any value. Design: `docs/design/junction_order.md`.

## [0.9.3] — 2026-09-30

### Added
- **A Tunnels row in the roads filter panel**, next to Bridges: switch every tunnel off and on, with
  its street names, arrows and mouth. From your own page: `rsSetTunnels(on)`. Shown only when the
  data has tunnels.
- **Draw order per edge: `band_col` and `order_col`.** Which road draws over which no longer has
  to come from its class and level alone. `band_col` names a column of -1 / 0 / 1 that puts an
  edge, casing included, under (`roads-low-*`) or over (`roads-high-*`) the ground roads: a
  sidewalk under its street, a zebra crossing over it; tunnels and bridges keep their band.
  `order_col` names a numeric column that orders edges inside their band instead of the class's
  `z_order` (clamped to -400 … 400, so `rsColor` still lifts a route over everything on its level).
  Both optional and per edge; without them the style is unchanged. Design:
  `docs/design/draw_order_per_edge.md`.

## [0.9.2] — 2026-09-30

### Changed
- **`rsColor` raises the roads it paints to the top of their level.** A highlighted route is no
  longer covered by a street it crosses: its line-sort-key goes up by 500 (levels are 1000
  apart), so a bridge above it still passes over it. `rsColor(null)` puts the order back.
- **Draw order follows the OSM `layer` tag.** Where roads cross, a tagged `layer` now decides
  which one is drawn on top (untagged: a bridge is 1, a tunnel -1, anything else 0). Before, a
  positive `layer` without a `bridge` tag counted as ground level, so a raised walkway was drawn
  under the street it passes over. The look still comes from the tags: deck styling and 3D decks
  only for `bridge`, the tunnel casing only for `tunnel`. Raised roads that aren't bridges draw
  plain in new layers `roads-high-*` (above the ground roads, below the bridges); lowered roads
  that aren't tunnels in `roads-low-*` (after the tunnels). A negative `layer` without a `tunnel`
  tag no longer gets the tunnel look.
- **Tunnel casings in two tones, never with empty gaps.** The dashed tunnel casing (osm-carto)
  left gaps where you couldn't tell whether two tunnel pieces connect. Now the casing is two dark
  shades of the road's own casing, a solid one with darker dashes on top (new layer
  `roads-tunnel-casing-dash` on top of `roads-tunnel-casing`): it is continuous, and the dash
  still says "tunnel". Settings: `tunnel_casing_dash` (default `[2, 2]`), `tunnel_gap_shade`
  (`0.25`) and `tunnel_dash_shade` (`0.5`): how much darker than the road's casing (an already
  dark casing, as in `mono`, keeps its own tone under the dashes).

### Fixed
- **A road running into a tunnel no longer looks cut off.** Tunnels draw under the surface roads,
  so at a tunnel mouth the surface road's casing and round end were painted across the tunnel's
  start like a wall. Now the first metres of the tunnel draw at street level (a new `portals`
  source and `roads-portal-fill` layer), and the road visibly runs into it. Recolouring
  (`rsColor`, `color_options`) and `rsFilter` reach those pieces too. Length: the
  `tunnel_portal_m` setting (default 8 m; `0` turns it off). A tunnel that passes under a street
  within 12 m of its mouth gets no piece, so that street stays whole. Feature ids and the JS API
  are unchanged.

## [0.9.1] — 2026-09-29

### Added
- **`roadstyle-mcp` on PyPI.** The MCP server under its own name, so the install is
  `claude mcp add roadstyle -- uvx roadstyle-mcp`. It has no code of its own: it installs
  `roadstyle[mcp]` (same version) and provides the command. Released together with roadstyle.
- **A Claude Code plugin.** `/plugin marketplace add Khoshkhah/roadstyle`, then
  `/plugin install roadstyle@roadstyle`: the MCP server and the agent skill in one install.
- **Listed in the MCP Registry** as `io.github.Khoshkhah/roadstyle`, published by the release
  workflow.

### Changed
- The license is declared as an SPDX expression (`license = "MIT"`), which setuptools requires
  from February 2027.

### Fixed
- **Base maps no longer go blank when you zoom in far.** Every base map has a last zoom level with
  real tiles: 16 for Esri's Light Gray and Dark Gray, 19 for Esri Streets, Satellite and
  OpenStreetMap, 20 for CARTO. Past it the map showed grey "Map data not yet available" squares
  (Esri answers with a real image, so nothing could tell) or nothing at all. Each base map now
  carries its `maxzoom`, and the map scales its last level up instead. New `Basemap.maxzoom` field
  (default 19); xyzservices providers bring their own.
- **Switching base maps updates the attribution.** It kept the first map's credit ("© CARTO" on
  an Esri map). Switching now rebuilds the base-map source, in the same place under the roads.
- **Roads appear even when the map starts late.** A map opened off screen (a background tab, a
  notebook output scrolled out of view) builds its sources only once it is shown; the inline data
  loader stopped waiting after 60 s and the map stayed empty. It now keeps waiting, and clears the
  self-check banner if the roads arrive after it appeared.

## [0.9.0] — 2026-09-29

### Added
- **osmnx edges render as they are.** `rs.render_edges(ox.graph_to_gdfs(G, nodes=False))` used to
  fail with `TypeError: unhashable type: 'list'`: osmnx keeps every differing tag of the OSM ways it
  merged as a list (`name=['Götgatan', 'Ringvägen']`). Each list now becomes its first present value
  (a merged `tunnel=[nan, 'yes']` stays a tunnel), and the `(u, v, key)` index becomes columns. New
  notebook `notebooks/10_osmnx.ipynb`.
- **An MCP server: roadstyle as tools for AI agents.** `pip install "roadstyle[mcp]"`, then
  `roadstyle-mcp` (stdio). Tools: `render_place` (any place name, roads downloaded with osmnx),
  `render_file` and `snapshot`. Each saves the map and returns its path, a summary and a PNG
  preview. A misspelt option is an error naming the closest valid keyword, errors reach the agent
  with their message, a download falls back to a second Overpass server, and without a CARTO key
  the map uses the keyless `esri_street` base map instead of watermarked tiles.
- **A warning for edges tagged both bridge and tunnel.** They are drawn as bridges; the usual cause
  is osmnx merging a tunnel with the bridge next to it. The warning names the osmnx setting that
  keeps them apart.

## [0.8.6] — 2026-09-28

### Fixed
- **The Street View window stays inside the map.** It could be dragged anywhere in the browser
  window, so on a page with a side panel it could end up under the panel - most easily by moving it
  while the panel was hidden and then showing the panel - and could not be reached again. Dragging now
  stops at the map's edges, and when the map changes size the window is pulled back inside.

## [0.8.5] — 2026-09-28

### Fixed
- **Classic -> Linked still showed a small panorama in a corner in a real browser** (0.8.4's fix held
  only headless). A panorama now exists only while it is on screen: hiding it (Classic, the window
  closed, a message) drops it, and the next Linked view builds a new one in a visible box.

## [0.8.4] — 2026-09-28

### Fixed
- **Classic -> Linked showed a black Street View panel** (one tile in the corner), on the window
  and on the side-by-side page: the panorama was set while its box was still hidden, so it drew at
  0x0. The box is shown first now, then the panorama is set and told its size.

### Added
- **`rsGetStreetViewSpot()` and the `rs:streetviewspot` event: where the Street View spot is, exactly.**
  The edge (`id`, `properties`), metres along it (`m`) and its length, the point (`lng`, `lat`), where
  the viewer looks (`heading`) and the road's own direction (`roadHeading`) - for placing something
  at a precise spot and direction. `source` says whether it is current: `"panorama"` when Linked put it
  there, `"map"` after a click or step (Classic cannot report the viewer's walk).

## [0.8.3] — 2026-09-28

### Added
- **`street_view_key=` on every map's floating Street View window**, not only on
  `render_street_view`: with a Google Maps JavaScript API key the window's bar offers the same
  **Linked** (a panorama; the map marker walks with the viewer) / **Classic** (the keyless embed)
  switch, remembered in the browser. Without a key the window is unchanged.

## [0.8.2] — 2026-09-28

### Added
- **`street_view_key=` on `render_street_view`: the map marker walks with the viewer.** With a
  Google Maps JavaScript API key the panel is a real panorama instead of the keyless embed: every
  step and turn inside it moves the marker (and pans the map to keep it in view), and only Google's
  own street imagery is shown - the embed also offered people's indoor photos. Without a key the
  page is unchanged. **Both versions stay on the page:** a switch in the panel's bar flips between
  **Linked** (the panorama) and **Classic** (the embed) at the spot the viewer is at, remembered in
  their browser. The walking marker is snapped onto the road as drawn, in its lane.
- **`rsSetStreetViewMarkerAt(lng, lat, heading)`**: the marker at any spot, off the clicked edge if
  need be; the next selection or step returns it to the edge.

## [0.8.1] — 2026-09-28

### Changed
- **The switcher offers Light Gray first, and always a blank map.** The default `basemaps` list is
  `esri_gray`, `positron`, `osm`, `satellite`, `voyager`, `dark_matter`, `blank`.
- **No black text on the web map.** The legend, the filter control, the base-map menu, popups and
  hover tooltips, the map's own buttons (2D/3D, Street View), the scale bar and the attribution use
  soft slate (`#334155`, `#475569`) instead of `#16181d` or the browser's black.

## [0.8.0] — 2026-09-27

### Changed
- **The base-map button is a map control**, last in the top-right column after zoom, 2D/3D and
  Street View, with their size and look; its menu opens to its left. It used to sit on `<body>` at
  the bottom right, so a host page with a side panel had to move it by hand
  (`.bm-icon{right:...}`); now it moves with an inset `#map` like the other controls, and those
  old host rules are outranked and do nothing.

### Added
- **`zoom_readout=`** (default `True`): `False` leaves out the "z 13.2" read-out beside the scale bar.

## [0.7.1] — 2026-09-27

### Added
- **`rs.render_street_view(..., layout="below")`** (CLI `--layout below`): the map on top and
  Street View under it, with a divider dragged up and down; `panel_width` is then its share of the
  height. `"beside"` (next to the map) stays the default.

### Changed
- The side-by-side page's header is one compact row (title · road name, then ◀ ▶) instead of two.
- The Street View pages switch to their phone layout only under 520 px (was 700): a docs page's
  text column (~690 px on a laptop) showed the side-by-side page stacked, without its divider, and
  the floating window as a full-width sheet.
- Docs: a **Street View** page with a live demo of each version (the floating window, beside the
  map, below the map); the Manual's colour-by demo opens on the data, its samples drop the
  default `backend="web"`.

- **Docs redesigned**: by task (Get started; seven short guides, each one screen with a live map;
  Gallery; Reference tables; Studio), roadstyle's colours and logo, cards and tabs. Old URLs
  redirect.

### Fixed (layout)
- `render_edges(backend="lonboard", view_3d=True)` (any web-only keyword) raised a TypeError from
  `lonboard.Map`; web-only keywords are now dropped, as on folium.
- The overlay **Layers** control sat on top of the base-map button; it now sits above it (and
  follows a host page's side panel like the button).

### Fixed
- Stepping Street View along a road (◀ ▶) pans the map when the marker nears its edge, so the
  marker stays in view.
- **A map whose Street View window was left open stopped working (0.7.0).** Reopening the window
  on load ran before the marker's state existed; the error stopped the page before any road was
  drawn, so nothing could be selected. The window now reopens once the map has loaded.
- The window's remembered state (open, place, size) is kept per page, not per site: a window
  enlarged on one map no longer reopens over another page's small embedded map. A reopened
  window is also kept to at most 60% of the map and inside it.
- On a two-way road the Street View marker sat 2.5 m right of the centre line, which is off the
  drawn road when zoomed in. It now sits on its direction's lane as the map draws it (the
  layer's own line-offset at the current zoom); Google still gets the 2.5 m lane point.

## [0.7.0] — 2026-09-26

### Added
- **Street View marker and steps.** While Street View is shown (the window, or the side-by-side
  page), a marker on the map (a dot and a viewing cone) shows where it stands and which way it
  looks. **◀ ▶** buttons walk 15 m back or forward along the edge, so a road can be followed
  without clicking the map again. JS: `rsStreetViewStep(m)` (event `rs:streetviewmove`),
  `rsSetStreetViewMarker(on)`.

### Fixed
- `rsSelect(id)` anchored its popup (and now the Street View spot) at the edge's middle VERTEX,
  which on a two-point edge is its end; it now uses the middle of the length (inline and tiled).

## [0.6.0] — 2026-09-26

### Changed
- **The Street View window is the default** (`street_view="window"`): every map gets a Street View
  button. `street_view=True` keeps the old plain link in the popup, `False` turns it off.
  `render_street_view` pages keep only their own panel.

## [0.5.0] — 2026-09-26

### Added
- **`rs.render_street_view(edges)`**: a page with the map and Google Street View side by side.
  Click a road and Street View shows it, looking the way the edge runs (no new window, no API
  key). A draggable divider shares the width (`panel_width=42`, `resizable=True`); on a phone,
  Street View sits under the map. Google's embed loads only in a served page (http/https);
  opened from disk, the panel says how to serve it and links to Street View instead.
  Live demo in the web-backend docs.
- **`street_view="window"`** (web backend): a Street View button on the map opening a floating
  window that follows each clicked road: drag it by its title bar, resize it by its corner; it
  opens at the map's corner (clear of the host page's own panels) and remembers open state,
  place and size per browser. Nothing is loaded from Google while it is closed. The popup link
  opens it instead of a new tab. JS: `rsSetStreetView(on)`, event `rs:streetviewchange`.
- **CLI `--page dashboard | report | street-view`**: the ready-made pages from the shell, with
  `--panel-width` / `--no-resize` for the street-view one.

### Changed
- The Street View link (and `rs:select`'s `detail.streetView`) now points at the nearest spot on the
  clicked edge's own geometry, the road's centre line, instead of the raw click. Clicks on a
  drawn lane, or at an overview zoom, landed metres off the road, so Google often picked a
  nearby indoor photo (a shop interior) instead of the road's Street View imagery. A two-way
  road's twin edges (one line) then each step 2.5 m right, into the middle of their own lane,
  so the two directions no longer share one spot.

## [0.4.2] — 2026-09-26

### Added
- **`street_view=True`** (web backend): a Google Street View link in the road popup / panel, at
  the clicked point and facing the clicked edge's direction, so a road's two directions get
  opposite headings. A plain maps URL, no API key; `street_view=False` turns it off.
  The URL also rides on `rs:select` as `detail.streetView`, for host pages with their own panel.
- **`skills/roadstyle/SKILL.md`**: an agent skill for code that *uses* roadstyle (the one call,
  the data contract, the JS API, the traps); **`AGENTS.md`** for agents working on the repo;
  **`llms.txt`** at the docs site root.
- **`rs.snapshot(..., scale=)`**: device pixel ratio (default 1); `scale=2` for sharp PNGs on HiDPI screens and in print.

### Changed
- Field names in the click popup and the hover tooltip are **bold**, values plain.
- Docs site merged from 15 pages to 9 (Home, Manual, Gallery, Studio, Web backend, Embedding,
  Parameters & API, Palettes/base maps/settings, Engines); the old URLs redirect. Parameters &
  API is now the one complete keyword reference, per backend.
- PyPI summary rewritten; the CLI's `--palette` accepts `mono`.
- README cut to a one-screen overview with a sharp 2x hero image (`docs/build_gallery.py`);
  the parameter tables live in the docs, base maps & API keys moved into the docs (now the palettes page).

### Fixed
- `rs.snapshot(html_string, ...)` raised `OSError: File name too long` instead of rendering it.
- `render_edges(backend="folium", tiles=True)` (or `view_3d`, `street_view`, … any web-only
  keyword) raised a `TypeError` from `folium.Map`; web-only keywords are now dropped on folium.

## [0.4.1] — 2026-08-29

### Added
- **Base map API key resolution & third-party provider support**:
  - Full API key resolution for commercial tile providers (CARTO, Mapbox, Stadia, Thunderforest, Jawg, MapTiler, etc.).
  - Added `roadstyle.set_api_key(key, provider=None)` and `roadstyle.get_api_key(provider=None)` for session management.
  - Added `api_key` parameter across all rendering backends (`render_edges`, `render_web`, `render_folium`, `render_lonboard`, and `to_spec`).
  - Automatic environment variable resolution (`CARTO_API_KEY`, `MAPBOX_API_KEY`, `STADIA_API_KEY`, `THUNDERFOREST_API_KEY`, `ROADSTYLE_API_KEY`).
  - Persistent config file support in `~/.config/roadstyle/roadstyle.json` and `./roadstyle.json`.
  - Automatic injection of `?key=` parameter for CARTO basemaps to prevent "API KEY REQUIRED" watermark.

### Fixed
- **`name=` shows as the page heading.** `render_dashboard` / `render_report` (and the studio's
  *Title* knob) now put the name in the sidebar's `<h2>` as well as the browser-tab `<title>`;
  before, the heading was stuck on the template's hardcoded text.

## [0.4.0] — 2026-07-24

### Added
- **`roadstyle studio`** — the Streamlit workbench now ships inside the package (`roadstyle/studio/`)
  and launches from one command: `pip install "roadstyle[studio]"`, then `roadstyle studio` (no repo
  checkout). The subcommand forwards every extra argument to `streamlit run`, so
  `roadstyle studio --server.port 8502` behaves as usual. Sample networks download on first use
  (cached under `~/.cache/roadstyle`), or are read straight from the repo when run from a source
  checkout. The `ui/studio/` tree keeps only the shared `samples/`.
- **`roadstyle[all]`** — one extra that pulls every user-facing extra
  (`numeric`, `basemaps`, `lonboard`, `duckdb`, `arrow`, `tiles`, `studio`).
  `[dev]` now builds on it (`roadstyle[all]` + pytest/ruff/mypy) instead of
  hand-listing packages — so it gains `streamlit` and can't drift.

### Fixed
- **Web backend honours `legend=`.** `render_edges(backend="web", color_by=…, cmap=…)` (and the CLI
  `--color-by … -f web`) now render the data styler's legend — a continuous ramp or categorical key,
  drawn as a single legend-only entry (no *Colour by* dropdown) — matching the folium backend.
  Previously a data-coloured web map showed no key unless you used `color_options`. `legend=False`
  opts out; class-styled maps are unchanged (they carry the road-type filter, no legend).

## [0.3.0] — 2026-07-24

### Added
- **`render_dashboard()` / `render_report()`** — one call renders a self-contained page: the styled
  map with the built-in controls off and a bundled sidebar injected (the dashboard's query /
  colour-by / class-filter + legend / table UI, or the report's stats panel), wired through the
  public `window.rs*` API. Returns a `WebMap` (`.save("dashboard.html")`). The sidebar templates now
  **ship inside the package** (`roadstyle/templates/`), so `pip install roadstyle` builds these pages
  with no repo checkout; `sidebar_html("dashboard" | "report")` returns the fragment to copy and
  reshape.

### Changed
- `ui/dashboard/build.py`, `ui/report/build.py` and the studio Dashboard / Report pages now wrap the
  packaged `render_dashboard` / `render_report` — one source of truth for the sidebars.

## [0.2.2] — 2026-07-24

### Changed
- **In-map controls restyled** (web backend, `web_template.html`) — the road-class filter,
  colour-by dropdown, legend, base-map menu and overlay control now share one look: muted
  uppercase headers, an accent for the active/hover state, soft shadows and hairline borders. The
  colour-by dropdown and filter are grouped into a single anchored top-left stack, fixing a stray
  top gap and an overlap with the native zoom controls.
- **Popup and hover tooltip are now translucent**, with a backdrop blur that keeps text legible
  over busy maps.

### Added
- Studio (repo tooling, not on PyPI): the **Map** page gains a multi-column colour-by with an
  in-map dropdown + legend, and a shared `colour_by_section` across Map / Dashboard / Report offers
  numeric **and** low-cardinality categorical columns (`bridge`, `oneway`, `layer`, …), drops
  id/key columns, and picks a discrete `min(5, n)` categorical scale or a continuous p2–p98 ramp
  per column (unmapped edges stay neutral). The **dashboard sidebar** is restyled to match the
  report and gains a road-class legend; Dashboard and Report gain a *Decorations* (labels / arrows)
  section.

## [0.2.1] — 2026-07-23

### Added
- **Report sidebar UI template** (`ui/report/`) — a stats-forward panel over any web map: KPI
  cards (edges / classes / named roads / length), the active colour-by legend, a checkbox filter
  for overlay layers and road types, search, and a selected-road read-out. Wired entirely through
  the public `window.rs*` API; a matching **Report** page joins the studio.
- **`RS_CLASS_COL` / `RS_CLASS_COLORS` JS globals** (web backend) — the column `RS_CLASSES` came
  from, and each class's baked fill colour, so a custom UI can build a by-class legend or filter.
- Studio **Dashboard** and **Report** pages gain a *Hover tooltip* section (`tooltip=`).

### Changed
- **Panel legend and road-class filter collapse by default** in panel mode (`popup_mode="panel"`),
  reclaiming the space above the record read-out; floating maps are unchanged.

### Fixed
- **Panel search matches column names too.** Bridges are `bridge=yes` (no *value* contains the
  string "bridge"), so a value-only search found nothing; the built-in `_sideSearch` and the report
  sidebar now also match the query against the column name when that field is set, so `bridge`,
  `tunnel`, `oneway`, … resolve.

## [0.2.0] — 2026-07-22

First PyPI release.

### Changed
- **`compress` is now on by default** for web maps (3–4× smaller files; sources under 256 KB
  stay inline). `compress=False` / `--no-compress` writes plain JSON. Gzip blobs are stamped
  with `mtime=0`, so the same map now renders byte-identical across runs.
- Version is single-sourced from `pyproject.toml` (`roadstyle.__version__` reads the install
  metadata).

### Added (vector tiles)
- **`tiles=True` (web backend)**: pack the roads — and the street-name/arrow annotation slots —
  as a **PMTiles vector tileset embedded in the single HTML file**, served to MapLibre from
  memory via an in-page `pmtiles://` protocol (vendored pmtiles.js). MapLibre parses only the
  tiles in view: ~10⁵-edge maps boot in a couple of seconds and stay responsive, still offline,
  still one file. Low zooms carry simplified geometry and only the classes the settings
  `minzoom` table shows there. The full JS API, popups and hover/select work unchanged — full
  per-edge attributes travel in a gzipped sidecar table sharing the same index-id space.
  New extra `roadstyle[tiles]` (mapbox-vector-tile + pmtiles), CLI `--tiles`, settings knobs
  under `config.tiles` (zoom range / extent / clip buffer). Class thinning in the tiles
  follows the `minzoom` parameter exactly like the inline version — off by default
  (residential visible at the opening zoom), opt-in with `minzoom=True`. The dashboard builder
  (`ui/dashboard/build.py --tiles`) and both studio pages (a *Vector tiles* toggle) expose it,
  and notebook/studio previews of tiled maps keep the vendored MapLibre v4 (the CDN v3 preview
  predates promise-style `addProtocol`).

### Fixed (grade separation on walking/cycling networks)
- **Solid roads vanished from maps with dashed classes**: `__rs_dash` is baked as null on
  non-dashed edges and MapLibre's `["has"]` counts a present-null as true — the not-dashed
  exclusion filter silently dropped every solid-class road from the fill/casing layers, so
  walking/cycling maps showed the *basemap's* streets instead of roadstyle's (and stacking
  around bridges looked wrong). The filter is now null-safe (`to-boolean`).
- **Stacked structures order by OSM `layer`**: `lvl` now carries the layer value (bridge ≥ +1,
  tunnel ≤ −1), so a layer=3 viaduct draws above a layer=1 footbridge instead of falling back
  to class importance.
- **Dashed-class bridges get a real deck**: the black bridge casing now includes footway /
  cycleway / path bridges, with a solid underlay (the class's light casing colour) beneath the
  dashes — the osm-carto footbridge look. Previously a path bridge drew as bare floating
  dashes, letting whatever passed underneath show through the gaps.
- **Draw-priority review for walking/cycling classes** (aligned with osm-carto's z_order):
  `service` moved BELOW `pedestrian`/`living_street` (was above — a parking alley could cover
  a plaza), `track` slots just above `footway`, `steps` just below (ties used to break
  arbitrarily), and `platform` gets an explicit bottom-of-stack entry (unknown classes default
  to residential priority — railway platforms were drawing at street level). Dashed classes
  (footway/cycleway/path) now honour the table too: their layers draw UNDER the solid
  casing+fill of the same grade, so a street covers a footpath crossing it (osm-carto order —
  they used to ride above everything as a side effect of the sibling-layer construction).
  Bridge-bucket dashes keep their deck sandwich on top: a footbridge is a structure, not a
  surface marking.
- **Overlay click precedence follows the visual stacking**: an `"over"` overlay (POIs) wins
  the click, then the roads, then `"under"` overlays (zone fills) — previously ANY clickable
  overlay ate the click, so a road inside a clickable zone could never be selected and
  dashboards got no `rs:select` for it. A selected road now also reports the interactive
  overlays under the click — the popup/panel appends a section per overlay, `rs:select`
  carries `detail.overlays` (`[{label, fields, properties}]`), and the dashboard sidebar
  renders road + zone together.
- **Overlay hover tooltips** (`Overlay(tooltip=[...])`): overlays get the same split the road
  layer has — `popup` fields on click, `tooltip` fields following the mouse. Direct clicks on
  ANY interactive overlay (sensors/POIs included, not just zones under a road) now dispatch
  `rs:select` (`detail.overlay` = its label), so dashboard sidebars show overlay info without
  extra wiring.
- Studio: every sidebar section is a collapsible expander (Data and Look start open); each
  overlay gets "Click popup columns" and "Hover tooltip columns" pickers.
- Studio: tiled maps preview correctly and show an "embedded vector tiles" badge. Vendored
  MapLibre v4 stalls ANY roads source (GeoJSON or vector) inside sandboxed iframes, so tiled
  previews go through the same CDN v3 slim variant as inline ones — pmtiles.js's Protocol is
  v3-compatible. Verified in a live Streamlit session.

### Added (release engineering)
- CI: lint + tests on Python 3.10–3.13, plus a headless-Chromium smoke test that boots a saved
  map and asserts the data reached MapLibre (`tests/test_web_smoke.py`).
- Tag-triggered PyPI release workflow (trusted publishing).
- The web page template now lives in `static/web_template.html` (was an inline Python string) —
  same output byte-for-byte.
- Docs: kepler.gl comparison + an explicit practical size ceiling for inlined maps.

### Added (2026-07 wave)
- **One settings file** for every styling default (`data/defaults.json`) with the override
  ladder: `~/.config/roadstyle/roadstyle.json` → `./roadstyle.json` → `$ROADSTYLE_CONFIG` →
  `rs.use_settings(...)` → per-call `render_edges(..., settings=...)`. The theme system was
  removed (single light-grey casing; black on bridges; primary base map is a setting).
- **JavaScript API**: `window.rsSetBasemap/rsSetClasses/rsSetColorField/rsSetOverlay/
  rsSetView3D/rsSelect/rsDeselect` — every in-map control scriptable and event-emitting
  (`rs:*` CustomEvents) — plus **id-set queries**: `rsQuery(predicate[, layer])` returns ids;
  `rsFilter/rsColor/rsHighlight/rsGetProps/rsFocus` act on the set, on roads or any overlay.
- **UI templates** (`ui/`): the sidebar dashboard (query box with SQL-style syntax, verb
  buttons, clickable results table → select + fly-to, detail panel, base-map/colour-by selects).
- **3D bridges**: ramped extruded decks with whole-structure hover/select, black side-strip
  casing (`bridge_decks.casing_px`), width trimmed by `bridge_decks.width_scale`, and a 2D LOD —
  flat cased lines below `bridge_decks.flat_below` (default 16) so bridges stay road-width and
  visible at overview zooms.
- **Tile-less base maps** `blank` / `blank_dark` (plain background colour; saved maps make zero
  network requests); `from_duckosm()`; `rs.snapshot()` (headless-browser PNGs); annotation
  slots (alternating names/arrows); `minzoom` class hiding; scale bar + zoom read-out;
  `road_popup="panel"`; overlay styling defaults in settings; compress; the docs gallery.

Goal: generalize roadstyle from an OSM-only tool into a reusable, data-driven road-map
styling library that can also be embedded in a website. The existing OSM styling stays
byte-for-byte unchanged; everything new is additive.

### Added
- **Curated default road popup**: `road_popup=True` (default) now shows a concise field set
  (`DEFAULT_ROAD_POPUP` = name, edge_id, edge_ref, highway, lanes, bridge, tunnel) instead of every
  column — `name` as the bold title (no label), `bridge`/`tunnel` only when the road actually is one,
  and blank / `nan` values dropped. Pass `road_popup=[fields]` for a custom set or `road_popup="all"`
  for every column; `road_popup=False` still disables it.
- **Per-edge colour table**: `render_edges(edges, color_table={edge_id: colour})` paints each edge
  from your own map (dict / `Series` / DataFrame with `color_key`+`color_col`) instead of by road
  class — for clusters, routes, metrics, etc. Edges not in the table get a **gray** fallback; class
  widths + casing are kept so the network still reads as roads. `colors="self"` does the same from
  a colour column already on the data. New `ColorTableStyler`; works on every backend.
- **MapLibre `web` backend is now the default** (`render_edges` `backend="web"`); the CLI's `-f web`
  emits it too and is the default format. The old `-f web` roadstyle.js page moved to **`-f rsjs`**
  (resolving the name clash). Folium-specific features (legends, filter panel) stay on
  `backend="folium"` / `-f folium`.
- **Web-backend UI toggles**: `arrows`, `labels`, `filter_control` (a new collapsible **road-class
  filter panel** — a checkbox per class present, hides that class across every road layer), and
  `basemap_switcher` (the in-map base-layer dropdown). All default `True`; CLI flags `--no-arrows`,
  `--no-labels`, `--no-filter`, `--no-basemap-switcher`.
- **Web-backend boundary overlay**: `render_edges(edges, backend="web", boundary=…)` draws a dashed
  outline on top of the roads (e.g. the area the network was clipped to). Accepts a shapely
  geometry, a `GeoSeries`/`GeoDataFrame` (reprojected to EPSG:4326), or a GeoJSON mapping; `None`
  (default) draws nothing. Rendered as its own `boundary` layer, so it is excluded from the
  road-class filter and from hover/click picking.
- **MapLibre `web` backend** (`render_edges(backend="web")` → a `WebMap` with `.save()`): a
  self-contained, **zoom-correct** vector map matching openstreetmap-carto. Per-zoom road widths
  (osm-carto width-by-zoom curve) instead of fixed pixels; **two-way directional lanes** via a
  pixel-proportional `line-offset` (`offset_frac`/`width_frac`/`offset_zoom`); direction **arrows**
  and curved **street names** (native symbol layers); **hover/select** via `feature-state`; an
  in-map **base-layer switcher**; class-based **draw order**; and **tunnel/bridge grade
  separation** — one baked `lvl` (from optional `tunnel`/`bridge`/`layer` columns) orders tunnels
  underneath (dashed + faded) and bridges on top (heavier, square-capped casing). The saved HTML
  **bundles MapLibre inline and inlines the data**, so it opens offline from disk with no server.
  Distinct from `save`/`-f rsjs` (the roadstyle.js spec page). See `docs/web-backend.md`.
- Command-line interface: a `roadstyle` console script (`roadstyle.cli`) renders any road file
  from the shell — `roadstyle edges.gpkg -o map.html --theme dark`, with `--include/--exclude`
  filtering, data-driven `--color-by/--cmap/--width-by`, and `-f folium|web|spec|geojson` output.
  Every flag mirrors a `render_edges` keyword. No Python required to make a styled map.
- Interactive selection that **returns the result**: clicking a road in `roadstyle.js` fires
  `onSelect(feature, layer)` (and `onDeselect`) with the edge's GeoJSON feature — geometry +
  properties incl. `__rs_class` — plus a `getSelection()` query method, so a custom page UI can
  react (single-select; click again / the map background to deselect). See `docs/embedding.md`.
- Canonical browser renderer: `static/roadstyle.js` (+ `roadstyle.css`) — one drop-in
  `RoadStyleMap` class (headless core: `load`/`setFilter`/`highlightRoad`/`getRoadClasses`, geometry
  sandwich, hover/selection; plus opt-in legend & road-type filter widgets). `to_html` now **inlines
  this same file** instead of a hand-written copy, so the embedded and standalone renderers can't
  drift (enforced by a test). Shipped as package data.
- Packaging/quality: MIT `LICENSE`, `py.typed` marker, richer `pyproject.toml` metadata
  (classifiers, keywords, URLs), optional extras (`numeric`, `basemaps`), and `ruff`/`mypy` config.
- Data-driven styling: color/size roads by any **categorical** (`color_by`+`colors`) or
  **numeric** (`color_by`+`cmap`+`width_by`) column, with auto legends; both folium & lonboard.
- Stack-agnostic JSON output: `to_spec` (canonical data + baked-in style + legend), `to_geojson`,
  `to_html(full=…)`, `to_iframe`, `save`, `save_spec`/`load_spec` — embed maps in any website
  (Leaflet / MapLibre / iframe; see `docs/embedding.md`).
- Canonical input layer: `RoadEdges` + `normalize_edges`/`load_edges` (normalize-at-boundary).
- Input validation with clear error messages; configurable `StyleConfig`; registries for custom
  palettes/themes/basemaps; palette JSON I/O (`save_palette`/`load_palette`).
- Docs: parameter reference, embedding guide, frontend-integration guide (baked HTML / JSON API /
  JS port), comparison vs `.explore()`/prettymaps, and a runnable example notebook.

### Verified by adoption
- `sweden-road-data` (`nvdb_acquirer.viz.aadt_map`): renders NVDB vehicle edges coloured by AADT
  traffic volume via `render_edges(color_by="aadt", cmap="YlOrRd", width_by=…)` — confirmed on
  927 real Nacka edges (AADT 1–37,828), both folium & lonboard.

### Fixed
- **Internal `lvl` is hidden from web popups/tooltips.** The web backend injects `lvl` (grade-
  separation elevation, -1/0/+1) for draw ordering; like `twoway` it's now skipped in the default
  popup/tooltip (still present in the feature data for z-ordering). Data columns such as `lanes`
  and `edge_ref` keep showing.
- **Large integer ids no longer round in web popups/tooltips.** Property integers past
  `Number.MAX_SAFE_INTEGER` (2^53) — e.g. a content-hash `edge_id` — were inlined as JSON numbers
  and silently rounded by the browser's `JSON.parse` (last digits changed). They're now emitted as
  JSON **strings**, so they display exactly. Display-only: feature ids are MapLibre-generated
  (`generateId`), so styling / filtering / feature-state / `color_options` are unaffected.
- **`tooltip=` now works on the `web` backend.** The shared `tooltip=` argument (and CLI
  `--tooltip`) was silently swallowed by the web backend, which only read its own `road_tooltip` —
  so the default backend produced no hover tooltip. `tooltip=` is now accepted as an alias that
  fills `road_tooltip` when unset, so the same call works across `web` / `folium` / CLI.
- `roadstyle.js` edge selection now works: clicking a road visibly highlights it (the
  glow is sized to cover the edge, so the colour changes even on wide roads), clicking it again
  or clicking the map background deselects it, and a filtered-out edge drops its selection. The
  highlight overlay is non-interactive so repeat clicks reach the road underneath.

### Changed
- Repositioned as an opinionated OSM road-cartography layer that **reuses** mature libraries —
  `branca` (colormaps + legends), `mapclassify` (numeric classification), `xyzservices` (basemaps) —
  instead of reinventing them.

## [0.1.0]

### Added
- Initial release: OSM-theme road/edge styling for folium & lonboard.
- Two palettes (`highsat`, `carto`); three themes (`light`, `dark`, `satellite`).
- Geometry-sandwich rendering; interactive folium layer (dynamic casing, hover highlight,
  road-type filter panel); thumbnail base-layer switcher; neon-violet selection overlay.
