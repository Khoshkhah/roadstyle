# 3D road tiles (GLB)

A page can draw 3D road surfaces from an archive of GLB tiles. SimReady writes such an archive for an area: the lanes, the junction areas,
the kerbs, the markings, the bridge decks and the tunnel shells, each at its own height. roadstyle reads the tiles of the view and draws
their triangles in the map. The map's base map, terrain, clicks and Street View stay.

```python
import roadstyle as rs

rs.render_dashboard(
    edges,
    ground=ground,                                    # the area's ground: the 3D roads lie on it
    terrain=True,                                     # the layer draws only with the 3D terrain on
    scene_3d="out/monaco-rust/gltf/monaco.page.pmtiles",
).save("look.html")                                   # put monaco.page.pmtiles next to the page
```

## What the archive must be

- A PMTiles v3 archive of GLB tiles at one zoom (SimReady: 16). Tile type 0, tile compression gzip.
- The root node of each GLB has one child for each part (`roads`, `kerbs`, `markings`, `structures`). The archive's metadata lists them in `kinds`.
- The root `extras.simready` of each GLB has `crs` (an EPSG code), `origin` `[x, y, 0]` and `ground` (the ground id). A vertex is
  `(east - origin.x, height, -(north - origin.y))` in metres of that CRS. The height is metres above the datum of the ground.
- The CRS is a row of `data/crs.json`: a UTM zone (EPSG 32601 to 32660, 32701 to 32760, 25828 to 25838), SWEREF99 TM (3006), L-EST97 (3301) or
  Web Mercator (3857). Another code is an error that lists the codes. A code of a known family is one more row.
- Each primitive has a material colour (`baseColorFactor`) and `extras`. The layer draws opaque triangles. A GLB with a feature that the layer
  does not read (a Draco or meshopt buffer, sparse accessors, an alpha material) is an error that names it.

## The ground

The heights are above the datum of the ground, so the layer draws on the page's own `ground`. The archive names its ground id in its
metadata. A page with another ground, or with no `ground`, is an error when roadstyle renders it, and the message names both ids. In an
open page, `rsGround(other)` makes the layer say so (`rsScene3dProblems()`) and draw nothing.

With the 3D terrain off the layer draws nothing: the rows are grey and say why. It never draws the roads flat. The layer lifts the whole
scene by `ontop.scene_3d.lift_m` (0.6 m): the terrain that the map draws is a mesh that is lower than the exact ground in places, and a road at its exact height is
covered by it. Measured on Monaco (3D terrain on): with no lift 0.3 to 6 % of the road pixels show, with 0.3 m 87 to 100 %, with 0.6 m 93 to 100 %. The surface normals of a GLB are noisy, so the lift does not follow the slope: it is one number.

## The switches

The base-map box has the row *3D scene* for the whole scene and one row for each part (*3D kerbs*, *3D markings*, ...). A part that is off
is not drawn and not picked. From JavaScript: `rsScene3d(on)`, `rsScene3dKind(kind, on)`.

A page that has its own flat road layers (SimReady's look page) hides them while the scene is drawn. It listens to `rs:scene3dchange` and
`rs:scene3dstatus` and reads `rsScene3dStatus().drawn`.

## A click

A click on a triangle of the scene is the event `rs:scene3dselect` (`kind`, `node`, `tile`, `extras`). With `popup` (the default) a popup lists the
`extras` (`lane_id`, `junction_id`, `structure_id`, ...). The picked primitive is drawn again in the select colour. A click on the
scene does not send `rs:select`. `rsScene3dPick({x, y})` asks the same without a click.

## Tiles and memory

The layer reads the tiles that the view touches and one ring around them (a primitive is in the tile of the centre of its box, so it can
reach a few metres into the next tile). A tilted view reaches far: the layer reads the nearest `max_tiles` (49) tiles, and
`rsScene3dStatus().tiles.capped` says when the view needs more. It reads nothing below `min_zoom` (15). A tile that does not load is tried 3 times and
then named in `rsScene3dProblems()` and in a toast. The tiles in memory stay under `cache_mb` (200 MB, `docs/design/memory_budget.md`); the least recently used tile that is not in view goes first.
All of Monaco (34 tiles, 0.7 M triangles) is about 10 MB on the graphics card.

## Look

The surface colour is the GLB's material colour. The light, the ambient value, the dark theme's dimming and the lift are `ontop.scene_3d` in
`data/basemaps.json`. The picked primitive takes the select colour of the palette. The design: [3D road tiles](../design/scene_3d_tiles.md).
