# Base maps past their last zoom level

Status: **implemented** 2026-09-29 (unreleased). CARTO measured with a key: tiles at every zoom
to 22, but from 21 under 1 KB and nearly empty, so its cap is 20.

## Problem

Every base map goes blank when the map is zoomed past the provider's last tile level. roadstyle's
map zooms to 22, so this is easy to reach: street names appear from zoom 14 and one-way arrows on
minor streets from zoom 16, which is where people look closely. The two Esri grey maps hit it first,
at zoom 17, and the grey "Map data not yet available" squares look like roadstyle is broken.

A second fault shares the cause: switching base maps swaps only the tile URLs (`setTiles`), so the
attribution line keeps the first map's text. After switching to an Esri map it still says "© CARTO".

## Data

Measured 2026-09-29, one tile over Södermalm at each zoom (HTTP status / size / body hash):

| Base map | Real tiles up to | Past that |
|---|---|---|
| `esri_gray` (Light Gray), `esri_dark_gray` | **16** | HTTP **200**, a 2 KB placeholder image, identical at every zoom and for every Esri map |
| `esri_street`, `satellite` | 19 | the same placeholder from zoom 20 |
| `osm` | 19 | HTTP 400 from zoom 20 |
| CARTO (`voyager`, `positron`, `dark_matter`) | not measured (keyed); CARTO documents 20 | |

Esri answers with a valid image and status 200, so the browser can't tell the tile is missing:
MapLibre draws the placeholder.

MapLibre's fix for this is the raster source's `maxzoom`: past it, the source keeps drawing its last
level, scaled up (overzoom). roadstyle never sets it. A source's `maxzoom` is fixed when the source is
created, so `setTiles` can't change it on a switch.

## Approach

1. **`Basemap.maxzoom`** (new field, default 19). Set it to 16 for `esri_gray` and `esri_dark_gray`,
   and to 20 for the CARTO maps (after checking one keyed tile at 20 and 21). User-registered
   and xyzservices base maps default to 19, or take the provider's `max_zoom` when xyzservices gives one.
2. **The source gets it.** `_basemap_style` writes `"maxzoom": bm.maxzoom` into the `bm` source, and
   each switcher entry in `BASEMAPS` carries `maxzoom` and `attr`.
3. **Switching rebuilds the source.** `rsSetBasemap` removes the `basemap` layer and the `bm`
   source, adds `bm` again with the new tiles, `maxzoom` and attribution, and adds the `basemap`
   layer back at the same place in the layer order, before the layer that followed it, recorded at
   load. The ids stay `bm` and `basemap`, so the rest of the page and anyone's host code keep working.
   Tile-less entries (`blank`) keep today's behaviour: the layer is hidden.

## Rejected

- **Capping the map's own `maxZoom` at the base map's limit.** That stops people zooming into the
  roads, which is the point of the map; overzooming the base map loses nothing that matters.
- **One source and layer per base map, switched by visibility.** It works, but it changes the ids
  `bm` / `basemap`, adds a layer per switcher entry, and still needs per-source `maxzoom`, which is
  the whole fix.
- **Detecting the Esri placeholder.** It is a valid image with status 200, so the only way to detect
  it is hashing tile bodies in a custom protocol. That's far more code for the same result.

## Impact

- `basemaps.py`: the field and five values. `render_web.py`: `maxzoom` and `attr` in the source and
  in `BASEMAPS`. The template: about 15 lines in `rsSetBasemap`.
- Tests: `maxzoom` present in the style and in each `BASEMAPS` entry; a Playwright check that after
  `rsSetBasemap("esri_gray")` at zoom 18 the `bm` source reports `maxzoom` 16 and the attribution
  shows Esri.
- No API change. Maps look sharper-then-softer instead of broken past zoom 16 (grey) or 19 (others).
