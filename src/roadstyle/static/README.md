# roadstyle-dashboard

The map dashboard of [roadstyle](https://github.com/Khoshkhah/roadstyle): the controls (colour by, legend, road filter, search,
2D/3D, base map, Street View, Google 3D), the popups and the road interaction (hover, click, select) for a MapLibre map of roads.
roadstyle's Python pages and the pages that use roadstyle's Rust engine (the package `roadstyle-wasm`) use the same files.

## Use it

The page must have MapLibre GL JS 5.8 or later as the global `maplibregl`.

```html
<link rel="stylesheet" href="node_modules/roadstyle-dashboard/dashboard/dashboard.css">
<link rel="stylesheet" href="node_modules/roadstyle-dashboard/popup.css">
<script type="module">
import init, { makeStyle, makeSources } from "roadstyle-wasm";
import { rsDashboard } from "roadstyle-dashboard";

await init();
const style = JSON.parse(makeStyle(roadsParquet, lookJson));   // a style of roadstyle's Rust engine
const road_table = JSON.parse(new TextDecoder().decode(makeSources(roadsParquet, lookJson).roadTable()));
const map = new maplibregl.Map({ container: "map", style });
const rs = rsDashboard(map, { style, road_table, street_view: "window" });
rs.on("select", (e) => console.log(e.properties));
</script>
```

- Call `rsDashboard` immediately after you make the map, before its `load` event.
- The options have the names of roadstyle's Python keywords (`render_edges`). The values that you do not give come from the style's
  metadata, or have roadstyle's defaults.
- The road table (each road's fields, midpoint, bbox, heading and line) is the option `road_table`, or `window.RS_SIDE`.
- Roads that come later (vector tiles, a new style after each build): give `style: null` and the `prefix` of their ids in the map,
  then call `rs.setStyle(style, {road_table})`.
- `rsDashboard` returns the `rs` object: `select`, `find`, `setFilter`, `getState`, `setState`, `link` (a URL fragment), `on`.

The options, the files and the data that each control reads: `docs/design/dashboard_module.md` in the repository.

The package has TypeScript types (`dashboard/index.d.ts`). MapLibre's own types need TypeScript 5.7 or later.

The package version is the version of roadstyle. License: MIT.
