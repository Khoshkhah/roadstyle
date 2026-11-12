# Party walls of different heights

Date: 2026-11-10. Status: proposal, not built.

## Summary

The dashboard module `walls.js` draws each wall as one strip from the base to the roof, in the color of its type. A tower that stands on a
podium has party walls that are shared with the podium. The tower shows `party` (purple) from the ground to its roof, but the podium covers
only the lowest part. This note makes `walls.js` draw two strips for such a wall: `party` up to the shared height, and the type of the open
wall above it.

The fault and the data are in duckOSM, `docs/concepts/building-walls.md`, section "Proposal: party walls of different heights". On Burnaby,
a tower of 123 m with a podium of 9 m shows 120 m of purple wall.

## The change

### The input of `rsSetWalls`

A wall (a LineString) gets two optional properties. A roof (a Polygon) gets one.

| Feature | Property | Meaning |
|---|---|---|
| wall | `open` | the type of the wall if no building stood beside it (duckOSM's `building_faces.open_type`) |
| wall | `with` | an array of the ids of the buildings that share the wall |
| wall | `building` | the id of the building of the wall |
| roof | `id` | the id of the building (the same space as `building` and `with`) |

A wall with no `open` or no `with` is drawn as now.

### The draw

For a wall of type `party` with `open` and `with`:

1. `shared` is the lowest height of the buildings in `with`. A building that has no roof in the data has no height, and it is left out. If none
   is left, the wall is drawn as now.
2. `shared` is limited to the height of the building of the wall and to its base: `base <= shared <= height`.
3. If `height - shared` is less than 1 m (`SPLIT_MIN_M`), the wall is one `party` strip, as now.
4. Else the wall is two strips of the same footprint: `party` from `base` to `shared`, and the type `open` from `shared` to `height + ROOF_M`.

The strip of the open type is the part of the wall that nothing stands beside. If `open` is itself `party` (the build found no other type),
the wall stays one strip.

### Why in `walls.js`

The heights come from the look (`buildingHeights(look, rows)`), and the page gets new heights each time that a person changes `m_per_level`.
The module already has the roofs with their heights, so it can find the shared height with no new data path. Every page that calls
`rsSetWalls` gets the rule, and no page has its own copy.

### The page

duckOSM Studio, `www/app/duck.js`, `wallsData`, adds `id` to each roof, and `building`, `with` and `open` to each wall. It finds `with` from
the rows of `main.building_faces` that have the same two nodes and another `building_id`. Studio changes by one query and three properties, and
by the move of the pins.

## What stays

The tiles, the roof slab, the style (`rsSetWallStyle`), and the walls of a page that does not send the new properties.

## Test

- A unit test of the split with a tower of 123 m, a podium of 9 m, and a free wall: two strips, the heights and the colors.
- The cases: `shared` over the height, `shared` under the base, a missing neighbour, a difference under 1 m, `open` equal to `party`.
- The Burnaby page: the tower at Willingdon Avenue shows purple up to the podium, and its own color above.
