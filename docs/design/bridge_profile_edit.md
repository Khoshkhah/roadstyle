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
- **The proposal: the engine has two parts, and a person edits only the input profile.** The input profile can be incomplete: every height and every width is optional, and the least input is empty.
  **Part 1, the filler,** reads it, keeps what the person gave, and fills what is missing with the rules. It writes a complete input profile. **Part 2, the maker,** reads only a complete profile and makes the deck pieces
  (the output profile). It has no rules and no defaults. The output profile is never edited. With the profile that today's rule gives, the output is the same as today.
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

## The proposal: the engine has two parts, and a person edits only the input profile

The 3D bridge has an **input profile** and an **output profile**. A person edits the input profile. Nobody edits the output profile. The engine has two parts, and the complete input profile is the only thing between them.

```text
the roads  +  an input profile that can be incomplete (down to an empty one)
        |
        v
  Part 1, the filler    finds the groups, chains and nodes. Keeps every value that the person gave.
        |               Fills every value that is missing, with the rules.
        v
  the complete input profile      it can be saved, read again, and edited again
        |
        v
  Part 2, the maker     no rules, no defaults. Makes the height along each chain and the deck pieces.
        |               A value that is missing is an error.
        v
  the output profile (the deck pieces)   ->   the page draws it
```

The design follows four rules:

1. **Every value of the input profile is optional.** A height, a width, a parameter, even the list of nodes. The least input is an empty profile. Then Part 1 makes everything from the roads and the rules.
2. **Part 1 never changes a value that the person gave.** It fills the values that are missing, and it marks each one it filled with `source: "rule"` and `method: "derived"`.
3. **Part 2 has no rules and no defaults.** If a height or a width is missing, it stops and says "fill the profile first". The same complete profile always makes the same output.
4. **Part 1 twice is the same as Part 1 once.** A complete profile goes through Part 1 with no change. This keeps the filled profile safe to save and edit.

This has three good results. The rules (the design rules of [the other note](bridge_height_design.md)) can change in Part 1 and nothing changes in Part 2. A complete profile from another source (a converter from urbanstyle, a measurement)
goes straight to Part 2. And the filled profile shows the person every number that the engine used.

### What is in the input profile

Everything is optional. The engine writes the rest.

| Part | Content | Needed from a person? |
|---|---|---|
| `parameters` | The design speed and the design grade | No. Defaults |
| A node | `lonlat` (its position, or its `id` in a complete profile), `kind` (`ground` or `junction`), the chains that meet there, `z_m` (its height), `source`, `method` | No. Only the `lonlat` and the `z_m` of a node that the person wants to set |
| A chain | `id`, `osm_ways`, `length_m`, `from`, `to`, `points`, `width_m` | No. Only `points` and `width_m` of a chain that the person wants to set |
| An interior control point | `s` (metres from the `from` end) and `z_m`. For a high point or a low point between two nodes | No |
| `source`, `method` | Where a value comes from. `method` is `mapped`, `measured`, `derived` or `chosen` | No |

The geometry of a chain is the geometry of the roads. It is not in the file. The width is not needed for a height: Part 1 fills it with the width that the engine draws, and a chain can set its own.

### The two parts

| | Part 1, the filler | Part 2, the maker |
|---|---|---|
| Reads | The roads, and an input profile that can be incomplete | A complete input profile, and the roads for the geometry |
| Writes | A complete input profile | The deck pieces (the output profile) |
| Does | Finds the groups, chains and nodes. Matches the given nodes to the found nodes. Fills the heights, the widths and the parameters that are missing. Checks the given values | Makes the profile of each chain: a straight grade between control points, with a vertical curve at each interior point. Cuts the chain into pieces. Writes the lift, the place and the width of each piece |
| Does not | Make a piece | Fill a value. Use a rule. Look at the road class |
| Errors | A given node that is not one node of the group. Two entries for one node. A height below 0. A given chain that has no road | A missing height or width. A control point outside its chain |

### An example: the Granville Bridge

The least useful input for the Granville Bridge is **5 junction heights**, each with the position of its node (`docs/img/bridge-height/granville_input_partial.json`, 14 lines):

```json
{
 "parameters": {"design_speed_kmh": 50, "design_grade": 0.06},
 "groups": [
  {
   "nodes": [
    {"lonlat": [-123.13097, 49.27397], "z_m": 11.0, "source": "example", "method": "chosen"},
    {"lonlat": [-123.1363, 49.27045], "z_m": 21.8, "source": "example", "method": "chosen"},
    {"lonlat": [-123.13785, 49.26922], "z_m": 11.1, "source": "example", "method": "chosen"},
    {"lonlat": [-123.13945, 49.26856], "z_m": 13.7, "source": "example", "method": "chosen"},
    {"lonlat": [-123.13834, 49.26843], "z_m": 5.3, "source": "example", "method": "chosen"}
   ]
  }
 ]
}
```

Part 1 turns it into the complete input profile (`granville_input_profile.json`, 38 lines, made by `granville_input_profile.py`). It finds the 13 nodes and the 12 chains, adds the 8 nodes on the ground (height 0, from
the data), keeps the 5 given heights as they are, and fills the width of each chain. This is a junction, a node on the ground and a chain of the complete profile:

```json
{"id": "n4", "lonlat": [-123.13097, 49.27397], "kind": "junction", "chains": ["c1", "c5", "c6", "c8"], "z_m": 11.0, "source": "example", "method": "chosen"}
{"id": "n1", "lonlat": [-123.12952, 49.27624], "kind": "ground", "chains": ["c6"], "z_m": 0.0, "source": "data", "method": "mapped"}
{"id": "c1", "osm_ways": [1419040127, 1419040128], "length_m": 550.4, "from": "n5", "to": "n4", "points": [], "width_m": 5.2, "width_source": "rule"}
```

Part 2 reads the complete profile and makes the height along each of the 12 chains: a straight grade between the heights of its two nodes. The steepest slope is 6 %, the design grade (the prototype `make`).

The prototype is in Python and is not the engine. Its rule for a missing junction height is a stand-in: the highest height that the design grade allows (`g` × the distance to the ground, not above 22 m). Without the height of
J1 in the input, Part 1 fills 11.0 m and marks it `derived`. The real rule is in [the design note](bridge_height_design.md).

### What Part 1 does with a value that is missing

| Value | Filled with |
|---|---|
| The groups, chains and nodes | The roads. A node is where a chain ends. A node where one chain ends is a free end on the ground |
| `z_m` of a node on the ground | 0 (`source: data`) |
| `z_m` of a junction | The rule: the lowest height that the clearances need and the design grade allows. The given heights are fixed points of the rule. Until the rule is built: the height that today's rule gives |
| `width_m` of a chain | The width that the engine draws, from the road class and the lanes |
| `parameters` | 50 km/h and 5 % (the defaults of [the design note](bridge_height_design.md)) |

A given height is fixed. If the given heights break the grade limit (two junctions too far apart in height for the length of the chain between them), Part 1 reports it. It does not change a given number.

### Where this is in the code today

Today's engine (`decks.rs`) does both parts in one function. The first part is `Bridges::new` (the groups and chains), `free_end_distances` and `deck_height` (the heights from the length), and `own_heights`
(`bridge_heights` and `bridge_height_col`). The second part is `chain_features` (the curve, the pieces and the width). What is new is the profile between them: today `chain_features` gets a group height and
a distance to the ground. In the new design it gets a complete chain with the height at its two nodes, its interior points and its width.

**The curve.** Part 2 today uses a smoothstep curve. The design rules use straight grades and parabolic vertical curves. The profile has a parameter `curve` for this: `smooth` (today) and `design`. The first build
uses `smooth`, so that a page with no input profile gives the same pieces as today. The change to `design` is a change of the look of every 3D bridge, and a decision (below).

### How many control points

| | Count |
|---|---|
| Nodes on the ground | 8. Height 0 from the data. Nothing to give |
| Junctions | 5. One height for each |
| Interior control points | 0 or more. One for each high point or low point that a chain needs between its nodes |

The Granville Bridge needs 5 heights and no more, if each chain can be a straight grade. A chain that needs a crest (for example the main span, 550 m) needs one point more for the crest.

### Checks

Each part checks what it can see. The engine says what is wrong and does not change a number of the person.

| Part | Case | Result |
|---|---|---|
| 1 | A given node is not within 5 m of exactly one node of the group, or two entries are for one node | Error |
| 1 | A `z_m` below 0 | Error |
| 1 | The grade between two given heights is above the design grade | Warning. Above the maximum grade of the road class: error |
| 1 | A `ground` node with `z_m` above 0 | Allowed: a landing on fill. The page closes the end of the deck down to the ground |
| 2 | A height or a width is missing | Error: fill the profile first |
| 2 | The `s` of a point is outside the chain, or the points are not in order of `s` | Error |
| 2 | Two curves overlap (a short chain with a high design speed) | Warning. The curves are shortened and the message says so |
| 2 | A sag curve whose low point is on the bridge, or a flat top with no grade on a long bridge | Warning |
| 1 | Two decks cross and the upper deck is not high enough above the lower one | Warning (later: it needs the crossings from the level solver) |

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
- The Height box shows the `z_m` of the selected node or chain, with its `source` and `method`, and can change it in the open page. A change is a change of the input profile, and Part 2 makes the output again.
- `rsBridgeGroups()` lists the chains and the nodes.

### The order of the work

1. **Documentation first** (this note and [the design note](bridge_height_design.md)). The guide gets new pages when the code exists.
2. **Part 2, the maker.** It reads a complete input profile and makes the pieces. With the profile that today's rule gives and the curve `smooth`, it makes the same pieces as today (the goldens do not change).
3. **Part 1, the filler.** It finds the groups, chains and nodes, matches the given nodes, and fills the values. `rs.bridge_profile(edges, given=None)` returns the complete input profile. The keyword `bridge_profile=` (a
   dictionary or a JSON file) gives the input. Tests: an empty input; the 5 Granville heights; a given value is kept; **Part 1 twice is Part 1 once**; every error of the table; the Granville file has 13 nodes and 12 chains.
4. The page: the landing on fill, the Height box, `rsBridgeGroups()`.
5. A converter from an urbanstyle profile to a complete input profile, outside the engine. It matches the axes to the chains by the OSM ways (12 of 12 on the Granville Bridge).
6. The default heights from the design rules (the other note), and the curve `design`.

### Decisions that are open

Each decision has the recommendation of this note.

1. **Two parts, one complete profile between them.** Yes.
2. **Control points.** The heights of the nodes, and interior points `(s, z)`. A height line with curves is not an input: the curves are calculated.
3. **Naming a node.** By its position in a partial input, and by its id in a complete profile. The engine writes the complete profile, so a person does not need to find the nodes.
4. **A new keyword.** `bridge_profile=` replaces `bridge_heights` and `bridge_height_col` in the end. The two stay while the engine has no input profile.
5. **The curve.** `smooth` first, then `design`. The change of the default to `design` changes the look of every bridge.
6. **The Height box in the open page.** It changes the input profile, and the output is made again. The ramps are then new too (today they keep the first length).
7. **The landing on fill.** The page draws the sides down to the ground.
8. **The urbanstyle converter.** Yes, outside the engine.
9. **Where the file is kept.** "One rule for every path" says the page, the tiles and the editor must read the same data. A profile that belongs to the area could be kept with the area, in duckOSM. This is for later.

### Regenerate the figures and the tables

```bash
python docs/img/bridge-height/granville_vs_lidar.py       # the comparison, and its table
python docs/img/bridge-height/granville_proposed.py       # the prototype of the shapes, and its table
python docs/img/bridge-height/granville_input_profile.py  # the least input, the complete input profile, and Part 2
```
