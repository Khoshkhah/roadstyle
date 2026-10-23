# How a map is drawn

<p class="lead">About what roadstyle makes, what MapLibre draws, the two forms of road data, and why the page uses one tile zoom.
This page is the same for the Python engine and the Rust engine.</p>

## roadstyle makes the map, MapLibre draws it

roadstyle does not draw pixels. It turns the road edges into a map **for one drawing library**, and that library draws. You
select the library with the keyword `backend` of `render_edges`:

| `backend` | The library that draws | What `render_edges` gives |
|---|---|---|
| `"web"` (the default) | MapLibre GL JS, in the browser | one HTML file |
| `"folium"` | Leaflet, in a notebook | a `folium.Map` |
| `"lonboard"` | deck.gl, in a notebook | a `lonboard.Map` |

The rest of this page is about `"web"`, the backend of almost all maps. The Rust engine makes only this backend.

```mermaid
flowchart TB
    roads["Road edges + look"]
    rsty["roadstyle<br/>makes the style<br/>and the road data"]
    ml["MapLibre GL JS<br/>draws the pixels"]
    roads --> rsty
    rsty -->|"style + GeoJSON<br/>or vector tiles"| ml
```

The `"web"` backend makes:

1. **A MapLibre style:** the layers and their paint expressions (the widths for each zoom, the colors, the casing under the fill,
   the drawing order of bridges and tunnels), and the `roadstyle:*` metadata for the dashboard.
2. **The road data**, as GeoJSON or as vector tiles (the next section).
3. With `render_edges`: **one HTML page** that holds 1 and 2, MapLibre and the dashboard.

MapLibre reads the style and the data and draws them with WebGL. It draws a new frame each time that the view or a filter
changes.

## GeoJSON or vector tiles

MapLibre draws only from tiles: small squares of the map, one grid for each zoom. The two forms of road data differ in **who
cuts the roads into tiles**:

| Step | GeoJSON (the default) | Vector tiles (`tiles=True`, `export_style`, `Tiler`) |
|---|---|---|
| 1. Cut the roads into tiles, and simplify them for each zoom | MapLibre, in the browser, for all roads when the page opens | roadstyle, before: in Python or with the Rust `Tiler` |
| 2. Turn each tile into shapes for the GPU | MapLibre | MapLibre |
| 3. Draw | MapLibre | MapLibre |

- **GeoJSON** is one step before the tiles. It is the simplest form: the page opens from disk and needs no server. Use it up to
  about 10⁴ edges. `data_maxzoom` and `data_tolerance` control how MapLibre cuts it.
- **Vector tiles** (MVT) are cut in advance, so the page reads only the tiles in view. Use them for about 10⁵ edges. They can be
  inside the page (`tiles=True`), in a folder of tile files, in one PMTiles file, or made on request in the browser.

The map looks the same with both forms, and the dashboard works on both.

## One tile zoom or several

When the map is flat, all tiles on the screen have the same zoom. When the map is tilted, MapLibre loads the near tiles at a
higher zoom than the far tiles, because the near part of the view is larger on the screen.

<div style="max-width:640px;margin:1em auto">
<svg viewBox="0 0 640 220" width="100%" role="img" aria-label="Left: a tilted view with zoom 15 tiles near and zoom 14 tiles far; the road changes width where they meet. Right: one tile zoom; the road has one width." style="display:block;font:13px sans-serif">
  <g fill="none" stroke="currentColor" stroke-opacity=".45">
    <path d="M70 30 H250 L300 190 H20 Z"/><path d="M45 110 H275"/>
    <path d="M160 30 V110"/><path d="M103 110 L90 190 M160 110 V190 M217 110 L230 190"/>
    <path d="M390 30 H570 L620 190 H340 Z"/><path d="M365 110 H595"/>
    <path d="M435 30 L425 110 M480 30 V110 M525 30 L535 110"/>
    <path d="M423 110 L410 190 M480 110 V190 M537 110 L550 190"/>
  </g>
  <path d="M160 30 V110" stroke="#ff6b35" stroke-width="6"/><path d="M160 110 V190" stroke="#ff6b35" stroke-width="14"/>
  <path d="M480 30 V190" stroke="#ff6b35" stroke-width="10"/>
  <g fill="currentColor">
    <text x="88" y="75">zoom 14</text><text x="180" y="75">zoom 14</text>
    <text x="40" y="160">15</text><text x="120" y="160">15</text><text x="180" y="160">15</text><text x="250" y="160">15</text>
    <text x="163" y="106" fill="#d9480f">a step</text>
    <text x="400" y="75">15</text><text x="450" y="75">15</text><text x="500" y="75">15</text><text x="550" y="75">15</text>
    <text x="370" y="160">15</text><text x="440" y="160">15</text><text x="500" y="160">15</text><text x="570" y="160">15</text>
    <text x="30" y="212">Several tile zooms: the road changes width</text>
    <text x="365" y="212">One tile zoom: the road has one width</text>
  </g>
</svg>
</div>

roadstyle bakes a road's width into each tile for the zoom of that tile. Where a near tile (zoom 15) meets a far tile (zoom 14),
the same road gets two widths, and the map shows a line across all roads at that place.

To stop this, the page makes MapLibre use **one tile zoom on the whole screen**. The page template sets it for each source that
is not a base map:

```js
source.calculateTileZoom = (z) => z;      // web_template.html, _flatTiles
```

The cost:

- Up to 60° of tilt, MapLibre already uses one tile zoom, so the rule changes nothing.
- Above 60°, the page loads 2 to 3.6 times as many tiles (66° to 70°).
- `max_pitch=60` keeps every view in the range where the rule costs nothing. The default is 70.

A page of your own that adds roadstyle's style to its own MapLibre map does not have this rule. Add the same line for each
roads source, as the tile example of [Use roadstyle in the browser](browser.md#add-roads-that-come-later-as-vector-tiles) does.

**See also:** [Big networks](../guides/big-networks.md) · [Make tiles and PMTiles](tiles.md) ·
[Architecture of the Rust version](architecture.md)
