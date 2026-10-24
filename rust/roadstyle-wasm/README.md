# roadstyle-wasm

The Rust engine of [roadstyle](https://github.com/Khoshkhah/roadstyle) in the browser (WebAssembly). It makes a MapLibre style, and
the vector tiles of that style, from a roads Parquet file and a look (roadstyle's palette, profile and settings, resolved one time). The page
then draws the roads with MapLibre GL JS. The package `roadstyle-dashboard` adds roadstyle's controls and road interaction.

## Use it

```js
import init, { Look, resolveLook, makeStyle, Tiler } from "roadstyle-wasm";

await init();                                            // loads pkg/roadstyle_wasm_bg.wasm
const look = resolveLook(JSON.stringify({ palette: "carto" }));   // or Look.fromJson(text): a saved look.json (version 1 or 0)
const style = JSON.parse(makeStyle(roadsParquet, look));          // one style, the roads in it as GeoJSON

// or vector tiles, made when the map asks for them
const tiler = new Tiler(roadsParquet, look, undefined, "Monaco", "rs://1/", ["name"]);
maplibregl.addProtocol("rs", async (p) => {
  const [, source, z, x, y] = p.url.slice("rs://".length).split("/");
  return { data: tiler.tile(source, +z, +x, +y) };
});
const tiled = JSON.parse(tiler.style());
```

- `readGeoParquet(bytes)`: the roads of a GeoParquet file as a `Roads` handle (the geometry in the column `geometry`).
- `readGeoJson(bytes)`: the roads of a GeoJSON file as a `Roads` handle; `roads.sources(look)` is stage 1 of them.
- `readShp(shp, dbf, prj?, name?)`: the roads of a Shapefile (its .shp and .dbf bytes and its .prj text), in EPSG:4326, as a `Roads` handle. A GeoPackage is read only by the native programs (SQLite is C).
- `Look` (`resolveLook`, `Look.fromJson`, `toJson`), `makeStyle`, `Tiler`, `makeSources`, `tileSources`, `tileFiles`, `makePage`,
  `exportLook` and `memoryBytes`: the types (`index.d.ts`) come from the Rust signatures, with their descriptions. The calls take a
  `Look`, not the look's text. `makeLook` is the old name of `resolveLook`, for one version.
- `roadstyle-wasm/roads_sql.js` (`makeRoads`, `writeRoads`) and `roadstyle-wasm/features_sql.js` (`writeFeatures`): the SQL that writes the
  engine's inputs from a duckOSM file in duckdb-wasm.
- TypeScript: 5.7 or later, with `lib` `esnext` (the classes have `Symbol.dispose`), or `skipLibCheck`.

## Build it

The package holds the files that wasm-bindgen makes. Build them before `npm pack`:

```bash
npm run build
```

This needs Rust with the target `wasm32-unknown-unknown` and `wasm-bindgen-cli` 0.2.129 (the version in `Cargo.toml`).

The package version is the version of roadstyle. License: MIT.
