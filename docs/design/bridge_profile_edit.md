# The bridge profile: roadstyle and urbanstyle, and an input profile

Date: 2026-11-10. Status: proposal. Nothing is built. The documentation comes first: this note is the spec, and the code waits for approval.
This note is about the profile of a group of 3D bridges: how [the engine](../guides/bridge-height.md) makes it, how urbanstyle makes the profile of the same bridge,
and a proposal for an edit step.

## Summary

- The two projects use the same design. A program makes a **profile** of the bridge, and another program **draws** the bridge from the profile only.
- The two profiles are in different forms. roadstyle makes a list of short deck pieces with a lift from 0 to 1 and one height H for the whole group. urbanstyle makes one JSON
  file for each bridge, with a height line `[s, z]` in metres for each axis and a `source` and a `method` for each value.
- On the Granville Bridge, the engine finds the same 12 chains as urbanstyle finds axes, with the same OSM ways. The heights are different. The engine gives all 12 chains the same top
  (22 m). The LiDAR gives 39 m on the main span and 11.6 m to 27 m on the ramps.
- **A second note gives the rules for the heights themselves:** [The height of a bridge from the design rules](bridge_height_design.md) (clearance, design grade, vertical curves).
- **The proposal: the 3D bridge has an input profile and an output profile, and a person edits only the input profile.** The engine writes the input profile for the roads: the group, its chains and nodes,
  and a default height `z` at each node. A person changes the numbers. The engine reads the file again and makes the output profile (the deck pieces). The output is never edited. With no change, the output is
  the same as today.
- **The input profile is small.** The Granville Bridge has 13 nodes. 8 are on the ground (height 0, from the data), so a person gives **5 heights**, one for each junction. A chain between two nodes is a straight
  grade with vertical curves. A chain that needs a crest or a sag between its nodes needs one more control point for each. A prototype shows why: node heights alone leave up to 10 m of error on the long chains.

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

## The proposal: edit only the input profile

The 3D bridge has an **input profile** and an **output profile**. A person edits the input profile and nobody edits the output profile.

```text
roads  ->  the engine writes the input profile (the nodes, with a height for each, from the rules)
                |
                |   a person changes the numbers
                v
         the input profile  ->  the engine (the rules, the vertical curves, the checks)  ->  the output profile (the deck pieces)  ->  the page draws it
```

- The **input profile** is small: the group (its chains and nodes), the height `z` of each control point, and a few parameters. The engine can write it for any page, with a default `z` from the rules at each
  node, so that a person edits only numbers.
- The **output profile** is the list of deck pieces of [the guide](../guides/bridge-height.md). It is made from the input profile. It is never edited. If the input profile has no change, the output is the output of the rules.
- This is also the design of urbanstyle: a profile file, and a model that reads only the file.

### What is in the input profile

| Part | Content | Edited by a person? |
|---|---|---|
| `parameters` | The design speed and the design grade. The engine needs them for the vertical curves and the checks | Yes |
| The group | A name, its chains and its nodes. They come from the roads | No. The engine writes them |
| A node | An id, its position (longitude and latitude), its kind (`ground` or `junction`), the chains that meet there, and its height `z_m`. A `ground` node is 0. A `junction` has the height that the rules give, until a person changes it | **The `z_m` of a junction: yes** |
| A chain | An id, the OSM ways, its length, its two end nodes (`from`, `to`), the interior control points (`points`), and optionally its width | `points` and the width: yes |
| An interior control point | `s` (metres from the `from` end) and `z_m`. For a high point or a low point between two nodes | Yes |
| `source`, `method` | Where a height comes from. `method` is `mapped`, `measured`, `derived` or `chosen`. Optional | Yes |

The width is not needed for a height. The engine takes it from the road class and the lanes, and a chain can override it. The geometry of a chain is the geometry of the roads. It is not in the file.

### An example: the Granville Bridge

`docs/img/bridge-height/granville_input_profile.json` is the input profile of the Granville Bridge group (5 KB, made by `granville_input_profile.py`). It has 13 nodes and 12 chains. This is a node on the ground, a junction, and a chain:

```json
{"id": "n1", "lonlat": [-123.12952, 49.27624], "kind": "ground", "chains": ["c6"], "z_m": 0.0, "source": "data", "method": "mapped"}
{"id": "n4", "lonlat": [-123.13097, 49.27397], "kind": "junction", "chains": ["c1", "c5", "c6", "c8"], "z_m": 11.0, "source": "example", "method": "chosen"}
{"id": "c1", "osm_ways": [1419040127, 1419040128], "length_m": 550.4, "from": "n5", "to": "n4", "points": []}
```

The 8 nodes on the ground are 0 and come from the data. The 5 junction heights are the example of [the design note](bridge_height_design.md): each is the highest height that a grade of 6 % allows. They are the
only 5 numbers that a person must give. `points` is empty for every chain: each chain is a straight grade between its two nodes, with vertical curves.

### What the engine does with it

1. It reads the nodes and chains. A node has one height. For this reason, two chains that meet at a node cannot have two heights (the problem of the first proposal is gone).
2. For each chain, it makes the profile through the height at its first node, its interior control points, and the height at its last node: a straight grade between two points, and a parabolic vertical curve
   of length `L = max(K × A, 0.6 V)` at each change of grade (the rules of [the design note](bridge_height_design.md), step 3).
3. It cuts the chain into deck pieces. The pieces carry the same properties as today (`__rs_lift0`, `__rs_lift1`, `__rs_s0`, `__rs_s1`, `__rs_full`). With a different `__rs_full` for each chain, the lift of a piece
   is `z ÷ __rs_full`, with `__rs_full` the highest `z` of the chain.
4. It runs the checks and reports them.

**With no input profile**, the engine writes the default input profile with the rules that it has. Until the rules of the design note are built, the default `z` of a junction is the height that today's rule gives. The output
is then the output of today.

### How many control points

| | Count |
|---|---|
| Nodes on the ground | 8. Height 0 from the data. Nothing to give |
| Junctions | 5. One height for each |
| Interior control points | 0 or more. One for each high point or low point that a chain needs between its nodes |

The Granville Bridge needs 5 heights and no more, if each chain can be a straight grade. A chain that needs a crest (for example the main span, 550 m) needs one point more for the crest.

### Checks

The engine says what is wrong and does not change a number of the person.

| Case | Result |
|---|---|
| The grade between two control points is above the design grade | Warning. Above the maximum grade of the road class: error |
| The `s` of a point is outside the chain, or the points of a chain are not in order of `s` | Error |
| A node id or a chain id that the roads do not have | Error |
| A `z_m` below 0 | Error |
| A `ground` node with `z_m` above 0 | Allowed: a landing on fill. The page closes the end of the deck down to the ground |
| Two curves overlap (a short chain with a high design speed) | Warning. The curves are shortened and the message says so |
| A sag curve whose low point is on the bridge, or a flat top with no grade on a long bridge | Warning |
| Two decks cross and the upper deck is not high enough above the lower one | Warning (later: it needs the crossings from the level solver) |

### What the prototype shows: node heights alone are not enough

`docs/img/bridge-height/granville_proposed.py` is a prototype in Python. It is not the engine. It compares three profiles against the LiDAR stations of each chain. Stage 1 is the profile of the chain
with the heights at its two nodes and its top only. Stage 2 is the profile through the grade points of the LiDAR fit, which are control points between the nodes. This is the evidence for interior control points.

![The engine today, the stage 1 profile, the stage 2 profile and the LiDAR](../img/bridge-height/granville_proposed.png)

| Chain | Input of stage 1: first end, last end, top | Largest error today | Largest error, stage 1 | Largest error, stage 2 |
|---|---|---|---|---|
| 1 | 27.0 m, 22.7 m, 39.3 m | 17.3 m | 10.0 m | 0.2 m |
| 2 | 11.7 m, 4.4 m, 11.7 m | 11.3 m | 2.5 m | 0.2 m |
| 3 | 0.0 m, 18.2 m, 17.7 m | 10.9 m | 7.0 m | 0.2 m |
| 4 | 27.1 m, 11.8 m, 27.1 m | 10.2 m | 9.8 m | 0.1 m |
| 5 | 22.7 m, 0.7 m, 22.7 m | 8.9 m | 9.5 m | 0.3 m |
| 6 | 0.0 m, 20.7 m, 20.2 m | 9.7 m | 8.9 m | 0.3 m |
| 7 | 11.7 m, 0.2 m, 11.7 m | 11.8 m | 6.3 m | 0.3 m |
| 8 | 22.7 m, 8.3 m, 22.7 m | 9.5 m | 5.7 m | 0.2 m |
| 9 | 18.2 m, 27.0 m, 27.0 m | 5.0 m | 4.9 m | 0.1 m |
| 10 | 11.6 m, 18.2 m, 18.2 m | 4.9 m | 3.4 m | 0.0 m |
| 11 | 11.6 m, 0.1 m, 11.6 m | 3.0 m | 0.9 m | 0.2 m |
| 12 | 0.0 m, 11.6 m, 11.6 m | 3.0 m | 0.9 m | 0.2 m |

- **Stage 1 is not enough.** The heights at the ends and the top of a chain remove part of the error, but the largest error stays at about 9 m to 10 m on chains 1, 4, 5 and 6. Chain 5 is a little worse than
  today. A real ramp is a straight line from the top down to the ground, and the profile of the engine is a flat top with a ramp of 1 m in 8 m. The shape is the limit, and not only the heights.
- **A height line is enough.** With the grade points of the LiDAR fit, the largest error is 0.3 m. This is partly expected, because the points are the fit of the same stations. It shows that the
  format can carry the real shape. It is not a test of the measurement.
- **Some free ends are above the ground.** The engine has a free end (lift 0) at the last end of chains 2 and 8. The LiDAR height there is 4.4 m and 8.3 m, because the OSM bridge way ends before
  the bridge does, and the deck goes on to the street on fill. Only a height line (or a node height) can say this.

### The page

- The page reads the same pieces. It does not change for an input profile.
- A deck end with `lift > 0` is blunt today. For a landing on fill, the page draws the sides down to the ground, as urbanstyle does.
- The Height box shows the `z_m` of the selected node or chain, with its `source` and `method`, and can change it in the open page (a change of the input profile, not of the output).
- `rsBridgeGroups()` lists the chains and the nodes.

### The order of the work

1. **Documentation first** (this note and [the design note](bridge_height_design.md)). The guide gets new pages when the code exists.
2. The engine: the input profile (read, write, default), the profile through the control points, the checks. `rs.bridge_profile(edges)` writes the input profile. The keyword `bridge_profile=` (a dictionary or a JSON file)
   reads it. Tests: a straight grade between two nodes; the rounded corner; the continuity of the pieces; one height at a node; an interior point; every check of the table; **no input gives the same pieces as today**;
   the Granville file gives its 12 chains and 13 nodes.
3. The page: the landing on fill, the Height box, `rsBridgeGroups()`.
4. A converter from an urbanstyle profile to this input profile, outside the engine. It matches the axes to the chains by the OSM ways (12 of 12 on the Granville Bridge).
5. The default `z` of a junction from the design rules (the other note).

### Decisions that are open

Each decision has the recommendation of this note.

1. **Edit only the input profile.** Yes. The output profile is never edited.
2. **Control points.** The heights of the nodes, and interior points `(s, z)`. A height line with curves is not an input: the curves are calculated.
3. **Naming a node.** By its id in the input profile that the engine writes, and its position. The engine writes the file so that a person does not need to find the nodes.
4. **A new keyword.** `bridge_profile=` replaces `bridge_heights` and `bridge_height_col` in the end. The two stay while the engine has no input profile.
5. **The Height box in the open page.** It changes the input profile, then the output is made again. The ramps are then new too (today they keep the first length).
6. **The landing on fill.** The page draws the sides down to the ground.
7. **The urbanstyle converter.** Yes, outside the engine.
8. **Where the file is kept.** "One rule for every path" says the page, the tiles and the editor must read the same data. A profile that belongs to the area could be kept with the area, in duckOSM. This is for later.

### Regenerate the figures and the tables

```bash
python docs/img/bridge-height/granville_vs_lidar.py       # the comparison, and its table
python docs/img/bridge-height/granville_proposed.py       # the prototype, and its table
python docs/img/bridge-height/granville_input_profile.py  # the input profile of the Granville Bridge
```
