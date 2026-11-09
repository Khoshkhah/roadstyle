# Object kinds in the data dock

**Status:** 2026-11-07. Signed off by Kaveh ("Yes, sign off", told to the duckOSM Studio session, with the answers at the end of this page). Step a (the hook, nodes) and the drawing of lines and areas are built (commit `60ade739`). Part 2, for every table of a duckOSM database, is [Object kinds, part 2](dock_kinds_table_views.md) (proposed 2026-11-09).

## What and why

A row of the data dock is a road today. The dock finds the roads of a result from its id column (`idColumn`, default `edge_id`) or from a key column (`keys`: `osm_id`, `name`) through the host's `roadsBy(sql, column)`. A node, a building or a wall has no map object in the dock and no info card. Kaveh: "selecting node from sql table doesn't show it on the map and also its info into card info", and earlier: "in ask and sql panel part we should select roads and nodes and building too; we want to ask and show everything we are editing in the Edit OSM data part".

Today a host page can use `data.addEventListener("row", ...)` and `data.card(...)` and do all the work itself ([A row of your own](../guides/data-dock.md#a-row-of-your-own)). This design moves that work into roadstyle, so that each page does not write it again. The host says only **which columns are nodes or buildings** and **the SQL for their geometry**.

## Words

- **A kind** is a sort of map object: `road` (built in), `node`, `building`. More kinds can come later with no change of the dock.
- **A kind of a host** is `{idColumns, geometryBy}`. The host gives it. roadstyle draws it.

## The hook

```js
const data = dataDock({
  ...,                                   // the options of today
  kinds: {
    node: {
      label: "Node",                     // the chip of the card (default: the name of the kind)
      idColumns: ["node_id", "source", "target", "via_node", "osm_id"],
      geometryBy(sql, column) {          // ONE SELECT: id, geom, then the facts of the card
        return `SELECT n.node_id AS id, ST_AsGeoJSON(n.geom) AS geom, n.* EXCLUDE (node_id, geom)
                FROM driving.nodes n WHERE n.node_id IN (SELECT "${column}" FROM (${sql}) AS rs_k)`;
      },
    },
    building: { idColumns: [...], geometryBy(sql, column) {...} },
  },
});
```

duckOSM gives this object: `kinds: objectKinds({names, hasTags})` from `web/ask/schema.js` (duckOSM main `68a4d0f5`). Studio only runs the DuckDB queries.

- `geometryBy(sql, column)` gives one `SELECT`. Its first column is `id`, its second column is `geom` (GeoJSON text), and the other columns are the facts of the card. `sql` is the result's own SQL. The dock runs it with the guard and the row limit, as it runs `roadsBy`.
- A column `name` is the title of the card. If there is none, the title is `<label> <id>`.
- A column `tags` (a JSON object or a map) shows as one row for each tag, under the other facts. `hasTags` of duckOSM decides if the query has this column.

## Which kind owns a result

1. The dock tries the roads first, with the rules of today.
2. If the result has no roads, the dock goes through the kinds in the order of `kinds`. A kind is a candidate when the result has one of its `idColumns`.
3. The dock runs `geometryBy` for the candidate. The first kind that gives at least one row **owns** the result. This solves the name `osm_id`, which is a node in one table and a building in another: the lookup in the wrong table gives no row.
4. A result of no kind has no map object, as today.

## What the dock does for a kind

- **Light.** The objects of the result are drawn in the dock's own layers (the source `rs-dock-kinds`): a dot with a ring for a node, a fill with an outline for a building, a line for a line. They have the blue of the road light (`#2563eb`, `#5aa9f8` on a dark map, no see-through). The map switch, the theme and **Reset** control them, as they control the road light. The most is 20 000 objects. More gives the note "Showing the first 20 000".
- **Select.** A click on a row selects its object: the select purple, a larger ring for a node, a thicker outline for a building. The camera moves to the object (a node: zoom 18; a building: its bounds). A second click on the same row, or the close button of the card, deselects it.
- **The card.** The card has the same look as the card of a road and of an overlay item: the title, the chip (the label of the kind), the facts as rows (a `null` or empty value is left out) and the id with **Copy id**. It uses `data.card` inside, so the events `row` and `cardclose` stay as they are.
- **Reset.** [Reset](../guides/data-dock.md#the-line) removes the objects and the selection of a kind too.
- **No change without `kinds`.** A page that gives no `kinds` works as today.

## Ask

Ask runs its SQL through the dock, so an answer with a node column lights nodes and a click on a row selects the node, with no change of Ask's tools. Two small changes:

- The prompt of Ask gets one line for each kind with its `idColumns`, so that the model selects the id column ("select `node_id` to show nodes on the map").
- The tools `color_roads`, `focus_roads` and `move_map` stay for roads. `move_map(sql)` can take the ids of a kind in a second step (see the questions).

## What roadstyle owns, and what the host owns

| roadstyle | The host |
|---|---|
| the layers, the light, the select look, the theme, Reset | which tables and columns are nodes, buildings, walls |
| the card (title, chip, facts, Copy id) | the SQL of `geometryBy` (duckOSM's `objectKinds`) |
| the order of the kinds, the limit, the guard | running the SQL on its database |

## Tests

A fake host with two kinds (canned GeoJSON for two nodes and two buildings), a blank base map, in the light and the dark theme and at 390 px:

- A result with node ids lights the nodes in the blue of the theme; one with building ids lights the buildings.
- A click on a row gives the purple ring, the camera move and the card with the facts and the tags.
- The name `osm_id` gives the right kind in both tables.
- **Reset** and the map switch remove the objects. A result with road ids is not changed.
- A page with no `kinds` is not changed (the tests of today).

A second test on the page of duckOSM Studio (a Monaco build) checks the real `objectKinds`.

## Steps

A PR for each step, with the tests on a host like Studio's (vector tiles, a DuckDB-wasm adapter, the dark and the light theme, a panel of 400 px, a phone of 390 px).

1. **a.** The hook, the detection, the light and the card for nodes (a ring on a dot), with the fake host tests.
2. **b.** Buildings (fill and outline) and the select look.
3. **c.** The prompt line for Ask, and the guide `data-dock.md`.
4. **d.** The test on Studio's page with `objectKinds`. Host change in each PR: none for a page with no `kinds`; the pin and `kinds: objectKinds(...)` for Studio.
5. **e.** Ask's tools for the kinds: `move_map` and a highlight tool take the ids of a kind.

## Answers of Kaveh (2026-11-07)

1. **A click on the map: yes.** A click on a lit node or building selects it and opens its card, as a click on a road does (in step b).
2. **Ask's map tools for the new kinds** (highlight, focus): yes, but in a later PR, not in the first ones (step e).
3. **The limit of 20 000 objects:** keep it, with a message when the result is cut.
4. **The colours:** as in this design. Blue for the result (`#2563eb` on a light map, `#5aa9f8` on a dark map, no see-through) and a purple ring for the selected object.
