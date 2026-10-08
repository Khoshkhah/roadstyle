# Monaco: the hand-made level tables

Hand-made changes for Monaco, made in the level editor (`roadstyle-levels edit`), see
[docs/design/level_input.md](../../../docs/design/level_input.md):

| file | what |
|---|---|
| `edits.csv` | the meet / stack / order edits on top of the found pairs |
| `heads.csv` | head lengths per road end, metres (empty: the default 5 m) |
| `caps.csv` | end shapes per road end: round / square / flat (empty: round) |

The ids are duckOSM `edge_id`s of `monaco.duckdb` (`driving.edges`). To use them, copy them in and make the area (make reads
`heads.csv` to decide which parts of a stack cross; it keeps `edits.csv`):

```bash
mkdir -p out/monaco && cp examples/levels/monaco/*.csv out/monaco/
roadstyle-levels make monaco.duckdb out/monaco --query "SELECT * EXCLUDE (geometry), ST_AsWKB(geometry) AS geometry FROM driving.edges"
roadstyle-levels solve out/monaco          # levels.csv
roadstyle-levels edit out/monaco           # the editor
```

2026-10-08: a stack edit names one part (`a_end` start / main / end). The one whole-road stack edit became its two parts that the old
rule lifted (start head, main), and two switch-offs of parts that were never lifted were taken out.
