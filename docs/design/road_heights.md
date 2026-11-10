# Road heights: one height profile for each road

Status: decided 2026-11-10. Built on the branch `claude/vehicles-p2` for the map's terrain as the source; the data sources (SimReady,
duckOSM `z_vertices`) and the 3D decks come next. Part of the vehicles work ([vehicles.md](vehicles.md),
[vehicles_spec.md](vehicles_spec.md), section 8) and of the ground reference standard (duckOSM
`docs/concepts/ground-reference.md`).

## Why

A vehicle's height came from the ground at its lon/lat (P2 step 1: the terrain on a 5 m grid). That is wrong for four reasons:

1. **A different point.** The vehicle is on SUMO's lane line, about 1.6 m beside the drawn road's centre line, and in a junction on
   netconvert's path. On a steep street with a cross slope, 1.6 m sideways is 0.3 to 1 m of height.
2. **A different surface.** MapLibre drapes the drawn road on its own terrain mesh, at the DEM detail of the zoom. A separate sample of
   the same DEM differs by up to 0.7 m (measured on Monaco between zoom 13 and 18.5).
3. **A road is not the terrain.** A road has cuts, fills, embankments and walls; a 30 m DEM smooths them. In SimReady's Monaco model the
   graded road is a median 1.5 m from the DEM, and often 4 to 14 m.
4. **Two roads at one point.** Under a bridge deck, the ground gives the road below, so a vehicle on the bridge falls to the valley. The
   same is true for stacked ramps and for tunnels. **No method that reads the ground at a point can work.**

## Decisions

| Date | Decision | Reason |
|---|---|---|
| 2026-11-10 | The height is a property of the road: each road has a height profile along its drawn line | a road, not a point, has a height; two roads can share a point |
| 2026-11-10 | A road's profile is made by the rule that draws the road: a ground road, a 3D bridge deck (the bridge mesh rule), a tunnel | a vehicle must stand on the road as the map draws it; one rule, no second copy |
| 2026-11-10 | A vehicle takes its height only from its road, at its distance along that road | its lon/lat does not tell which of two roads it is on |
| 2026-11-10 | The profile lives in roadstyle's Rust engine (`roadstyle-camera`); its heights come from the data when the data has them: SimReady's road model, else duckOSM's `z_vertices`, else the map's terrain along the road's line | roadstyle draws the roads and holds the deck rule; duckOSM and SimReady compute the data ("roadstyle draws, duckosm-rust computes") |

## The profile of a road

- **One profile for each drawn road** (a row of the road table, by its `edge_id`): heights at fixed distances along the road's drawn
  line, and linear between them. Each direction of a two-way road is its own row, so it has its own profile (one profile for the pair is
  a later saving, see "Memory").
- **A lane's part of the road:** netconvert cuts each lane back from its junctions, so a lane starts some metres after its drawn line
  starts. The start and the end of each lane are projected onto the road's drawn line, once; a place along the lane is the same fraction
  of that span. This also gives the direction: a drawn line can run against the SUMO lanes of its edge (39 of 2,765 roads on Monaco).
  (Before 2026-11-10 the fraction of the lane was the fraction of the whole line: on a 30 % street, 8 m of error was 2.7 m of height.)
- **Step:** 5 m on a ground road (the DEM is 30 m data), 2 m on a bridge deck and its ramps (their shape changes quickly).
- **Built when a vehicle first drives on the road**, and kept. It is made again when its source changes: the terrain on or off, another
  exaggeration, a new terrain tile (a finer tile after a zoom changes the drawn terrain under the road), a deck height set with
  `rsBridgeHeight`, new data.
- **Sources, in this order:**

| Source | When | Heights |
|---|---|---|
| SimReady's road model | the page has the model's roads | the `graded` elevation profile of the road's carriageway; decks and tunnels from its structures |
| duckOSM | the roads have `z_vertices` (a build with a DEM) | the ground at each vertex of the edge line; a bridge or a tunnel by the deck and tunnel rules |
| the map | neither | the map's terrain along the road's own line (`queryTerrainElevation`); a bridge by the deck rule; a tunnel by the tunnel rule |

- **By kind of road:**

| Road | Profile |
|---|---|
| ground road | the source's heights along the line |
| bridge (3D decks on) | the deck surface, by the bridge mesh rule (`bridgemesh.js`, PR #140): level between the ground at the two ends of its chain, ramps from the ground at each free end, the group height. The same function draws the deck and gives the vehicle's height |
| tunnel | the tunnel rule of the page: today the tunnel is drawn on the terrain above it, so the profile is the terrain along its line, and the vehicle has the tunnel's look (`rs_terrain_tunnel`) |

- **Exaggeration:** a height from the map's terrain already includes it; a height from the data is multiplied by the same factor, so the
  road, the deck and the vehicle stay together.

## The vehicle

- **Its road position**, from the lane placement (`roadstyle-sim`): SUMO's edge id is duckOSM's `edge_id`, which is the drawn road's
  `edge_id`. The distance along the drawn road is the vehicle's fraction along its SUMO lane, in the lane's span on the drawn line (see
  "A lane's part of the road").
- **A lane change:** the position is a blend of the places on the two lanes; the height is the same blend of the two roads' profiles,
  with the same weights. The vehicle state holds one to three entries (road, distance along, weight).
- **A junction:** SUMO's internal lane has no drawn road. The height goes linearly, along the internal lane, from the end of the road
  coming in to the start of the road going out; the two meet at the same node.
- **Height** = the weighted sum of the profiles at the vehicle's middle. **Pitch** = the slope of the profile over the vehicle's length.
  **Roll** = 0 (a road is level across).
- **Lon/lat placement** (no lane data) has no road: those vehicles keep the ground at their lon/lat, and the page says so.

## Memory

About 2 KB for each km of road (one 4-byte height every 2 m), plus about 32 bytes for each road. Measured on duckOSM's directed driving
roads (the largest case: every road built, no sharing):

| Area | Driving roads | Length | Profiles |
|---|---|---|---|
| Monaco | 2,765 | 93 km | about 0.3 MB |
| Södermalm | 4,565 | 192 km | about 0.5 MB |
| Tartu | 22,498 | 1,212 km | about 3 MB |
| a large region | — | each 10,000 km | about 20 MB |

The real cost is smaller: a profile is built only for a road that a vehicle drives on, and a ground road has a 5 m step. Measured on the
Monaco page (2026-11-10): 157 roads and 20 KB at 5:00 of the run, 806 roads and 96 KB after 30 s more. One profile for both directions of
a two-way road would halve it. For comparison, the Monaco page's engine holds about 68 MB, and the 900 s SUMO run is 3.5 MB as Parquet.

## Limits

- Until roadstyle draws the area's conformed ground (the ground reference standard), the map's terrain is the AWS Terrain Tiles, while
  duckOSM and SimReady use the area's DTM. A profile from the data and the drawn terrain can then differ by up to about a metre.
- The 3D decks wait for PR #140 (the bridge mesh).

- The map drapes a road on the terrain, so on a street that slopes across, the drawn road is not level across. A vehicle on a lane
  1.6 m beside the centre line has the centre line's height, and the drawn road under it can be up to about 1.5 m higher (measured on
  Monaco, 2026-11-10: most vehicles less than 1 m). Open: decide how a vehicle stands on a draped road.

## What it replaces

The 5 m ground grid of P2 step 1 (`GroundGrid` in `roadstyle-camera`) for vehicles with lane placement. The grid stays only for lon/lat
placement.

## Tests

- A profile on a sloped plane gives the plane's height along the road.
- A vehicle on a deck has the deck's height at its point, from the same function that draws the deck.
- A bridge over a road: at the same lon/lat, a vehicle on the bridge and a vehicle on the road below each have their own road's height.
- A lane change and a junction: no jump in height (the same test as the position's "no jump at a sample").
- The memory of the profiles on the full Monaco run, measured and reported.
