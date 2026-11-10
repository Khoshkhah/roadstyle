# Vehicles and the follow camera: specification

Status: draft for review, 2026-11-09. The plan, the decisions and the P0 results are in [vehicles.md](vehicles.md).
This file says what roadstyle builds and how. It does not cover the SimReady glTF adapter (a SimReady document).

## 1. Scope

**In scope (roadstyle):**

- Read the output of a traffic microsimulation (SUMO first) in Python and in the browser.
- Play it back on a MapLibre map: a clock, interpolation, vehicles in 3D on the road surface (terrain, bridge decks, levels).
- Follow one vehicle with a camera that keeps it in view (driver seat, chase, overview).
- The parts of the page: play bar, vehicle picker, camera buttons, status line.
- The host adapters for roadstyle, urbanstyle, SimReady and plain MapLibre pages.

**Not in scope:**

- Running a simulation. roadstyle reads its output only.
- The 3D scene export for other viewers (glTF, FBX, USD). SimReady makes it.
- Live data from TraCI or libsumo. The data contract allows it (section 4.5); the work is a later phase.
- Pedestrians and bicycles as people (SUMO persons). Bicycles as vehicles are in scope.

## 2. Words

| Word | Meaning |
|---|---|
| run | one simulation output: the trajectory table, the vehicle types and the network it used |
| sample | one row of the trajectory table: one vehicle at one time |
| station | metres along a lane from its start |
| lateral offset | metres to the right of the lane's centre line, in the travel direction |
| internal lane | a SUMO lane inside a junction, id `:<junction>_<n>_<m>` |
| host | the page that shows the map: a roadstyle, urbanstyle or SimReady page, or a plain MapLibre page |
| host adapter | the small object that tells the module the host's ground, structures and obstacles |
| obstacle | a thing that can hide the followed vehicle: terrain, a building, a bridge deck |
| scene origin | one lon/lat point near the middle of the run; vehicle positions on the GPU are metres from it |

## 3. Architecture

```
                      Python                                   Browser
  ┌──────────────────────────────────────┐   ┌───────────────────────────────────────────────────────────┐
  │ roadstyle.sim.read_run()             │   │ dashboard/vehicles.js (JS: MapLibre glue, parts, events)  │
  │   └─ roadstyle-py ─┐                 │   │   │  one call per frame, flat arrays                      │
  │                    ▼                 │   │   ▼                                                       │
  │ render(..., vehicles=...)  ──page──► │──►│ roadstyle-wasm, feature "vehicles"                        │
  └──────────────────────────────────────┘   │   ├─ roadstyle-sim:    run, readers, clock, interpolation  │
                                              │   └─ roadstyle-camera: surface, obstacles, camera rig     │
                                              └───────────────────────────────────────────────────────────┘
```

| Unit | Kind | Holds |
|---|---|---|
| `rust/roadstyle-sim` | new crate | the data contract (`Run`, `Sample`, `VehicleType`, `LaneShape`), the SUMO readers (FCD Parquet, CSV, XML; vType; `net.xml` location and lane shapes), the clock, the interpolation, the placement on lanes |
| `rust/roadstyle-camera` | new crate | the road surface (ground + structure height, grade, cross slope), the obstacles and the visibility test, the camera rig |
| `rust/roadstyle-wasm` | existing crate, new Cargo feature `vehicles` | the class `VehicleScene` (section 7) |
| `rust/roadstyle-py` | existing crate | `read_run` and the bytes for the page (section 6) |
| `dashboard/vehicles.js` | new module (a line in `files.txt`) | the custom layer, the per-frame call, the host adapters' JS side, the `rs.vehicles` API, the events |
| `dashboard/vehiclebar.js` | new module | the parts: play bar, vehicle picker, camera buttons, status line |

Rules:

- The two crates do not depend on the page code (`roadstyle-engine`, `roadstyle-tiles`). `roadstyle-sim` depends on `roadstyle-io` for the reprojection only (`Crs::Proj`: the UTM lanes of `net.xml` to lon/lat), and on the workspace's `parquet` and `arrow` crates.
- `net.xml` and the `<vType>` elements are read with a small tag scanner (SUMO's XML is plain elements with attributes), as SimReady's `netconvert.rs` does: no XML library.
- A page without vehicles does not load the feature's code: the Rust page writer and `render_web.py` add `vehicles.js`, `vehiclebar.js` and the WASM with the feature only when the page has vehicles.
- No new JS dependency. No new Rust dependency for Parquet (`roadstyle-io` already has `parquet` and `arrow`, also in WASM).

## 4. The data contract

### 4.1 The run

A run has three tables and one header.

**Header** (`RunHeader`):

| Field | Type | Meaning |
|---|---|---|
| `source` | text | `sumo` for now |
| `crs` | text | the CRS of `x`, `y` in the samples: `EPSG:4326` (lon/lat) |
| `t0`, `t1` | f64, s | the first and the last sample time |
| `step` | f64, s | the most common time step between two samples of one vehicle |
| `origin` | [f64; 2] | the scene origin (lon, lat): the middle of the samples' bounding box |
| `net_offset`, `proj` | from `net.xml` `<location>` | kept for lane shapes in network coordinates |

**Samples** (one row per vehicle per time; sorted by `t`, then by `id`):

| Column | Type | Unit | Required | SUMO FCD source |
|---|---|---|---|---|
| `t` | f64 | s | yes | `timestep_time` (Parquet), `<timestep time>` (XML) |
| `id` | u32 | — | yes | index into the vehicle id list (`vehicle_id` as text in the list) |
| `x`, `y` | f64 | degrees | yes | `vehicle_x`, `vehicle_y` with `--fcd-output.geo true`; else network metres converted with `<location>` |
| `z` | f32 | m | no | `vehicle_z`, only when the network has heights. Not used for placement (decision 2026-11-09: heights come from the map) |
| `angle` | f32 | degrees, 0 = north, clockwise | yes | `vehicle_angle` |
| `speed` | f32 | m/s | yes | `vehicle_speed` |
| `lane` | u32 | — | no | index into the lane id list (`vehicle_lane`) |
| `pos` | f32 | m | with `lane` | `vehicle_pos`: the station of the **front bumper** on the lane |
| `pos_lat` | f32 | m | no | `vehicle_posLat` (sublane model): the lateral offset |
| `type` | u16 | — | yes | index into the vehicle types (`vehicle_type`) |
| `signals` | u16 | bit set | no | `vehicle_signals` (brake light, indicators) |

**Vehicle types** (`VehicleType`), from the `<vType>` elements of the route and additional files:

| Field | Type | Unit | Default when not in the file |
|---|---|---|---|
| `name` | text | — | — |
| `class` | enum | — | `passenger` (SUMO `vClass`) |
| `length`, `width`, `height` | f32 | m | the SUMO default of the class (profile key `vehicles.sizes.<class>`) |
| `colour` | rgba or null | — | null: the palette colour of the class |
| `shape` | enum | — | from `guiShape`, else from `class` |

**Lane shapes** (`LaneShape`), from `net.xml`, also the internal lanes:

| Field | Type | Meaning |
|---|---|---|
| `lane` | u32 | index into the lane id list |
| `edge_id` | text | the edge part of the lane id (`<edge_id>_<n>`); empty for an internal lane |
| `points` | [[f64; 2]] | the lane's centre line, lon/lat, in the travel direction |
| `length` | f32, m | the lane's length |
| `width` | f32, m | the lane's width |

Rules:

- Ids stay text in the lists; the tables hold indices. A SUMO edge id is a duckOSM `edge_id` (past 2**53), so a JS number must never hold it.
- A sample with a `lane` that is not in the lane shapes is placed by its lon/lat (`x`, `y`), counted (`lanes_unknown`) and shown in the status line (section 10.4). It is not dropped silently. A pair of samples with no chain of lanes between them is placed the same way and counted (`path_gaps`).

### 4.2 Where the lane shapes come from

The lane shapes come from the `net.xml` of the run. The network of a run is made from the same model as the page:
duckOSM `to_sumo` for a roadstyle page, urbanstyle's `netconvert` step, SimReady's `sumo` adapter. So these lanes are
the host's lanes. The reader checks this: for each edge, it measures the distance from the lane shapes to the page's road
of the same `edge_id`, and puts the 99th percentile in the run's report. P0 measured 1.6 m (median) and 3.2 m (99 %) on Monaco.

### 4.3 Placement

A vehicle is placed in one of two ways. The page chooses with the option `vehicle_placement`.

- **`"lane"`** (default when the samples have `lane` and `pos`): the middle of the vehicle is at station
  `pos - length / 2` on the lane, at `pos_lat` (else 0) to the right. A station before the lane's start continues
  backward on the vehicle's previous lanes (the run keeps up to 8 lanes behind each pair). This is correct on curves,
  where a shift along the heading is not.
  - **Two kinds of distance.** A station (SUMO's `pos`) is measured on SUMO's lane length, and each lane maps it onto
    its drawn line, as SUMO does. Some lanes have a drawn line much shorter than their SUMO length (on Monaco, a lane with
    `length="3.99"` and a line of 0.2 m). So the front of the vehicle follows the stations, and the half length back (and
    the look ahead of the heading) is in drawn metres: the vehicle keeps its size.
- **`"lonlat"`**: the middle of the vehicle is `length / 2` behind (`x`, `y`) along `angle`.

### 4.4 Interpolation

The clock time `t` is between two samples `a` and `b` of one vehicle (`a.t <= t < b.t`).

1. **Distance along the path.** For lane placement, the path is the chain of lanes from `a.lane` to `b.lane` through
   the connections of `net.xml` (also the internal lanes), at most 16 lanes (a cluster of short edges has many: on Monaco, chains of 7
   lanes span 3 to 8 m). The search takes `b.lane` itself when a
   connection reaches it; else the first lane of `b.lane`'s edge, and then a lane change at `b`.
   The distance `s(t)` along that chain is a cubic Hermite curve with the end values `s(a) = 0`, `s(b) = L` and the end
   slopes `a.speed`, `b.speed`. So the vehicle moves at the simulated speed with no jump at a sample.
2. **Lane change.** The place is a blend of the place on the old lane and the place on the new lane (the same distance
   before or after `b`), with a smoothstep weight over `vehicles.lane_change_s` (profile, default 2 s), centred on `b.t`.
   A blend of real places, not a sideways shift by the lane width: the lanes of a junction's internal edge are not
   parallel.
3. **Heading.** The tangent of the path at `s(t) + vehicles.heading_lookahead_m` (default 2 m), not at `s(t)`: the
   vehicle turns into a curve a little before it, as a driver does.
4. **Height, pitch, roll.** From the road surface (section 8) at the vehicle's middle, front and back and both sides.
   With `vehicle_always_vertical: true`, pitch and roll are 0.
5. **Start and end.** A vehicle shows from its first sample to its last. A jump of more than
   `vehicles.teleport_m` (default 50 m) between two samples (a SUMO teleport) is not interpolated: the vehicle disappears at
   `a` and appears at `b`, and the jump is counted in the status line.

For `lonlat` placement, steps 1 and 3 use the straight line from `a` to `b`, with `angle` interpolated on the shortest turn.

### 4.5 Live data (later phase)

A live source sends the same samples, one time step per message, as the bytes of one Parquet row group or as a small
binary block with the same columns. The clock then plays at `t_live - vehicles.live_delay_s` (default 2 s), so that two
samples always exist around the clock time.

## 5. Formats and sizes

| Input | Read by | Notes |
|---|---|---|
| FCD Parquet (`--fcd-output fcd.parquet`, SUMO 1.24 and later) | Rust, in Python and in WASM | the first choice. 400 vehicles × 900 s = 3.5 MB on Monaco |
| FCD CSV (`.csv`) | Rust | the same column names |
| FCD XML (`.xml`, `.xml.gz`) | Rust, in Python only | streamed; converted to Parquet for the page |
| `<vType>` | Rust | from the route file and the additional files of the run |
| `net.xml` | Rust | `<location>`, `<lane id shape length width>`, also internal lanes |

Big runs: the Parquet file is read one row group at a time. The browser keeps the samples from
`t - vehicles.window_back_s` to `t + vehicles.window_ahead_s` (defaults 30 s and 120 s) and reads the next row groups
in a worker before the clock needs them. The reader requires the rows sorted by time (SUMO writes them so).

## 6. Python API

```python
import roadstyle as rs

run = rs.sim.read_run("fcd.parquet", net="monaco.net.xml", routes="routes.rou.xml")   # a Run (Rust object)
run.report()              # samples, vehicles, time span, lanes not found, teleports, lane-to-road distance (p50, p99)

m = rs.render_edges(edges, vehicles=run, terrain=True)        # or vehicles="fcd.parquet" with vehicle_net=..., vehicle_routes=...
m.save("page.html")
```

| Keyword | Default | Meaning |
|---|---|---|
| `vehicles` | `None` | a `Run`, or the path of an FCD file (then `vehicle_net` is required for lane placement) |
| `vehicle_net`, `vehicle_routes` | `None` | the `net.xml` and the route or additional files with the `<vType>` elements |
| `vehicle_placement` | `"lane"` when possible | `"lane"` or `"lonlat"` (section 4.3) |
| `vehicle_data` | `"inline"` up to `vehicles.inline_max_mb` (profile, 20 MB), else an error that says to use `"file"` | `"inline"`: the run is in the page; `"file"`: written next to the page as `<page>.run.parquet` and `<page>.lanes.bin`, read by URL |
| `vehicle_colour_by` | `"class"` | `"class"`, `"type"`, `"speed"` |
| `vehicle_follow` | `None` | a vehicle id: the page opens following it |
| `vehicle_camera` | `"chase"` | the start mode: `"seat"`, `"chase"`, `"overview"` |
| `vehicle_speed` | `1.0` | the clock speed (× real time) |
| `vehicle_always_vertical` | `False` | section 4.4 step 4 |
| `vehicle_obstacles` | the host adapter's list | the MapLibre layer ids that count as obstacles (section 9) |

Each keyword follows the rule of AGENTS.md for a new web option: a key in `render`'s `page` dict and in `PageOptions`,
its default in `dashboard/index.js` (`RS_DEFAULTS`), a test in `tests/test_render_web.py`, rows in
`docs/reference/parameters.md`, `docs/reference/javascript.md` and `docs/design/dashboard_module.md`, CHANGELOG, and
`skills/roadstyle/SKILL.md`.

## 7. The WASM boundary

One class, `VehicleScene`, built with the feature `vehicles`.

| Method | When | Does |
|---|---|---|
| `new(options_json)` | once | the options and the profile values |
| `load_run(bytes, kind)` / `load_row_group(bytes)` | at load, then while it plays | the Parquet (or CSV) bytes of the run; `kind` names the format |
| `load_lanes(bytes)` / `load_types(json)` | at load | the lane shapes (a compact binary made by the Python side) and the vehicle types |
| `set_surface(kind, arrays...)` | when the host's structures change | deck pieces, level heights or graded profiles (section 8) |
| `set_obstacles(kind, coords, ring_starts, heights, bases)` | when the map's obstacle features change | buildings and other prisms (section 9) |
| `set_ground(points, heights)` | each frame | the answers to the last frame's ground requests (NaN = not known yet) |
| `frame(t, dt, view)` | each frame | moves the clock, places the vehicles, moves the camera |
| `instances()`, `camera()`, `ground_requests()`, `status()` | after `frame` | views into WASM memory (no copy) |

**Instances** (`Float32Array`, 16 numbers for each visible vehicle): `x_m, y_m, z_m` (metres east, north and up from the
scene origin; `z` above sea level), `heading, pitch, roll` (radians), `length, width, height` (m), `shape`,
`r, g, b, a`, `flags` (followed, selected, brake, left, right), `vehicle` (index). Metres from an origin keep float32
exact to about 1 mm across 10 km; 0–1 Mercator in float32 would be exact to about 2 m only.

**Camera** (`Float64Array`): eye `lon, lat, alt`, target `lon, lat, alt`, `fov`, `mode`, `state` (section 10.4). JS turns it into a
`jumpTo` with `map.calculateCameraOptionsFromTo`.

**Ground requests** (`Float64Array`, lon/lat pairs): the points whose ground height Rust needs next frame. JS answers
with `map.queryTerrainElevation` (P0: metres above sea level times the exaggeration). Rust keeps the answers in a grid
of `vehicles.ground_cell_m` (default 5 m) cells and clears it on `rs:terrainchange`.

Budget for one `frame` call with 1,000 vehicles: 2 ms on a desktop.

## 8. The road surface

**Decided on 2026-11-10: [road_heights.md](road_heights.md).** A vehicle's height comes from its road's height profile (made by the
rule that draws the road: ground, 3D deck, tunnel), never from the ground at its lon/lat. That document replaces the ground sampling below
for lane placement.

`surface(p)` gives, at a point on a lane: the height (m above sea level), the grade and the cross slope.

```
height = ground(p) + structure(p)        (structure = 0 off a structure; negative in a tunnel)
```

| Host | `ground` | `structure` | Source on the page |
|---|---|---|---|
| roadstyle | the conformed ground of the area's ground reference (its terrain tiles), through ground requests; else the page's terrain with "ground: AWS Terrain Tiles" shown; else 0 | the deck height at `p`, by the rule of the bridge mesh: the deck is level between the ground at the two ends of its chain, the ramps rise from the ground at each free end, the group height wins over the look's `full` height | the features of the source `decks` and their marks (`__rs_lift0`, `__rs_lift1`, `__rs_full`, `__rs_group`, `__rs_s0`, `__rs_s1`, thickness), and `rsBridgeHeight` |
| urbanstyle | terrain if on, else 0 | level × 6 m (`DECK_M`), or the height of the `bridge.json` mesh at `p` | the level of the lane's edge; the bridge mesh vertices |
| SimReady | the DEM that its profiles came from | the `graded` elevation profile of the carriageway at the lane's station, minus `ground` | `sim.elevation_profile` rows given to the page |
| plain MapLibre | terrain if on, else 0 | 0 | — |

Rules:

- **One rule for decks.** The formula of a deck's height moves to Rust (`roadstyle-camera`), and the bridge mesh
  (`bridgemesh.js`, branch `claude/bridge-mesh-3d`) calls it through WASM, so the deck and the vehicle on it always
  agree. Until that branch is merged, the roadstyle adapter has decks off.
- **Exaggeration.** `queryTerrainElevation` includes the terrain exaggeration (P0). A structure height is multiplied
  by the same factor, so a vehicle on a deck stays on the drawn deck.
- **Tunnels.** A lane of a tunnel edge has a structure height that puts it under the ground. The vehicle is drawn
  there. The terrain hides it unless the page shows tunnels (`terrain_tunnels`); the camera then uses its tunnel state
  (section 10.4).

## 9. Obstacles and the visibility test

**Kinds:**

| Kind | From | Shape for the test |
|---|---|---|
| terrain | the ground grid of section 7 | a height field |
| buildings | `map.querySourceFeatures` of the obstacle layers (roadstyle: `vbm-building-3d`; urbanstyle: its building layers) | prisms: footprint, base (the lowest ground height of the footprint, plus `render_min_height`), top (base + `render_height`) |
| decks | the surface data of section 8 | slabs: the deck piece's footprint, from the deck height minus its thickness to the deck height |

JS sends the features again on `idle` after a move, and on `sourcedata` of an obstacle source. Rust keeps them in a grid
of `camera.obstacle_cell_m` (default 25 m) cells, for the area within `camera.obstacle_radius_m` (default 300 m) of the
followed vehicle.

**The test** `visible(eye, target)`: the straight line from the camera to the target (the vehicle's middle at half its height):

- **terrain:** samples every `camera.terrain_step_m` (default 5 m); each must be above the ground;
- **prisms and slabs:** for each one whose box touches the line, the line must not cross its footprint at a height between its base and its top.

A target is visible when the line is clear to at least one of three target points (the middle, the front top, the back top),
so a corner of a building does not hide a vehicle that the viewer can still see.

**The measure that tests the test.** The vehicle layer runs a WebGL2 occlusion query (`ANY_SAMPLES_PASSED_CONSERVATIVE`)
on the draw of the followed vehicle. `rs.vehicles.visibility()` gives the frames counted and the frames hidden.
This is valid only when the vehicle layer is drawn after the obstacles (section 11).

## 10. The camera rig

### 10.1 Modes

| Mode | Key | Camera |
|---|---|---|
| `seat` | 1 | at the driver's eye (`camera.seat.eye_m`, 1.5 m above the surface, `camera.seat.forward_m` 0.3 m behind the front), looking `camera.seat.look_m` (15 m) ahead along the path; `fov` `camera.seat.fov` (70°) |
| `chase` | 2 | behind and above (section 10.2); `fov` `camera.chase.fov` (50°) |
| `chase_far` | 3 | `chase` with the distance and height × `camera.chase.far_factor` (2.5) |
| `overview` | 4 | top-down at `camera.overview.zoom`, centred on the vehicle, north up |
| `free` | Esc | the person moves the camera; the module does not move it |

A new mode eases in over `camera.mode_change_s` (0.6 s). A drag or a wheel on the map while following goes to `free`, with
a message in the status line and a button to follow again. When the vehicle reaches its last sample, the camera goes to
`overview` over the vehicle's last point, then stops following.

### 10.2 Chase: the wanted position

- **Direction:** the direction of the vehicle's last `camera.chase.trail_m` (30 m) of path, not its heading now.
- **Distance** `D0 = camera.chase.dist_base_m (18) + camera.chase.dist_per_mps (0.5) × speed`.
- **Height above the vehicle** `H0 = max(camera.chase.height_min_m (10), camera.chase.height_ratio (0.5) × D0)`.
- **Eye** = the point `D0` behind the vehicle along the direction, at the vehicle's height plus `H0`. Its height is also at
  least the ground at the eye plus `camera.clearance_m` (3 m).

### 10.3 Chase: avoiding obstacles

Each frame:

1. **Look ahead.** Test the wanted eye against the vehicle's position `camera.look_ahead_s` (0.75 s) ahead as well as now.
   The camera moves before the vehicle is hidden.
2. **Tries.** If the wanted eye is not clear, try other eyes in this order and take the first clear one:
   closer (`D0` × 0.8, 0.6, 0.45, 0.3), higher (`H0` × 1.4, 2, 2.8, 4, up to `camera.chase.height_max_m` 90 m),
   lower to see under a deck (only when a slab is between: the eye at the deck's underside minus `camera.clearance_m`),
   and to one side (the direction ± 30°, ± 60°). The pairs are tried by the size of the change, smallest first.
   No eye is closer than `camera.chase.dist_min_m` (6 m) or inside a prism, a slab or the terrain.
3. **Short blocks.** A block shorter than `camera.min_block_s` (0.3 s) is ignored (a lamp post, a thin roof edge).
4. **Smoothing.** The eye and the target move toward their new values with a critically damped spring
   (Game Programming Gems 4, "Critically Damped Ease-In/Ease-Out Smoothing"): smoothing time `camera.damp_away_s`
   (0.2 s) when the change avoids a block, `camera.damp_back_s` (1.0 s) when it returns to the wanted eye. The
   direction turns at most `camera.max_turn_dps` (60° per second).
5. **Guarantee.** If the smoothed eye is not clear, the camera takes the chosen clear eye at once. A hidden vehicle is
   never shown because of smoothing.

### 10.4 States in the status line

| State | When | Shown |
|---|---|---|
| `following` | a clear eye exists | the mode, the vehicle id, its speed |
| `in_tunnel` | the vehicle is on a tunnel lane | "In tunnel": the camera goes to `overview` until the vehicle comes out |
| `no_clear_view` | no try is clear | "No clear view": the closest and highest eye; the frames are counted |
| `free` | the person moved the map | "Free camera", a button "Follow again" |
| `ended` | the vehicle's last sample passed | "Vehicle left the network" |

The status line also counts the samples with a lane that is not known and the teleports (section 4).

## 11. Drawing

- One custom layer, id `<prefix>vehicles`, `renderingMode: "3d"`, matrix `defaultProjectionData.mainMatrix` (P0).
- The model matrix is `mainMatrix × translate(origin in Mercator) × scale(metre in Mercator units)`, so instance positions
  stay metres from the scene origin.
- **Layer order.** The layer must be drawn after every obstacle layer. The module moves it to the top on `styledata`,
  after `rsTerrain`, after a base map change and after the 3D switch adds the building layer (P0: a building layer added
  after the vehicle layer makes the depth test and the occlusion query wrong).
- One instanced draw (WebGL2 `drawArraysInstanced`) for each shape. Shapes: `car` (a box with a smaller box for the cabin),
  `van`, `truck`, `bus`, `bicycle`, `motorcycle`; each is a few dozen triangles, scaled by the vehicle's length, width and height.
- A vehicle is drawn at least `vehicles.min_px` (3 px) long, so it shows at low zoom.
- **Picking.** A click finds the nearest vehicle in screen space within `vehicles.pick_px` (8 px), from the instance
  positions projected in JS. No extra render pass.
- Colours come from the palette (section 13). Brake light and indicators are small faces of the shape, on when `signals` says so.

## 12. The page: parts, API, events

### 12.1 Parts (`dashboard/vehiclebar.js`)

| Part | Holds |
|---|---|
| play bar | play / pause, the time (h:mm:ss), a time slider (`rs.slider`), speed buttons (0.5×, 1×, 2×, 4×, 8×) |
| vehicle picker | a search box (id or type), a list of the vehicles present now (a virtual list), a click follows |
| camera buttons | seat, chase, chase far, overview (keys 1–4), Esc for free |
| status line | section 10.4 |

The parts follow the rules of AGENTS.md for dashboard parts: the theme tokens of `dashboard.css` (no fixed colour), both
themes, no native tooltip or select, a browser test, a place in `tests/test_dashboard_themes_browser.py`, and the list of the
vehicle picker in `_PS_AREAS` (it scrolls). A row in `docs/guides/dashboard-parts.md`.

### 12.2 JS API

| Call | Does |
|---|---|
| `rs.vehicles.load({run, lanes, types} | {url, lanesUrl, typesUrl})` | loads a run (a host page that builds its own map) |
| `rs.vehicles.play()`, `.pause()`, `.seek(t)`, `.speed(x)`, `.time()` | the clock |
| `rs.vehicles.follow(id, {mode})`, `.unfollow()`, `.mode(name)` | the camera |
| `rs.vehicles.find(text)` | the ids that match |
| `rs.vehicles.state(id)` | `{t, lon, lat, alt, heading, speed, lane, type}` now |
| `rs.vehicles.visibility()` | `{frames, hidden}` of the occlusion query (section 9) |
| `rs.vehicles.report()` | the run's report (section 6) |

### 12.3 Events

| Event | `detail` |
|---|---|
| `rs:vehicleload` | the run's report |
| `rs:vehicletime` | `{t}`, at most 4 times a second |
| `rs:vehicleselect` | `{id}` (a click on a vehicle) |
| `rs:followchange` | `{id, mode}` (`id` null: not following) |
| `rs:camerastate` | `{state}` (section 10.4) |

`rs.getState()` gets `vehicles: {t, speed, playing, follow, mode}`, so `rs.link()` keeps a view of a run.

## 13. Style values

Every number is a key in `profiles/default.yaml`; every colour is a key in each palette (`tests/test_theme.py` rule).

**Profile** (new section `vehicles:` and `camera:`): `vehicles.sizes.<class>` (length, width, height), `vehicles.min_px`,
`vehicles.pick_px`, `vehicles.lane_change_s`, `vehicles.heading_lookahead_m`, `vehicles.teleport_m`,
`vehicles.window_back_s`, `vehicles.window_ahead_s`, `vehicles.inline_max_mb`, `vehicles.ground_cell_m`,
`vehicles.live_delay_s`; `camera.clearance_m`, `camera.look_ahead_s`, `camera.min_block_s`, `camera.damp_away_s`,
`camera.damp_back_s`, `camera.max_turn_dps`, `camera.mode_change_s`, `camera.terrain_step_m`, `camera.obstacle_cell_m`,
`camera.obstacle_radius_m`, `camera.seat.*`, `camera.chase.*`, `camera.overview.*`. The defaults are the values in
sections 4 to 11.

**Palettes** (new section `vehicles:`, in each palette, light and dark): a colour for each class, the followed vehicle's
outline, the selected vehicle's outline, the brake light, the indicator, and the speed ramp for `vehicle_colour_by: "speed"`.

## 14. Tests

| Level | Test |
|---|---|
| Rust, `roadstyle-sim` | the readers on a fixture made by SUMO itself (Monaco, 90 s, 60 vehicles, 2,676 rows: `monaco_fcd.parquet` 118 KB and the edges of the vehicles' routes in `monaco_net.xml` 604 KB): row counts, ids as text, no lane unknown and no pair without a chain; the middle is 2.5 m behind SUMO's front bumper (median error under 0.1 m); no jump at a sample (99 % under 5 cm, all under 0.1 m, lane changes too); the heading near SUMO's angle (median under 3°); a teleport; a class with no size |
| Rust, `roadstyle-camera` | `visible` on hand-made cases (a prism between, a slab above, a hill between, a corner); the deck rule gives the same height as the bridge mesh at its vertices; the camera rig on a fixed path is the same each run (no randomness) and never puts the eye inside an obstacle |
| Python | `read_run` report values on the fixture; each keyword lands in `RS_OPTIONS` (`_opt(html, key)`); `vehicle_data="file"` writes the two files |
| Browser (Playwright) | load, play, seek, follow, mode keys; layer order after the 3D switch and a base map change; the parts in both themes; the host route (`examples/dashboard_rust/`) with vehicles |
| Browser, the camera measure | at the test places (vehicles.md), following a fixed vehicle for 60 s of simulation: visible frames ≥ 99 % (occlusion query), largest turn rate ≤ `camera.max_turn_dps`, the eye never inside an obstacle |
| Speed | 1,000 vehicles: `frame` ≤ 2 ms and 60 fps on a desktop GPU; 10,000 vehicles: ≥ 30 fps. Measured on a real GPU, not SwiftShader |

## 15. Phases and "done when"

| Phase | Work | Done when |
|---|---|---|
| P1 | `roadstyle-sim` (contract, Parquet and `net.xml` readers, clock, lane placement, interpolation); `VehicleScene` with flat ground; the custom layer with boxes; `rs.vehicles` play / pause / seek; `vehicles=` keyword | the P0 Monaco run plays on a Södermalm-style page and a Monaco page at 60 fps, the vehicles in their lanes, and the Rust and Python tests pass |
| P2 | `roadstyle-camera` surface: terrain ground requests, the deck rule in Rust (after `claude/bridge-mesh-3d` is merged), tunnels; pitch and roll | on Monaco with terrain on, the vehicles stand on the hills and on the decks, at exaggeration 1 and 2 |
| P3 | obstacles, `visible`, the camera rig, the status states, the occlusion measure | the camera measure passes at every test place |
| P4 | the urbanstyle and SimReady adapters | a SUMO run from each project's network plays on its page, with the measure passing |
| P5 | the parts, the docs (guide page, reference rows, SKILL.md), speed work | the part rules of AGENTS.md are met; the speed targets are met |
| P6 (later) | live data (section 4.5) | a TraCI run streams to a page with the same camera |

## 16. Risks

| Risk | What is done |
|---|---|
| MapLibre changes the custom layer API again (5.x moved the matrix) | the vehicle layer reads one function for the matrix; a browser test fails if a box at the map centre does not project to the centre |
| A layer added later goes above the vehicle layer | the module moves its layer on every style event; a browser test checks the order after each kind of change |
| float32 precision | metres from the scene origin (section 7) |
| The terrain exaggeration differs from the structure heights | one factor for both (section 8) |
| The DEM of the map and the heights of the road model differ (SimReady uses FABDEM, the map uses Terrarium tiles) | the ground reference standard (duckOSM `docs/concepts/ground-reference.md`, 2026-11-09): the map's terrain is the conformed ground of the area; the run report names its ground id |
| SwiftShader results differ from a real GPU | the speed targets are measured on a real GPU; the occlusion query results are checked on both |
| Junction-internal lanes are 15 % of the samples (P0) | lane shapes include the internal lanes of `net.xml` |
| Big runs do not fit in memory | row-group reading and the time window (section 5) |

## 17. Open questions

To decide one at a time, before or during the phase that needs the answer:

1. **The look of a vehicle** (P1): simple boxes by class, low-poly shapes by class (section 11), or glTF models (larger pages)?
2. **Inline limit** (P1): is 20 MB the right limit for a run inside the page?
3. **The default colour** (P1): by class, by type or by speed?
4. **Live TraCI** (P6): needed soon, or later?
5. ~~**One ground**~~: decided 2026-11-09 by the ground reference standard (duckOSM `docs/concepts/ground-reference.md`).
