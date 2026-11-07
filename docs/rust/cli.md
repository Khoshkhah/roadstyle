# The roadstyle program

<p class="lead">`roadstyle` is the Rust engine as one program, with no Python. Each command does one job.</p>

The options have the names of roadstyle's Python keywords: `--color-by lanes` is `color_by="lanes"`, and `--no-arrows` is `arrows=False`. The program reads a value that is JSON (a number, `true`, a list) as JSON.

Build the program from the repository:

```bash
cargo build --release --manifest-path rust/Cargo.toml -p roadstyle-cli
```

The program is `rust/target/release/roadstyle`. `roadstyle help` shows the commands.

| Command | What it does |
|---|---|
| [`page`](#make-the-page) | the map, as one HTML file |
| [`sources`](#draw-a-map-in-two-stages), [`tiles`](#draw-a-map-in-two-stages) | stage 1 (style and sources), then stage 2 (vector tiles) |
| [`levels make`, `levels solve`, `levels edit`](#make-and-solve-a-level-area) | a level area: make it, solve it, edit it |
| [`serve`](#make-and-solve-a-level-area) | the level editor, with no check of the area |
| [`design edit`](#edit-the-design-of-a-map) | the design editor |
| [`snapshot`](#make-a-picture-of-a-page) | a PNG of a saved page |

The roads file is a GeoParquet file (`.parquet`, the line in the column `geometry`), a GeoJSON file (`.geojson`), a Shapefile (`.shp`, with its `.dbf` and `.prj` beside it) or a GeoPackage (`.gpkg`, its first feature table). The program changes the coordinates of a Shapefile or a GeoPackage to longitude and latitude. All commands that read roads use these files.

## Make the page

`roadstyle page` makes the same page as `render_edges(backend="web")`: the map, its dashboard and MapLibre, in one file that works offline. Any other option is a keyword of `render`:

```bash
roadstyle page roads.parquet out/map.html --basemap osm --views '{"plain": {"road_fill": false}}'
roadstyle page roads.parquet out/geojson.html --no-tiles        # GeoJSON roads: the page has tiles by default
roadstyle page roads.parquet out/mvt.html --tile-format mvt
roadstyle page roads.parquet out/dashboard.html --template dashboard
```

| Option | What it does |
|---|---|
| `--palette P`, `--profile P`, `--settings FILE.json` | the look |
| `--api-key KEY` | the key of a base map that is a tile URL. Default: the environment variable `ROADSTYLE_API_KEY` |
| `--street-view-key KEY` | the key for Google 3D and the Street View window. Default: `GOOGLE_MAPS_KEY` |

The program writes a key into the page only when you give one.

## Draw a map in two stages

Stage 1 makes the style, one file for each source, and the road table.

```bash
roadstyle sources roads.parquet out/stage1 --format geoparquet --color-by lanes
```

`--format` is `geojson` or `geoparquet`. `--keep COL,COL` keeps more columns. `--name NAME` sets the map name.

Stage 2 makes the vector tiles from the files of stage 1: one PMTiles file, or a folder of XYZ tiles with its `style.json`.

```bash
roadstyle tiles out/stage1 out/roads.pmtiles
roadstyle tiles out/stage1 out/xyz --format xyz --base-url https://example.org/tiles
roadstyle tiles out/stage1 out/roads_mvt.pmtiles --tile-format mvt
```

`--format` is `pmtiles` (default) or `xyz`. The tiles are MapLibre Tiles (MLT) by default. `--tile-format mvt` makes Mapbox Vector Tiles. One rule cuts the tiles for `page`, `tiles` and all other paths ([Make tiles and PMTiles](tiles.md)).

## Make and solve a level area

```bash
roadstyle levels make edges.parquet out/area      # roads.parquet, pairs.csv, edits.csv
roadstyle levels make edges.parquet out/area --boundary area.geojson   # also boundary.geojson
roadstyle levels solve out/area                   # levels.csv, levels_info.json
roadstyle levels edit out/area                    # the level editor, http://127.0.0.1:8780/level_editor/
roadstyle levels edit out/area --port 8790        # another port
```

`levels make` gives the same files as Python's `make_area`. Its options:

| Option | Default | What it does |
|---|---|---|
| `--id-col` | `edge_id` | the column with the road id |
| `--band-col` | none | the column with the band of a road |
| `--order` | `priority` | `priority`, `class`, `none` or a column name |
| `--band-dist` | 10 | the distance of a band, in metres |
| `--head-m` | 5 | the head length, in metres |
| `--near-rules` | off | also use the near rules ([How the levels are solved](levels-solver.md#the-rules)) |
| `--highway-col`, `--layer-col`, `--bridge-col`, `--tunnel-col`, `--junction-col` | `highway`, `layer`, `bridge`, `tunnel`, `junction` | the names of the tag columns |
| `--boundary AREA.geojson` | none | copies a GeoJSON polygon, feature or feature collection to `boundary.geojson`. The editor draws it as the dashed line of the edge of the area |

`levels solve` reads `roads.parquet`, `pairs.csv` and `edits.csv`, and also `heads.csv` and `caps.csv` when they exist. It writes `levels.csv` and `levels_info.json`.

`levels edit AREA_DIR` serves the level editor. It stops with an error when the folder has no `roads.parquet`. The page is the standard dashboard (one panel, the bar, both themes, the phone sheet). The editor saves `edits.csv`, `heads.csv`, `caps.csv` and `levels.csv` in the folder. The three input files have a column `time`, which the readers ignore.

- `--port` sets the port (default 8780).
- `--page DIR` serves another page folder. The page reads the area files relative to itself, from `../area/`.
- `serve AREA_DIR` does the same, with no check of the folder.

The server answers only on 127.0.0.1, only to its own address, and saves only the changes of the editor page. The page files are in the program. Build the WebAssembly package of the page with `rust/roadstyle-wasm/build_editor.sh` before you build the program.

The guide [Which road is on top](../guides/levels.md#edit-the-levels) shows the editor.

## Edit the design of a map

```bash
roadstyle design edit roads.parquet                       # the design editor, http://127.0.0.1:8781/design_editor/?roads=...
roadstyle design edit roads.geojson --design night.json   # another design file in the same folder
roadstyle design edit roads.shp --port 8790               # a Shapefile (its .dbf and .prj beside it), another port
```

`design edit ROADS` shows the roads on a map with the design panel: the theme, the road colours and widths, bridges and tunnels, the street names, the one-way arrows and the layers ([Edit the design of a map](../guides/design-panel.md#the-design-editor-on-its-own-page)). The program prints the address.

- The page reads a GeoParquet, GeoJSON or Shapefile file. It does not read a GeoPackage. Write the GeoPackage as GeoParquet first.
- Each change goes into the design file. Default: the name of the roads file without its extension, plus `.design.json`, in the folder of the roads.
- `--design NAME` sets another `.json` file name in that folder. It has no folder part.
- `--port` sets the port (default 8781). `--page DIR` serves another page folder.

The server answers only on 127.0.0.1, only to its own address. The page can read only the roads file (with the `.dbf` and `.prj` of a Shapefile) and the design file. It can write only the design file. The page uses the same WebAssembly package as the level editor: build it with `rust/roadstyle-wasm/build_editor.sh` before you build the program.

## Make a picture of a page

```bash
roadstyle snapshot map.html map.png --center 7.42,43.735 --zoom 15 --width 1200 --height 800
```

`snapshot` makes a PNG of a saved page. Chromium draws the page (the same as Python's `rs.snapshot`). The options are `--center LON,LAT`, `--zoom`, `--pitch`, `--bearing`, `--width` (1200), `--height` (800), `--scale` (1), `--settle` (2.5 seconds) and `--timeout` (40 seconds). A build without the Cargo feature `snapshot` stops with an error.
