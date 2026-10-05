# Editable solver pair tables

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
- `connect`: shared road endpoints, including the endpoint side on each road.
- `order`: junction drawing priority, with `upper_edge_ref` above
  `lower_edge_ref`.

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
