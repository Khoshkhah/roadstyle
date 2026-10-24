# The roadstyle program

`roadstyle` is the Rust engine as one program, with no Python. Each command is one job. The options have the names of roadstyle's
Python keywords: `--color-by lanes` is `color_by="lanes"`, and `--no-arrows` is `arrows=False`. A value that is JSON (a number,
`true`, a list) is read as JSON.

Build it from the repository:

```bash
cargo build --release --manifest-path rust/Cargo.toml -p roadstyle-cli
```

The program is `rust/target/release/roadstyle`. `roadstyle help` lists the commands.

## Draw a map in two stages

Stage 1 makes the style, one file for each source, and the road table. The roads are a GeoParquet file, with the line in the column
`geometry` in longitude and latitude.

```bash
roadstyle sources roads.parquet out/stage1 --format geoparquet --color-by lanes
```

Stage 2 makes the vector tiles from stage 1's files: one PMTiles file, or a folder of XYZ tiles with its `style.json`.

```bash
roadstyle tiles out/stage1 out/roads.pmtiles
roadstyle tiles out/stage1 out/xyz --format xyz --base-url https://example.org/tiles
```

## Make and solve a level area

```bash
roadstyle levels make edges.parquet out/area      # roads.parquet, pairs.csv, edits.csv
roadstyle levels solve out/area                   # levels.csv, levels_info.json
roadstyle serve out/area                          # the level editor, http://127.0.0.1:8780/level_editor/
```

`levels make` takes the options of `roadstyle-levels make`: `--id-col`, `--band-col`, `--order`, `--band-dist`, `--head-m`,
`--near-rules` and the tag columns (`--highway-col`, `--layer-col`, `--bridge-col`, `--tunnel-col`, `--junction-col`). It gives the
same files as Python's `make_area`: Monaco in 0.1 s (Python 2.2 s), Tartu in 0.7 s (Python 13.2 s).

`serve` answers only on 127.0.0.1, only to its own address, and saves only the editor page's own changes. Its page files are in the
program. Build the page's WebAssembly package with `rust/roadstyle-wasm/build_editor.sh` before you build the program.

A command for one HTML page (`roadstyle page`) comes with the facade's page call.
