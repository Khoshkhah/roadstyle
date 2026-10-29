# Dashboard templates and the toolbox

Status: approved 2026-10-29. Being built in the steps D1 to D8 of section 4.

## 1. Why

A SimReady session built a layout and a toolbox on the old Python `main` branch (67 commits, `git log 87917037..python-engine-final`). Since 2026-10-29 the old branch is the tag `python-engine-final`, and `main` is the Rust engine.
It is in Python (`render_dashboard(layout=, toolbar=)`) and in `window.rs*` switches. Kaveh wants named dashboard forms and one toolbox
for every project, with the options in Rust and a phone form for each form. The design changes only the page: tile contract 2 and the tile budget stay as they are.

## 2. Inventory of the old `main` (tag `python-engine-final`)

| Feature | Where on the old `main` | In the Rust engine |
|---|---|---|
| Overlay layout: full map, floating panel, chevrons, corner scale box that slides with the panel | `dashboard_layout/layout.js`, `layout.css`, `pages._with_layout` | a module; `Layout` in Rust; binding pass-through; Playwright |
| Toolbar: 4 positions, slides beside the panel, theme first, attribution last, dark theme, pop-ups in its look | `layout.js` (moves MapLibre controls into the bar) | the tool registry (3.2); `Toolbar` in Rust; the bar written by `page.rs` |
| Base-map box: swatches, themed pairs, keyless list, "On top" | `layout.js`, `basemaps.py` (`_MENU`, `_TWINS`, `_SWATCH`) | fields in `data/basemaps.json`; `BasemapBox` in Rust |
| OpenFreeMap vector styles under the roads, `rsBuildings` | `basemap.js`, `basemaps.py` | `style_url` in `data/basemaps.json`; `basemap.js` |
| A 401/403 tile check of each base map at build time | `basemaps._answers` | open question 4 |
| Window rules: clamped, re-clamped, keep their size, no map re-center, start closed | `layout.js`, `float.js`, `streetview.js` | `WindowRules` in Rust; `float.js` |
| Google 3D: one-way link, Follow, `rsG3dFov`, the low-camera note, imagery modes and labels | `google3d.js` | `Google3d` in Rust; `google3d.js` |
| 3D layers and the "Show" selector, one selection style | `google3d.js`, `render_web.py` (`google_3d_layers`) | `Google3d.layers`; JS under `rs.g3d` |
| Debug switches (`?g3dalt=`, `?g3d=leave`, logs, counters) | `google3d.js` | open question 5 |

These parts are SimReady parts. They stay out of roadstyle: the Guide and its steps, the milestones, the verdicts and `reviews.yaml`, the
Layers tab of the model, `#sr-focus`, `rsJumpLog`, the four 3D layer registrations (M1 to M4), the Monaco thumbnails.

## 3. Design

### 3.1 The templates

One typed option, `Dashboard`, in a new module `rust/roadstyle/src/dashboard.rs`. `PageOptions` gets a field `dashboard`. The template
gives the defaults. A page can change each field, except the panel's template HTML (the template is that HTML).

| Form | Called by | Desktop form | Phone form (width 700 px or less) |
|---|---|---|---|
| `map` | `render_edges` (default) | The map and the MapLibre control column, as today. A host panel (`side_panel_html`) is possible | The column as today; the boxes fold (`panel._narrow`) |
| `dashboard`, `layout="overlay"` | `render_dashboard` (default) | The sidebar `templates/dashboard.html` floats at the right, toolbar at the right, window rules on | Toolbar horizontal at the top; the sidebar is a bottom sheet; a window is a bottom sheet, and one sheet is open at a time |
| `dashboard`, `layout="dock"` | `render_dashboard(layout="dock")` | The same sidebar docked at the right, 340 px. No toolbar | The sidebar is a bottom sheet (3 heights: closed, 40 %, full). The map stays full width |

**Decided 2026-10-29: there is one template, `dashboard`.** There is no `classic` and there is no report page. The old docked form is
`layout="dock"`, a setting of the dashboard. The names `classic` and `report` are errors of `template=`; a caller of `render_report` uses
`render_dashboard`. A future template is built in the style of the dashboard (3.4), never in another style.

The boundary is an input of the page (`boundary=`), not read from a file by roadstyle. Its shade and its camera limit are off until the page
asks (`boundary_dim`, `boundary_limit`): a fixed area is a choice of the page, because a page can show a general map.

Each template has one panel at most (Kaveh, 2026-10-28: "the design was wrong from the beginning by adding two side panels").

The Rust types (serde, `deny_unknown_fields`; the defaults come from the template):

```rust
pub enum Template { Map, Dashboard }
pub enum Layout { Dock, Overlay }
pub enum Edge { Right, Left, Top, Bottom }

pub struct Dashboard {
    pub template: Template,
    pub layout: Layout,
    pub panel: Option<Panel>,            // side, width_px; the HTML is the template's
    pub toolbar: Option<Toolbar>,        // None: the MapLibre control column
    pub windows: WindowRules,
    pub basemap_box: BasemapBox,
    pub google_3d: Google3d,
    pub phone: Phone,                    // max_width_px: 700, toolbar: Edge::Top
}
pub struct Toolbar { pub position: Edge, pub tools: Vec<Tool> }
pub struct WindowRules { pub clamp: bool, pub recenter_map: bool, pub restore_open: bool, pub remember: bool }
pub struct Google3d { pub fov_deg: Option<f64>, pub follow: bool, pub min_alt_m: f64, pub min_zoom_drawn: f64,
                      pub layers: Vec<Layer3d>, pub selection_style: LineStyle }
```

Only `dashboard` sets `windows.clamp: true` and `recenter_map: false`. The other templates keep today's window rules.

The `window.rs*` switches of the old `main` become fields:

| Old `main` | Rust engine |
|---|---|
| `rsWindowRecentre = false` | `windows.recenter_map: false` |
| `rsRestoreWindows = false` | `windows.restore_open: false` |
| `rsG3dFov` | `google_3d.fov_deg` |
| `rsG3dMinAlt`, `rsG3dMinZoomDrawn` | `google_3d.min_alt_m`, `google_3d.min_zoom_drawn` |
| `rsG3dSelectionStyle` | `google_3d.selection_style` |
| `rsToolbarHold`, `rsToolbarShow` | a page tool in `toolbar.tools` (the bar knows its size at the first paint) |
| `rsG3dOwnDraw`, `rsG3dDraw` | the page registers the 3D layer `selected` |

### 3.2 The toolbox

| Kind | Tools (default order) | Rules |
|---|---|---|
| `button` | `zoom_in`, `zoom_out`, `compass` | One action |
| `toggle` | `theme`, `view3d`, `buildings` | A pressed state; `buildings` needs a vector base map |
| `box` | `basemap`, `legend`, `attribution` | One open at a time; opens toward the map's center, stays inside the window, closes on an outside click or Escape |
| `window` | `street_view`, `google_3d` | Section 3.3 |

The default order on the bar: `theme`, `zoom_in`, `zoom_out`, `compass`, `view3d`, `street_view`, `google_3d`, `basemap`, `buildings`,
`legend`, the page's tools, `attribution`. A tool whose option is off (`google_3d: false`) is not on the bar.

In Rust, a `Tool` is a built-in name or a page tool `{id, icon, title}`. A page adds or removes a tool in `toolbar.tools`. `page.rs`
writes the bar with its buttons in the first HTML, so no frame shows an empty bar or the old column.

The JS side, on the `rs` object (`window.rsTools` is the alias):

| Call | Effect |
|---|---|
| `rs.tools.bind(id, {onClick, box, pressed, available})` | Gives a page tool its behavior |
| `rs.tools.add(tool)`, `rs.tools.remove(id)` | Adds or removes a tool at run time (the bar grows or shrinks) |
| `rs.tools.open(id)`, `rs.tools.close(id)`, `rs.tools.list()` | Opens or closes a box or a window; lists the tools and their states |
| `rs.on("tool", fn)` | Tells the page of each open, close and press |

Each control module registers its tool and adds no MapLibre control. Two renderers read the registry: the column (template `map`) and
the bar. Thus the DOM moves and the 150 ms poll of the old `layout.js` go.

### 3.3 The pop-up boxes and the windows

| Part | Rule |
|---|---|
| Base-map box | One radio row with a swatch for each map, then "On top": Hillshade, Labels, 3D buildings. A themed pair is one row. Labels is one state for the 2D map and the Google 3D window (decided 2026-10-29): the switch is always on, the Google 3D window always follows it (HYBRID with labels, SATELLITE without), and the 2D map gets labels only from the base maps that can show them (the OpenFreeMap styles; Esri Gray and Esri Satellite add Esri's label tiles). Blank, OpenStreetMap, Esri Streets and CARTO get no label layer from the page |
| Base-map data | `data/basemaps.json` gets `style_url`, `group`, `title`, `dark`, `swatch`, and a `menu` list in place of `switcher`. The Esri label and hillshade URLs move there from the JS |
| Legend box | The legend of the active color option, the classes in two columns |
| Attribution box | The base map's text, and Google's when a Google window is open |
| Area boundary | The outline of the area (decided 2026-10-29, level 3): a thin line over the base map and under the roads, the outside of it shaded, and the camera limited to the boundary's bounds (`maxBounds`, with a margin). It comes from the table `main.boundary` of the duckOSM file; a page of a plain GeoDataFrame gives it with `boundary=`. Fields: `boundary.outline`, `boundary.dim`, `boundary.limit`, each on by default in `dashboard` and `dashboard` and off in `map` and `report` |
| Theme | One value on `<html>` (`light` or `dark`) that the sidebar, the bar, the boxes, the popup and the tooltip all read (decided 2026-10-29: the popup and the tooltip have a dark theme too). The theme button of the bar sets it; a dark base map can set it |
| Windows | Opened and clamped in the free area (between the panel and the bar) at each change. A window keeps the user's size and grows back. With `recenter_map: false`, it never moves the map |
| Google 3D | The map leads, in one direction only (brief section 9). Input in the window, or a Google camera change that the page did not set, turns Follow off |
| 3D "Show" selector | `Layer3d {id, label, kind (Line, Ribbon, Polygon, Points), source, match_prop, scope (Selection, View), max: 500, style, arrows, on}`. JS: `rs.g3d.layers.register`, `list`, `setOn`, `refresh` (alias `window.rsG3dLayers`). The menu shows with two layers or more. A page can replace the built-in layer `selected` |

### 3.4 The style rules for every part

Every part that is added to a dashboard (a tool, a box, a window, a control of a panel) follows these rules. A part that breaks one is not
finished. (Decided 2026-10-29: "every item must follow the style, and have a dark and a light theme".)

| Rule | What it means |
|---|---|
| Two themes | The part works in the light and the dark theme, and follows the one theme value on `<html>` (`data-rs-theme`). It has no color of its own: it reads the tokens |
| Tokens | Colors come from the tokens of `popup.css`: `--rs-tb-bg` (the bar, the panel, the scale box), `--rs-box-bg` (boxes, windows, popup, tooltip), `--rs-card-bg` (the layer before the text), `--rs-tb-ink`, `--rs-tb-border`, `--rs-tb-hover`, `--rs-tb-on`. The opacities are `--rs-a-tb`, `--rs-a-box`, `--rs-a-card`, which the person sets in the settings box |
| One look | Rounded corners (10 px for boxes, 14 px for windows and lists, 8 to 12 px for controls), the 6 px blur, no light border line on a dark surface, one shadow. Text sits on the card layer, not straight on a translucent layer |
| No system parts | No native `title` tooltip (tip.js takes it), no native `<select>` list (selectbox.js), no native scrollbar style. Native controls get `color-scheme` from the theme |
| Boxes | A box of the bar has the same width (264 px), padding (8 px) and font (12 px) as the others, keeps 12 px from the window edge, opens toward the map, and closes on an outside click and on Escape. It is never clipped by its parent: a bar must not have an `overflow` rule |
| Panels | The header stays and only the body scrolls (`.sb-top` and `.sb-body`). The body does not hand its scroll to the map |
| Places | The part works with the bar at each of the four edges, with the panel on the left and on the right, and on a phone (700 px) |
| Test | The part is on the sample page (a panel with cards, text and controls), and it is looked at in both themes, with the bar at two edges and on a phone, before it is committed |

## 4. The port from the old `main`

The port copies the JS from the tag `python-engine-final` into `rust/roadstyle-assets/files/static/dashboard/` and changes it to read the typed options. It is
not a git merge of the old branch. Each step lands alone, with its desktop form, its phone form and its tests.

| Step | Content | Tests |
|---|---|---|
| D1 | `Dashboard`, `Template` and their defaults in Rust; the binding passes `template`; `sidebar=` becomes the template | The `map`, `dashboard` and `report` pages are the same as before; a Rust test for each template's defaults; the guard `scripts/check_no_python_shape.py` |
| D2 | The tool registry and the column renderer | The column has the same buttons in the same order as before |
| D3 | The bar renderer: 4 positions, theme and attribution tools, the box rules, the dark theme | The bar checks of section 5 |
| D4 | The overlay layout, the floating panel, the chevrons, the corner box; template `dashboard` | The panel checks |
| D5 | The window rules in `float.js` | The window checks |
| D6 | The base-map box, the `basemaps.json` fields, the OpenFreeMap merge, "On top" | The base-map checks |
| D7 | Google 3D from the last form of the old `main`: one-way link, Follow, the note, modes and labels | The Google 3D checks, with the `gmp-map-3d` stub |
| D8 (done) | The 3D layers and the "Show" selector: `Layer3d` in Rust (`Google3d.layers`, the page keyword `google_3d_layers`), read by `google3d.js` | The 3D layer checks (`tests/test_google3d_layers_browser.py`, with a stub of Google's `maps3d` library) |
| D9 | The area boundary: `Boundary` in Rust, the outline, the dim and the limit in JS. The polygon is the page's input (`boundary=`); the dim and the limit are off until `boundary_dim` and `boundary_limit` | The boundary checks: the line is under the roads; a pan cannot leave the bounds when the limit is on; each field can be turned off |

What happens to the old `main` (the tag `python-engine-final`, which no branch follows):

1. It gets no new work. A SimReady fix that it needs is made in the Rust engine, with a line in the port list below.
2. The Rust engine is `main` (`rust-engine` is the same commit).
3. The SimReady page moves to the Rust dashboard (`template="dashboard"`, its tools and 3D layers as options) in the SimReady repository.
   Its `tools/test_map.py` must pass on the new page before the move.

Port list (commits of the tag after 1c835679, and their step): none yet.

## 5. Tests

The Playwright checks from the tag's `tests/test_dashboard_layout_browser.py`, `test_google3d_layers_browser.py`, `test_g3d_fov_option.py`
and the SimReady brief (sections 7j to 7m, 8 to 10):

| Group | Checks |
|---|---|
| Bar | 4 positions; same box after 5 zooms; each button clickable (`elementFromPoint`) with the panel open; no old column or empty bar at 100, 300, 1000 ms |
| Boxes | Close on an outside click and on Escape; inside the window; the base-map box fits at 703 px height |
| Panel | Open and close: the map's container, the camera and an open window do not change; the bar is 8 px beside the open panel and comes back |
| Windows | Inside the free area at a drag, a resize and a panel change; keeps its size; `restore_open: false` |
| Base maps | The default list in order; a themed pair follows the theme; the Labels rule; a vector style under the roads; 3D buildings follow the pitch and the toggle |
| Google 3D | A Google camera change never changes the map's camera; a map move sets Google only with Follow on; input turns Follow off; the button and a selection turn it on; range and zoom are inverse |
| 3D layers | No menu with only `selected`; 4 kinds; the choice is kept; `scope: View` stops at 500; a Rust layer reaches the page; the selection style can be replaced |

A phone check for each template, at 390 x 844 with touch: no horizontal scroll; each tool is 32 px or more and clickable; the sheet does
not cover the bar; a window is a bottom sheet; 40 % of the height or more shows the map; each box is inside the screen.

## 6. Open questions for Kaveh

| Question | Recommendation |
|---|---|
| 1. Must `render_dashboard` use the new form by default? | **Yes (decided 2026-10-29).** The new form is `dashboard`, the old docked form is `classic`; a project that wants the old look writes `layout="dock"`. The name `review` is gone: it came from the SimReady page and did not describe the form |
| 2. One phone width for every rule? Today windows change at 520 px and boxes at 700 px | Yes, 700 px for all, in `phone.max_width_px` |
| 3. Where is the bar on a phone? | At the top, horizontal, for every desktop position; the panel and the windows are bottom sheets |
| 4. Keep the 401/403 tile check of each base map when the page is built? | No. The engine makes no network requests. A provider that stops answering is removed from `basemaps.json` |
| 5. Keep the debug switches of Google 3D (`?g3dalt=`, `?g3d=leave`, the logs and counters)? | Keep only one read-out behind `?debug=1`; remove the URL switches |
| 6. When does the old `main` stop? | At once: the tag `python-engine-final` gets no new work |
