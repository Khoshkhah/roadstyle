# Palettes

A palette maps each OSM `highway` tag to a [`RoadStyle`](api.md) (fill colour, line width,
casing width, casing colour for light vs dark/satellite, optional dash). Choose one with
`palette="highsat"` or `palette="carto"`.

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
| service | `#A6A6A6` | — | `#000000` | 1.0 | 2.0 |
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
| service | `#ffffff` | `#bcbcbc` | 1.2 | 2.2 |
| track | `#9e7b54` | — | 1.5 · dash 4,4 | |
| cycleway | `#5c7cb6` | — | 1.2 · dash 3,3 | |
| footway / path | `#9e5b5b` | — | 1.2 · dash | |

## Overrides

- **`*_link`** (e.g. `primary_link`) — same colour as the parent class, rendered ~30% narrower.
- **`tunnel`** — opacity → ~45%, line becomes dashed.
- **`bridge`** — casing forced to pure black, +1.5 px wider.
- **Unknown tags** — fall back to `unclassified`.

## Extending

`PALETTES` is a plain dict of `{name: {highway: RoadStyle}}`. Add or tweak entries:

```python
from roadstyle import PALETTES, RoadStyle
PALETTES["highsat"]["busway"] = RoadStyle("#FF00AA", 2.0, 4.0, "#880055", "#000000")
```
