# 3D scene (GLB tiles) on the map

Date: 2026-11-12. Status: built (Option A), with the changes in "What the build changed" below. The request comes from SimReady (`docs/7-plan/3d-map.md`, step 4, and
`build/roadstyle-gaps.md`, "No 3D scene (GLB) on the map").

## Summary

SimReady writes its roads as 3D surfaces (lanes, junctions, kerbs, markings, bridge decks, tunnel shells). It cuts them into one
GLB for each zoom-16 map tile and puts the GLBs in one PMTiles archive. roadstyle gets a layer that reads the tiles of the view
and draws their triangles in a MapLibre custom layer, as `bridgemesh.js` does for the bridge decks.

The open choice is **where the GLB reader and the map projection live**: in JavaScript or in Rust compiled to wasm. All other points
have one recommendation and are in "The same in every option".

## What the archive holds (measured on `monaco.page.pmtiles`, SimReady commit 6c350d8)

| Item | Value |
|---|---|
| Format | PMTiles v3, tile type 0, tile compression gzip, zoom 16 only, 34 tiles, 12 MB |
| A tile | one GLB, 1.3 MB gzip and 5.1 MB raw for the largest tile |
| GLB content | `POSITION` and `NORMAL` as float32 VEC3, indices as uint32. No vertex colour, no extension (no Draco, no meshopt) |
| Colour | the `baseColorFactor` of the primitive's material (the material names are lane types: `driving`, `bus`, `biking`, ...) |
| Parts | the root node has four children: `roads`, `kerbs`, `markings`, `structures`. Archive metadata `kinds` lists them |
| Primitive `extras` | `lane_id`, `lane_section_id`, `role`, `use`, `junction_id`, `stop_line_id`, `structure_id`, `island_id`, `mark`; a mesh node has `carriageway_id` |
| Frame | root `extras.simready`: `crs` (`EPSG:32632`), `origin` `[x, y, 0]`, `axes`, `vertical_datum`, `ground` (the ground id). Metadata has the same values |
| Vertex | `(east - origin.x, height, -(north - origin.y))` in metres of the project CRS; height in the datum of the ground |

The Monaco CRS is a UTM zone. SimReady's other areas use other CRS: Stockholm EPSG:3006 (transverse Mercator), Tartu EPSG:3301
(Lambert conformal conic). A map needs longitude and latitude, so **the layer must convert every vertex from the project CRS to the
map's Web Mercator**. This is the main cost, and it decides the options.

## The same in every option

These points do not depend on the option. Each has a recommendation. Say so if one is wrong.

1. **Keyword.** `scene_3d` on `render_edges`, `render_dashboard` and the other page functions. A string is the path of the
   archive: roadstyle reads the archive's header and metadata at render time (`kinds`, `crs`, `zoom`, ground id), so the switch rows
   exist at the first paint, and a ground that does not fit is an error at render time. A dict `{"tiles": path, "url": address}` sets the
   address that the page fetches (default: the file name, next to the page). The page fetches the tiles with `pmtiles.js`, which is on
   every page and un-gzips them. The archive is never put inside the page (12 MB).
2. **Same ground.** The archive's ground id and the page's `ground` id must be equal. A different id, or an archive with a ground id and a page
   with no `ground`, is an error that names both ids (the rule of `profile_on_ground` in `page_options.rs`). No other terrain
   is accepted.
3. **Height.** A vertex height is metres above the datum of the ground, drawn as `height x terrain exaggeration`, the way `bridgemesh.js`
   draws an elevation profile. The layer needs the 3D terrain on. With the terrain off it draws nothing, the switch row is
   disabled and says why. It does not draw the roads flat.
4. **Tiles in view.** The tiles that the view box touches, plus one ring (a primitive reaches a few metres into the next tile). A camera
   tilt makes a long view box, so the number of tiles has a cap (default 49); the nearest tiles to the centre win, and the row says "n of m
   tiles". The layer loads nothing below a minimum zoom (default 15). A tile that does not load is tried 3 times, then named in
   `rsScene3dProblems()` and in a toast. It is never an empty tile that looks right.
5. **Memory.** A tile becomes an indexed vertex buffer: 12 B position, 4 B normal, 4 B colour. All of Monaco is about 10 MB on the GPU.
   An LRU cache keeps parsed tiles under a byte budget (default 200 MB, `memory_budget.md`). The CPU keeps positions and indices for the pick.
6. **Switches.** One row for each `kind` in the base-map box, next to the Hillshade and 3D terrain rows, and one master row. A row only
   skips the draw of that kind (one draw range for each tile and kind): no upload. The rows are the box's own part, so they have both
   themes with no new CSS. JS: `rsScene3d(on)`, `rsScene3dKind(kind, on)`, event `rs:scene3dchange`.
   SimReady hides its flat overlays on this event.
7. **Pick.** The pick of `bridgemesh.js` (`_bmPickPoint`): a bounding sphere for each primitive, then the triangles under the pointer,
   projected with the layer's matrix. A click on the layer sends `rs:scene3dselect` with `{kind, tile, extras}`. By default a popup lists
   the extras (`scene_3d_popup=False` gives it to the page). The picked primitive is drawn again in the select colour of the palette. Where the
   layer is under the pointer, it wins over the click on a road.
8. **Colour and light.** The surface colour is the GLB material colour. The light, the ambient value and the select colour are palette
   keys (light and dark theme), not literals (`tests/test_theme.py`).
9. **Errors, not fallbacks.** A GLB with a feature that the reader does not support (Draco, sparse accessors, other component types), a CRS that the
   projection table does not have, and a primitive of a kind that is not in the metadata are each an error that names the cause.
10. **Risk to measure first: the terrain mesh can cover the road.** The map's terrain is a mesh that differs from the exact ground by
    centimetres, and by more than a metre on a steep slope (the reason for `_BM_CLEAR` in `bridgemesh.js`). A road at the ground height
    can be hidden by it. The first spike measures this on Monaco (Boulevard du Larvotto, the Parking de la Costa exit) and picks one way to fix
    it: a small lift that follows the slope, or a depth bias. The result goes into this note before the layer is final.

## Option A (recommended): JavaScript, with a small projection table

A new module `dashboard/scene3d.js`, next to `bridgemesh.js` (about 400 lines).

- **GLB reader:** about 60 lines (header, JSON chunk, BIN chunk, the accessors that the files use).
- **Projection:** the inverse of the two families that SimReady's areas use, written by hand: transverse Mercator (UTM, SWEREF99 TM) and
  Lambert conformal conic (L-EST97). The parameters are rows of a data file `data/crs.json` keyed by EPSG code. A new code in a known family is
  one row. A code that is not in the file is an error that lists the supported codes. A test compares every row with `pyproj`.
- **Where it runs:** on the main thread, one tile for each frame, so the map stays smooth. A worker is the upgrade if the measurement of the first
  spike (a 5 MB tile, about 0.4 M vertices) shows a stall.
- **For:** no new asset on the page, no new dependency, the same language as `bridgemesh.js`, small to review.
- **Against:** a family that is not in the table (a Lambert azimuthal, a local grid) needs new code. A second implementation of a projection exists next to the Rust code.

## Option B: Rust compiled to wasm (`proj4rs`), in a worker

A new crate function in `roadstyle-wasm`: it reads the GLB, converts the vertices and returns the vertex buffers. A worker runs it.

- **For:** any CRS that `proj4rs` knows; no stall on the main thread; one tested implementation in Rust (the library's direction since 2026-10-24).
- **Against:** every page that uses the layer ships a wasm file (the size is not measured; `proj4rs` is large) and the worker plumbing; a page opened from disk
  cannot start a worker or fetch the wasm; the page keeps two build steps (wasm and the assets). The layer, the pick and the switches stay in JavaScript, so
  this adds to Option A and does not replace it.

## Option C: JavaScript with a vendored `proj4js`

Like Option A, with `proj4js` (about 90 KB) in `rust/roadstyle-assets/files/vendor/` in place of the hand-written table.

- **For:** any CRS, and no projection code of our own.
- **Against:** a new dependency (it needs approval); SimReady must write the PROJ definition of the CRS into the GLB extras, because `proj4js` has no EPSG database
  (a change in SimReady's writer); the page grows by 90 KB for a feature that most pages do not use.

## Recommendation

**Option A.** It is the smallest, and the table covers Monaco, Stockholm and Tartu today. If a CRS outside the two families appears, move the projection to
Option B. The module keeps the projection behind one function (`crsToLonLat`), so the move changes nothing else.

## What the build changed

Option A was built (the pick of the roadstyle session, 2026-11-12). The spike and the build changed these points of the proposal:

1. **The lift of risk 10 is one number, 0.6 m** (`ontop.scene_3d.lift_m`, `data/basemaps.json`). Measured on SimReady's look page with the real Monaco archive (3D terrain on, the flat
   layers hidden, three views): the share of road pixels that show, against a lift of 4 m: 0.3 to 6 % with no lift, 7 to 23 % with 0.15 m, 87 to 101 % with 0.3 m, 93 to 102 % with 0.6 m.
   A lift that follows the slope (0.3 m + 2.5 m for each metre of slope, from the surface normal, the rule of `bridgemesh.js`) was tried first and made the road edges ragged. That test is void:
   the layer read the normal buffer with a wrong stride (3 bytes for a vertex, the buffer has 4), so the normals were wrong. Measured again with the stride fixed (the same page, four views, share of road
   pixels that show): 0.15 m gives 82 to 100 %, 0.3 m gives 91 to 100 %, 0.6 m gives 92 to 100 %, 1.0 m gives 93 to 100 %, with no lift 44 to 100 %. The count grows by 1 % from 0.3 m to 1 m, and the growth is
   the shift of a raised road in the pitched view, not a hidden road. The terrain mesh does not cover the road above 0.3 m on Monaco, so a lift that follows the slope has no gain to show and the lift stays one number, 0.6 m
   (twice the first value that is enough). Heights agree with the page's ground (median road height minus terrain height: 6 mm).
2. **The CRS table is read by Rust, not by the page.** `scene3d.rs` looks the archive's EPSG code up in `data/crs.json` at render time and writes the parameters into the page option;
   the page has only the formulas (transverse Mercator, Lambert conformal conic, Web Mercator). So the keyword needs the archive's path (not only an address), and the rows of the
   switches and the ground check exist before the page opens. The page keeps the ground check for `rsGround` at run time.
3. **The rows are `rsAddTopRow` rows** of the base-map box (the page part for a page's own layers), so they have both themes with no new CSS. The scene's own row is *3D scene*, one row for each part is
   *3D roads*, *3D kerbs*, ... An unavailable row shows why in its tooltip.
4. **Light:** `ambient` 0.8 (a choice of look: the slopes of a ramp show a little shade); the dark theme dims the colour (`dim`).
5. **Speed:** a tile is read and converted in 2 to 50 ms on the main thread (Monaco, 8 tiles, 270,000 vertices, 0.57 s in all), so there is no worker.
6. **Not done:** hover on the scene, a part's colour from the palette (the GLB's material colour is used), a `File` or `Blob` as the archive.

## Steps after the pick

1. Spike on the real Monaco file: GLB reader, projection, one tile drawn, the terrain-mesh measurement of risk 10. The note is updated with the result.
2. Layer: tile loading, cache, switches, JS API, keyword and Rust option, errors.
3. Pick, popup, event; both themes.
4. Tests: a browser test with a synthetic archive (two tiles: one road, one bridge deck) that checks the triangle positions against `pyproj`, one switch
   hiding one kind, and the extras of a click; a test on the real Monaco file when it exists (skipped without it); `test_dashboard_themes_browser.py`;
   a Rust test of the render-time ground check.
5. Docs: a guide page, `parameters.md`, `javascript.md`, `dashboard_module.md`, CHANGELOG, `skills/roadstyle/SKILL.md`.
6. Check on SimReady's look page (`http://localhost:8802/build/monaco/look/`), then tell the SimReady session the keyword and the JS calls.
