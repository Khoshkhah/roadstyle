# Editable solver pair tables

For the full v2 level-calculation model and optimization priorities, see the
[level-calculation guide](./level_calculation.md).

The v2 stacking solver normally discovers road relationships from corridor
geometry and tags on every run. To inspect or edit those relationships, export
them once as an original-pairs CSV and an empty override CSV:

```python
from roadstyle.v2 import write_pair_tables, solve_stacking

write_pair_tables(corridors, "pairs.csv", "pair_overrides.csv")
```

Every corridor needs a stable unique `id`, `edge_ref`, `ref`, or `edge_id` for
saved tables. The CSV edge references must continue to identify the same roads
when you solve again. Corridors without references still work when the solver
discovers pairs in memory, but that run-local fallback is not suitable for
persistent files.

The original table records four relationship types:

- `near` and `cross`: vertical stacking relationships, with
  `upper_edge_ref` above `lower_edge_ref`.
- `connect`: a selected head (`start` or `end`) on each edge. `node_ref` is
  optional: discovered rows record the shared coordinate, while manual rows can
  connect selected heads without a shared coordinate or geometry change.
- `order`: junction drawing priority, with `upper_edge_ref` above
  `lower_edge_ref`.

## Monaco pair-table data

The generated tables are stored in [`data/v2/`](../../data/v2/):

- [`road_pairs_original.csv`](../../data/v2/road_pairs_original.csv) contains
  the discovered Monaco road relationships.
- [`road_pairs_overrides.csv`](../../data/v2/road_pairs_overrides.csv) is the
  editable override table for manual changes.

The original table was generated from the 2,765 `corridor_fill` features and
their geometry, band, road-class, and stable edge-reference properties in the
self-contained [Monaco v2 map](./monaco_roads_v2.html). It contains 9,899
relationship rows: 7,442 `connect`, 460 `cross`, 618 `near`, and 1,379 `order`.
These are relationship inputs, not level results or the full raw OSM road
table. To reuse them, supply corridors with the same geometries and stable
references via `pair_table` and `pair_overrides`.

Edit `pair_overrides.csv` to add, change, or disable a relationship. Its columns
are `action` followed by the original table columns. Use `replace` with the
existing `pair_id` to change non-empty fields; blank fields retain their
original values. Use `remove` to disable an original row. Use `add` with a new
`pair_id` to add a row. For example, an order replacement can be written as:

```csv
action,pair_id,relation,edge_a,edge_b,node_ref,endpoint_a,endpoint_b,upper_edge_ref,lower_edge_ref,enabled
replace,EXISTING_PAIR_ID,order,,,,,,road-that-goes-over,road-that-goes-under,
```

Run the solver with the saved original and override files:

```python
solution = solve_stacking(
    corridors,
    pair_table="pairs.csv",
    pair_overrides="pair_overrides.csv",
)
```

The original table is not rewritten during solving. Keep the override file
under version control to retain intentional edits and review them separately
from automatically discovered relationships.

## Preparing solver inputs from DuckOSM

Use the v2 helper script to combine every available `driving.edges`,
`walking.edges`, and `cycling.edges` table from a DuckOSM database. It writes
one solver-ready corridor GeoJSON and one pair-table set for the combined
network; it does not run the optimizer or write level results.

```bash
python scripts/v2/prepare_duckosm_solver_input.py area.duckdb
```

The default output directory is `data/v2/duckosm_solver_input/`:

- `corridors.geojson` contains every directed corridor and its normalized v2
  fields plus source properties.
- `road_pairs_original.csv` contains the discovered relationships across all
  loaded modes.
- `road_pairs_overrides.csv` is an empty editable override template.

Pass `--output` to select a different directory and `--band-dist` to change
the distance used when discovering `near` pairs. The script opens the database
read-only. Mode is included in each edge reference and physical-road ID so
identifiers remain unique across mode tables; only exact reverse directions
within the same mode can be grouped by the solver.

## Editing overrides in the dashboard

Launch the local MapLibre pair editor from the repository root:

```bash
python scripts/v2/pair_override_dashboard.py            # smooth road lines by default; use --smooth 0 to disable
```

Open the printed local URL to see the Monaco MapLibre map. Click two roads
directly on the map, or search by road name, class, or edge reference. Choose
`near`, `cross`, `connect`, or `order`, then save the relationship. If a
matching discovered relationship exists, the editor can write a sparse
`replace` override instead of adding a duplicate. The original table is
read-only; edits are validated and saved to
[`road_pairs_overrides.csv`](../../data/v2/road_pairs_overrides.csv), and the
page also offers a CSV download.

The saved-overrides panel lists every override row. Select a row to zoom to and
highlight its roads on the map; use **Delete** to remove that override row from
the override CSV. Deleting an `add` removes it, while deleting a `replace`
restores the original discovered relationship.

For a `connect` override, select which head of each edge is related. The solver
constrains those two heads without requiring a shared point or changing either
geometry. The map displays four labeled head markers (`1S`, `1E`, `2S`, `2E`)
for the two selected edges; clicking a marker selects that head in the form.
Use `--original`, `--overrides`, and `--map-html` to select another input set
and a map with matching edge references. `--host` and `--port` control the
local server address.

An added coordinate-free connect row looks like:

```csv
add,MANUAL_PAIR_ID,connect,edge-a,edge-b,,end,start,,,true
```

The generated GeoJSON can be loaded back as solver corridors, and the paired
CSV files can be passed directly to `solve_stacking`:

```python
from scripts.v2.prepare_duckosm_solver_input import read_corridor_geojson
from roadstyle.v2 import solve_stacking

corridors = read_corridor_geojson(
    "data/v2/duckosm_solver_input/corridors.geojson"
)
solution = solve_stacking(
    corridors,
    pair_table="data/v2/duckosm_solver_input/road_pairs_original.csv",
    pair_overrides="data/v2/duckosm_solver_input/road_pairs_overrides.csv",
)
```

Solved levels are a separate output, not a replacement for either pair input.
Use [`write_level_table`](../../src/roadstyle/v2/engine/solver.py) to save one
row per directed corridor. The generated Monaco levels are in
[`data/v2/road_levels.csv`](../../data/v2/road_levels.csv). The export has 2,765
rows; 807 exact reverse pairs were solved once and expanded back with their
start/end casing levels swapped. For this dataset, the shared physical-road ID
is the way/segment prefix of `edge_ref` (the part before `#f` or `#r`), and the
solver additionally verifies the reversed geometry and compatible level
inputs before grouping a pair.

## Rebuilding the level table

`python scripts/v2/build_road_levels.py` reads the DuckOSM driving edges (15 m heads), rewrites
`data/v2/road_pairs_original.csv`, and solves original pairs plus `road_pairs_overrides.csv` into
`data/v2/road_levels.csv`. The overrides file is only read. The pair editor does the same after every
save or delete (it writes `road_levels.csv`) and redraws the map with the solved levels; pass
`--database` to point it at another DuckOSM file.
