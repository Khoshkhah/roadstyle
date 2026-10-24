# roadstyle studio in the browser

The Python studio's Map, Dashboard and Report pages with no Python: the knobs, roadstyle's Rust engine in a Web Worker (`worker.js`)
that makes the whole page for each change (`Roads.page`: `page_from`, as `render_edges(backend="web")` with the Rust engine), that page in
an iframe, and the Python code of the knobs (`code.js`). The Python studio (`src/roadstyle/studio/`, Streamlit) is the model: the same
knobs in the same sections.

## Open it

1. Build the engine's WebAssembly files once: `npm run build` in `rust/roadstyle-wasm/` (needs Rust with the target
   `wasm32-unknown-unknown` and `wasm-bindgen-cli`).
2. Serve the repository's root and open `/ui/studio/`:

```bash
python -m http.server 8000
```

## What it does

- Page: Map (`render_edges`), Dashboard (`render_dashboard`) or Report (`render_report`). A Dashboard or Report page has its sidebar
  (`sidebar=`), a title and the base maps it offers.
- Data: the three Södermalm samples (GeoJSON), a GeoJSON or GeoParquet road file in EPSG:4326, or a Shapefile (its `.shp`, `.dbf` and
  `.prj`, picked together; reprojected to EPSG:4326). A GeoPackage is read only by the native programs: SQLite is C.
- Look: palette, base map (all of `src/roadstyle/data/basemaps.json`), 3D bridges, vector tiles (in the page, as PMTiles).
- Colour by data, as the Python studio: a numeric column with more than 12 values is a ramp from its 2nd to its 98th percentile; another
  column with 1 to 12 values is up to 5 stepped colours of the ramp (`rampStops`), its sorted values in even groups.
- Filter (the road classes, through the dashboard), minor roads hidden when zoomed out, street names, one-way arrows.
- Click popup (Map page: curated fields, chosen columns, side panel, all columns, off) and hover tooltip columns.
- Overlays: GeoJSON files and the sample overlays, each with its label, colour, place and popup and tooltip columns.
- Download: the page in the iframe, with MapLibre inlined (`src/roadstyle/vendor`), so it works offline, as `WebMap.save` writes it.

Each change of a knob makes the page again in the worker (Södermalm driving, 4,563 roads: about 1 s) and keeps the camera
(`rs.getState` / `rs.setState`). All the calls of the look are in `worker.js`.
