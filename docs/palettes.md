# Palettes

A palette maps each OSM `highway` tag to a [`RoadStyle`](api.md) (fill colour, line width,
casing width, casing colour for light vs dark/satellite, optional dash). Choose one with
`palette="highsat"`, `palette="carto"`, or `palette="mono"`.

The built-in palettes are **data, not code**: they live as JSON files shipped in the package
(`roadstyle/data/palettes/*.json`) and are loaded at import, so you can retint a class — or add a
whole palette — by editing a data file or dropping a [user override](#customising-data-files--overrides),
with no code change. The styling knobs (opacities, link scale, tunnel/bridge factors, selection
colours) likewise live in `roadstyle/data/style.json`.

## highsat

High-saturation, high-contrast theme. Casing swaps with the theme (a darker tone on a light
base map, **pure black** on dark/satellite). Widths are pixel widths at city zoom.

| highway | fill | light casing | dark/sat casing | width | casing |
|---|---|---|---|---|---|
| motorway | `#00E5FF` | `#007785` | `#000000` | 6.0 | 10.0 |
| trunk | `#FF007F` | `#9E004F` | `#000000` | 5.5 | 9.0 |
| primary | `#FF9100` | `#A86000` | `#000000` | 4.5 | 7.5 |
| secondary | `#FFEA00` | `#A39600` | `#000000` | 3.5 | 6.0 |
| tertiary | `#00E676` | `#007A3E` | `#000000` | 2.5 | 4.5 |
| unclassified | `#FFFFFF` | `#999999` | `#000000` | 2.0 | 4.0 |
| residential | `#FFFFFF` | `#999999` | `#000000` | 2.0 | 4.0 |
| living_street | `#EDEDED` | `#CCCCCC` | `#000000` | 2.0 | 4.0 |
| service | `#F0F0F0` | — | — | 1.0 | — (fill only) |
| track | `#9E7B54` | — | `#000000` | 1.5 | 2.5 · dash 4,4 |
| cycleway | `#2980B9` | — | `#000000` | 1.5 | 2.5 · dash 3,3 |
| footway / path | `#C0392B` | — | `#000000` | 1.5 | 2.5 · dash 1,3 |

## carto

The classic **OSM Carto** look (muted warm tones). Casing is a fixed coloured tone per class
(theme-independent).

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
Casing is theme-independent (like `carto`).

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
- **`bridge`** — casing forced to pure black, +1.5 px wider.
- **Unknown tags** — fall back to `unclassified`.

## Customising (data files + overrides)

Palettes and the style config are **data files** shipped in the package
(`roadstyle/data/palettes/*.json`, `roadstyle/data/style.json`), loaded at import. Three ways to
change them, lowest-effort first.

**1. A `roadstyle.json` override** — no code, no package edit; read at import. Sources, lowest
precedence first: `~/.config/roadstyle/roadstyle.json` → `./roadstyle.json` → `$ROADSTYLE_CONFIG`.

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

**2. Edit a bundled data file** (`roadstyle/data/palettes/highsat.json`, …) to change the built-in
defaults, or drop a new `data/palettes/<name>.json` — it's auto-discovered by its `"name"` field.

**3. At runtime in Python** — `PALETTES` is a plain dict of `{name: {highway: RoadStyle}}`:

```python
from roadstyle import PALETTES, RoadStyle, register_palette, load_palette
PALETTES["highsat"]["busway"] = RoadStyle("#FF00AA", 2.0, 4.0, "#880055", "#000000")
register_palette("mytheme", {...})     # a whole new palette
load_palette("my_palette.json")        # from a file written by save_palette()
```
