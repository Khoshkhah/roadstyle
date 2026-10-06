# JavaScript API

<p class="lead">Every <code>window.rs*</code> function, every <code>rs:*</code> event and every registry in a saved web map.</p>

Each built-in control is a thin UI over one of these functions, so a host page can drive the map
with the controls hidden. How to use them together: [Dashboards & JavaScript](../guides/dashboards.md).

## Functions

`layer?` is optional; see [the `layer` argument](#the-layer-argument).

| function | does | fires |
|---|---|---|
| **Query and act on id sets** | | |
| `rsQuery(p => bool, layer?)` | the ids of the features whose properties match | |
| `rsGetProps(ids, layer?)` | the rows behind the ids, internal fields removed | |
| `rsFilter(ids, layer?)` | show only these features; `null` resets. On roads it combines with the class filter; on an overlay attached to edges it keeps each layer's position and order | `rs:filterchange` |
| `rsColor(ids, "#hex", layer?)` | paint the set one colour over the base colours, and draw it on top of the other roads on its level | `rs:colorchange` |
| `rsColor([[idsA, "#f80"], [idsB, "#08f"]])` | several sets at once, earlier pairs win overlaps (roads only) | `rs:colorchange` |
| `rsColor(null)` / `rsColor(null, null, layer)` | reset | `rs:colorchange` |
| `rsHighlight(ids, layer?)` | selection glow on the set; `[]` clears | `rs:highlightchange` |
| `rsFocus(ids, opt?, layer?)` | fit the camera to one id or a set; `opt` goes to MapLibre `fitBounds` (default `padding` 80, `maxZoom` 17) | |
| **Selection** | | |
| `rsSelect(id)` | select one road exactly like a click: glow, popup or panel | `rs:select` |
| `rsDeselect()` | clear the selection | `rs:deselect` |
| **Built-in controls** | | |
| `rsSetBasemap(keyOrIndex)` | switch the base map (key, label or index into `RS_BASEMAPS`) | `rs:basemapchange` |
| `rsSetClasses(list)` | show exactly these road classes | `rs:filterchange` |
| `rsSetBridges(on)` | show / hide every bridge and its 3D deck (the filter panel's *Bridges* row) | `rs:filterchange` |
| `rsSetTunnels(on)` | show / hide every tunnel, with its street names and arrows (the filter panel's *Tunnels* row) | `rs:filterchange` |
| `rsSetColorField(nameOrIndex)` | switch the active `color_options` entry | `rs:colorchange` |
| `rsSetTunnelStyle({strength, palette, ratio})` | move the tunnel look: `strength` 0-100, `palette` a name of `RS_TUNNEL_PALETTES`, `ratio` `[dash, gap]` (any may be left out) | `rs:tunnelchange` |
| `rsSetOverlay(labelOrIndex, on)` | show / hide one overlay | `rs:overlaychange` |
| `rsSetView3D(on)` | tilt to `camera.pitch_3d`, or back to flat and north-up | `rs:viewchange` |
| `rsPanelShow(on)` | panel mode only: hide / show the docked side panel | |
| **Street View** | | |
| `rsSetStreetView(on)` | open / close the Street View window (`street_view="window"` only; otherwise does nothing) | `rs:streetviewchange` |
| `rsStreetViewStep(m)` | move the Street View spot `m` metres along the edge (negative = back), stopping at its ends; returns the new URL | `rs:streetviewmove` |
| `rsSetStreetViewMarker(on)` | show / hide the map marker at the Street View spot | |
| `rsSetStreetViewMarkerAt(lng, lat, heading)` | put the marker where a panorama stands, looking `heading` degrees (for a Street View that reports its own moves). The spot is snapped onto the road as drawn, in its lane: the clicked edge while the viewer is on it, else the nearest road on screen in the direction they walked; free only with no road within 20 m. `null` goes back to the edge spot; the next selection or step clears it | |
| `rsGetStreetViewSpot()` | where the Street View spot is now: `{id, properties, m, len, lng, lat, heading, roadHeading, onRoad, source}`, or `null` before any pick. `m` is metres along the edge from its start, `len` its length, `heading` where the viewer looks, `roadHeading` the edge's direction there. `source` is `"panorama"` when a Street View that reports its moves (Linked) put it there - current - and `"map"` after a click or step: in the keyless embed (Classic) the viewer may have walked on since. Off every road (`onRoad: false`) only `lng`, `lat`, `heading` are set | `rs:streetviewspot` |

## Events

All fire on `document` as `CustomEvent`s; read the fields from `e.detail`.

| event | when | `e.detail` |
|---|---|---|
| `rs:select` | a road is clicked or `rsSelect` runs | `id`, `layer` (`null` from `rsSelect`, the MapLibre layer id from a click), `properties`, `overlays` (`[{label, fields, properties}]` of clickable overlays under the point), `streetView` (URL or `null`) |
| `rs:select` | an overlay feature is clicked | `id`, `layer` and `overlay` (both the overlay label), `fields`, `properties` |
| `rs:deselect` | a click on empty map, or `rsDeselect` | none |
| `rs:filterchange` | `rsSetClasses` | `visible`, `hidden` (class lists) |
| | `rsSetBridges` | `bridges` |
| | `rsSetTunnels` | `tunnels` |
| | `rsFilter` on roads / an overlay | `ids` / `overlay`, `ids` |
| `rs:colorchange` | `rsSetColorField` | `option` (the `RS_COLOR_OPTIONS` entry), `index` |
| | `rsColor` with one set / several | `ids`, `color` / `groups: [{ids, color}]` |
| | `rsColor` on an overlay | `overlay`, `ids`, `color` |
| `rs:highlightchange` | `rsHighlight` | `ids` (plus `overlay` on an overlay) |
| `rs:basemapchange` | `rsSetBasemap` | `basemap` (key), `index` |
| `rs:overlaychange` | `rsSetOverlay` | `overlay` (label), `visible` |
| `rs:viewchange` | `rsSetView3D` | `view3d` |
| `rs:tunnelchange` | `rsSetTunnelStyle` | `strength`, `palette`, `ratio` |
| `rs:streetviewchange` | `rsSetStreetView` | `open` |
| `rs:streetviewmove` | `rsStreetViewStep` | `id`, `streetView`, `atStart`, `atEnd` |
| `rs:streetviewspot` | a pick, a step, a walk or turn in the panorama | the `rsGetStreetViewSpot()` object (or `null`) |

```js
document.addEventListener("rs:select", e => {
  if (e.detail.overlay) return;                 // an overlay click, not a road
  console.log(e.detail.properties.name, e.detail.streetView);
});
```

## Registries

Read-only globals for building your own controls.

| global | holds |
|---|---|
| `window.map` | the MapLibre `Map` (camera: `map.easeTo({pitch, bearing})`) |
| `RS_BASEMAPS` | `[{key, label, tiles, bg}]`, the switcher's base maps |
| `RS_CLASSES` | the road classes in the filter, in order |
| `RS_CLASS_COL` | the column `RS_CLASSES` came from |
| `RS_CLASS_COLORS` | `{class: fill colour}` |
| `RS_COLOR_OPTIONS` | `[{name, prop, legend}]`, the `color_options` entries |
| `RS_TUNNEL_PALETTES` | `{name: [dash, gap] or null}`, the tunnel casing palettes (`null`: one colour) |
| `RS_OVERLAYS` | `[{label, source, layers, visible, color, popup, tooltip, under, interactive, …}]` |

## The `layer` argument

- Omitted or `null`: the roads.
- An overlay's `label` (or its index in `RS_OVERLAYS`): that overlay.
- Each layer has its own ids. Never pass ids from one layer to another.
- The one-way arrows and the street names belong to an edge (the edge under the middle of each): `rsFilter` on the roads hides them with it, and so does the class filter. The 3D decks are a
  separate source: `rsFilter` does not reach them.

## Ids past 2**53

!!! warning "Use roadstyle's ids, not your `edge_id`"
    `rsSelect`, `rsColor`, `rsFocus` and the other functions take roadstyle's **feature ids**
    (the same ids as in `rs:select`), never your `edge_id`. A 64-bit `edge_id` does not fit a
    JavaScript number, so roadstyle stores big ids as strings. Look ids up by string:

    ```js
    const ids = rsQuery(p => String(p.edge_id) === "8121729169906061189");
    rsSelect(ids[0]); rsFocus(ids);
    ```

    Or add a small integer column in Python (`pidx = 0..n-1`) and query on it. In pandas, a column
    that mixes big ints and `None` turns into float64 and rounds the ids: use `dtype="Int64"`.

**See also:** [Dashboards & JavaScript](../guides/dashboards.md) · [Every parameter](parameters.md) · [Put it on a website](../guides/website.md)
