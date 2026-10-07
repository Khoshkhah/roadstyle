# Settings & palettes

<p class="lead">Every styling default is a setting you can override without touching code: palettes, opacities, camera, base map, API keys.</p>

## Settings levels

Each level overrides the ones above it. State only what changes; everything else keeps the
bundled default.

| level | where | scope |
|---|---|---|
| 1. bundled | `roadstyle/data/defaults.json` in the package | the defaults |
| 2. user | `$XDG_CONFIG_HOME/roadstyle/roadstyle.json` (else `~/.config/roadstyle/roadstyle.json`) | read at import |
| 3. project | `./roadstyle.json` in the working directory | read at import |
| 4. explicit file | the path in `$ROADSTYLE_CONFIG` | read at import |
| 5. code | `rs.use_settings("my.json")` or a dict (several allowed; none = drop them) | rest of the process |
| 6. one call | `rs.render_edges(edges, settings={...})` | this render only |

Files at levels 2-4 are read when `roadstyle` is imported: create them before `import roadstyle`.
A file that is not valid JSON is skipped.

## The settings file

Every level uses the same layout as `defaults.json`:

| section | holds | merges |
|---|---|---|
| `palettes` | `{palette: {class: RoadStyle fields}}`; a new name adds a palette | per road class |
| `config` | the [`StyleConfig`](parameters.md#styleconfig) fields: opacities, labels, arrows, camera, basemap, bridge decks, tiles, API keys | per key |
| `selection` | selection colours: `core`, `glow`, `glow_opacity`, `casing` | per key |
| `roads` | the web width and draw-order model: `width`, `width_zoom_rate`, `casing_ratio`, `group`, `links`, `zoom_stops`, `z_order` | per table entry |

```jsonc
{
  "palettes": {
    "highsat": { "service": { "fill": "#E0E0E0" } },            // retint one class
    "mytheme": { "motorway": { "fill": "#f00", "width": 6, "casing_width": 8 } }
  },
  "config":    { "fill_opacity": 0.95, "basemap": "positron", "api_keys": { "carto": "…" } },
  "selection": { "core": "#FF0000" },
  "roads":     { "z_order": { "service": 5 } }
}
```

A palette entry may also be wrapped as `{"roads": {...}}`, the form `save_palette` writes.

## Palettes

Pick one with `palette=`. Widths are px at city zoom; the web backend scales them with zoom. All
three palettes: `opacity` 1.0.

=== "highsat"

    Bright fills, light-grey casing on major roads, no casing on minor ones.

    | highway | fill | casing | width / casing width | dash |
    |---|---|---|---|---|
    | motorway | `#00E5FF` | `#bcbcbc` | 6.0 / 8.0 | |
    | trunk | `#FF007F` | `#bcbcbc` | 5.5 / 7.5 | |
    | primary | `#FF9100` | `#bcbcbc` | 4.5 / 6.5 | |
    | secondary | `#FFEA00` | `#bcbcbc` | 3.5 / 5.5 | |
    | tertiary | `#00E676` | `#bcbcbc` | 2.5 / 4.5 | |
    | unclassified, residential | `#FFFFFF` | `#bcbcbc` | 2.0 / 4.0 | |
    | living_street | `#DDDDDD` | none | 2.0 | |
    | pedestrian | `#DDDDDD` | none | 1.5 | |
    | service | `#F0F0F0` | none | 1.0 | |
    | track | `#9E7B54` | none | 1.5 | |
    | cycleway | `#2980B9` | none | 1.5 | 6, 4 |
    | footway, path | `#D98880` | none | 1.5 | 4, 4 |

=== "carto (default)"

    The OpenStreetMap Carto look: muted fills, a darker casing per class.

    | highway | fill | casing | width / casing width | dash |
    |---|---|---|---|---|
    | motorway | `#e892a2` | `#dc2a48` | 6.0 / 8.0 | |
    | trunk | `#f9b29c` | `#c84e2f` | 5.5 / 7.5 | |
    | primary | `#fcd6a4` | `#a06b00` | 4.5 / 6.5 | |
    | secondary | `#f7fabf` | `#707d00` | 3.5 / 5.5 | |
    | tertiary | `#ffffff` | `#bcbcbc` | 2.5 / 4.0 | |
    | unclassified, residential | `#ffffff` | `#bcbcbc` | 2.0 / 3.5 | |
    | living_street | `#ededed` | `#cccccc` | 1.8 / 3.0 | |
    | service | `#ffffff` | `#d4d4d4` | 1.2 / 2.2 | |
    | track | `#9e7b54` | same | 1.5 | 4, 4 |
    | cycleway | `#5c7cb6` | same | 1.2 | 3, 3 |
    | footway | `#C59D9D` | same | 1.2 | 4, 4 |
    | path | `#C59D9D` | same | 1.2 | 2, 5 |

=== "mono"

    Greys only: a quiet base for data colours (`palette="mono"` + `color_options`).

    | highway | fill | casing | width / casing width | dash |
    |---|---|---|---|---|
    | motorway | `#707070` | `#3c3c3c` | 6.0 / 8.0 | |
    | trunk | `#7a7a7a` | `#444444` | 5.5 / 7.5 | |
    | primary | `#8a8a8a` | `#4f4f4f` | 4.5 / 6.5 | |
    | secondary | `#9c9c9c` | `#5c5c5c` | 3.5 / 5.5 | |
    | tertiary | `#b0b0b0` | `#6e6e6e` | 2.5 / 4.0 | |
    | unclassified, residential | `#c4c4c4` | `#828282` | 2.0 / 3.5 | |
    | living_street | `#d4d4d4` | `#9a9a9a` | 1.8 / 3.0 | |
    | service | `#e4e4e4` | `#bcbcbc` | 1.2 / 2.2 | |
    | track | `#9a9a9a` | same | 1.5 | 4, 4 |
    | cycleway | `#888888` | same | 1.2 | 3, 3 |
    | footway | `#ABABAB` | same | 1.2 | 4, 4 |
    | path | `#ABABAB` | same | 1.2 | 2, 5 |

In every palette:

- `*_link` roads take the parent's colour, 0.7 × the width (`link_scale`).
- Tunnels: on the web map, v2's tunnel slider (`tunnel_strength`) moves everything on a tunnel toward slate, opaque; the casing is
  dashes, one colour or a two-colour palette (`tunnel_palette`) ([design](../design/tunnel_look.md)). Bridges get a black casing 1.5 px wider.
- An unknown class draws as `unclassified`.

## Custom palettes

| call | does |
|---|---|
| `rs.register_palette("mine", {"motorway": rs.RoadStyle("#f00", 6, 8), ...})` | add or replace a palette; then `palette="mine"` |
| `rs.PALETTES["highsat"]["busway"] = rs.RoadStyle("#FF00AA", 2.0, 4.0)` | add one class to a palette |
| `rs.save_palette("highsat", "mine.json", name="mine")` | write `{"name", "roads": {class: fields}}` to edit by hand |
| `rs.load_palette("mine.json")` | read it back and register it under its `name` (`register=False` to skip) |
| `rs.palette_to_dict(p)` / `rs.palette_from_dict(d)` | the same as plain dicts |

A `RoadStyle` needs `fill`, `width`, `casing_width`; `casing` (default `#bcbcbc`, `None` = none),
`dash` (`[on, off]` px) and `opacity` (1.0) are optional. For a non-OSM class column, register a
palette keyed by your classes and pass `highway_col=`.

## Base maps & API keys

`basemap=` picks the base map; the default is `voyager` (`config.basemap`). All built-ins are in
`rs.BASEMAPS`.

| key | tiles | key needed |
|---|---|---|
| `voyager`, `voyager_nolabels`, `positron`, `dark_matter` | CARTO | yes (see below) |
| `osm` | OpenStreetMap | no |
| `esri_gray`, `esri_street`, `esri_dark_gray` | Esri light grey / streets / dark grey | no |
| `satellite` | Esri World Imagery | no |
| `blank`, `blank_dark` | none: a plain canvas, no network requests, fully offline | no |

Other sources:

- **A tile URL**: `basemap="https://tiles.example.com/{z}/{x}/{y}.png"`. It may contain an
  `{api_key}` or `{accessToken}` placeholder.
- **xyzservices**: any provider object, e.g. `basemap=xyz.CartoDB.Positron`
  (`pip install "roadstyle[basemaps]"`).
- **Your own, by name**: register it once, then use `basemap="mytiles"` and list it in `basemaps=`.

```python
rs.register_basemap(rs.Basemap("mytiles", "My tiles",
                               "https://tiles.example.com/{z}/{x}/{y}.png", "© My tiles",
                               maxzoom=18))   # its last zoom level with tiles (default 19)
```

!!! warning "CARTO watermark"
    Without a key, CARTO tiles (`voyager`, `voyager_nolabels`, `positron`, `dark_matter`) load but
    are stamped *API KEY REQUIRED*. roadstyle warns when it renders one. Get a free key at
    [carto.com/basemaps/apikey](https://carto.com/basemaps/apikey), or use a keyless map:
    `esri_street`, `esri_dark_gray`, `osm`, `blank`.

A keyed provider (CARTO, Mapbox, Stadia, MapTiler, …) uses the first key it finds:

| order | source | example |
|---|---|---|
| 1 | the call | `rs.render_edges(edges, api_key="pk.…")` |
| 2 | the session, this provider, then any provider | `rs.set_api_key("pk.…", provider="mapbox")`, `rs.set_api_key("…")` |
| 3 | settings, this provider, then any provider | `{"config": {"api_keys": {"carto": "…"}, "api_key": "…"}}` |
| 4 | environment, this provider | `CARTO_API_KEY`, `MAPBOX_ACCESS_TOKEN` (suffixes `_API_KEY`, `_ACCESS_TOKEN`, `_TOKEN`, `_KEY`) |
| 5 | environment, any provider | `ROADSTYLE_API_KEY` |

Settings keep keys out of your code: put them in `~/.config/roadstyle/roadstyle.json`.

**See also:** [Style the roads](../guides/style.md) · [Every parameter](parameters.md) · [Command line](cli.md)
