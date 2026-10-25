# mapstyle's page scripts: what the shared dashboard takes over

The mapstyle merge (2026-10-23) moves a duckOSM map's page to roadstyle: the Rust stages make its style (`roadstyle.duckosm`), and
the page writer (R3) and the shared dashboard (`rust/roadstyle-assets/files/static/dashboard/`) make its page. mapstyle's `render_map` keeps its own
page until then. This note lists what mapstyle's two page scripts do, so that the dashboard can port each part. The line numbers are
of mapstyle at `ebd6b12` (`src/mapstyle/layers.js`, 292 lines; `src/mapstyle/dashboard.js`, 164 lines).

The rule for the port (audit R7): the dashboard finds a layer by its role in the style's metadata, not by a prefix of its id.

## What the Rust style has already

The Rust engine makes the base map's look in the style, for the export and for a page (`roadstyle-engine` `overlays::feature_overlays`
and `layers.rs`, from the look's `features`). The page does not need these parts of `layers.js` (lines 90 to 160):

- the colour and the outline by `kind`, the dashes, the widths by zoom, the zoom ranges;
- the textures (`ms-pat-<kind>`) and the icons (`ms-icon-<layer>`), in `roadstyle:images`;
- the 3D buildings: the layer `ov<i>-3d` (fill-extrusion, hidden), metadata `roadstyle:group: "buildings 3D"`, `roadstyle:over: true`;
  its overlay entry names it (`extrude`), and the dashboard reads that, because a page's layers have no metadata;
- each base-map layer's entry in `roadstyle:controls.overlays` (`label`, `source`, `layers`, `visible` from layers.yaml's `ticked`,
  `popup`, `tooltip`, `interactive`), and each layer's `roadstyle:group`;
- the rows of the roads you may not use in `roadstyle:controls.filter.access`: `[kind, colour, label, count]` (private, bus,
  pedestrian, delivery).

## What the dashboard must add

| Part | mapstyle | What it does | Its inputs | What the Rust style gives for it |
|---|---|---|---|---|
| `rsSetModes(list)`, `rsGetModes()` | layers.js 35 to 49 | Shows only the roads that one of the modes can use (`list`: some of driving, walking, cycling; null: all). One road filter with `rsSetAccess`. Sends `rs:filterchange` `{modes}`. | Each road's flags `driving`, `walking`, `cycling` (true or false). | The flags are columns of the road table (the duckOSM reader writes them); a page has the road table. Missing: the list of the modes of the map (which flags exist). |
| `rsSetAccess(kind, on)`, `rsGetAccess()`, `RS_ACCESS` | layers.js 50 to 56, 234 to 258 | Shows or hides the roads of one restriction (`access`: private, bus, pedestrian, delivery); a row with a colour swatch for each in the Roads box, after Bridges and Tunnels; `RS_ACCESS`: the count of each. A pedestrian street that cars may not use has its own row; the class row `pedestrian` goes away where no usable road has that class (docs/design/one_mode_map.md of mapstyle). | Each road's `access`. | `roadstyle:controls.filter.access` (kind, colour, label, count). |
| The colour of a restricted road | layers.js 58 to 89 | Its own colour as the base of each road fill, by edge id (not by the `access` property: tiles do not carry it), and again after each `rs:colorchange`; only the fill pieces (`__rs_k == 1`) of the road layer. | The edge ids of each kind; the colour of each kind. | The colours: as above. The engine can bake this colour into the fill itself (a design question for the engine, not the dashboard). |
| `rsSetBuildings3D(on)`, `rsGetBuildings3D()` | layers.js 160 to 194 | Shows or hides the 3D buildings; a button under the 2D/3D button, and a row "Buildings 3D" under the buildings row of the Layers box. Sends `ms:buildings3d` `{on}`. | The 3D layer. | The layer with `roadstyle:group: "buildings 3D"`. |
| `rsSetInteraction(label, {clickable, tooltip, popup})`, `rsGetInteraction(label)` | layers.js 194 to 221 | Each base-map layer: clickable (with its hover and select colour), its tooltip, its popup. A layer that is not clickable loses the hover/select `case` of its colour. Popup off: the popup of a click on that layer is closed at `rs:select`. Sends `rs:interactionchange`. | The start values of each layer: clickable is false for landcover, water, paved and the decoration lines (not raceway, other_ways); tooltip false; popup true (mapstyle's `feature_overlays`, map.py, the `interaction` of each layer). | `interactive`, `tooltip`, `popup` of each overlay entry. Missing: mapstyle's start value of clickable (today `interactive` is true when a popup is given). |
| `rsSetKinds(label, list)`, `rsGetKinds(label)`, `RS_KINDS` | layers.js 222 to 234 | Shows only some `kind` values of a base-map layer, as one more filter on each of its layers' own filters. Sends `rs:filterchange` `{overlay, kinds}`. `RS_KINDS`: for each layer, its kinds and their counts, most first. | Each feature's `kind`. | Missing: the kinds and their counts of each layer (mapstyle's `feature_overlays` returns them as `kinds`). |
| The Roads and Layers boxes | layers.js 262 to 292 | Both folded at the start; the Layers box goes under the Roads box in the top-left stack and folds like it (a page with no stack keeps it in place). The boxes stay unseen until they are placed (map.py's `_BOX_CSS`), so that they do not move after they show. | | Page layout only. |
| The dashboard page | dashboard.js 1 to 164 | On roadstyle's report panel: a Modes box (a check for each mode with its count, the access rows), and under each base-map layer's box its clickable, tooltip and popup switches and its kinds (a check for each, with its count). Without the panel, a box in the page's corner. A colour option "Modes" colours the roads by the modes that can use them (`modes.yaml`'s `mode_colors`). | `rsSetModes`, `rsSetAccess`, `rsSetInteraction`, `rsSetKinds`, `RS_KINDS`, `RS_ACCESS`; the report panel's `#rp-ovs`, `#rp-cls`, `#rp-detail`, `#rp-co`, `#rp-legend`. | The colour option is a `color_options` entry (`color_by: "modes"`, a column that render_map adds). |

The route planner (`planner.html`, `render_map(planner=True)`) is a page of its own and is not in this list.
