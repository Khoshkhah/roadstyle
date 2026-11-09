# Object kinds, part 2: every table on the map

**Status:** Signed off 2026-11-09. Nothing in this note is built.

[Object kinds in the data dock](dock_kinds.md) is part 1. Its hook `kinds` is built for nodes and areas (commit `60ade739`). This note answers four requests from duckOSM and one question about weak id names. The source of the requests is "Asked of roadstyle" in `duckOSM/docs/design/table_views.md`. The goal of duckOSM: every table of a duckOSM database shows its rows on the map, and a click on a row gives one standard card.

## The rule that decides the design

A UI part that the dock lacks is added in roadstyle first. duckOSM adds no fallback and no drawing code. duckosm-studio only moves the roadstyle version. So every change below is **additive**: a kind that works today (`idColumns` and `geometryBy`) keeps its drawing, its detection result and its card.

## What part 1 does today

Read from `dashboard/data/data_dock.js` and `dashboard/data/kinds.js`.

| Part | State |
|---|---|
| The hook `kinds`, `idColumns`, `geometryBy(sql, column)` | Built |
| Detection: the first kind whose `geometryBy` gives at least one row owns the result (`detectKind`) | Built. This is the weak-id problem (see "Weak id names"). |
| Layers for a point, a line and an area; the select look; the camera (`fit`); Reset; the theme | Built. Buildings use the same layers as nodes, and a test draws one polygon. |
| The card: title, chip, facts, `tags`, Copy id (`kindFacts`, `drawFacts`) | Built |
| The limit `KIND_LIMIT` = 20 000 and the table note "the map shows the first 20 000" | Built |
| A click on an object on the map | **Not built.** The answer of 2026-11-07 says yes. |
| The prompt line of Ask for the kinds; the test on the page of Studio; the Ask tools | Not built (steps c, d, e of part 1) |

## 1. `geometryOf(ids)`

**Why.** DuckDB has no H3 functions here. A host with h3-js can draw a cell, but no SQL can build it.

**API.** A kind has `geometryOf` **or** `geometryBy`. Not both.

```js
kinds: {
  cell: {
    label: "H3 cell",
    idColumns: ["h3_cell", "h3_id"],
    async geometryOf(ids, { column, signal }) {
      // ids: the distinct, non-null values of the id column of the result
      return ids.map((id) => ({ id, geom: hexagonGeoJSON(id), resolution: res(id) }));
      // [{ id, geom, ...facts }]  - the same shape as a row of geometryBy
    },
  },
}
```

Rules:

- `ids` has the distinct non-null values of the id column. The order is the order of the first row that has the value. The dock does not change the type of a value. A BIGINT stays what the query adapter gives (a `BigInt`). The host must not convert it with `Number`, because a 64-bit H3 index loses digits.
- The dock gets the ids from the rows that it already has when the result is complete. When the result has more rows than the table holds, the dock runs `SELECT DISTINCT "col" ... LIMIT 20001` through the guard. It passes at most `KIND_LIMIT` ids. When there are more, it sets `more`, and the note says so.
- The return value is an array or a promise of an array. Each entry is `{ id, geom, ...facts }`. `geom` is a GeoJSON geometry (an object or JSON text), as for `geometryBy`. The other keys are the facts of the card. `name` and `tags` keep their meaning from part 1.
- The dock matches an entry to a row with `String(id)`. An entry whose id is not in `ids` is dropped.
- `signal` is an `AbortSignal`. It aborts when a new result or a Reset makes the call out of date.
- The dock draws the entries and builds the card exactly as for `geometryBy`. The two ways give one drawing path.

**Default that keeps old hosts working.** A kind with only `geometryBy` is unchanged. A kind with both functions, or with neither, is a host error: the dock skips the kind, writes one `console.error` that names the kind, and sends the event `kinderror` (see question 2).

**Tests.** The fake host of `tests/test_dock_kinds_browser.py` gets a kind with `geometryOf` and a hexagon that the test builds with no library.

- The dock calls `geometryOf` with the distinct ids only. A result with 3 rows and 2 ids gives 2 ids.
- A `BigInt` id arrives as a `BigInt` and keeps all its digits (use `9223372036854775807`).
- A result with more than `KIND_LIMIT` rows calls it with `KIND_LIMIT` ids and shows the note.
- A new result aborts the signal of the old call.
- The cells show in the blue of the theme, and a click on a row gives the purple look and the card.
- A kind with both functions is skipped, with one `console.error`.

## 2. A geometry collection per row, with a role for each part

**Why.** A turn is two roads and the node between them. One row, one object, three parts.

**API.** The `geom` of an entry (from `geometryOf`) or the second column of `geometryBy` has one of two forms:

```js
geom: { type: "LineString", coordinates: [...] }          // one geometry: as today
geom: [ { role: "from", geom: {...} },                      // a list of parts
        { role: "via",  geom: {...} },
        { role: "to",   geom: {...} } ]
```

In SQL a host builds the list with `json_group_array(json_object('role', r, 'geom', ST_AsGeoJSON(g)::JSON))`. A part has `role` (a text) and `geom` (a geometry). A part with no `role` has the default look.

The kind can list its roles to set their order in the legend of the card: `roles: ["from", "via", "to"]`.

**Colours.** The kind names the role. It does not give a colour. The colour of a role is in the palette, under a new key `dock.roles.<name>` in every file of `rust/roadstyle-assets/files/data/palettes/`. This follows the rule that every style value is in a config file and that `tests/test_theme.py` fails on a colour literal. A light page and a dark page then both get a colour with enough contrast. The roles `from`, `via` and `to` have their own colours. Any other role takes the next colour of a list `dock.role_series` in the palette. The blue and the purple of `kinds.js` move to the same place in the same PR. The exact colours are a design choice: the PR shows them in both themes before the step ends.

**Drawing.**

- All parts of a row share one `rs_id`. Each feature also has `rs_role`.
- The layers colour by `["match", ["get", "rs_role"], ...]`. Lines draw under points. A point part is a dot with a ring.
- The selected row draws a purple halo under the colours of its parts. The parts keep their role colours, so the person can still tell "from" from "to".
- `fit` takes the bounds of all parts. Today `fit` reads `geometry.coordinates`, so it fails for a list of parts: it needs a fix in this step.
- The default card of a row with parts has a block "Parts" with a colour swatch and the role name for each part.
- `KIND_LIMIT` counts rows (objects), not parts. A limit of 20 000 rows with 3 parts gives up to 60 000 features.

**The key of a row.** A turn row has no single id column: it has `from_edge`, `via_node`, `to_edge`. So an entry of `idColumns` can be an array of columns, which is a composite key:

```js
idColumns: [["from_edge", "to_edge"], "restriction_id"]
```

For a composite key, `geometryBy(sql, columns)` gets the array. `geometryOf(ids)` gets an array of arrays, `[[12, 15], ...]`. The host returns `id` as an array of the same length. The dock turns a key into text with `values.map(String).join("|")`. A kind with only single columns is unchanged.

**Default that keeps old hosts working.** A `geom` that is one geometry draws as today. The blue and the purple keep their values.

**Tests.**

- A row with three parts draws three features with three role colours, in the light and the dark theme, and at 390 px.
- A click on the row selects all three parts (a halo) and the camera shows all of them.
- A role that no palette key names takes a colour from `dock.role_series`.
- A composite key: two rows with the same `from_edge` and different `to_edge` are two objects.
- `tests/test_theme.py` passes: no colour literal in the new code. A palette without `dock.roles` fails the palette test.

## 3. A result of many objects

**What the dock does now.** It draws every object that the geometry query returns, up to `KIND_LIMIT` (20 000), in one GeoJSON source. It shows a note when the result is cut. Part 1 plans a click on a row (built) and a click on the map (not built), and it plans buildings (they work through the same layers).

**What is still missing.**

| Gap | Why it matters | Step |
|---|---|---|
| A click on the map | Planned and approved on 2026-11-07, not built. | 5 |
| The table cannot mark a row by key. `rs.dock.table` has only `clear()`. | A click on the map must show its row. The table draws only the rows in view when it has more than 1000 rows. | 5 |
| A row with no drawn object does nothing on click. `kindPick` returns when it finds no feature. | The person clicks a row and sees nothing. This also happens for rows after the first 20 000 objects, and for tables that have no shape on purpose (`visualization_metadata`, `config`). | 5 |
| The card shows only the columns of the geometry query. It ignores the columns of the clicked row. | In `turn_restrictions` the facts are the row. | 4 |
| The cut is not exact. "The first 20 000" is the first 20 000 rows of the geometry query, in the order of the database. It is not the first 20 000 rows of the table. | The note is wrong for `geometryBy`. | 2 |
| Detection runs a full query for each candidate. | With ten kinds and weak names, one result can run ten queries of 20 000 rows. | 1 |

**API.**

- **No shape on purpose.** An entry can have `geom: null`. The row counts as known. The dock draws nothing. A click on its row opens the card with the line "Not on the map", and with the text of `noShape` when the kind has one (`noShape: "A table of settings. It has no place."`). A click on a row with no entry at all gives the same card with the line "No object found for this row". A click never does nothing.
- **Click on the map.** A click on a lit object selects it as a click on its row does: the purple look, the card, and the mark on its row in the table. The dock uses `queryRenderedFeatures` on its own layers with a box of 6 px around the point, so a thin line is easy to hit. Where objects overlap, the one on top wins. A click that hits no object does nothing, and a click on a road keeps its own handler.
- **`table.mark(key)`.** A new method of `rs.dock.table`. It marks a row, scrolls it into view and clears the old mark. `clear()` removes the mark. The key is the `String` of the id of the kind.
- **Exact cut.** For `geometryOf`, the first `KIND_LIMIT` ids in the order of the result are exact. For `geometryBy`, the note says "the map shows 20 000 objects" and not "the first".

**Detection by a probe.** The dock does not load 20 000 objects for each candidate. It probes with the first 200 distinct ids (for `geometryBy`, with `SELECT * FROM (sql) LIMIT 200` as the `sql` argument). It loads all objects only for the winner. See "Weak id names".

**Default that keeps old hosts working.** A host that never returns `geom: null` sees no change in drawing. The click on the map is on for a page that has `kinds`, and it does nothing for a page that has none. The new click on a row that has no object shows a card where today nothing happens. No host depends on that.

**Tests.**

- 20 000 point objects and 20 000 hexagons draw. The test records the time to draw and the time of a click. If the time is over 3 s, the PR says so, and the limit is a question for the owner.
- 20 001 objects show the note.
- A click on a lit object selects it, opens the card, and marks the row. A click on a thin line works. A click on empty map changes nothing.
- A click on a row of a result with no entry opens the card with "No object found". A row with `geom: null` opens the card with the `noShape` text.
- `table.mark` scrolls to a row far down a 5 000-row table.
- Reset and the map switch remove the objects and the mark.

## 4. A card with sections and one action

**Why.** The card of a H3 cell has facts, then counts that come from a query, then a button "Show cell". The card of a turn has a button "Zoom to road".

**API.** A kind can have `card(info)`.

```js
card({ id, label, row, facts, parts, kind }) {
  // row:   the clicked row as { column: value }
  // facts: the facts from the entry of geometryOf / geometryBy
  return {
    title: "Cell 8a2a1072b59ffff",
    chip: "H3 cell",                         // default: the label of the kind
    rows: [["resolution", 8], ["area km2", 0.74]],           // the facts
    sections: [                                              // optional blocks, each with a small heading
      { title: "Inside", rows: [["nodes", 143], ["edges", "..."]] },
    ],
    action: { label: "Show cell", run: (info) => hexagonGeoJSON(info.id) },
  };
}
```

Rules:

- `title`, `chip` and `rows` are as in part 1. `sections` is a list of `{ title?, rows }`.
- **One action at most.** `action` is `{ label, run }`. It draws as one block with one button at the end of the card, above the id line. A second action is not possible. This keeps the card small on a phone.
- `run(info)` can do anything the host needs (for example `rs.focus([edgeId])` for "Zoom to road"). It can also return a GeoJSON geometry, or a list of parts as in request 2. The dock then draws the result with the selected object, in the select look, and fits the camera to it. A new selection or the close button removes it. So a host with no access to the dock's layers can show a cell without its own drawing code.
- `card` can return a promise. The dock then draws the card at once from the entry's facts, and shows "Loading…" in each section that is not ready. When the promise resolves, the dock replaces the card. When the person has selected another object in the meantime, the dock ignores the answer. If the promise rejects, the section shows the message of the error. The dock does not hide the error.
- The dock adds the id line and **Copy id** as before.
- The event `cardaction` (`{ kind, id }`) tells the host that the button was used.

**Default that keeps old hosts working.** A kind with no `card` gets the card of part 1. A road keeps its own card; this note does not change it.

**Style.** Sections and the action reuse the classes of the card (`rs-dd-rc-*`) and the tokens of both themes. New classes `rs-dd-rc-sec` and `rs-dd-rc-act` go in `dashboard.css`, in `docs/guides/dashboard-parts.md`, in `tests/test_dashboard_themes_browser.py` (contrast, no light surface in the dark theme) and in `tests/test_dashboard_scroll_browser.py` if the card scrolls. No native tooltip and no native select.

**Tests.**

- The default card for a kind with no `card` is unchanged (the tests of today).
- A card with a title, a chip, rows, two sections and an action shows in this order, in both themes and at 390 px.
- The button calls `run` once, sends `cardaction`, and draws the returned geometry in the select look with the camera on it. Close removes the geometry.
- An async card: "Loading…" shows, then the sections. A fast second click shows only the second card.
- A rejected promise shows the message in the section.

## Weak id names

**The problem.** `osm_id` and `node_id` are in many tables. In OSM, node 123 and way 123 are two objects. Today the first kind (in the order of `kinds`) that returns at least one row owns the result. One matching id is enough, so a result of ways can be drawn as nodes with no sign that it is wrong. Also, a result that has two id columns (`node_id` and `restriction_id`) takes the first kind in the list, not the better one.

**The new rule.**

1. A candidate is a kind that has one of its `idColumns` in the result. A kind can add `needs: ["lane_num"]`: columns that the result must also have. A kind without all its `needs` is not a candidate.
2. Roads come first, as today. A result with `edge_id` is a road result.
3. For each candidate (and each of its id columns) the dock probes the first 200 distinct ids. The **coverage** is the number of probed ids that get an entry (an entry with `geom: null` counts) divided by the number of ids probed.
4. The owner is the candidate with the highest coverage. A tie goes to the earlier kind in `kinds`, then to the earlier column in `idColumns`. A coverage of 0 means no owner. The result then has no objects, as today.
5. The dock loads all objects for the owner only.
6. The note of the table says which kind owns the result: "Shown as Node (node_id)". The dock sends the event `kind` with `{ name, column, coverage, candidates }`. A wrong guess is then visible, and a test can read it.

The host still orders its kinds and its columns, strong names first (`restriction_id` before `osm_id`). The order now decides only a tie, not the whole choice. To force a kind, the person selects the column under the id name of that kind, for example `SELECT osm_id AS way_id`. The note of the table says this when the coverage of the owner is below 1.

**Default that keeps old hosts working.** A host with the fake kinds of part 1 gets the same owner in its tests: the node kind has coverage 0 for 5001, and the building kind has coverage 1. A result that has exactly one candidate behaves as before, except for the probe.

**Tests.**

- Two kinds share `osm_id`. The ids exist in both tables, but only 1 of 200 ids is in the first table. The second kind owns the result.
- Full coverage in both: the earlier kind owns it, and the note names it.
- `needs` removes a candidate.
- A composite key kind and a single-column kind in one result: the higher coverage wins.
- The probe runs one query for each candidate with 200 ids, and one full load. The test counts the queries.

## Steps

One PR for each step. Each PR runs the browser tests on a host with the shape of Studio's (a DuckDB-wasm adapter, both themes, a panel of 400 px, a phone of 390 px). Each PR text ends with the line `Host change: none, only move the version`. Each PR changes `docs/guides/data-dock.md`, `docs/reference/javascript.md`, `docs/design/dashboard_module.md`, `dashboard/index.d.ts` and `CHANGELOG.md`.

1. **Choice of the owner.** Probe, coverage, `needs`, the note "Shown as ...", the events `kind` and `kinderror`. Errors of a kind query are reported, not swallowed.
2. **`geometryOf`.** Request 1, and the exact cut for `geometryOf`. Includes `geom: null`.
3. **Parts and roles.** Request 2: the list form of `geom`, the palette keys, the composite key, the `fit` fix.
4. **The card.** Request 4: `card(info)`, sections, one action, async, the returned geometry.
5. **Many objects.** Request 3: the click on the map, `table.mark`, the card for a row with no object, the 20 000 tests.

Steps 2 to 5 do not depend on each other except that step 4 uses the parts of step 3 for the returned geometry. duckOSM can start step 3 of its own plan (`web/ask/views.js`) when steps 1 and 2 are on `main`. The tables with turns need step 3, and the cell card needs step 4.

## Answers (2026-11-09)

The owner signed off this note on 2026-11-09. Both open questions have the answer **yes**.

1. **Role colours.** The kind names the role. The palette gives the colour, under `dock.roles.<name>`. The host gives no colour.
2. **Errors of a kind query.** The dock reports an error of a kind query with `console.error` and the event `kinderror`. The dock does not swallow it. The kind then counts as having no rows.

## Not covered

- The card of a road (`drawCard`): the road lane (`lane_profile`) has `edge_id`, so it takes the road path, and its `lane_num` is not in the road card. A change of the road card is a separate design.
- Ask's tools for kinds (step e of part 1).
- A button "Fit to all objects" for a large result.
