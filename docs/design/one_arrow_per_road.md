# One arrow per road in the window

**Status:** built (branch `arrows`), waiting for Kaveh's review. Asked for 2026-10-06: "a road in the window should not have more than one
arrow"; the arrows crowded zoom 15.

## Before

Every road chain (same name, class, level and direction, walked through simple junctions) is cut into 100 m slots; the one-way arrows were
repeated along **every** slot (`symbol-placement: line`, spacing 200 px at zoom 15). At zoom 15, 100 m is about 20 px, so a long road
carried many arrows. An older version put one arrow per chain (`line-center`), but that arrow was often outside the window.

## Now

The page places the arrows (`_rsArrows`, after every move and once the slots are loaded):

- every one-way chain that is in the window gets **one** arrow, in the middle of the part of it inside the window, rotated along the road;
- the arrow **stays** where it is while it is still in the window: re-centring after each pan made it slide along the road; only a chain
  whose arrow left the window, or a newly visible chain, gets a new place;
- none below zoom 15 (as before); the minor classes from zoom 16 (as before).
- thinned (Kaveh, after trying it: "still too many"): below zoom 17 only the main classes (motorway, trunk, primary, secondary, tertiary
  and their links); a road whose visible part is shorter than 100 px gets none; arrows stay at least 150 px apart on screen, an arrow
  already shown keeping its place first (no jumps while panning), then the higher class (`rank`, the class order on each slot piece),
  then the longer road. The numbers are `_RS_ARROW` in the page.

Each slot piece carries `chain` (its chain's number). The arrow is a point in the `arrows` source with the properties of the piece it lies on,
so the arrow layers keep their filters (one-way, position, class, minzoom), and `rsFilter`, the class filter and the bridge / tunnel toggles
treat it as before. `icon-allow-overlap`: a road's only arrow is not dropped by a label's collision box.

## Limits

- A map from a tile archive (`tiles=True`) has no slot geometry in the page: it keeps the arrows repeated along the slots.
- A street whose chain is split (a class, level or name change in the middle) is two roads: two arrows.
