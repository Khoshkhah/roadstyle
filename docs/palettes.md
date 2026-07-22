# Palettes

A palette maps each OSM `highway` tag to a [`RoadStyle`](api.md) (fill colour, line width,
casing width, ONE casing colour, optional dash). Choose one with `palette="highsat"`,
`palette="carto"`, or `palette="mono"`.

The built-in palettes are **data, not code**: they live in the bundled
`roadstyle/data/defaults.json` (section `"palettes"`) and are loaded at import, so you can retint
a class — or add a whole palette — via a [user override](#customising-data-files-and-overrides),
with no code change. The styling knobs (opacities, link scale, tunnel/bridge factors, selection
colours) live in the same file (section `"config"` / `"selection"`).

## highsat

High-saturation, high-contrast palette; light-grey casing (`#bcbcbc`) on the major classes,
fill-only minors. Widths are pixel widths at city zoom (the web backend scales them per zoom).

| highway | fill | casing | width | casing width |
|---|---|---|---|---|
| motorway | `#00E5FF` | `#bcbcbc` | 6.0 | 8.0 |
| trunk | `#FF007F` | `#bcbcbc` | 5.5 | 7.5 |
| primary | `#FF9100` | `#bcbcbc` | 4.5 | 6.5 |
| secondary | `#FFEA00` | `#bcbcbc` | 3.5 | 5.5 |
| tertiary | `#00E676` | `#bcbcbc` | 2.5 | 4.5 |
| unclassified / residential | `#FFFFFF` | `#bcbcbc` | 2.0 | 4.0 |
| living_street | `#DDDDDD` | — | 2.0 | — (fill only) |
| service | `#F0F0F0` | — | 1.0 | — (fill only) |
| track | `#9E7B54` | — | 1.5 | — |
| cycleway | `#2980B9` | — | 1.5 · dash 6,4 | — |
| footway / path | `#C0392B` | — | 1.5 · dash 4,4 | — |

## carto

The classic **OSM Carto** look (muted warm tones), with a coloured casing tone per class.

| highway | fill | casing | width | casing |
|---|---|---|---|---|
| motorway | `#e892a2` | `#dc2a48` | 6.0 | 8.0 |
| trunk | `#f9b29c` | `#c84e2f` | 5.5 | 7.5 |
| primary | `#fcd6a4` | `#a06b00` | 4.5 | 6.5 |
| secondary | `#f7fabf` | `#707d00` | 3.5 | 5.5 |
| tertiary | `#ffffff` | `#bcbcbc` | 2.5 | 4.0 |
| unclassified / residential | `#ffffff` | `#bcbcbc` | 2.0 | 3.5 |
| living_street | `#ededed` | `#cccccc` | 1.8 | 3.0 |
| service | `#ffffff` | `#d4d4d4` | 1.2 | 2.2 |
| track | `#9e7b54` | — | 1.5 · dash 4,4 | |
| cycleway | `#5c7cb6` | — | 1.2 · dash 3,3 | |
| footway / path | `#9e5b5b` | — | 1.2 · dash | |

## mono

A neutral **grayscale** palette (no hues) — road importance reads from gray shade + width, with a
few-shades-darker casing for separation. Useful for print, or as a quiet backdrop for data overlays.

| highway | fill | casing | width | casing |
|---|---|---|---|---|
| motorway | `#707070` | `#3c3c3c` | 6.0 | 8.0 |
| trunk | `#7a7a7a` | `#444444` | 5.5 | 7.5 |
| primary | `#8a8a8a` | `#4f4f4f` | 4.5 | 6.5 |
| secondary | `#9c9c9c` | `#5c5c5c` | 3.5 | 5.5 |
| tertiary | `#b0b0b0` | `#6e6e6e` | 2.5 | 4.0 |
| unclassified / residential | `#c4c4c4` | `#828282` | 2.0 | 3.5 |
| living_street | `#d4d4d4` | `#9a9a9a` | 1.8 | 3.0 |
| service | `#e4e4e4` | `#bcbcbc` | 1.2 | 2.2 |
| track | `#9a9a9a` | — | 1.5 · dash 4,4 | |
| cycleway / footway / path | `#888888` | — | 1.2 · dash | |

## Overrides

- **`*_link`** (e.g. `primary_link`) — same colour as the parent class, rendered ~30% narrower.
- **`tunnel`** — opacity → ~45%, line becomes dashed.
- **`bridge`** — casing forced to the deck colour (`bridge_casing_color`, black by default), +1.5 px wider; extruded 3D decks in `view_3d`.
- **Unknown tags** — fall back to `unclassified`.

## Customising data files and overrides

Palettes and the style config are **data files** shipped in the package
(one bundled `roadstyle/data/defaults.json` holding palettes, config, selection and the road
width/draw-order model), loaded at import. Three ways to
change them, lowest-effort first.

**1. A `roadstyle.json` override** — no code, no package edit; read at import. Sources, lowest
precedence first: `~/.config/roadstyle/roadstyle.json` → `./roadstyle.json` → `$ROADSTYLE_CONFIG`.
From code, `rs.use_settings("my.json")` (or a dict in the same layout) applies the same kind of
override at runtime — highest precedence of all; call it again (no argument) to drop it. For a
single map, skip the state entirely: `render_edges(edges, settings={...})` applies the override
for that one render and restores everything after.

```jsonc
{
  "palettes": {
    "highsat": { "service": { "fill": "#E0E0E0" } },   // retint one class; rest inherited
    "mytheme": { "roads": { "motorway": { "fill": "#f00", "width": 6, "casing_width": 8 } } }
  },
  "config":    { "fill_opacity": 0.95 },
  "selection": { "core": "#FF0000" }
}
```

Palette overrides deep-merge **per road class** — change just `service.fill` and its widths/casing
are inherited; `config`/`selection` override individual keys. Overrides are read at **import time**,
so set the file (or `$ROADSTYLE_CONFIG`) before `import roadstyle`.

**2. Edit the bundled `roadstyle/data/defaults.json`** to change the built-in defaults (all
palettes live under its `"palettes"` section).

**3. At runtime in Python** — `PALETTES` is a plain dict of `{name: {highway: RoadStyle}}`:

```python
from roadstyle import PALETTES, RoadStyle, register_palette, load_palette
PALETTES["highsat"]["busway"] = RoadStyle("#FF00AA", 2.0, 4.0, "#880055")   # fill, w, cw, casing
register_palette("mytheme", {...})     # a whole new palette
load_palette("my_palette.json")        # from a file written by save_palette()
```
