# Monaco: the hand-made level tables

Hand-made changes for Monaco, made in the level editor (`scripts/edit_levels.py`), see
[docs/design/level_input.md](../../../docs/design/level_input.md):

| file | what |
|---|---|
| `edits.csv` | the meet / stack / order edits on top of the found pairs |
| `heads.csv` | head lengths per road end, metres (empty: the default 5 m) |
| `caps.csv` | end shapes per road end: round / square / flat (empty: round) |

The ids are duckOSM `edge_id`s of `monaco.duckdb` (`driving.edges`). To use them, make the area and copy them in:

```bash
python scripts/level_input.py monaco.duckdb out/monaco --query "SELECT * EXCLUDE (geometry), ST_AsWKB(geometry) AS geometry FROM driving.edges"
cp examples/levels/monaco/*.csv out/monaco/
python scripts/solve_levels.py out/monaco          # levels.csv
python scripts/edit_levels.py out/monaco           # the editor
```
