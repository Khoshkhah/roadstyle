# How the height of a 3D bridge is calculated

With `view_3d=True`, roadstyle draws each bridge as a raised deck. The deck rises from the ground along a ramp, stays at one height, and comes down again.
Two programs make this picture, one after the other. This page explains what each program does. To switch the bridges on or off, read [Bridges in 3D](style.md#bridges-in-3d).

## Two parts: the engine makes the profile, the page draws it

1. **The engine** (Rust, `decks.rs`) runs when you make the page. It finds the bridges, joins them into groups, and calculates the profile of each group.
   The profile is a list of deck pieces in the style source `decks`. The engine does not draw.
2. **The page** (`bridgemesh.js`) runs in the browser. It reads the profile, adds the height of the ground, and draws the pieces as one mesh.
   The page does not find groups and does not calculate group heights.

The profile of a group is the values that each deck piece carries.

| Property of a piece | Meaning |
|---|---|
| `__rs_group` | The number of the group |
| `__rs_chain` | The number of the chain (a line of bridge roads, see step 2) |
| `__rs_full` | The group height H, in metres |
| `__rs_lift0`, `__rs_lift1` | The lift at the start and at the end of the piece, from 0 (ground) to 1 (H) |
| `__rs_s0`, `__rs_s1` | Where the piece starts and ends along its chain, from 0 to 1 |
| `__rs_thick` | The thickness of the deck, in metres |
| `__rs_enda`, `__rs_endb` | The two end nodes of the chain (on its first and its last piece) |
| `__rs_edges` | The roads of the piece |

A piece also has its outline on the map. `__rs_base` and `__rs_height` are the underside and the top of the piece at its middle, without terrain. The page uses them for clicks.
The names with `__rs_` are internal names of the engine. They can change.

## Part 1. The engine calculates the profile

The engine works in five steps. Each step uses the result of the step before it.

### 1. Find the 3D bridges

A road is a 3D bridge when two conditions are true. Its `bridge` value is `yes`, and its level (`lvl`) is 1 or more. A bridge at level 0 or less stays a flat line.

A two-way road is one bridge road. The engine draws it as two half-width ribbons, one for each direction.

### 2. Join the bridges into groups

Bridge roads that share a node are one group. The level of the roads does not matter. A group has one height, so two roads of one group have the same height at the node where they meet.

Inside a group, the engine joins roads into chains. A chain is a line of bridge roads through nodes where only two bridge roads meet. The engine makes one deck for a chain, with no seam.
A node where three or more bridge roads meet is the end of a chain.

A free end is a node where only one bridge road ends. The deck meets the ground at a free end.

### 3. Give each group a height

The group height, H, is the height of the deck above the ground on its flat part. The engine finds H in one of two ways.

**From the length of the group.** This is the default. The length of a group is the sum of the lengths of its roads. A two-way pair counts one time. A long bridge crosses something wide, so it stands higher.

- Up to 60 m (`grow_from_m`), H is 5 m (`base_m`).
- From 600 m (`grow_to_m`), H is 22 m (`max_m`).
- Between 60 m and 600 m, H grows on a straight line: H = 5 + 17 × (length − 60) ÷ 540.

| Length of the group | H |
|---|---|
| 60 m or less | 5 m |
| 120 m | 6.9 m |
| 330 m | 13.5 m |
| 600 m or more | 22 m |

**From your own value.** Give `bridge_heights` or `bridge_height_col`. The engine uses your value for the whole group in place of the length rule.
Two different values in one group are an error. For the keywords, read [Every parameter](../reference/parameters.md).

### 4. Find the height at each node

The height at a node is a lift from 0 to 1. Lift 0 is the ground. Lift 1 is H.

1. Find the grade: `ramp_m` ÷ `base_m`. With the default look, the grade is 40 ÷ 5 = 8. The deck needs 8 m of ramp for each 1 m of height.
2. Find the full ramp: H × the grade, but at least 1 m. A group of 5 m has a full ramp of 40 m. A group of 13.5 m has 108 m. A group of 22 m has 176 m.
3. For each node, find the distance along the roads to the nearest free end of its group.
4. Divide that distance by the full ramp. The result is the lift at the node, but not more than 1.

The lift belongs to the node and not to the road. For this reason, two chains that meet at a node have the same height there.
A node with no free end in its group, for example in a closed loop, has lift 1.

If the distance from a free end to the middle of a bridge is shorter than the full ramp, the deck does not reach H. A bridge of 40 m has H = 5 m and a full ramp of 40 m.
Its deck rises only 1.8 m at the middle. A short bridge has a low, round hump and no wall.

### 5. Calculate the curve between the nodes, and cut it into pieces

Inside a chain, the engine finds the lift at each distance d along the chain.

1. Start from each end node. Take the lift of the node and add the distance from that end divided by the full ramp.
2. Take the smaller of the two values. The deck rises from each end and stops at 1.
3. Round the place where the two values meet. Where they are within 0.4 of each other, the smaller value drops by up to 0.1. This is a smooth minimum.
   A short bridge gets a round top and no ridge. The rounding fades out over the last 15 % of the chain at each end, so the lift at a node is exact.
4. Keep the result from 0 to 1.
5. Smooth the result with t × t × (3 − 2t). Each ramp gets a soft start on the ground and a soft end at the flat part.

The underside of the deck is H × the lift. The top is `thickness_m` (1 m) above the underside.

The engine then cuts the chain into pieces. On a ramp, a piece is at most `step_m` (2.5 m) long. A piece also ends where one road changes to the next.
For each piece, the engine writes the lift at its start and at its end (`__rs_lift0`, `__rs_lift1`). These pieces are the profile.

![The profile of a straight bridge for four lengths](../img/bridge-height/profile.png)

The figure shows the profile of one straight bridge for four lengths. The engine made it with the default look. The orange band is the deck, which is 1 m thick.
The dashed line is H. Make the figure again with `python docs/img/bridge-height/make.py`.

## Part 2. The page draws the profile

The page reads the pieces from the source `decks`. It does not calculate the lift of a piece again.

### 6. Put the deck on the terrain

Without terrain, the ground height is 0, and the underside is H × the lift. When the 3D terrain is on, the page changes this in four ways.

- The page reads the ground height at the two end nodes of each chain (`__rs_enda`, `__rs_endb`) from the terrain tiles of the page.
- The deck is level between those two ground heights. The underside is that level line plus H × the lift.
- Close to the ground, the deck follows the ground under each side of its width, because a hill can slope sideways.
  As the lift rises, the height changes from the ground to the level line.
- A small gap keeps the start of a ramp above the terrain that the map draws. The gap is 0.3 m plus 2.5 m for each 1 m of slope. It fades out as the deck rises.

If a terrain tile has not arrived, the page does not draw the chains that need it. It draws them when the tile arrives.

### How the page draws a piece

For each piece, the page makes triangles: a top that slopes from the start lift to the end lift, two side walls and a bottom. It draws all pieces in one custom layer, as one smooth mesh.
The casing is a thin slab along each long side of the deck.

The extrusion layers of the decks stay in the map with opacity 0. A click or a hover finds the bridge on them. The Street View marker stands on the deck.

## What the height is not

The height is a rule for the picture and not a measurement. The engine does not read a `height` or `maxheight` tag to find H.
Two bridges of the same length get the same H.

To draw a measured height, use `bridge_heights` or `bridge_height_col`. `rsSetBridgeHeight(road, metres)` changes H in the open page.
The page keeps the lifts of the pieces, so the ramps keep the length that they had with the first height.

## Settings that change the height

Set these in the `bridge_decks` setting, for example `settings={"config": {"bridge_decks": {"ramp_m": 80}}}`. A longer `ramp_m` makes every ramp longer.
For an 800 m bridge, `ramp_m: 80` moves the start of the flat part from 176 m to 352 m.

| Key | Default | What it changes |
|---|---|---|
| `base_m` | 5 | H of a short group, and the base of the grade |
| `max_m` | 22 | H of a long group |
| `grow_from_m` | 60 | The length up to which H is `base_m` |
| `grow_to_m` | 600 | The length from which H is `max_m` |
| `ramp_m` | 40 | Metres of ramp for `base_m` of height. The grade is `ramp_m` ÷ `base_m` |
| `step_m` | 2.5 | The longest piece on a ramp |
| `thickness_m` | 1 | The thickness of the deck |

Other `bridge_decks` keys change the picture and not the height: `width_scale`, `match_zoom`, `flat_below`, `casing_px` and `opacity`.
Read [Every parameter](../reference/parameters.md) for all of them.
