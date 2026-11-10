# Vehicles and the follow camera

Status: plan, accepted 2026-11-09. Phase P0 (checks) is done; the results are at the end of this file. The detailed
specification of the roadstyle part is [vehicles_spec.md](vehicles_spec.md).

## Goal

Show moving vehicles from a traffic microsimulation (SUMO first) in 3D on a MapLibre map, and follow one vehicle with
a camera that keeps it in view. The same module must work on:

- a roadstyle page (roads, terrain, 3D bridge decks, base map buildings);
- an urbanstyle page at lane level (urbanstyle pages are roadstyle pages, made with `render_dashboard`);
- a SimReady model (lanes with their true shape, paths through junctions, a graded height profile for each carriageway);
- a MapLibre map that roadstyle did not make (the host route, `rsDashboard(map, {style: null})`).

The roads are not always lines on flat ground. They can be lines on terrain with 3D decks (roadstyle), polygons on levels
(urbanstyle) or lanes with a 3D shape (SimReady). The module never assumes one kind: it asks the host's road model.

## Decisions

| Date | Decision | Reason |
|---|---|---|
| 2026-11-09 | The module is in roadstyle, as new crates and one dashboard module | urbanstyle pages are roadstyle pages; a vehicle must stand on the deck that roadstyle draws, with the same Rust code (one rule); one WASM build, one set of style and test rules |
| 2026-11-09 | All logic is in Rust (WASM in the browser); JS is only the MapLibre glue | Rust is the main library; the page runs in the browser |
| 2026-11-09 | Heights come from the map, not from SUMO | the vehicle must stand on what the map draws; SUMO `z` exists only when the network has heights, and it can differ from the map |
| 2026-11-09 | The vehicles are drawn by a custom WebGL layer of our own | no new dependency; deck.gl layers do not drape on MapLibre terrain |
| 2026-11-09 | A vehicle is placed by lane, station and lateral offset when the data has them; lon/lat only when the page chooses it. The lane shapes come from the run's `net.xml`, which is made from the same model as the page (duckOSM `to_sumo`, urbanstyle, SimReady's `sumo` adapter), so they are the host's lanes; the reader measures the distance to the page's roads | the vehicle is then exactly in the lane that the map draws, on every kind of road model; the internal lanes of junctions are in `net.xml` too |
| 2026-11-09 | The 3D scene for other 3D viewers (Unity, CARLA, PTV Vissim, Aimsun, Cesium) is a glTF (GLB) export made by a SimReady adapter, next to its `opendrive` adapter; FBX and USD are conversions of that file. roadstyle does not write it | SimReady already writes the `.xodr` that these viewers read; a mesh is a computed product ("roadstyle draws, duckosm-rust computes"); the mesh and the `.xodr` then share one model and one frame. The browser module can show the same meshes for close-up views |
| 2026-11-10 | A vehicle's height comes from its road: each road has a height profile made by the rule that draws it (ground, 3D deck, tunnel), in roadstyle's Rust engine, with heights from SimReady or duckOSM when the data has them ([road_heights.md](road_heights.md)) | the ground at a lon/lat is not the road's height, and under a bridge there are two roads at one point |

## What exists (2026-11-09)

- SUMO edge id = duckOSM `edge_id`; SUMO lane id = `<edge_id>_<index from the right>` (duckOSM `to_sumo`, `gmns_sumo.py`).
  A vehicle's `lane` in SUMO output therefore joins the road table and the lanestyle lanes directly.
- urbanstyle runs `netconvert` only (through duckOSM `to_sumo`, in its own UTM zone, `netOffset` removed). It runs no
  simulation and reads no SUMO output.
- `dashboard/svspot.js` `_svAt(f, m)`: the point and the heading m metres along a road. No general lateral offset in metres.
- Terrain: the MapLibre DEM (`dashboard/elevation.js`). No code on main reads the ground height.
- 3D bridge decks: source `decks`, fill-extrusion (main). The sloped mesh with group heights is on the branch
  `claude/bridge-mesh-3d` (`bridgemesh.js`); its `_bmDeckZ` gives one mean height for each deck piece, not the height at a point.
- No animation loop, no playback control and no vehicle layer.
- SimReady (`/home/kaveh/projects/simready`): one road model for micro-simulators. `sim.lane` (lane sections, width
  profiles, predecessor and successor lanes), `sim.movement` (paths through a junction), `sim.junction` (the area),
  `sim.elevation_profile` (for each carriageway: `station_m`, `z_m`, `grade_pct`; the `graded` rows are what the lanes
  use; the datum is the source's, `EGM2008` for Copernicus and FABDEM), `sim.structure_group` (bridges). Its Rust crates
  are `roadstyle-lanes` and `simready-wasm`. It uses roadstyle as a library.
- urbanstyle keeps SUMO's paths through each junction (`urban.turn`: from and to edge and lane, the path).

## Parts

```
SUMO FCD (XML / CSV / Parquet)  ->  reader  ->  trajectory table + vehicle types
                                                       |
                                     clock (play, seek, interpolate)
                                                       |
            host adapter  ->  height model  ->  vehicle states (x, y, z, heading, size)  ->  custom layer (draw)
            host adapter  ->  obstacles     ->  camera rig  ->  map.jumpTo
```

1. **Data contract and reader** (`roadstyle-sim`).
   - The trajectory table: `t` (s), `id`, the position, `angle` (degrees, 0 = north, clockwise), `speed` (m/s), `type`, `lane`.
     The position is lon/lat (and `z` when known), or `edge` + metres along + lateral metres.
   - The vehicle types: `length`, `width`, `height`, `class`.
   - The SUMO reader moves the point from the front bumper (SUMO's `x`, `y`) to the middle of the vehicle, and joins the
     type sizes from the vType definitions. Edge and lane ids stay text (they are past 2**53).
   - Later: the same rows live, from TraCI or libsumo through a websocket.
2. **Clock** (`roadstyle-sim`). Play, pause, speed, seek. It interpolates the position and the heading between two samples.
   A big run loads in pieces of time.
3. **Road surface** (`roadstyle-camera`). The host adapter answers two questions:
   - *where*: (lane, station, lateral offset) to x, y on its own lane geometry, including SUMO's internal lanes
     (`:<junction>_<n>_<m>`, the paths through a junction);
   - *how high*: the height of the road surface there, its grade and its cross slope. The vehicle gets its pitch and roll
     from them.

   The sources differ by host: terrain + deck (`decks.rs` data) for roadstyle; level × 6 m or the `bridge.json` mesh for
   urbanstyle; the `graded` height profile for SimReady. A tunnel is under the ground.
4. **Drawing** (JS, `dashboard/vehicles.js`). A custom layer with `renderingMode: "3d"` draws one instanced shape for each
   vehicle class at x, y, z, turned to its heading. Rust gives one flat buffer for each frame. Colours come from the palettes.
5. **Obstacles** (`roadstyle-camera`). `visible(eye, target)` tests the line against terrain samples, building prisms (on the
   ground height) and deck slabs. The host adapter says which layers are obstacles; nothing is guessed.
6. **Camera rig** (`roadstyle-camera`). Modes: driver seat, chase, overview.
   - Chase: the camera stays above the vehicle's own past road. Distance and height come from the speed, measured from
     the vehicle's height. The camera stays above the terrain and never goes inside a building or a deck.
   - A blocked line: try, in this order, closer, higher, lower (to see under a bridge), to one side. The first clear
     position wins.
   - Look ahead: test the vehicle's position 0.5 to 1 s ahead.
   - Smoothing: a critically damped spring on the camera position and on the look-at point, a maximum turn rate, a fast
     damping away from a block and a slow one back, and short blocks are ignored.
   - No clear position (a tunnel): a state on the screen, never a silent fallback.

**Host adapters** (one small object for each kind of map): the ground height, the structure height, the obstacle layers.

| Host | Ground | Structure | Buildings |
|---|---|---|---|
| roadstyle | terrain DEM | decks (`decks.rs` data) | base map `vbm-building-3d` |
| urbanstyle | terrain DEM, if on | level × 6 m (`DECK_M`), the `bridge.json` mesh | its own building heights |
| SimReady | the DEM its profiles came from | `graded` height profile; structure groups | the page's building layer |
| plain MapLibre | terrain DEM, if on | none | the fill-extrusion layers that the page names |

**One ground for all.** Decided 2026-11-09 by the ground reference standard (duckOSM `docs/concepts/ground-reference.md`): an
area has one bare-earth DEM with a known vertical datum; SimReady makes the road heights and the conformed ground from it; the
map's terrain for that area is raster tiles of the conformed ground, not the AWS Terrain Tiles; every product names its ground id.
A page with no ground reference shows which ground it uses.

**JS and WASM.** One call across the boundary for each frame, with flat arrays: JS gives the time, the terrain samples
and the building features that MapLibre has; Rust gives the vehicle buffer and the camera. The Rust code is behind a Cargo
feature, so a page with no vehicles does not get bigger.

## Phases

| Phase | Work | Done when |
|---|---|---|
| P0 | Checks: custom-layer depth with fill-extrusion and terrain together; `queryTerrainElevation` units; a visibility measure; one SUMO FCD run on a duckOSM network | each check has a result in this file |
| P1 | Data contract, SUMO reader, clock, 3D boxes on flat Södermalm | a SUMO run plays on a Södermalm page |
| P2 | Height model and adapters: terrain (Monaco), decks (after `claude/bridge-mesh-3d` is merged), tunnels | the vehicles stand on hills and on decks |
| P3 | Obstacles and camera rig | the test places pass the measures below |
| P4 | urbanstyle and SimReady adapters; lane-level SUMO from start to end (SimReady's SUMO network, its lane ids) | a SUMO run plays on an urbanstyle page and on a SimReady lane page |
| P5 | UI parts (play bar, vehicle picker, camera buttons) in both themes with tests; docs; speed with 1,000 and 10,000 vehicles; live TraCI if wanted | the part rules of AGENTS.md are met |

**Test places:** a Södermalm street between buildings; Monaco (hills, tunnels, bridges); a bridge over a road; a ramp; an
urbanstyle lane page with a SUMO run.

**Measures:** the share of frames in which the followed vehicle is visible (measured by the GPU, not by our own model);
the largest turn rate of the camera; the camera is never inside terrain, a building or a deck; frames per second.

## P0 results (2026-11-09)

Checked in headless Chromium (SwiftShader, WebGL2) on a Monaco page with terrain on, MapLibre 5.24.0.

| Check | Result | What the design takes from it |
|---|---|---|
| Matrix of a custom layer | `modelViewProjectionMatrix` does not take 0–1 Mercator units (a point at the map centre projects to clip x ≈ −197,637). `defaultProjectionData.mainMatrix` does (the same point projects to 0, 0) | The vehicle layer uses `defaultProjectionData.mainMatrix` |
| Terrain heights | `queryTerrainElevation` gives metres above sea level times the exaggeration: port 0 m, palace 35.8 m, Jardin Exotique 119.4 m; with exaggeration 2, each value is exactly two times | The ground height comes from `queryTerrainElevation`; a structure height on top of it must be multiplied by the same exaggeration, or the page uses exaggeration 1 |
| Depth with terrain | A box on the ground (`alt` = ground height) is visible; boxes 30 m under the ground and at 0.3 m above sea level (44 m under the ground) are hidden | The custom layer shares the depth buffer with the terrain; `MercatorCoordinate.fromLngLat(ll, alt)` takes metres above sea level |
| Depth with buildings | A box inside a 33 m building is hidden and a box above its roof is visible, but only when the custom layer is drawn after `vbm-building-3d`. The page adds that layer after `load`, above a custom layer added at `load`, and the box then reads visible | The vehicle layer must stay above every obstacle layer, also when the page adds layers later (move it to the top on each style change) |
| A visibility measure | A WebGL2 occlusion query (`ANY_SAMPLES_PASSED_CONSERVATIVE`) around the draw of a box gives true or false one frame later, and agrees with the cases above | P3 measures "the vehicle is visible" with an occlusion query on the vehicle's own draw. It is valid only when the vehicle is drawn after the obstacles |
| SUMO run | duckOSM `to_sumo` on Monaco → `netconvert` (SUMO 1.28.0) → `randomTrips.py` (600 s) → `sumo --fcd-output fcd.parquet --fcd-output.geo true` (900 s): 400 vehicles, 87,928 rows. Parquet 3.5 MB, XML 14.0 MB | SUMO writes Parquet directly; the reader takes Parquet first |
| FCD columns (Parquet) | `timestep_time`, `vehicle_id`, `vehicle_x` (lon), `vehicle_y` (lat), `vehicle_angle`, `vehicle_type`, `vehicle_speed`, `vehicle_pos`, `vehicle_lane`, `vehicle_edge` (empty), `vehicle_slope` (0 on every row: the network has no heights) | The reader maps these names; `slope` is of no use without heights in the network |
| Ids | Every lane that is not internal (`<edge_id>_<n>`) joins `driving.edges.edge_id` (74,737 of 74,737 rows). 15 % of the rows are on internal lanes (`:<junction>_<n>_<m>`), which have no duckOSM edge | Placement by lane needs the paths through junctions (urbanstyle `urban.turn`, SimReady `sim.movement`, or the internal lane shapes of `net.xml`) |
| Position on the road | Distance from an FCD point to its edge's centre line: median 1.62 m, 90 % 1.63 m, 99 % 3.24 m, maximum 8.38 m | The points are on the lanes, beside the centre line, as expected. The front bumper to middle shift is not checked yet |

## Ideas from other tools (2026-11-09)

None of Sumonity, BME SUMO–Unity3D, CARLA + SUMO, PTV Vissim or Aimsun Next is a web tool, and none documents what its
camera does when a building is between it and the vehicle. Ideas to take:

- A simulation at a low rate (SUMO about 10 Hz) and a view at a high rate, with a smooth curve on the lane shape between
  samples (Sumonity's position ripple of 0.5 m comes from a poor join of the two rates).
- Camera presets on keys: inside, behind near, behind far, bird's eye; the normal view comes back when the vehicle leaves
  the network (Aimsun Next).
- A switch "always vertical": the vehicle stays upright on a slope, or turns with the road (Aimsun Next).
- Saved camera positions (PTV Vissim).
- A table from a SUMO vType to a 3D model (CARLA + SUMO).
