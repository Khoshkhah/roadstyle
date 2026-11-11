# The bridge profile: input and output (planned)

**Status: Part 1 and Part 2 are built, with the curve `smooth`.** The filler (Part 1) completes an input that has values missing, and the maker (Part 2) makes the 3D deck pieces from the complete profile: see
[What works today](#what-works-today). Interior control points, the curve `design` and the design-rule heights are planned. The format is fixed, and the sample files are
real: scripts make them from the real roads of the Granville Bridge in Vancouver, and tests check them.

## The idea

A 3D bridge has an **input profile** and an **output profile**. You edit the input profile. The output profile (the deck pieces that the page draws) is made from it, and nobody edits it.

The engine has two parts:

1. **Part 1, the filler.** It reads the roads and an input profile that can be incomplete. It finds the groups of bridges, their chains and their nodes. It keeps every value that you gave. It fills every value that is
   missing with the rules, and marks it `derived`. It writes a **complete input profile**.
2. **Part 2, the maker.** It reads a complete input profile. It has no rules and no defaults: if a value is missing, it stops. It makes the height along each chain and the deck pieces.

Every value of the input profile is optional: a height, a width, a parameter, even the list of nodes. The least input is an empty profile. If you run Part 1 on a complete profile, nothing changes.

## What works today

Both parts are built. You can get the complete profile of a page, change a number, and give it back. You can also give only the numbers you want to set, and the filler adds the rest:

```python
import roadstyle as rs

profile = rs.bridge_profile(edges)                      # the complete profile that the engine writes for these roads
junction = next(n for g in profile["groups"] for n in g["nodes"] if n["kind"] == "junction")
junction["z_m"] = 9.0                                   # the height of one node, in metres
rs.render_dashboard(edges, view_3d=True, bridge_profile=profile).save("map.html")
```

- `bridge_profile=` takes a dictionary or the path of a JSON file. `rs.bridge_profile(edges, given)` returns the complete profile of an input `given`.
- **The input can be incomplete.** Every value is optional, down to `{}`. An empty input gives the profile of today. A page with no `bridge_profile=` has the empty input: every page goes through the filler, and the default input is `{}`. The filler keeps every value that you give and fills the others with the rules of today: the height of a junction from the length of its group, 0 for a node on the ground, the `top_m` of a chain, the parameters (50 km/h, a grade of 1 in 8, the curve `smooth`). A value that it adds has `source: "rule"` and `method: "derived"` (a junction), or `source: "data"` and `method: "mapped"` (a node on the ground).
- **Name a node by its position or its id.** An entry with a `lonlat` is for the one node of the roads within 5 m of it. If more than one node is within 5 m, give the `id` of the node. A chain entry needs its `id` (`c1`, `c2`...), which is in the complete profile.
- **The filler twice is the filler once.** A complete profile goes through the filler with no change, so you can save a filled profile and edit it.
- **A height without a source gets** `source: "given"` and `method: "chosen"`. If you give a `source` and a `method`, the filler keeps them. If you remove a `z_m`, the filler fills it again, with its `source` and `method`.
- **A node above the rule's top raises the top of its chains.** A `top_m` that you give is kept, and a node above it is an error.
- **A warning, not an error:** a chain whose average grade between a height of yours and the other end is above the `design_grade` (the filler never changes your number).
- With the profile that `rs.bridge_profile(edges)` gives, the page is the same as without it. A page that is given a profile writes the same profile again.
- **You can change** the `z_m` of a node, the `top_m` of a chain (its full height), and the `width_m` of a chain. A node is higher than the `top_m` of a chain that ends there: that is an error.
- **Not built, and the engine says so with an error:** interior control points (`points`), and the curve `design`.
- **Not built:** the colored view of what you gave and what the engine added is made by the prototype (`granville_input_profile.py`). The engine does not return the paths of your values yet.
- The chains are `c1`, `c2`... in the order of the engine, and a profile is for the roads that it was made from. A profile for other roads is an error (a chain or a node that these roads do not have, a chain of another length, a node more than 5 m from the place that the profile gives).
- **Sample:** [`granville_bridge_profile_today.json`](../samples/bridge-profile/granville_bridge_profile_today.json) is the profile that the engine writes for the roads of the Granville Bridge. It has 13 nodes (8 on the ground
  and 5 junctions, at 22 m, 22 m, 22 m, 22 m and 11.2 m) and 12 chains, all with the full height of 22 m.

**The 5 heights of Granville work today.** The filler reads [`granville_input_partial.json`](../samples/bridge-profile/granville_input_partial.json) (the next section), finds the 13 nodes and the 12 chains, keeps the 5 heights and fills the rest, and the maker draws it. The engine warns that chain c3 rises 5.8 m in 96 m, a grade of 0.061, above the design grade of 0.06. The complete profile below and the straight grades of the design are the planned design: the filler fills the 12 `top_m` with 22 m (the rule of today), and the curve is `smooth`, not `design`.

## The least input: 5 heights

A group of bridges has **nodes**: the ends of its chains of roads. A node where only one road ends is on the ground, and its height is 0. The data gives it. A node where chains meet is a **junction**, and it needs one height.
The Granville Bridge has 13 nodes: 8 on the ground and 5 junctions. So the least useful input is **5 heights**, each with the position of its node
([`granville_input_partial.json`](../samples/bridge-profile/granville_input_partial.json), 0.6 KB):

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

These 5 heights are an example. Each junction is at the highest height that a design grade of 6 % allows. A person must choose them from what each junction has to clear.

## The complete input profile

Part 1 turns the 5 heights into the complete profile
([`granville_input_profile.json`](../samples/bridge-profile/granville_input_profile.json), 3.9 KB): 13 nodes and 12 chains. It adds the 8 nodes on the ground (height 0, `source: data`),
keeps your 5 heights as you gave them, gives each node an id, and fills the width of each chain with the width that the engine draws. The colors show **what is yours and what is added**: your values
(profile 1) are bold blue, and the values that the engine added (profile 2) are orange. A bold value is also the one with a tooltip.

<span class="rs-bp-key"><span class="given">Given in your input (profile 1)</span> &nbsp; <span class="added">Added by the engine (profile 2)</span></span>

<pre class="rs-bp"><code>{
 <span class="added">"format": "roadstyle.bridge_profile/1"</span>,
 "parameters": {<span class="given" title="given in your input">"design_speed_kmh": 50</span>, <span class="given" title="given in your input">"design_grade": 0.06</span>},
 "groups": [
  {
   <span class="added">"name": "Granville Bridge"</span>,
   "nodes": [
    {<span class="added">"id": "n1"</span>, <span class="added">"lonlat": [-123.12952, 49.27624]</span>, <span class="added">"kind": "ground"</span>, <span class="added">"chains": ["c6"]</span>, <span class="added">"z_m": 0.0</span>, <span class="added">"source": "data"</span>, <span class="added">"method": "mapped"</span>},
    {<span class="added">"id": "n2"</span>, <span class="added">"lonlat": [-123.1292, 49.27515]</span>, <span class="added">"kind": "ground"</span>, <span class="added">"chains": ["c8"]</span>, <span class="added">"z_m": 0.0</span>, <span class="added">"source": "data"</span>, <span class="added">"method": "mapped"</span>},
    {<span class="added">"id": "n3"</span>, <span class="added">"lonlat": [-123.12744, 49.27507]</span>, <span class="added">"kind": "ground"</span>, <span class="added">"chains": ["c5"]</span>, <span class="added">"z_m": 0.0</span>, <span class="added">"source": "data"</span>, <span class="added">"method": "mapped"</span>},
    {<span class="added">"id": "n4"</span>, <span class="given" title="given in your input">"lonlat": [-123.13097, 49.27397]</span>, <span class="added">"kind": "junction"</span>, <span class="added">"chains": ["c1", "c5", "c6", "c8"]</span>, <span class="given" title="given in your input">"z_m": 11.0</span>, <span class="given" title="given in your input">"source": "example"</span>, <span class="given" title="given in your input">"method": "chosen"</span>},
    {<span class="added">"id": "n5"</span>, <span class="given" title="given in your input">"lonlat": [-123.1363, 49.27045]</span>, <span class="added">"kind": "junction"</span>, <span class="added">"chains": ["c1", "c4", "c9"]</span>, <span class="given" title="given in your input">"z_m": 21.8</span>, <span class="given" title="given in your input">"source": "example"</span>, <span class="given" title="given in your input">"method": "chosen"</span>},
    {<span class="added">"id": "n6"</span>, <span class="given" title="given in your input">"lonlat": [-123.13785, 49.26922]</span>, <span class="added">"kind": "junction"</span>, <span class="added">"chains": ["c3", "c9", "c10"]</span>, <span class="given" title="given in your input">"z_m": 11.1</span>, <span class="given" title="given in your input">"source": "example"</span>, <span class="given" title="given in your input">"method": "chosen"</span>},
    {<span class="added">"id": "n7"</span>, <span class="given" title="given in your input">"lonlat": [-123.13945, 49.26856]</span>, <span class="added">"kind": "junction"</span>, <span class="added">"chains": ["c2", "c4", "c7"]</span>, <span class="given" title="given in your input">"z_m": 13.7</span>, <span class="given" title="given in your input">"source": "example"</span>, <span class="given" title="given in your input">"method": "chosen"</span>},
    {<span class="added">"id": "n8"</span>, <span class="given" title="given in your input">"lonlat": [-123.13834, 49.26843]</span>, <span class="added">"kind": "junction"</span>, <span class="added">"chains": ["c10", "c11", "c12"]</span>, <span class="given" title="given in your input">"z_m": 5.3</span>, <span class="given" title="given in your input">"source": "example"</span>, <span class="given" title="given in your input">"method": "chosen"</span>},
    {<span class="added">"id": "n9"</span>, <span class="added">"lonlat": [-123.14242, 49.26811]</span>, <span class="added">"kind": "ground"</span>, <span class="added">"chains": ["c7"]</span>, <span class="added">"z_m": 0.0</span>, <span class="added">"source": "data"</span>, <span class="added">"method": "mapped"</span>},
    {<span class="added">"id": "n10"</span>, <span class="added">"lonlat": [-123.13848, 49.26764]</span>, <span class="added">"kind": "ground"</span>, <span class="added">"chains": ["c11"]</span>, <span class="added">"z_m": 0.0</span>, <span class="added">"source": "data"</span>, <span class="added">"method": "mapped"</span>},
    {<span class="added">"id": "n11"</span>, <span class="added">"lonlat": [-123.13835, 49.26764]</span>, <span class="added">"kind": "ground"</span>, <span class="added">"chains": ["c12"]</span>, <span class="added">"z_m": 0.0</span>, <span class="added">"source": "data"</span>, <span class="added">"method": "mapped"</span>},
    {<span class="added">"id": "n12"</span>, <span class="added">"lonlat": [-123.13592, 49.26645]</span>, <span class="added">"kind": "ground"</span>, <span class="added">"chains": ["c3"]</span>, <span class="added">"z_m": 0.0</span>, <span class="added">"source": "data"</span>, <span class="added">"method": "mapped"</span>},
    {<span class="added">"id": "n13"</span>, <span class="added">"lonlat": [-123.14096, 49.26513]</span>, <span class="added">"kind": "ground"</span>, <span class="added">"chains": ["c2"]</span>, <span class="added">"z_m": 0.0</span>, <span class="added">"source": "data"</span>, <span class="added">"method": "mapped"</span>}
   ],
   "chains": [
    {<span class="added">"id": "c1"</span>, <span class="added">"osm_ways": [1419040127, 1419040128]</span>, <span class="added">"length_m": 550.4</span>, <span class="added">"from": "n5"</span>, <span class="added">"to": "n4"</span>, <span class="added">"points": []</span>, <span class="added">"width_m": 5.2</span>, <span class="added">"width_source": "rule"</span>},
    {<span class="added">"id": "c2"</span>, <span class="added">"osm_ways": [35354210]</span>, <span class="added">"length_m": 404.2</span>, <span class="added">"from": "n7"</span>, <span class="added">"to": "n13"</span>, <span class="added">"points": []</span>, <span class="added">"width_m": 3.0</span>, <span class="added">"width_source": "rule"</span>},
    {<span class="added">"id": "c3"</span>, <span class="added">"osm_ways": [37226820, 304881410, 1419040130, 1419040131]</span>, <span class="added">"length_m": 367.1</span>, <span class="added">"from": "n12"</span>, <span class="added">"to": "n6"</span>, <span class="added">"points": []</span>, <span class="added">"width_m": 3.1</span>, <span class="added">"width_source": "rule"</span>},
    {<span class="added">"id": "c4"</span>, <span class="added">"osm_ways": [992936499, 1419040134, 1419040135, 1419040136]</span>, <span class="added">"length_m": 311.8</span>, <span class="added">"from": "n5"</span>, <span class="added">"to": "n7"</span>, <span class="added">"points": []</span>, <span class="added">"width_m": 3.0</span>, <span class="added">"width_source": "rule"</span>},
    {<span class="added">"id": "c5"</span>, <span class="added">"osm_ways": [24530078, 341691672]</span>, <span class="added">"length_m": 286.4</span>, <span class="added">"from": "n4"</span>, <span class="added">"to": "n3"</span>, <span class="added">"points": []</span>, <span class="added">"width_m": 5.2</span>, <span class="added">"width_source": "rule"</span>},
    {<span class="added">"id": "c6"</span>, <span class="added">"osm_ways": [26440580, 341691648, 1419312044]</span>, <span class="added">"length_m": 276.5</span>, <span class="added">"from": "n1"</span>, <span class="added">"to": "n4"</span>, <span class="added">"points": []</span>, <span class="added">"width_m": 5.1</span>, <span class="added">"width_source": "rule"</span>},
    {<span class="added">"id": "c7"</span>, <span class="added">"osm_ways": [35354235]</span>, <span class="added">"length_m": 228.0</span>, <span class="added">"from": "n7"</span>, <span class="added">"to": "n9"</span>, <span class="added">"points": []</span>, <span class="added">"width_m": 2.9</span>, <span class="added">"width_source": "rule"</span>},
    {<span class="added">"id": "c8"</span>, <span class="added">"osm_ways": [1316244490, 1316244492]</span>, <span class="added">"length_m": 183.9</span>, <span class="added">"from": "n4"</span>, <span class="added">"to": "n2"</span>, <span class="added">"points": []</span>, <span class="added">"width_m": 4.0</span>, <span class="added">"width_source": "rule"</span>},
    {<span class="added">"id": "c9"</span>, <span class="added">"osm_ways": [1419040129, 1419040137]</span>, <span class="added">"length_m": 178.6</span>, <span class="added">"from": "n6"</span>, <span class="added">"to": "n5"</span>, <span class="added">"points": []</span>, <span class="added">"width_m": 5.1</span>, <span class="added">"width_source": "rule"</span>},
    {<span class="added">"id": "c10"</span>, <span class="added">"osm_ways": [1419040132, 1419040133, 1419040138]</span>, <span class="added">"length_m": 95.8</span>, <span class="added">"from": "n8"</span>, <span class="added">"to": "n6"</span>, <span class="added">"points": []</span>, <span class="added">"width_m": 5.1</span>, <span class="added">"width_source": "rule"</span>},
    {<span class="added">"id": "c11"</span>, <span class="added">"osm_ways": [336795552]</span>, <span class="added">"length_m": 89.1</span>, <span class="added">"from": "n8"</span>, <span class="added">"to": "n10"</span>, <span class="added">"points": []</span>, <span class="added">"width_m": 5.2</span>, <span class="added">"width_source": "rule"</span>},
    {<span class="added">"id": "c12"</span>, <span class="added">"osm_ways": [256879265, 1285848467]</span>, <span class="added">"length_m": 88.9</span>, <span class="added">"from": "n11"</span>, <span class="added">"to": "n8"</span>, <span class="added">"points": []</span>, <span class="added">"width_m": 5.1</span>, <span class="added">"width_source": "rule"</span>}
   ]
  }
 ]
}</code></pre>

| Key | Meaning |
|---|---|
| `parameters` | The design speed (km/h) and the design grade (0.06 is 6 %). Part 2 uses them for the vertical curves |
| A node: `id`, `lonlat`, `kind` | The node, its position, and `ground` or `junction` |
| A node: `chains` | The chains that meet at the node. A junction has two or more |
| A node: `z_m` | The height of the node above the ground, in metres |
| A chain: `osm_ways`, `length_m` | The OSM ways of the chain, and its length |
| A chain: `from`, `to` | The nodes at its first end and its last end |
| A chain: `points` | Interior control points `{"s": metres from the first end, "z_m": height}`, for a crest or a sag between the two nodes. Empty here |
| A chain: `width_m`, `width_source` | The width of the deck in metres, and where it comes from |
| `source`, `method` | Where a value comes from. `method` is `mapped`, `measured`, `derived` or `chosen` |

Between two nodes, a chain is a straight grade from the height at one end to the height at the other, with a vertical curve at each interior point. A chain that needs a crest in the middle, for example the main
span of 550 m, needs one interior point for it.

## If you update the input file

Open the complete profile and look at the colors. **Bold blue** is what you gave: change it as you wish, and it stays as you wrote it. **Orange** is what the engine added: you can write any orange value into your
input to set it yourself. After that it is blue, because it is yours now. A value that you leave out is filled again, and it is orange again. Part 1 never changes a blue value.

## What you can leave out

| Leave out | Part 1 fills it with |
|---|---|
| The whole profile | Everything, from the roads and the rules |
| The height of a node on the ground | 0 |
| The height of a junction | The rule: the lowest height that the clearances need and the design grade allows. Until the rule is built: the height that today's rule gives |
| The width of a chain | The width that the engine draws, from the road class and the lanes |
| The parameters | 50 km/h and 5 % |
| `source` and `method` | `given` and `chosen` for your values, `rule` and `derived` for the filled values |

## What the engine checks

The engine says what is wrong. It does not change a number that you gave.

- Part 1: a node that is not within 5 m of exactly one node of the group; two entries for one node; a height below 0; a grade between two given heights that is above the design grade.
- Part 2: a height or a width that is missing; an interior point outside its chain or out of order; two vertical curves that overlap.

## Sample files

All files are in `docs/samples/bridge-profile/` and are published with this site.

| File | What it is | Size |
|---|---|---|
| [`granville_bridge_profile_today.json`](../samples/bridge-profile/granville_bridge_profile_today.json) | The complete profile that the engine writes today for the same roads (`rs.bridge_profile`). The maker reads it and makes the same pieces | 3.3 KB |
| [`granville_input_partial.json`](../samples/bridge-profile/granville_input_partial.json) | The least input: 5 junction heights | 0.6 KB |
| [`granville_input_profile.json`](../samples/bridge-profile/granville_input_profile.json) | The complete input profile that Part 1 makes from it | 3.9 KB |
| [`granville_input_profile_colored.html`](../samples/bridge-profile/granville_input_profile_colored.html) | The same complete profile in one HTML page, with the values of the input and the values that the engine added in two colors. Open it in a browser | 10.9 KB |
| [`bridge_profile_input.schema.json`](../samples/bridge-profile/bridge_profile_input.schema.json) | The JSON Schema of the input profile: every value is optional | 4.9 KB |
| [`bridge_profile_complete.schema.json`](../samples/bridge-profile/bridge_profile_complete.schema.json) | The JSON Schema of the complete input profile | 5.0 KB |
| [`granville_bridge_edges.parquet`](../samples/bridge-profile/granville_bridge_edges.parquet) | The roads of the example: the 41 edges (27 OpenStreetMap ways) of the Granville Bridge and its ramps, from duckOSM's Vancouver database. OpenStreetMap data, ODbL | 16.6 KB |
| [`granville_lidar_samples.json`](../samples/bridge-profile/granville_lidar_samples.json) | The deck heights that the City of Vancouver LiDAR 2022 gives on the 12 axes of the same bridge, from urbanstyle's profile (Open Government Licence - Vancouver). It is for comparison only. The profile above does not use it | 7.7 KB |

The scripts that make them are in `docs/img/bridge-height/`. A prototype of the two parts, in Python, is `granville_input_profile.py` (`fill` is Part 1 and `make` is the planned design). It is not the engine. The engine's maker is in `rust/roadstyle-engine/src/decks.rs`.

```bash
python docs/img/bridge-height/granville_input_profile.py   # writes the two profiles
```

## Read more

The exact format, key by key, is in [Inputs and outputs](../reference/formats.md#the-bridge-profile-planned). The two JSON Schemas check the form of both files.

The design notes are in the repository, in `docs/design/`: `bridge_profile_edit.md` (the two parts, the checks, the comparison with urbanstyle) and `bridge_height_design.md` (the design rules for the heights: clearance,
grade and vertical curves, with their sources).
