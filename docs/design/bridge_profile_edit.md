# The bridge profile: roadstyle and urbanstyle, and an edit step

Date: 2026-11-10. Status: proposal. Nothing is built. This note is about the profile of a group of 3D bridges: how
[the engine](../guides/bridge-height.md) makes it, how urbanstyle makes the profile of the same bridge, and where an edit step can go.

## Summary

- The two projects use the same design. A program makes a **profile** of the bridge, and another program **draws** the bridge from the profile only.
- The two profiles are in different forms. roadstyle makes a list of short deck pieces with a lift from 0 to 1 and one height H for the whole group. urbanstyle makes one JSON
  file for each bridge, with a height line `[s, z]` in metres for each axis and a `source` and a `method` for each value.
- On the Granville Bridge, the engine finds the same 12 chains as urbanstyle finds axes, with the same OSM ways. The heights are different. The engine gives all 12 chains the same top
  (22 m). The LiDAR gives 39 m on the main span and 11.6 m to 27 m on the ramps.
- The engine has no input for the height of one chain or one node. urbanstyle has one: its `heights` section. An edit step for roadstyle can use the same idea.

## How roadstyle makes the profile

Read [How the height of a 3D bridge is calculated](../guides/bridge-height.md). In short:

1. The engine joins the bridge roads into groups and chains. A free end is a node where one bridge road ends.
2. A group has one height H, from its length (5 m up to 60 m, 22 m from 600 m) or from `bridge_heights` or `bridge_height_col`.
3. The lift at a node is `min(1, distance to the nearest free end ÷ (8 × H))`. The lift along a chain is a smooth curve between the two end lifts.
4. The engine writes a list of deck pieces (GeoJSON, source `decks`). Each piece has `__rs_lift0`, `__rs_lift1`, `__rs_s0`, `__rs_s1` and `__rs_full`.
5. The page reads the pieces, adds the ground height, and draws the mesh.

## How urbanstyle makes the profile

The code is `src/urbanstyle/bridge_profile.py`. The notes are `docs/notes/bridge-profile.md` and `docs/notes/bridge-heights.md` of urbanstyle.

**The file.** `urbanstyle bridge` writes one `<name>.bridge.json` for each bridge. Its format is `urbanstyle.bridge/1`. The values are in metres, in the UTM zone of the bridge.
The file holds:

| Part | Content |
|---|---|
| `deck` | The outline (from OSM `man_made=bridge`, or made from the lanes), the thickness (1.8 m) and the parapet (1.1 m) |
| `axes` | One axis for each chain of road ways between two junction nodes. An axis has `ways`, `line`, `length_m`, `ends`, `vertical` and `sections` |
| `axes[].vertical` | `points` (`[s, z]`: the grade points), `curves` (the length of the vertical curve at each point), `samples` (`[s, z]` every 10 m), `source`, `method`, `rule` |
| `axes[].sections` | The bands across the deck (lanes, paths) for each length of the axis where the cross-section does not change |
| `connectors`, `paths`, `piers` | The paths from lane to lane at a fork, the paths on the deck, and the piers |
| `heights` | The known heights: a few numbers (see "Edit" below) |

Every value has a `source` and a `method`: `mapped`, `measured`, `derived` or `chosen`. The scripts make the file. Nobody edits it by hand. The 3D model reads only the file.

This is the vertical profile of axis a1 (the main span) in the measured profile of the Granville Bridge. The list `samples` has 56 items. `points` and `curves` are the fit of the LiDAR stations.

```json
"vertical": {
  "points": [[0.0, 27.02], [160.0, 31.06], [220.0, 33.66], "... 9 points"],
  "curves": [0.0, 54.0, 54.0, 27.0, 18.0, 18.0, 27.0, 54.0, 0.0],
  "samples": [[0.0, 27.02], [10.0, 27.29], [20.0, 27.56], "... 56 samples"],
  "source": "City of Vancouver LiDAR 2022", "method": "derived"
}
```

**The height rule, with no measurement.**

1. A node on the ground has height 0. A node is on the ground when a road that is not a bridge also uses it. (A path does not count.)
2. For each node, D is the shortest distance along the bridge roads to a node on the ground.
3. The height is `h = min(27 m, 0.05 × D)`.

At a node where branches meet, D is the smallest distance through any branch, so all branches have the same height there. This is the rule of roadstyle too, with other numbers.

**The measured heights.** `urbanstyle bridge-measure` reads LiDAR tiles. At a station every 10 m along each axis, the deck top is the 25 % quantile of the deck returns, and the ground is the median of
the ground and water returns within 30 m. The profile stores the height of the deck top above one smooth reference ground. On the Granville Bridge, 340 stations on 12 axes are measured.

**Edit: the `heights` section.** A person, LiDAR or a survey can add known heights. The model pulls the deck to them. The rule fills in everywhere else.

```json
"heights": {
  "n21918825": {"deck_m": 9.0, "source": "manual", "method": "chosen"},
  "a2": {"mid_m": 6.5, "source": "manual", "method": "chosen"},
  "a1": {"points": [[0, 27.0], [340, 39.0], [550, 22.7]], "curves": [0, 60, 0],
         "source": "City of Vancouver LiDAR 2022", "method": "measured"}
}
```

| Key | Meaning |
|---|---|
| `n<id>` (an OSM node) | `deck_m`: the height of the deck at that node. Every axis that ends there takes it |
| `a<k>` (an axis) | `mid_m`: the height at the middle of the axis |
| `a<k>` (an axis) | `points` and `curves`: the height line of the axis, with a vertical curve at each inside point |

## The two profiles side by side

| | roadstyle (the engine) | urbanstyle |
|---|---|---|
| Unit of the profile | A deck piece: 2.5 m on a ramp, long on a flat part | An axis, with a height line `[s, z]` |
| Height | `H × lift`: one H for the group, a lift from 0 to 1 | `z` in metres, for each axis |
| Group height | From the length (5 m to 22 m), or one value for the group | None. The rule gives each node its own height, to 27 m |
| Ramp | 8 m of ramp for 1 m of height (12.5 %) | A grade of 5 % |
| Curve | A smooth minimum and a smoothstep between the end lifts | Straight grades, with a vertical curve (60 m by default) at each point |
| Ground node | A free end: a node where one bridge road ends | A node that a road that is not a bridge also uses |
| The landing | Stops at the end of the OSM bridge way | Continues on fill along the next OSM roads to the next junction (150 m at most) |
| Measured heights | Not read | LiDAR, in the `heights` section |
| Edit | `bridge_heights`, `bridge_height_col`, `bridge_decks`, `rsSetBridgeHeight`: H of a group, and the numbers of the rule | The `heights` section: a node, the middle of an axis, or the points of an axis |
| Source of a value | Not kept | `source` and `method` for each value |
| Who draws | The page reads the pieces | The 3D model reads only the file |
| Terrain | The page adds the ground height from the terrain | A flat map (ground z = 0), or elevations where the profile has `ground_elev` |

## The Granville Bridge, side by side

The data is in `docs/img/bridge-height/`: the 41 edges of the bridge group, and the LiDAR heights of the 12 axes (copied from urbanstyle's measured profile). The generator is `granville_vs_lidar.py`.
The engine's group has 12 chains. Each chain has the same OSM ways as one axis of urbanstyle: 12 of 12.

![The profile of the engine and the LiDAR heights, for each chain](../img/bridge-height/granville_vs_lidar.png)

| Chain | Axis of urbanstyle | Length (engine, urbanstyle) | Highest deck, engine | Highest deck, LiDAR |
|---|---|---|---|---|
| 1 | a1 | 550 m, 550 m | 22.0 m | 39.3 m |
| 2 | a2 | 404 m, 454 m | 22.0 m | 11.7 m |
| 3 | a3 | 367 m, 368 m | 22.0 m | 18.2 m |
| 4 | a4 | 312 m, 312 m | 22.0 m | 27.1 m |
| 5 | a5 | 286 m, 306 m | 22.0 m | 22.7 m |
| 6 | a6 | 276 m, 306 m | 22.0 m | 22.7 m |
| 7 | a7 | 228 m, 246 m | 22.0 m | 11.7 m |
| 8 | a8 | 184 m, 246 m | 22.0 m | 22.7 m |
| 9 | a9 | 179 m, 179 m | 22.0 m | 27.0 m |
| 10 | a10 | 96 m, 96 m | 22.0 m | 18.2 m |
| 11 | a11 | 89 m, 90 m | 11.2 m | 11.6 m |
| 12 | a12 | 89 m, 89 m | 11.2 m | 11.6 m |

What the comparison shows:

- **The structure is right.** The engine and urbanstyle find the same chains, the same junction nodes and the same ground ends. The ramps of the engine rise from the ground at the same places.
  Where the height depends on the distance to the ground only (chains 11 and 12), the engine is within 0.4 m of the LiDAR.
- **One H is too simple here.** The main span is 17 m lower in the engine than in the LiDAR. The ramps of chains 2 and 7 are 10 m higher. The height of a ramp follows what it crosses, not
  the length of the group. A group of 3061 m always gets the largest H.
- **The ends are not the same.** Five LiDAR axes are 18 m to 62 m longer (chains 2, 5, 6, 7 and 8), because urbanstyle continues each landing on fill. The engine stops at the OSM bridge way.
- **The grade is not the same.** The engine rises 1 m in 8 m. The rule of urbanstyle rises 1 m in 20 m. The LiDAR ramps are steeper at the start and flatter later: on chain 3, the deck rises 10 m in the first 100 m.

## Where an edit step can go

The engine makes the profile in five steps (see the guide). An edit can enter at four places.

| | Where | What the user gives | Risk |
|---|---|---|---|
| A | The engine, before it cuts a chain into pieces | The height of a node (`deck_m`), of the middle of a chain (`mid_m`), or a height line for a chain (`points`, `curves`) | The engine keeps all rules by itself. The engine needs a way to name a chain or a node |
| B | The engine, as a file | A profile file in the format of urbanstyle (`urbanstyle.bridge/1`), matched to the chains by the OSM ways | A converter from `[s, z]` to lifts. One H for each chain, not for each group |
| C | The page, after the engine | `rsSetBridgeHeight` for one chain, or a new call for a height line | The page keeps the lifts of the pieces. It cannot change the ramp |
| D | The pieces, between the engine and the page | A program that changes `__rs_lift0`, `__rs_lift1`, `__rs_base` and `__rs_height` | The program must keep the six rules of the guide. A mistake shows as a step or a gap |

The design can use the idea of urbanstyle: **a few known heights, and the rule fills in everywhere else.** The `heights` section of urbanstyle for a bridge with no LiDAR is a few numbers,
for example one for each junction. Its measured Granville profile has 82 grade points on the 12 axes. How many numbers the engine needs for the Granville Bridge is not tested.
Every value can keep a `source` and a `method`, so a measured height can replace a chosen one.

### Decisions that are open

1. Is the input a height for a node, for the middle of a chain, or a height line for a chain? (urbanstyle has the three.)
2. How does a user name a chain? By the id of one road of the chain (as `bridge_heights` does for a group), by an OSM way, or by a node?
3. Does a chain keep the group height H, or does each chain get its own H? With a height line, a chain needs its own H, and the lift is `z ÷ H`. At a node, two chains must have the same `z`.
4. Heights above the ground, or elevations? The engine and the page use heights above the ground (the page adds the terrain). urbanstyle also uses heights above the ground on a flat map.
5. Where is the input file kept? "One rule for every path" says the page, the tiles and the editor must read the same data. A profile that belongs to the area could be kept with the area, in duckOSM.
6. Does the landing continue on fill, as urbanstyle does? The engine stops at the OSM bridge way.

### Regenerate the figure and the table

```bash
python docs/img/bridge-height/granville_vs_lidar.py     # the figure, and the table above
```
