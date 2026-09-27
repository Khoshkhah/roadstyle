# Palettes, base maps & settings

A palette maps each OSM `highway` tag to a [`RoadStyle`](parameters.md#public-api) (fill colour,
line width, casing width, ONE casing colour, optional dash). Choose one with `palette="highsat"`,
`palette="carto"`, or `palette="mono"`. The base map under the roads is `basemap=`; every other
styling default (opacities, label colour, camera, …) is a [setting](#customising-data-files-and-overrides).

The built-in palettes are **data, not code**: they live in the bundled
`roadstyle/data/defaults.json` (section `"palettes"`) and are loaded at import, so you can retint
a class — or add a whole palette — via a [user override](#customising-data-files-and-overrides),
with no code change.

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
| footway / path | `#D98880` | — | 1.5 · dash 4,4 | — |
| pedestrian | `#DDDDDD` | — | 1.5 | — |

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
| footway / path | `#C59D9D` | — | 1.2 · dash | |

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
| cycleway | `#888888` | — | 1.2 · dash | |
| footway / path | `#ABABAB` | — | 1.2 · dash | |

## Links, tunnels, bridges & unknown tags

- **`*_link`** (e.g. `primary_link`) — same colour as the parent class, rendered ~30% narrower.
- **`tunnel`** — opacity → ~45%, line becomes dashed.
- **`bridge`** — casing forced to the deck colour (`bridge_casing_color`, black by default), +1.5 px wider; extruded 3D decks in `view_3d`.
- **Unknown tags** — fall back to `unclassified`.

## Base maps & API keys

`basemap=` picks the base map; the default is `voyager` (the `config.basemap` setting). Built in:

| key | what |
|---|---|
| `voyager` · `voyager_nolabels` · `positron` · `dark_matter` | CARTO (need a key, see below) |
| `osm` | OpenStreetMap standard tiles |
| `esri_gray` · `esri_street` · `esri_dark_gray` | Esri light grey / streets / dark grey — keyless; `esri_street` and `esri_dark_gray` stand in for `voyager` and `dark_matter` |
| `satellite` | Esri World Imagery |
| `blank` · `blank_dark` | no tiles, a plain canvas: zero network requests, so the saved map is fully offline |

`rs.BASEMAPS` holds them all. Any [xyzservices](https://xyzservices.readthedocs.io/) provider
(`pip install "roadstyle[basemaps]"`) or a tile URL template works too. Register your own — it
then works as `basemap="mytiles"` and in the switcher — with a [`Basemap`](parameters.md):

```python
rs.register_basemap(rs.Basemap("mytiles", "My tiles",
                               "https://tiles.example.com/{z}/{x}/{y}.png", "© My tiles"))
```

!!! note "CARTO watermark"
    CARTO base maps (`voyager`, `voyager_nolabels`, `positron`, `dark_matter`) come back stamped
    *"API KEY REQUIRED"* unless a free key from
    [carto.com/basemaps/apikey](https://carto.com/basemaps/apikey) is set. The tiles still load,
    so nothing fails; roadstyle warns at render time instead. Keyless alternatives: `esri_street`,
    `esri_dark_gray`, `osm`, `blank`.

A provider that needs a key (CARTO, Mapbox, Stadia, MapTiler, Thunderforest, Jawg, …) takes the
first one found, in this order:

1. the call: `rs.render_edges(edges, basemap=xyz.MapBox, api_key="pk.…")`
2. the session: `rs.set_api_key("pk.…", provider="mapbox")` (no `provider` = any provider)
3. the [settings](#customising-data-files-and-overrides), which keep keys out of your code:
   `{"config": {"api_key": "…", "api_keys": {"mapbox": "pk.…"}}}`
4. the environment: `<PROVIDER>_API_KEY` (e.g. `CARTO_API_KEY`, `MAPBOX_API_KEY`; also
   `_ACCESS_TOKEN`, `_TOKEN`, `_KEY`), then `ROADSTYLE_API_KEY` for any provider

A custom tile URL may carry an `{api_key}` or `{accessToken}` placeholder:
`basemap="https://tiles.example.com/{z}/{x}/{y}.png?api_key={api_key}"`.

## Customising data files and overrides

Every styling default ships in one bundled data file, `roadstyle/data/defaults.json`, with four
sections: `palettes`, `config` (opacities, link scale, tunnel/bridge factors, label colour,
`basemap`, camera, API keys, …), `selection` (the highlight colours) and `roads` (the `web`
renderer's width / draw-order model). Three ways to change it, lowest-effort first.

**1. Settings overrides** — a JSON file (or dict) in the same layout, restating only what
changes. Levels, later wins:

1. `~/.config/roadstyle/roadstyle.json` (or `$XDG_CONFIG_HOME/roadstyle/roadstyle.json`)
2. `./roadstyle.json` (the working directory)
3. the file named by `$ROADSTYLE_CONFIG`
4. `rs.use_settings("my.json")` (or a dict; several sources allowed) — from code, for the rest
   of the process; call it with no argument to drop it
5. `rs.render_edges(edges, settings={...})` — this one render only, restored afterwards

```jsonc
{
  "palettes": {
    "highsat": { "service": { "fill": "#E0E0E0" } },   // retint one class; rest inherited
    "mytheme": { "roads": { "motorway": { "fill": "#f00", "width": 6, "casing_width": 8 } } }
  },
  "config":    { "fill_opacity": 0.95, "labels": { "color": "#8899aa" } },
  "selection": { "core": "#FF0000" },
  "roads":     { "z_order": { "service": 5 } }
}
```

Palette overrides deep-merge **per road class** — change just `service.fill` and its
widths/casing are inherited; `roads` tables merge per entry; `config`/`selection` override
individual keys. The three files are read at **import time**, so create them (or set
`$ROADSTYLE_CONFIG`) before `import roadstyle`; `use_settings` and `settings=` work at any point.

**2. Edit the bundled `roadstyle/data/defaults.json`** to change the built-in defaults (all
palettes live under its `"palettes"` section).

**3. At runtime in Python** — `PALETTES` is a plain dict of `{name: {highway: RoadStyle}}`:

```python
from roadstyle import PALETTES, RoadStyle, register_palette, load_palette
PALETTES["highsat"]["busway"] = RoadStyle("#FF00AA", 2.0, 4.0, "#880055")   # fill, w, cw, casing
register_palette("mytheme", {...})     # a whole new palette
load_palette("my_palette.json")        # from a file written by save_palette()
```
