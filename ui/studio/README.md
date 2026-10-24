# roadstyle studio in the browser

The studio's Map page with no Python: the knobs, roadstyle's Rust engine in a Web Worker (`worker.js`), the map with the shared
dashboard (`preview.html`, in an iframe) and the `render_edges(...)` code of the knobs (`code.js`). The Python studio
(`src/roadstyle/studio/`, Streamlit) is the model: the same knobs in the same sections.

## Open it

1. Build the engine's WebAssembly files once: `npm run build` in `rust/roadstyle-wasm/` (needs Rust with the target
   `wasm32-unknown-unknown` and `wasm-bindgen-cli`).
2. Serve the repository's root and open `/ui/studio/`:

```bash
python -m http.server 8000
```

## What it does now

- Data: the three Södermalm samples (GeoJSON), or a GeoJSON or GeoParquet road file in EPSG:4326.
- Look: palette, base map (all of `src/roadstyle/data/basemaps.json`; the map's switcher has the active one and the default set), 3D bridges, vector tiles (the engine's tiles, made in the worker when the map asks for them).
- Colour by data, as the Python studio: a numeric column with more than 12 values is a ramp from its 2nd to its 98th percentile; another
  column with 1 to 12 values is up to 5 stepped colours of the ramp (`rampStops`), its sorted values in even groups.
- Filter (the road classes, through the dashboard), minor roads hidden when zoomed out, street names, one-way arrows.
- Click popup (curated fields, chosen columns, side panel, all columns, off) and hover tooltip columns.
- Overlays: GeoJSON files and the sample overlays, each with its label, colour, place and popup and tooltip columns.

## What waits for other parts

- Shapefile road files: `readShp` (branch readers-rs). GeoPackage stays with the native programs: SQLite is C.
- The download of the page, and the Dashboard and Report pages: `makePage(roads, look, options)` makes them (R3; a sidebar with
  `"sidebar": "dashboard"` in the args), but the studio has no button for it yet.

Each change of a knob runs the look and stage 1 again in the worker (Södermalm driving, 4,563 roads: 0.3 to 0.5 s). All the calls
of the look are in `worker.js`, so the look's typed handle changes one file.
