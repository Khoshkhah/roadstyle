# The roadstyle program

`roadstyle` is the Rust engine as one program, with no Python. Each command is one job. The options have the names of roadstyle's
Python keywords: `--color-by lanes` is `color_by="lanes"`, and `--no-arrows` is `arrows=False`. A value that is JSON (a number,
`true`, a list) is read as JSON.

Build it from the repository:

```bash
cargo build --release --manifest-path rust/Cargo.toml -p roadstyle-cli
```

The program is `rust/target/release/roadstyle`. `roadstyle help` lists the commands.

## Make the page

`roadstyle page` makes the same page as `render_edges(backend="web")`: the map, its dashboard and MapLibre, in one file that works
offline. Any other option is a keyword of `render`:

```bash
roadstyle page roads.parquet out/map.html --basemap osm --views '{"plain": {"road_fill": false}}'
roadstyle page roads.parquet out/tiled.html --tiles
roadstyle page roads.parquet out/dashboard.html --sidebar dashboard
```

A CARTO base map needs a key: `--api-key KEY`, else the environment variable `ROADSTYLE_API_KEY`. Google 3D and the Street View
window take `--street-view-key KEY`, else `GOOGLE_MAPS_KEY`. The program writes a key into the page only when you give one.

## Draw a map in two stages

Stage 1 makes the style, one file for each source, and the road table. The program reads the roads by the file's extension:
GeoParquet (`.parquet`, the line in the column `geometry` in longitude and latitude), GeoJSON (`.geojson`), a Shapefile (`.shp`,
with its `.dbf` and `.prj` beside it) or a GeoPackage (`.gpkg`, its first feature table). It reprojects a Shapefile or a GeoPackage
in another CRS to longitude and latitude. `page` and `levels make` read the same files.

```bash
roadstyle sources roads.parquet out/stage1 --format geoparquet --color-by lanes
```

Stage 2 makes the vector tiles from stage 1's files: one PMTiles file, or a folder of XYZ tiles with its `style.json`.

```bash
roadstyle tiles out/stage1 out/roads.pmtiles
roadstyle tiles out/stage1 out/xyz --format xyz --base-url https://example.org/tiles
roadstyle tiles out/stage1 out/roads.pmtiles --tile-format mlt
```

`--tile-format mlt` writes MapLibre Tiles in place of Mapbox Vector Tiles (see [Make tiles and PMTiles](tiles.md)).

## Make and solve a level area

```bash
roadstyle levels make edges.parquet out/area      # roads.parquet, pairs.csv, edits.csv
roadstyle levels solve out/area                   # levels.csv, levels_info.json
roadstyle levels edit out/area                    # the level editor, http://127.0.0.1:8780/level_editor/
```

`levels make` takes the options of `roadstyle-levels make`: `--id-col`, `--band-col`, `--order`, `--band-dist`, `--head-m`,
`--near-rules` and the tag columns (`--highway-col`, `--layer-col`, `--bridge-col`, `--tunnel-col`, `--junction-col`). It gives the
same files as Python's `make_area`: Monaco in 0.1 s (Python 2.2 s), Tartu in 0.7 s (Python 13.2 s).

`levels edit` (and `serve`, the same without the check that the folder has `roads.parquet`) answers only on 127.0.0.1, only to its own address, and saves only the editor page's own changes. Its page files are in the
program. Build the page's WebAssembly package with `rust/roadstyle-wasm/build_editor.sh` before you build the program.

A command for one HTML page (`roadstyle page`) comes with the facade's page call.
