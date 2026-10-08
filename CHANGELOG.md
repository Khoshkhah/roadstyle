# Changelog

All notable changes to **roadstyle** are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed
- **The notebook preview draws again, with the bundled MapLibre (5.24 from the CDN, was 3.6.2):** 3.6 rejected simple mode's per-feature
  `line-cap` / `line-dasharray`, so the default map was blank. Why the preview had been held at 3.6: it is an `<iframe srcdoc>`, whose
  `location.origin` is `"null"`, while MapLibre's worker reports the notebook server's origin; MapLibre 4.0 to 5.19 drops worker messages
  whose origin differs, so no source ever loaded (style never finished, zero roads). 5.20 accepts the `"null"` origin. Checked headless in
  Jupyter Notebook 7.5 and JupyterLab 4.5: simple, `simple=False` and `tiles=True` draw their roads. A test pins the CDN version to the vendored one.

### Changed
- **A two-way footway, path, steps, cycleway ... is one full-width line, not two lanes** (setting `single_line_classes`, default footway, path, steps,
  pedestrian, cycleway, track, bridleway, corridor, platform; `[]` = lanes for all). Of a reverse pair only the first edge is drawn (so two reversed
  dash patterns never overlap); the second is flagged `__rs_dup` and draws nowhere (simple, full look, `tiles=True`, the level editor). Both edges
  keep their data and name each other (`__rs_edge2`): a click, `rsSelect` and the tooltip show "Direction 1" and "Direction 2" with each one's own
  fields, `rs:select` carries `detail.twin`. Filters and colours treat the line as both edges: it shows (and takes a colour) while either edge is in
  the `rsFilter` / `rsColor` set; hiding one direction alone is not possible (the class, bridge and tunnel switches hit both alike). No arrows.
- **The level solver works from the tables only** (`pairs.csv` + `edits.csv`): a stack is written at make (`rs.level_input`, `roadstyle-levels make`,
  `duckosm levels`, and inside `compute_levels`) as one row per part of the upper road that crosses the lower one (`a_end` `start` / `main` / `end`),
  worked out once with the heads of that time (`heads.csv`, else `head_m`); no whole-road stack rows. The solver lifts exactly the named parts of the
  enabled rows, with no geometry and no head lengths, so a head change never solves (the editor's `what_solver_sees` check is gone). Rows union; an
  edit with `enabled=false` switches off that exact row. `solve_levels` loses `parts` and `near_rules`; `near_rules` moved to `level_input` /
  `make --near-rules` (written as `near` rows, kept last). An old `pairs.csv` with whole-road stack rows, or an edit stack with no part, is an error
  that says what to do (make again / name the part). Monaco all modes: 4,918 whole-road rows to 487 part rows; 14.8 s, 0 given up, 22 wishes not kept.
- **The level editor redraws only the roads an Apply changed, in place** (no page reload): the server finds the roads whose levels, heads
  or caps are drawn differently and sends their features (roads, simple pieces, and the names / arrows when a fill number changed), built
  by `render(_edges=...)`; the page swaps them with `GeoJSONSource.updateData`. More than 1,500 changed roads: the whole page again, said
  in the status line. Monaco all modes, one cap: 6.1 s to 0.7 s from Apply to drawn. The roads and simple sources carry feature ids
  (the roads source its index, as `generateId` gave; a piece `16 * edge + k`).
- **A local re-solve keeps the untouched roads' numbers exactly** (`level_area.solve_local`): the result is shifted back when the solver's ground
  moved, so the editor's update in place sees only the roads that really moved (fixed roads that moved by different amounts: an error).
- **Simple mode's line-sort-key has a per-edge tie-breaker** (`+ edge * 1e-8`, under the smallest key step of 0.05; at most 1,000,000 edges, more is
  an error that says to pass `simple=False`): pieces with the same key are drawn by edge, so a road redrawn in place keeps its place.
- **The level editor's stack box**: start head / main / end head, several at once, one row each; *whole road* adds all three. *Switch off all found
  stack rows of this pair* (one switch-off per row) to override a found stack.

### Added
- **The level editor's guard before a rule is added** (`rs.levels.rule_conflicts`, `POST /api/check`): an exact duplicate, or a loop of the
  solver's own difference rules through the new one (found, yours, and the list waiting to be applied), named in plain words; you may add it anyway.

### Changed
- **The level solver's near rules are off by default** (`near_rules=False` in `level_input` and `compute_levels`; CLI `make --near-rules` turns them on).
  A part that only comes near the road under it is not lifted (as if switched off); `attrs["levels_near"]` is empty. Monaco all modes: 14.4 s, 9 positions, 0 given up,
  against 45.9 s, 27 positions with 11,911 near rules, 1,477 of them broken anyway.

### Added
- **`render_edges(..., simple=True)`** (web): every road piece in ONE line layer instead of a few hundred (Monaco all modes: 310 layers
  to 7), ordered by `line-sort-key` position by position, casings before fills, with each casing cut into its heads as in the full look;
  colour and width per feature. A bridge has a wider casing and a blurred shadow evenly around it. Leaves out twin end caps;
  names, arrows and edge items are drawn above all roads. Not with `tiles=True` or `tunnel_control=True`. The full look is unchanged.
- **The tunnel look moves toward a colour you choose** (`tunnel_toward`, default `Sand`, #d6cfc4): a name in `tunnel_towards` (Slate, Dark, Light, Graphite, Navy, Stone,
  Sand, Teal) or any `#rrggbb`, the same on every base map (Dark or Light on the base map's own theme sinks a tunnel into the map and keeps each class hue).
  `rsSetTunnelStyle({toward})`, `RS_TUNNEL_TOWARDS` and a colour list in the Tunnels box.

### Changed
- **`tunnel_control=True` works in simple mode:** the *Tunnels* box, with its palette and dash-ratio selects, and `rsSetTunnelStyle({strength, toward, palette, ratio})` recolour the one road layer (and the names, arrows and items that take the tunnel look).
- **Simple mode draws dashes and end shapes (MapLibre 5.24 per-feature `line-dasharray` and `line-cap`):** a tunnel's casing is two pieces in the one layer, a solid one in the palette's gap colour (clear for *One colour*) and the dashes on top, 3 px wider than a casing; a dashed class's fill (footway, path, steps ...) has the full look's dash pattern; each road's end shapes (`cap_col`, `cap_start_col`, `cap_end_col`, the level editor's round / square / flat) are drawn per piece, two different ends as two fill halves and casing heads, as the full look. A casing's main piece stays round.
- **Simple mode: the bridge shadow and the wider bridge casing grow with the zoom:** none below zoom 14 (no shadow, the full look's bridge casing), linearly to the full values at zoom 17 and above (they were too strong zoomed out).
- **`simple=True` is the default** for every web map (`render_edges`, the dashboard, report and street-view pages, the level editor): one road layer, no tunnel / dashed-class dashes, every end round,
  a blurred bridge shadow. `simple=False` draws the full look. `tiles=True` works with simple mode: the pieces of the one road layer are a layer
  (`simple`) of the embedded archive, read by `roads-simple` as a vector source layer; the command line (`--tiles`) and the Studio (vector tiles) use simple mode too.
- **One tunnel slider for every colour**: the steps 0, 25, 50, 55, 60, 65, 70, 75, 100, and `tunnel_strength` defaults to 60 (was 35), and the default target is Sand (was slate), so the default tunnel look changes.
- **The level editor does not solve for a head change** (see the first entry: the solver takes no heads).

## [0.17.1] — 2026-10-07

### Fixed
- **pyarrow is a dependency:** a level area writes `roads.parquet` (`roadstyle-levels make`, `duckosm levels`); without pyarrow it failed.
- **The solver's last stage at its time limit keeps its best numbers** (cost and fewest positions; what is over what is fixed by the stages
  before), with a warning and `levels_info["status"] == "TIME_LIMIT"`, instead of failing: an all-modes area failed on a slower machine.

## [0.17.0] — 2026-10-07

### Added
- **`Overlay(select="road" | "item")`** for items attached to a road: `"item"` selects the item itself (its own select and hover highlight,
  its own popup with the road's Street View link, `rs:select` with `item` = `{overlay, id, properties}` next to the road's `id` and
  `properties`); `"road"` (default) selects the road as before. The item still hides with its road. Overlays now take the page's
  `hover_color` / `select_color` for their highlight (they kept the default colours).

### Fixed
- **Each direction of a two-way road selects its own edge:** a click or hover takes the road right under the cursor before the tolerance box
  around it, which reached both directions near the middle and picked the one drawn last.
- **The class filter hides a road's street names and arrows with `filter_col` too:** every piece of a road (fill, casing pieces, fill halves,
  end caps, name and arrow slots) carries `__rs_cls`, its road's `filter_col` value (else `highway_col`), and the class filter reads it; the
  slots carried only the chain's `highway`, so with `filter_col` set the names and arrows of a hidden class stayed.

### Changed
- **One lookup for every piece of a road** (docs/design/edge_items.md, step 2): `rsFilter` on the roads, the class filter and the bridge and tunnel
  switches hide a road's items attached with `Overlay(edge_col=...)` too (they carry `__rs_edge`, the index of their road, and its class and level as
  `__rs_cls` / `__rs_lvl`), and `rsFilter` now hides the bridge shadows and 3D decks of the filtered roads (shown while any of their edges is).
  Hovering an attached item highlights its road; clicking it selects the road (`rs:select` with the road, its panel and Street View; an interactive
  item's fields come along in `overlays`). `rsFilter(ids, label)` on an attached overlay combines with its roads' filters. An overlay that belongs
  to no road is as before.
- **Every piece of a road names its edge** (docs/design/edge_items.md, step 1): `roads` features carry `__rs_edge` (their index), and the casing pieces, seams, fill halves, end caps, name and arrow slots carry `__rs_edge` (and `__rs_edge2` for a two-way pair) in place of `__rs_road` / `__rs_road2`; bridge shadow lines and 3D decks carry `__rs_edges`, the list of their edges (a list, no longer a string). The map looks and behaves as before.
- **The road tooltip waits** until the mouse rests on a road for `hover_delay_ms` (300 ms; `0`: at once): a mouse passing over the map shows none. The hover highlight still follows at once.
- **`roadstyle-levels make | solve | edit FOLDER`**: the level step and its editor come with the package (`roadstyle.level_area`:
  `make_area`, `solve_area`; `roadstyle.level_editor`), in place of `scripts/level_input.py`, `scripts/solve_levels.py` and
  `scripts/edit_levels.py`. The area folder and its files are as before.
- **Lanes pair only within one class:** two edges on one line in opposite directions are a two-way street's two lanes only when they
  are the same class (names, arrows and end caps too): a footway lying on a street the other way round left the street one narrow, shifted lane.
- `rsFilter` (and the editor's mode boxes) hides a filtered road's fill halves too (a road with two different end shapes kept its colour).
- **Fast filters:** `rsFilter`, `rsColor`, the class / bridge / tunnel switches and the editor's mode boxes look ids up (a MapLibre `match`)
  and set the filters without MapLibre's grammar check (~6 ms a layer): a switch on a page of ~500 layers froze it for seconds.
- The level editor shows only the roads of the modes you tick (driving, walking, cycling, private), when the roads have `modes`; display only.
- The level step keeps a `modes` column (who may use a road, e.g. `driving + walking`) and the level editor shows it in the road's card.
- **Roads on the same line join only if they are the same kind** (`highway`, `tunnel`, `bridge`, `layer`): a footway lying exactly on a tunnel's
  piece was joined with it, and the tunnel piece took the footway's tags (solved and drawn as a footway).
- The priority order warns when the edges have no `junction` column: no road is then known as a roundabout (it lost them silently).
- **An area of a database:** `make_area(edges, folder, db=...)` ties the area to a .duckdb file (`area.json`); every solve of it, the editor's
  too, writes the result with each edge's ends into `visualization.edge_levels` (`rs.save_area_levels`), and `rs.load_area_levels(con, edges)`
  reads it back (refusing other edges). duckOSM's `duckosm levels` makes such an area for all modes.
- **The editor's *Apply and solve* re-solves only the roads around the change** (`roadstyle.level_area.solve_local`,
  `rs.solve_levels(fixed=...)`): the roads within three relations of the changed ones are solved again with the same rules, every other road
  keeps its numbers. When the local result breaks a crossing the previous one kept, has more order wishes not kept, near warnings or drawing
  positions, or the solver fails, the whole area is solved instead and the page says so and why. `roadstyle-levels solve` stays a whole solve.
- **Leaner pages:** a road layer is made only where some feature can be drawn by it (a position without a bridge has no bridge layers, none
  without square ends has no square-end layers, ...); the look is the same. The all-modes Monaco page: 485 road layers before, 291 now.

## [0.16.0] — 2026-10-07

### Added
- **The level step on its own** (`docs/design/level_input.md`): `rs.level_input(edges)` (the solver's input from any edges: `roads`, one row per road, and `pairs`,
  `meet` / `stack` / `order`), `rs.solve_levels(roads, pairs, edits=...)`, and `scripts/level_input.py` / `scripts/solve_levels.py` writing `roads.parquet`, `pairs.csv`,
  an `edits.csv` you own, and `levels.csv`. `compute_levels` is the two in one call.
- **The level editor** (`scripts/edit_levels.py AREA_DIR`): a local page to write `edits.csv`: pick two roads, see their pairs, switch one off or add one;
  every change is solved at once and shown, an edit the solver refuses is not saved.
- **A stack edit on one part of A** (`a_end` = `start` / `main` / `end`): added, that part of A's casing is after B's fill even at a junction; switched off,
  only that part of a found pair is left out. The editor has the part chooser.
- The editor warns when a new order (road 1 after road 2) meets an active stack of road 2 over road 1: the stack outranks it, so the order would be given up.
- The editor: you choose which road is on top for an order or a stack (it was always the road clicked first); changes wait in a list until *Apply and solve*,
  one solve for all, with a busy layer over the map until the new map is drawn.
- `level_input` keeps the edges' `lanes` (shown in the editor's cards). A delete in the editor names its row as the page saw it: if edits.csv changed since, nothing is applied.
- **Your own stacks are always real** (never a near warning), and the order wishes let go are named (`attrs["levels_orders_not_kept"]`) and
  listed in the editor's Issues tab.
- **Street names fit their road:** 9/10 of the road's fill width (at most the old 10 to 14 px), and none where that would be under 8 px:
  names on secondary roads from zoom 16, on tertiary and residential streets from 17 (a service road shows none: the name data stops at z18).
- **The casing follows the same line as the fill:** the casing pieces and fill halves are simplified like the roads (`tolerance` 0.05, was MapLibre's 0.375):
  the outline no longer wobbles along curves.
- **A bridge shadow** (`bridge_shadow`, on): a soft dark shadow shifted 2 px down-right, drawn like an extra casing: every part of a bridge
  (start head, main part, end head) at its own casing number, so it lies over what the part crosses and never on its own road at a joint;
  parts at one number joined into one line, lines meeting end to end (flat ends); none over the last 3 m where a bridge comes down.
- Hiding the bridges (`rsSetBridges(false)`, the filter panel's *Bridges* row, a view's `bridges`) hides their shadows too.
- **Bridge casing slate** (`bridge_casing_color` `#64748b`, the colour tunnels fade to; black was too dark).
- **Casing that closes:** a bridge's heavier casing keeps each piece's cap (it was always flat: two bridge pieces could not close at a bend or
  a junction), and a round seam of casing at each cut inside a road closes the outline on a curve (from zoom 17: below it a seam reached past
  a 5 m head and showed as a bump on a flat end). The fill halves of a road with two
  different ends only paint; the road stays clickable in its own (transparent) fill layer. Default caps stay round.
- **Automatic head lengths and caps per road end, as an option** (`rs.auto_ends`, at zoom 18; `solve_levels.py --auto-ends`; the default stays 5 m and round:
  made for one zoom, the heads were too short at the others): heads as long as the drawings overlap at the join (before
  solving), caps round unless the round end would lie over a lower road or out of the joined roads (after solving, from the levels);
  `heads.csv` / `caps.csv` override (empty = automatic), and `levels.csv` carries each edge's ends as drawn. `rs.class_width_px`.
- **Three casing parts for every road; no length in the solver:** `solve_levels(empty_main=...)` (the roads whose main part is drawn with no length,
  from `rs.empty_mains(roads, head_m, heads)`) replaces its `head_m`: an empty main part is never lifted. A short road's heads count one by one,
  so given-up pairs are counted honestly (Monaco 22, was 16 undercounted). Head lengths per road end are the drawing's: `render_edges(head_start_m_col=...,
  head_end_m_col=...)`; the editor's *heads* inputs (`heads.csv`).
- **End shapes:** `cap_col` takes `"square"` (flat, as long as round), and `cap_start_col` / `cap_end_col` set one end each (an edge with two different ends is drawn
  from its casing heads and two fill halves). The editor: *start* / *end* round / square / flat per road (`caps.csv`), and the road's drawn width and lanes in its card.
- **Near rules last:** a stack rule whose part of A does not cross B (only near) is kept after the order wishes and, broken, is a warning
  (`attrs["levels_near"]`), not a given-up pair; `rs.casing_parts` gives the parts (replaces `empty_mains`), `solve_levels(parts=...)`.
- The editor has an **Issues** tab (given up in red, near warnings in amber): the crossing pairs the solver could not keep, A's parts under B's fill in red, each clickable.
- `examples/levels/monaco/`: hand-made level tables for Monaco (`edits.csv`, `heads.csv`, `caps.csv`).
- The editor has a search box: an edge id (either direction of a road) or an edge_ref, or a part of one; a hit is picked and shown.
- **An `amber` palette**: motorway `#f28c28`, trunk `#f5a623`, primary `#f4c542`, secondary `#f7df72`, tertiary `#b8d986`,
  residential `#d7dee8`, living_street `#cbd5e1`, service `#94a3b8`, track `#a3a3a3`; the other classes, the widths and the casings as `carto`.
- **`views=`**: a *View* menu next to *Colour by*. A view is a name and a set of settings applied together: the colour option, the road fill, which overlays show, the road classes,
  bridges, tunnels, 3D and the base map (`{"Lanes": {"road_fill": False, "overlays": {"lanes": True}}}`). The page opens with the first view; `rsSetView(name)` applies one from a host page.
  An unknown setting, or a name the page does not have, is an error. Design: `docs/design/core_model_and_views.md`.
- **`rsSetRoadFill(on)`**: the roads' own fill on or off in the page; with `road_fill=False` it can now be shown again.

### Changed
- **Meet or cross:** roads of different bands that only meet (a tunnel mouth, a bridge end) follow the priority order; roads that cross keep the band. With `band_col`
  the caller's bands decide everywhere. A short road on top keeps its pair on its fill (it was dropped). Monaco: tunnels on top at 223 of 350 mouths, every crossing right.
- **`render_edges` takes no `band_col` and no `order`** (an error says to compute the levels first); without level columns it calls `compute_levels` with its defaults.
  `compute_levels(order=...)` defaults to `"priority"`.
- **One arrow per one-way road in the window** (`docs/design/arrows_and_names.md`): the page puts one arrow in the middle of each one-way road's visible part,
  and keeps it there while it stays in the window; below zoom 17 only the main classes, none on a road shorter than 100 px on screen, and 150 px between arrows; the arrows no longer repeat along every 100 m slot (they crowded zoom 15). A tiled map keeps the old arrows.
- **The *Tunnels* box is off by default** (`tunnel_control=False`): it was the tool for choosing the tunnel look; the look it chose stays the default.
- **The default palette is `amber`** (`palettes.DEFAULT_PALETTE`) in place of `highsat` (too sharp); `carto` was tried first, but its white streets
  vanish on a light base map. `palette="highsat"` keeps the old look.
- **The order where roads meet:** `compute_levels(order="priority")`, now the default of `render_edges`: where roads of one band meet, a roundabout's fill is over a tunnel's,
  a tunnel's over a bridge's, a bridge's over the road class (`junction_col`, default `junction`: `roundabout` or `circular`). The band is unchanged, so a road that crosses over a tunnel
  still covers it. `order="class"` keeps the road class alone.
- **The tunnel look, v2's slider** (`docs/design/tunnel_look.md`): `tunnel_strength` (0-100, 35) moves everything on a tunnel, its fill, street names,
  arrows and attached items, toward slate, opaque (replaces the 72 % see-through fill and its underlay). The casing is two layers with MapLibre's dash, 3 px wider:
  a palette's two colours, dash on gap (`tunnel_palette`, default `Graphite + silver`), or slate dashes with empty gaps (`One colour`), moved toward slate with the rest; dash ratio 1:1 (`tunnel_casing_dash`). The two-tone casing
  (`tunnel_gap_shade`, `tunnel_dash_shade`) is gone. A *Tunnels* box (`tunnel_control`) and `rsSetTunnelStyle({strength, palette, ratio})` move it in the page; the slider has five steps (Normal colors 0, Subtle 20, Balanced 35, Strong 70, Full 100).
- **No light dashes on a tunnel's fill by default** (`tunnel_fill_dash: []`, v2's look); `[1.2, 1.2]` brings them back.
- **An arrow that would touch a street name is left out** (MapLibre places the names first; an arrow never pushes a name away).
- **`road_fill=False`**: the tunnel pattern is drawn over the items of its position, so a tunnel reads as a tunnel on the lanes; a hovered interactive overlay wins over the road under it.
- **Faster page building:** the casing pieces and the arrow and street-name slots are cut with a small numpy cutter instead of shapely's `substring` (the same lines), and a slot of a group of one edge no longer searches for its edge.
  A page of a city of 64,000 roads builds about 40% faster.

## [0.15.0] — 2026-10-04

### Added
- **`render_edges(road_fill=False)`**: the casing of each road, not its fill (the fill layers stay in the page, invisible, for clicks and hovers). The items attached with `Overlay(edge_col=, order_col=)` are then the fill: the use of a library that draws lanes,
  dash lines and connectors itself. Design: `docs/design/edge_overlays.md`, *Three ways to use it*.

- **Overlay styles**: an `Overlay` can name a `style` that a library passes in `settings=` (`config.overlays.styles`; roadstyle ships none) and has new fields: `width_m` (a width in metres, exact from `min_zoom`), `dash`, `min_zoom` / `max_zoom`, and
  the kind `"text"` (`text_col`, `text_size`, `text_color`, `text_halo`), a text along a line or at a point. They work for overlays attached to edges too. Design: `docs/design/overlay_styles.md`.

### Changed
- **A settings file can be YAML** (`.yaml`, `.yml`; PyYAML is now a dependency) as well as JSON. **A settings file that cannot be read is an error**: `settings=` (and `use_settings`, and the files roadstyle finds itself) with a file that is missing, not JSON / YAML or not a mapping raised nothing before and was skipped; it now raises a `ValueError` that names the file, and the settings stay as they were.

## [0.14.0] — 2026-10-04

### Added
- **Overlays attached to edges**: `Overlay(edge_col=, order_col=, color_col=)` and `render_edges(edge_id_col="edge_id")`. A feature is drawn at the position of its edge's fill number, after the fills and before the arrows of that position,
  by `order_col` (global, lower first), so a lane, a marking, a zebra crossing or a sign is over its own road and under every road above it. An edge id that is not among the roads is an error. `rsFilter` on such an overlay keeps each layer's position and order.
  Design: `docs/design/edge_overlays.md`; guide: *Overlays*.
- **The one-way arrows and the street names are connected to the roads**: each piece of road that carries one belongs to the edge under its middle point (`__rs_road`, and `__rs_road2` for the twin of a two-way street) and has that edge's fill number. `rsFilter` on the roads now hides the arrows and names of the edges that are not shown
  (before, only the class filter reached them). Tiles carry the same properties.

## [0.13.1] — 2026-10-04

### Added
- **`compute_levels(min_positions=True)`, on by default**: also minimises the span of the numbers (the highest minus the lowest), so the page has fewer positions, that is fewer layers. It has a lower priority than a stack or an order wish
  and a higher one than compaction, so nothing more is given up; the casings may lie a little farther from their fills. Stage 0 stays a minimum-cost flow. Estonia driving: 9 positions become 5, and the solve takes half the time;
  Vancouver walking: 6 become 5, the solve takes 4.5 times longer; on smaller networks the time is the same. `min_positions=False` leaves it out. The option is stored with the numbers (`min_positions` in `visualization.edge_levels_meta`).
  Numbers saved by 0.13.0 were computed without it: `load_levels` stops with a message that says so, and they must be computed again (or read with `min_positions=False`). Section 7.3.1 of the design.

### Changed
- **A road with no `highway` takes no part in the class order** (`order="class"`): no wish is made for it, with any road, instead of an error. The same for a null number in an `order` column (it was 0.0).

## [0.13.0] — 2026-10-03

### Breaking (0.13.0)
- **Position drawing is the only way the web map draws.** `render_edges(edges)` computes the two positions of every edge itself
  (`compute_levels(method="solve", order="class")`) and draws by them; with `casing_level_col` / `fill_level_col` it draws your own numbers. The three bands
  (below ground, ground, above), the class order as a drawing order, `order_col` (now a `ValueError`) and the separate bridge layers are gone.
  `band_col` stays as an input of the solver. A bridge keeps its heavier black casing, a tunnel its faded, dashed look. See `docs/design/levels_split_casing.md`, section 12.
- **scipy and ortools are core dependencies** (the solver); there is no `levels` extra.
- **`compute_levels(method="solve")` is 2 to 9 times faster:** stage 0 is solved as a minimum-cost flow (OR-tools) instead of an LP with HiGHS; every row of the LP is `x_i - x_j <= c`, the dual of a flow.
  Same optimum on the five reference networks (objectives 130, 1008, 868, 1608, 4786), same number of positions; where several optima exist the numbers can differ in about 2% of the cases. Vancouver driving 29 s to 6 s, Vancouver walking 345 s to 22 s, Estonia driving (738,655 edges) 1,085 s to 352 s; the preparation of the rows is vectorised. `levels_info["solver"]` says `flow` or `highs` (stages 1-3 and an uncertified stage 0 still use HiGHS).
- **`tiles=True` carries the positions**: the archive holds the casing pieces and the twin end caps as tile layers (`casings`, `ends`) next to `roads` and `slots`, and the page reads them
  from the one source (docs/design/levels_split_casing.md, 12.1). Monaco: 3.3 MB tiled against 2.3 MB inline. For a big network compute the positions once (`compute_levels`, `save_levels`).
  Measured: 75,866 edges 6 s, 249,278 edges 22 s, 738,655 edges 352 s (7, 6 and 9 positions).
- `compute_levels(order="class")` raises a `ValueError` for a null road class.

### Added
- **`rs.save_levels(con, levels)` / `rs.load_levels(con, edges, ...)`**: the result of `compute_levels` saved in a duckOSM file, in the new schema `visualization` (`edge_levels`: one row per `edge_id`; `edge_levels_meta`:
  the parameters, the number of edges and a hash of the ids), and read back. Both calls are explicit; reading checks the parameters and the edges and raises an error that says what differs, it never recomputes silently.
- **`rs.compute_levels(edges)`**: the `casing_level_col` / `fill_level_col` positions of every edge. The default `method="solve"` is the optimization (real variables, a margin `margin`, a range `max_level`,
  slack variables for Stack and the order wish; stage 0 as a minimum-cost flow, HiGHS when a wish must be given up). It takes a band (`band_col`, else the tag level), a divided casing (`head_m`) and an order (`order`, a column or `"class"`);
  pairs that cannot be satisfied are reported, not hidden. `method="tags"` is a closed-form rule on `layer` / `bridge` / `tunnel` and the shared nodes.
  It returns `casing_start`, `casing_level` (main), `casing_end` and `fill_level`. The specification is `docs/design/levels_split_casing.md`; the guide is *Which road is on top*.

### Changed
- **The bridge look in position mode** (with `casing_level_col` / `fill_level_col`): a bridge edge is drawn with its heavier black casing and flat ends again, in an extra casing layer of its own casing
  position (`roads-casing-bridge`, `-lv<p>`); the other casing layers leave bridge edges to it.
- **Twin end caps with a divided casing:** the cap's casing ring is painted at the head number of the lane that ends there (`casing_start` / `casing_end`), and is hidden where another road at the node is painted below
  that number; a pair drawn flat with `cap_col` gets no cap.
- **The end caps of two-way pairs follow the positions** (with `casing_level_col` / `fill_level_col`): for each position, the caps' casing is drawn right before that position's casing layers and
  their fill right before its fill layers (they were drawn before all positions and after all positions), and a cap hides its casing where a road at the node is painted below it by position.
- **`casing_start_col` / `casing_end_col` / `head_m`: a divided casing.** The casing of each edge can be drawn as a start head, a main part and an end head, each at its own number, from its own source of pieces;
  the fill stays one line; the main piece ends flat (butt caps, through the `cap_col` twin layers) so that its end cannot reach into the heads, the heads stay round. `compute_levels(method="solve")` returns `casing_start`, `casing_level` (main), `casing_end` and `fill_level`, with the heads swapped for the reversed direction of a road.
- **One-way arrows and street names follow the positions too** (with `casing_level_col` / `fill_level_col`): one layer of each per position, right after
  that position's fill layers, instead of tiers chosen by the `layer` tag and one name layer above everything. A tunnel's arrows were drawn under all road
  layers in this mode; they are now above their own road.
- **With `casing_level_col` / `fill_level_col` the position alone decides the drawing order, with no exception.** The class order
  (`z_order`), the level (`layer`), `band_col` and `order_col` no longer order anything, and a bridge is drawn at its positions like
  any road instead of in its own deck layers (it keeps its colours; the heavier black deck casing is not drawn; the 3D decks of `view_3d` still follow the tags).
  Without the columns nothing changes.

## [0.12.0] — 2026-10-03

### Added
- **`casing_level_col` / `fill_level_col`: the drawing order of each edge** (docs/design/level_columns.md). Two integer columns: the
  position in the drawing order where an edge's casing is drawn and where its fill is drawn. At each position every casing of the
  position is drawn first, then every fill, so edges that share a node merge cleanly and an edge drawn at a higher position is over the
  lower one with its own casing. One casing layer and one fill layer (with the tunnel look and the dashed classes) for each position
  that occurs, in position order; position 0 keeps the layer ids; `rsColor` / colour-by reach every fill layer. They replace the three
  bands for every edge but a bridge. Without the columns nothing changes.
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
