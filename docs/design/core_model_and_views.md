# A general core: roads, items, and views

**Status:** design; step 1 (views) built and merged, 2026-10-06. Builds on [Overlays attached to edges](edge_overlays.md),
[Overlay styles](overlay_styles.md) and [Levels and looks](levels_and_looks.md). Takes ideas from the `v2-dev`
branch (`docs/v2/`, an unfinished test).

## Why

roadstyle should be a core that other libraries build on (lanestyle, mapstyle, urbanstyle) without reaching
into its page. The `v2-dev` branch started for this reason. It drew a new data model (Corridor, Channel,
Demarcation, Patch, Glyph) and a new page.

Most of that model is already in roadstyle:

| v2-dev | what it is | roadstyle today |
|---|---|---|
| Corridor | the road: line, width, casing, heads, band, levels | the roads table (`width_m_col`, `casing_start_col`, `fill_level_col`, ...) |
| Channel | a lane: an area inside the road | `Overlay(edge_col=, order_col=, kind="fill")` |
| Demarcation | a painted line | the same, `kind="line"`, `width_m`, `dash` |
| Patch | a polygon (fillet, island, zebra) | an overlay, `kind="fill"` |
| Glyph | text or a symbol | an overlay, `kind="text"`; there is no icon kind |
| `fill_visible=False` | the items are the road's fill | `road_fill=False` |
| style names in the theme | lane, divider, zebra ... | `config.overlays.styles` |

What is missing is not the names. It is what the core cannot do, and lanestyle shows it: lanestyle adds
seven pieces of JavaScript to roadstyle's page, and each one uses roadstyle's layer ids, its globals or its
internals.

| lanestyle snippet | what it does | what it reaches into |
|---|---|---|
| `_ANCHOR_JS` | finds where a position's fill layers are | the layer ids (`roads-fill-lv4`) |
| `_FILLETS_JS` | draws junction fillets at a position, in the road class colours | layer ids, `RS_CLASS_COLORS`, its own source |
| `_LABELS_JS` | a second layer (the lane type) on the lanes' data | `RS_OVERLAYS`, the name layer's font |
| `_STREET_VIEW_JS` | a click on a lane opens Street View at its road | the click of an overlay does not reach the road |
| `_CASING_ZOOM_JS` | no casing below a zoom | every casing layer id |
| `_NO_PATTERN_ON_RINGS_JS` | no tunnel pattern on a roundabout | the pattern layers' filters |
| `_USE_ROWS_JS` | lane-use rows in the filter box, the colour menu hidden | the page's CSS classes |

A change inside roadstyle (a layer renamed, a filter changed) breaks lanestyle without a test failing in
either repository.

**The goal:** a library that builds on roadstyle uses only the keywords of `render_edges` and the public
`rs*` API. Its own page code (lanestyle's turn highlight, `_CLICK_JS`, uses `rs:select`, `rsQuery`,
`rsGetProps`) is fine; reaching into layer ids and globals is not. Each step below removes one or more of
the snippets above, so the goal can be checked.

## The model

```
Roads       line · width · casing · heads (start and end, per road) · band · priority · look
            the solver gives each road its numbers: casing (start, main, end) and fill
Items       overlays, each attached to
              a road      edge_col   drawn at the road's fill number, by order_col   (today)
              nothing                placement under / over                        (today)
            kind: fill · line · circle · text · icon (new)
            style: a name in the theme (lane, divider, zebra, arrow, ...)
Views       named sets of settings, switched in the page
```

### One item type, not five

An item stays an `Overlay`. Lane, marking, patch and glyph are **roles**, and a role is a style name in the
theme, as lanestyle's `lane`, `divider`, `zebra` already are. A new kind of thing on a road needs a style,
not a class. If a typed call reads better in a library, it can be a small function that returns an `Overlay`.

### What an item gets from its road

An item attached to a road is drawn at its road's place. It should also get the rest of what the road has,
so a library does not copy it onto every item:

- **The look.** A lane of a tunnel is drawn as tunnel, a lane of a bridge as bridge. `v2-dev` does this in
  its tunnel colouring (`docs/v2/tunnel-coloring.md`): an item is tunnel when its `edge_id` is a tunnel's.
- **The filters.** Hiding tunnels, a road class or a filtered set hides that road's items, always
  (2026-10-05). Today `rsFilter` on roads and on an overlay are separate.
- **The selection.** A click on an item selects its road as well: Street View, the docked panel and
  `rs:select` follow, and the item's own popup still shows. `_STREET_VIEW_JS` does this by hand now.

### Clicks: some items let them through

From `v2-dev`: a marking (a dash line, a stop line) should not catch a click meant for the lane under it.
`popup=[]` already makes an overlay not interactive; the theme style should be able to say so too
(`interactive: false`), so that every library's markings let clicks through by default.

### One item layer, several looks

An overlay is one data set drawn with one style. lanestyle needs the lanes drawn as a fill **and** labelled
with their type: today it adds a second MapLibre layer on the lanes' source by hand (`_LABELS_JS`). An
overlay should take a list of styles that all read the same data:

```python
rs.Overlay(lanes, edge_col="road_id", order_col="order", style=["lane", "lane_type_label"])
```

The data is in the page once. (This is the useful half of `v2-dev`'s "single source": one data set, many
layers. The other half, putting roads and items into one source, does not make the page smaller: see
"Not taken" below.)

### Junction pieces are road items

A fillet (the corner piece where roads meet) or a gap between lanes is not a new kind of item. lanestyle
already gives each one the level and colour of its nearest lane (`junctions.py`), so it is attached to that
lane's road with `edge_col` and a low order, as the road-end discs are (`items.end_caps`, order -2). This
replaces `_FILLETS_JS` and `_ANCHOR_JS` (its only user) with no new feature in roadstyle. The tunnel hatch on
a gap is its road's look; its popup is the overlay's `popup`.

### The look per road

Today a look is all or nothing: every tunnel gets the tunnel pattern, every casing shows at every zoom.
Two small things make it per road:

- **Look columns**: `pattern_col` (true/false per road; lanestyle sets it false on a roundabout ring), and
  later others if a library asks.
- **Zoom ranges**: `casing_zoom=(min, max)` and `fill_zoom=(min, max)` for the roads' own layers.

This replaces `_NO_PATTERN_ON_RINGS_JS` and `_CASING_ZOOM_JS`.

## Views

Today the page switches one thing from a menu: the colour (`color_options`, which can also switch the width
with `width_by`). The other settings have their own controls: the overlays (`rsSetOverlay`), the classes,
bridges and tunnels (`rsSetClasses`, `rsSetBridges`, `rsSetTunnels`), the base map (`rsSetBasemap`), 3D
(`rsSetView3D`).

A **view** is a name and a set of these settings, applied together:

```python
rs.render_edges(roads, overlays=[...], views={
    "Traffic": {"color": "flow", "road_fill": True, "overlays": {"lanes": False, "arrows": False}},
    "Lanes":   {"color": None, "road_fill": False, "overlays": {"lanes": True, "arrows": True}},
    "Night":   {"basemap": "dark"},
})
```

The page shows a *View* menu next to the *Colour by* menu (2026-10-05). `rsSetView(name)` applies a view from host
page code. A view sets only what it names; the rest stays as it is.

| a view can set | how the page does it | new? |
|---|---|---|
| `color` | an entry of `color_options` (with its width) | no: `rsSetColorField` |
| `overlays` | each overlay on or off | no: `rsSetOverlay` |
| `classes`, `bridges`, `tunnels` | what is shown | no |
| `basemap` | the base map | no |
| `view3d` | 3D on or off | no |
| `road_fill` | the roads' fill shown or not (with `road_fill=False` the fill layers are in the page already, at opacity 0) | **yes** |
| `labels` | the street names from a chosen column, or none | **yes** |
| `item_color` | a colour option for an overlay (`{"lanes": "use"}`) | **yes** |
| `filter` | a set of ids shown, the rest dimmed or hidden | partly: `rsFilter` |
| `camera` | where to look | partly: `rsFocus` |

The first rows cost almost nothing: a view is a list of calls the page already has. `road_fill` is the one
lanestyle needs most: one page that is a road map coloured by flow **and** a lane map, where it is two pages now.

`v2-dev`'s `ViewPreset` is the checklist for later rows (`width_mode="flow"`, `opacity_unselected`). Its
"0 ms by feature state" design is not taken: feature state is set one feature at a time and cannot change a
layout property (the label text), while the colour options already switch every road in one call, by a
column baked per option.

Event: `rs:viewselect` (`rs:viewchange` is taken by 3D).

## Not taken from v2-dev, and why

- **The five dataclasses.** See "One item type": roles are style names.
- **A second page** (`WebMap.to_html`). It has none of the 21 `rs*` functions, Street View, the panel,
  tiles or snapshots. The page stays one.
- **Roads and items in one source.** `docs/v2/monaco_benchmark_results.json` measured the v2 roads page at
  5.1 MB against 2.1 MB for v1, and the lanes page at 7.4 MB against 7.1 MB. Items are separate geometries:
  putting them in the roads' source saves nothing.
- **Bridge shadow, two-colour tunnel dashes.** Looks, possible later as theme entries; not part of the model.

Taken separately (the solver steps of the v2 review): pair tables with overrides, heads per road at each end,
the two directions of a road solved as one, priority tiers (roundabout, tunnel, road).

## Steps

Each step is a release that is tried on local pages first.

| step | what | lanestyle snippet it removes |
|---|---|---|
| 1 | views: `views=`, the *View* menu, `rsSetView`, with `road_fill` | (new: one page for roads and lanes) |
| 2 | an item click selects its road; items follow their road's filters | `_STREET_VIEW_JS` |
| 3 | several styles per overlay; `interactive` in a style | `_LABELS_JS` |
| 4 | lanestyle only: fillets and gaps as items attached to the nearest lane's road | `_FILLETS_JS`, `_ANCHOR_JS` |
| 5 | look columns (`pattern_col`) and `casing_zoom` / `fill_zoom` | `_NO_PATTERN_ON_RINGS_JS`, `_CASING_ZOOM_JS` |
| 6 | legend and filter rows from an overlay's categories | `_USE_ROWS_JS` |
| 7 | the solver ideas from `v2-dev` | |

After step 6, lanestyle's page code uses only the public API.

## Decided (2026-10-05)

1. The *View* menu sits next to the *Colour by* menu.
2. Items always follow their road's filters.
3. No junction items and no public layer slot: junction pieces are road items (above).
