# The style in a config file

**Status:** agreed 2026-10-19 (the three open points as proposed). **Step 1 implemented** 2026-10-19 on the local branch
`theme` (unreleased): `data/themes/default.yaml`, the loader in `_settings.py`, `render_edges(theme=...)`, `tests/test_theme.py`.
**Step 2, parts a and b, implemented** (2026-10-19, local branch `theme`): the page sets state values (MapLibre `global-state`) and builds
no style expression; part c too (the arrow icon and rules and the Tunnels box lists come from the profile); and part d, the `palette`
view row: Python builds the style once more for each palette that a view names and merges the builds (`_merge_palettes`): a value that
differs becomes a choice by the state `rs_palette`, a road's baked colors get a copy per palette (`__rs_fill@mono`). The check: 24 screenshots
(open, tunnel slider, tunnel palette, Colour by, rsColor, road fill off, a view, an overlay colour; simple, full and tiled pages) are the
same as before. **The next section (palette, profile, view) is agreed** (2026-10-19, its three open points as proposed) and **implemented**,
except the `palette` row of views (it needs the page work of step 2): `data/profiles/{default,highsat}.yaml`,
`data/palettes/{amber,carto,highsat,mono}.yaml`, `render_edges(profile=..., palette=...)`. `theme=` is gone. Steps 2-4 are not
started. It comes before version 2 of [duckOSM roads in GeoLibre and RustGIS](style_export.md).

## Palette, profile and view (agreed and implemented 2026-10-19)

Step 1 put every style value in one theme file. That file mixes two kinds of value: colors, and everything else. A person
who wants other colors must not touch the widths and the zoom rules, and the reverse. So the theme splits in two:

| Part | Holds | Picked by | Switched in the page? |
|---|---|---|---|
| **Palette** | only colors | `palette="amber"` (a name) | yes: a view can name it |
| **Profile** | everything that is not a color: widths by zoom, zoom ranges, sizes, dashes, caps, spacing, the tunnel look | `profile="default"` (a name) | no: one profile per page |
| **View** | a name and the page settings that it changes ([core_model_and_views.md](core_model_and_views.md#views)) | `views={...}` | it is the switch |

A page is **one profile, one palette at the start, and its views**.

### What goes where

From the sections of step 1:

| Palette (colors) | Profile (the rest) |
|---|---|
| per class: `fill`, `casing` | per class: group, order, minzoom, `no_casing`, `single_line`, `minor`, `dash` |
| the fallback fill and casing; the palette casing | widths by zoom, zoom rate, casing ratio, links, the two-way split, metre widths; folium's `width`, `casing_width` (they leave the palettes) |
| label color and halo color; arrow color | label font, glyphs, sizes, minzooms, fraction, min_px, angle, padding; arrow icon, sizes, minzooms, `main_below`, spacing |
| bridge casing color, shadow color, deck underlay | bridge casing widths, wing scale, ramp, shadow (on, blur, offset, trim, width scale), decks (heights, ramp, flat_below) |
| tunnel colors: `toward`, `towards`, the casing `palettes`, `to`, the fill dash color | the tunnel look: `strength`, casing dash, fill dash, dash extra px, cap, folium dash, opacity scale |
| selection hover and select colors | selection opacity, folium's widths |
| data maps: no-data color, color table fallback | data maps: width, opacities |
| overlay colors; boundary color; background | overlay sizes; boundary width and dash |

The tunnel `strength` is in the profile: it decides how far a tunnel fades, which is its look, not its color
(2026-10-19: a sample that changed it changed the tunnel's style, not only its color).

### Implemented (2026-10-19)

- **highsat's widths and dashes** (no casing on minor classes, other dashes and folium widths, one more class) were in its
  palette. They are the bundled profile `highsat` now (decided 2026-10-19). `palette="highsat"` alone uses the default profile;
  `profile="highsat", palette="highsat"` gives the old highsat map exactly (checked: the same page and folium looks).
- **The proof** for the other palettes: the ten reference pages and the folium looks are the same as before the split.
- **A trap found on the way:** a test reloaded the `roadstyle.palettes` module, which left two `PALETTES` dicts in the
  process (the renderers kept the first). The test now uses the in-place rebuild that `use_settings` runs.

### Files and names

- `data/palettes/<name>.yaml`: the bundled palettes `amber` (the default), `carto`, `highsat`, `mono`. Each holds every
  color of the table above. Today only the class colors differ between them; the other colors are the same in all four.
- `data/profiles/<name>.yaml`: the bundled profile `default`, the widths and rules of today.
- Own palettes and profiles: `./palettes/<name>.yaml` and `./profiles/<name>.yaml` in the project, or
  `~/.config/roadstyle/palettes/` and `.../profiles/`. They are picked by name. Each states only what it changes and merges
  over the bundled `amber` or `default`.
- Keywords: `render_edges(palette="carto", profile="default")`, names only. `theme=` of step 1 goes (it was never released).

### Views stay as core_model_and_views.md says

That note decides: a view **sets only what it names**, the rest stays as it is, and a view is **a list of calls the page
already has**. `color` in a view is a `color_options` entry (which data decides the fill), not a palette. So:

- **`palette` is a new view row, and a cheap one.** For each palette that a view names, Python bakes one more fill and
  casing column per road, exactly as it does for each color option (`__rs_fill__1`, ...). The page switches with the code
  of `rsSetColorField`. The other palette colors (labels, arrows, bridges, tunnels, selection) are a few paint values per
  palette, which Python gives the page. The page only applies them; it computes no color.
- **`profile` is not a view row.** Widths and zoom rules are fixed in the style. A second profile in one page needs a second
  style and a swap of the whole style (`map.setStyle`), which is not a call the page has. It can be a later row, if a page
  needs it.

```python
rs.render_edges(roads, profile="default", palette="amber", views={
    "Day":     {"palette": "amber", "basemap": "positron"},
    "Night":   {"palette": "mono", "basemap": "dark_matter"},
    "Traffic": {"color": "Flow", "road_fill": True},        # as today: a color option
})
```

### Libraries (mapstyle, lanestyle)

[overlay_styles.md](overlay_styles.md) says that a library keeps its looks in its own theme and that roadstyle ships no
overlay style. With the split, a library ships a profile (its overlay styles: widths, dashes, zooms) and a palette (their
colors). An overlay style names its color by a key of the palette (`color: lane`), so that a palette switch reaches the
items too.

### Open points of this proposal

1. **Opacities** (fill, casing, label, arrow): proposal, in the palette, because an opacity is a part of how a color looks.
2. **The class `dash`** (footway dashes): proposal, in the profile, because it is a pattern, not a color.
3. **Overlay style colors by palette key** (above): proposal, yes; the libraries change with step 3.

## Problem

The look of a roadstyle map is in three places:

1. **A config file:** `data/defaults.json` holds the palettes (fill, casing, widths per class), the width model per
   zoom (`roads`), the class draw order (`z_order`), the class minzoom, and some label, arrow, bridge, tunnel and
   selection values.
2. **Python code:** `render_web.py` writes many style values as literals. An inventory (2026-10-19) found more than
   60. Examples: the link width factor `0.6`, the hover and select colors `#b388ff` / `#7c4dff`, the fallback colors
   `#888888` / `#000000`, the minor class list `_MINOR`, the arrow spacing and icon sizes, the label minzoom 14 and
   arrow minzoom 15, the label font, the bridge shadow scale `1.6` and wing scale `1.25`, the boundary look
   (`#6a0dad`, 2.5 px, `[3, 2]`).
3. **Browser JavaScript:** the page sets the look again at load (`rsSetTunnelStyle`, `_applyFill`, `_simpleColor`,
   `_simpleDash`, the first view), and it holds style values of its own: the arrow icon (SVG path, 96 x 40 px), the
   arrow rules (`_RS_ARROW`: 100 px, 150 px, zoom 17), the tunnel dash list. mapstyle's `layers.js` styles all its
   feature layers in JavaScript at load (color by kind, outlines, dashes, textures, icons, zoom ranges).

This causes three faults:

- **Lost looks.** A path that does not run the page's JavaScript loses those looks: the style export, RustGIS, any
  other app ([style_export.md](style_export.md)).
- **Values that disagree.** The same value has two definitions that differ:
  - the link width is `0.6` in the web renderer and `link_scale` 0.7 in the config;
  - the hover and select colors are `#b388ff` / `#7c4dff` on the web and `#EE00FF` / `#D000FF` in `selection`;
  - the minor classes are three different lists (`_MINOR`, `minor_no_casing`, `single_line_classes`);
  - config defaults are written again as literals (labels, arrows, overlays, bridge decks, tiles).
- **One rule in two languages.** The tunnel look is in Python (`_tun_mix`, `_tun_hex`, `_simple_color`) and again in
  JavaScript (`_tunMix`, `_tunHex`, `_simpleColor`).

## The rule

- **The style is a config file.** Every color, width, dash, opacity, zoom range, class list, font, icon and size is a
  value in the file.
- **Python reads the file and builds the MapLibre style.** Python keeps the *rules*: the casing and fill layers,
  the drawing positions, the slots for names and arrows, the bridge decks. Python holds no style value.
- **JavaScript does only interaction:** click, hover, popups, toggles, filters, the camera, arrow placement. When a
  person changes the look (a slider, the Colour by menu), JavaScript changes a *state value*. The style that Python
  made reads that value. JavaScript builds no style expression.

## The theme file

One file holds one look: a **theme**. The name is the one that mapstyle already uses for its YAML looks
([overlay_styles.md](overlay_styles.md)).

- **Format:** YAML, because a style file needs comments. JSON is also accepted (the same keys).
- **Bundled:** `src/roadstyle/data/themes/default.yaml`, the look of today's maps, value for value.
- **Pick a theme:** `render_edges(edges, theme="my.yaml")` (a path, a bundled name or a dict). A theme states only
  what it changes, and it merges over `default.yaml`, key by key, as the settings levels do now.
- **Palettes stay:** a palette is a named color set inside the theme (`palettes:`), and `palette="amber"` picks one.

### Sections

| Section | Holds | Today in |
|---|---|---|
| `palettes` | per palette and class: fill, casing, dash, opacity; widths for folium and lonboard | `defaults.json` |
| `roads` | per class: group, minzoom, draw order, minor, single line; per group: widths by zoom, zoom rate, casing ratio; links (classes, width factor); fallback fill and casing; caps and joins; the two-way split (`offset_frac`, `width_frac`, `offset_zoom`, the ramp) | `defaults.json` and `render_web.py` |
| `casing` | opacity, extra, the minor classes without casing, metre casing (`casing_m`, `casing_min_px`) | both |
| `labels` | color, halo, font, glyphs URL, size by zoom, minzoom, minor minzoom, fraction of the road width, minimum px, max angle, padding | both |
| `arrows` | color, opacity, icon (SVG path, size, pixel ratio), minzoom, minor minzoom, main classes, size by zoom, the page's placement values (main below zoom 17, 100 px, 150 px), the export's thinning (slot step per zoom) | `render_web.py` and page JS |
| `bridges` | casing color, px and m, shadow (color, blur, offset, trim, width scale, zoom ramp), wing scale, decks (base, thickness, ramp, step, opacity, width scale, flat below) | both |
| `tunnels` | palettes, palette, strength, toward colors, casing dash, fill dash, dash extra px, the slider steps | both and page JS |
| `selection` | hover and select colors and opacity (web), glow (folium) | both, with different values |
| `overlays` | default look, and named overlay styles | both |
| `boundary` | color, width, opacity, dash | `render_web.py` |
| `background` | the canvas color under a light or a dark base map | `render_web.py` |

The settings files keep what is not a look: API keys, the camera, the base map choice, tiles, `slot_m`.

### Example

```yaml
# default.yaml (part)
roads:
  fallback: {fill: "#888888", casing: "#000000"}
  links:
    classes: [motorway_link, trunk_link, primary_link, secondary_link, tertiary_link]
    width: 0.6                     # of the main class's width
  classes:
    motorway: {group: major, minzoom: 4, order: 9}
    footway:  {group: path, minzoom: 15, order: 1, minor: true, single_line: true}
labels:
  color: "#5b5b5b"
  font: [Noto Sans Regular]
  glyphs: https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf
  minzoom: 14
  minor_minzoom: 16
arrows:
  icon: {path: "M 0,2 7,2 7,0 12,2.5 7,5 7,3 0,3 z", width: 96, height: 40, pixel_ratio: 4}
  minzoom: 15
  place: {main_below: 17, min_len_px: 100, min_gap_px: 150}
selection: {hover: "#b388ff", select: "#7c4dff", opacity: 0.85}
```

## The page: state values, not style in JavaScript

- **No look change at load.** Python bakes the final paint, so the page stops calling `rsSetTunnelStyle()`,
  `_applyFill()`, `_simpleColor` and `_simpleDash` at load. Python applies the first view when it builds the page.
- **Sliders and menus set state.** MapLibre 5.24 (vendored) has the `["global-state", name]` expression and
  `map.setGlobalStateProperty`. Python writes the tunnel strength, the tunnel palette colors, the dash ratio and the
  active color option as `global-state` in the expressions. The tunnel slider then calls
  `setGlobalStateProperty("tunnel_strength", 70)`, and MapLibre draws again. `_tunMix`, `_tunHex`, `_simpleColor`,
  `_simpleDash` and `_fillExpr` go. The tunnel look is then one rule, in Python.
- **`rsColor` (colors per edge from a host page)** sets a state value that holds the groups of ids and colors, which
  a Python-made expression reads.
- **Values from the theme.** The arrow icon, the arrow placement values, the slider steps and the dash ratio list
  come from the theme (injected as JSON). The page has no style literal.
- **The export bakes the state.** For the style export, Python writes the default state values in place of
  `global-state`, because RustGIS cannot read `global-state` and other apps have no slider.

## Step 3: mapstyle and lanestyle (plan, 2026-10-19)

**Status:** plan, waiting for an OK. Its decisions are asked one by one in the conversation, not here.

### What the two libraries do today

**mapstyle** combines three choices into one roadstyle palette and one `settings=` dict (`map.mode_settings`):

| Choice | Files | Holds |
|---|---|---|
| theme | `osm_carto.yaml`, `themes/google.yaml`, `themes/grey.yaml` | road and feature colors; `grey` and `google` also a color rule: every inherited color moved by `saturation` and `lighten` |
| mode | `modes.yaml`: all, driving, walking, cycling | widths per group, the classes that stand out (`em`), `lanes` (one line or two), `fade` (the roads for cars move toward white) |
| path style | `paths.yaml`: komoot, osm, cyclosm, google | path colors (a palette part) and path widths, casing ratio, `minor_no_casing` (a profile part); the amount of `fade` |

Its page script `layers.js` styles every feature layer at load: color by `kind`, outline by `kind`, dashes, textures
(`fill-pattern` by kind, images made with PIL in `patterns.py`, darker by the factor 0.6), icons (SVG files, a symbol layer per point
layer, size by zoom, rotated by `bearing`), zoom ranges, and the colors of the roads you may not use (private, bus, pedestrian, delivery:
four colors written in the script). It also does interaction: `rsSetModes`, `rsSetAccess`, `rsSetKinds`, `rsSetInteraction`, the boxes,
and the arrow rules scaled for a tilted map (with 100 and 150 written as numbers).

**lanestyle** keeps its look in `data/lanestyle.json` (colors, widths, dashes, zooms, trims mixed). The editor (`editor.py`) writes
more of it in code: the label color, halo and sizes, roadstyle's amber palette with every fill set to the car lane color, and two
debug colors from environment variables. `arrows.py` writes the arrow color (white), `items.py` the item order.

### What roadstyle adds first (for every library)

1. **A library's folders.** `rs.add_style_dirs(path)`: a library names its folder with `profiles/` and `palettes/`, at import. The
   order: the project (`./profiles/`), the user (`~/.config/roadstyle/`), the libraries, then roadstyle's own files.
2. **A stack of names.** `profile=` and `palette=` also take a list of names, merged in order, each over the one before:
   `profile=["walking", "komoot"]`, `palette=["osm_carto", "komoot", "grey"]`. mapstyle's choices then stay files that combine at
   render time, not 4 x 4 x 3 files.
3. **Color rules in a palette:** `transform: {saturation, lighten}` moves every color that the palette inherits and does not set
   (the themes `grey` and `google`); `fade: {classes, toward, amount}` moves the colors of those classes (the roads for cars in the
   walking and cycling modes, a small palette that mapstyle adds to the stack for those modes).
4. **More overlay style fields** (the overlay styles live in a profile, their colors in a palette by key, as agreed):
   `color_by` and `outline_by` (`{property, colors: {value: color or palette key}, default}`), `pattern_by`
   (`{property, images: {value: image name}}`), `icon` (`{image, size: [[zoom, size], ...], opacity, rotate_by}`). Python makes the
   layers that `layers.js` adds now: the pattern fill layer, an icon layer per point layer, the unseen click circle under an icon.
5. **Images:** a profile names its image files (`images: {bus: icons/bus.svg}`, paths beside the profile file);
   `render_edges(images={name: path or bytes})` takes images made in code (mapstyle's textures, in the palette's colors). The page loads
   them before it shows the layers (it applies given data; it draws nothing itself).
6. **The roads you may not use:** a palette gives their colors (`roads.access: {private, bus, pedestrian, delivery}`); Python bakes
   each road's access color from its `access` column, and the fill expression takes it between rsColor and the color option, as
   `layers.js` does now. The rows in the Roads box stay mapstyle's UI, with the colors from the palette.

### mapstyle

1. **Files:** `palettes/osm_carto.yaml`, `google.yaml`, `grey.yaml` (the themes; their `transform`); `palettes/<path style>.yaml`
   (komoot, osm, cyclosm, google: the path colors) and `palettes/<path style>_fade.yaml` (the fade of the roads for cars);
   `profiles/<mode>.yaml` (all, driving, walking, cycling) and `profiles/<path style>.yaml` (the path widths); the feature layers'
   overlay styles in `profiles/features.yaml`, their colors in the palettes. `layers.yaml` (which layers, their order) stays.
2. **`mode_settings`** returns the two stacks: profile `[mode, path style, "features"]`, palette `[theme, path style]` (plus
   `<path style>_fade` in the walking and cycling modes).
3. **`layers.js`** keeps only interaction. The arrow scaling reads the profile's values from `_RS_ARROW` and scales them.
4. **The textures:** `patterns.py` stays code (it draws the shapes); the colors come from the palette, the darker factor from the profile.

### lanestyle

1. `lanestyle.json` splits into `profiles/lanestyle.yaml` (widths, dashes, gaps, zooms, trims, arrows) and
   `palettes/lanestyle.yaml` (the lane colors, the line color, the tunnel body color).
2. The editor's look becomes `profiles/lanestyle_editor.yaml` and `palettes/lanestyle_editor.yaml` (labels; the car lane fill).
3. The arrow color goes to the palette, the item order to the profile.

### The checks

As in steps 1 and 2: the pages of each library are saved before the work (mapstyle: each mode with one path style and each theme;
lanestyle: the lane page and the editor page) and compared after it, page by page and by screenshots; the tests of the three projects.

### Order

1. roadstyle: points 1 to 6 above, with tests (branch `theme`).
2. mapstyle, on a branch of its own. 3. lanestyle, on a branch of its own.

## Compatibility

- `palette=`, `settings=` and the settings levels keep working. The style keys of a settings file
  (`palettes`, `roads`, `selection`, and the look keys of `config`) are read as theme overrides, by a fixed table of
  old key to new key, for one release. A warning names the new key. Then the old keys go.
- The `style=` keyword of `render_edges` (data-driven colors) keeps its name and meaning.

## Steps

1. **The theme file and its loader.** `default.yaml` with the values of `defaults.json` and the literals of the
   inventory. The renderers read every value from it. The disagreeing values get one value each (open point 1).
   **Test:** the style dict of every page in the test suite and of Södermalm is the same before and after, except the
   values that open point 1 changes. Python holds no style literal (a test searches `render_web.py` for hex colors).
2. **The page.** No look change at load; `global-state` for the sliders and `rsColor`; theme values for the icon and
   the placement values. **Test:** the browser tests, and the tunnel slider and Colour by menu by hand.
3. **mapstyle** (its theme with `features:`, `layers.js` without styling), then **lanestyle**.
4. **Version 2 of the export** continues on top ([style_export.md](style_export.md)). The export reads the same
   theme, so the apps get the same look.

## Step 1: what was done and what is left (2026-10-19)

- **The proof.** Ten pages (Södermalm in simple and full mode, tiles, 3D with overlays and color options, four palettes, data
  colors) and the folium looks of every class were saved before the work and compared after it. The pages are the same, except
  three intended changes: the link width of folium and lonboard (0.7 to 0.6, also in the per-edge `__rs_w` / `__rs_cw` that
  `roadstyle.js` reads), folium's selection colors, and the order of the classes in the minor class list (the same seven).
- **The minor class lists stay three.** Open point 1 proposed one list with the members of `_MINOR`. The three lists have three
  jobs and different members (`no_casing`: fill only; `single_line`: a two-way pair as one line; `minor`: arrows and names later).
  One list would make service roads single lines and give living streets a casing. So they are three flags per class in
  `roads.classes`, with the members of today: the map does not change. Merging them is a decision still open.
- **YAML 1.1:** the key `on` reads as `true`. The bridge shadow switch is `bridges.shadow.show`.
- **Left in Python on purpose (rules, not looks):** geometry constants of the drawing rules: `_SEAM_M`, `_LAP_M`, `_MITRE_MAX`,
  `_ITEM_JOIN_M`, the deck half-width floor, the shadow turn limit, `_NAME_MARGIN_M`, `_ZEBRA_HALF_M`, `_ARROW_MIN_M`, the
  zebra classes, `head_m` (a parameter of the levels). `rgba(0,0,0,0)` (invisible) is not a color choice.
- **Not in this step:** the base map list in `basemaps.py` (the switcher's thumbnails and canvas colors: base map data, a file
  of its own later), the page JavaScript (step 2: the folium hover color in `interactive.py`, the arrow icon, the tunnel
  look at load), mapstyle and lanestyle (step 3).

## Open points (agreed 2026-10-19)

1. **The values that disagree.** Proposal: keep what the web map shows now: link width `0.6`, hover `#b388ff`,
   select `#7c4dff`, and one minor class list with the members of `_MINOR`. Folium and lonboard then follow the web
   values.
2. **The name of the keyword.** Proposal: `theme=`, the word mapstyle uses. `style=` is taken.
3. **The UI colors** of the controls, legend and popups (CSS in the template and in `legend.py`, `controls.py`). They
   are a look too, but not the map's. Proposal: a `ui:` section in step 2, not in step 1.
