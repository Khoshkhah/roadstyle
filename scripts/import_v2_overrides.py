"""Carry the v2 test's override table (docs/v2/pair-tables.md on v2-dev) into an area's edits.csv (docs/design/level_input.md).

    python scripts/import_v2_overrides.py road_pairs_overrides.csv AREA_DIR SOURCE [--query SQL]

SOURCE (and --query) are the edges the area was made from (as for roadstyle-levels make): they turn v2's edge_ref into the ids of AREA_DIR. v2's
"add" rows become edits: connect -> meet (its endpoint_a / endpoint_b), order -> order and near / cross -> stack (upper over lower). A
"replace" or "remove" row names a pair of v2's own pair table, which this area does not have: the script stops and lists them, and writes
nothing. A row already in edits.csv is not added twice.
"""
import argparse
from pathlib import Path

import pandas as pd

from roadstyle.level_area import read_edges

COLS = ["relation", "a", "b", "a_end", "b_end", "enabled"]


def convert(v2, id_of):
    bad = v2[v2["action"].str.strip().str.lower() != "add"]
    if len(bad):
        raise SystemExit(f"{len(bad)} v2 row(s) are not 'add' (they name v2's own pair ids, which this area does not have); nothing written:\n"
                         + bad.to_string(index=False))
    rows, missing = [], set()
    for r in v2.to_dict("records"):
        rel = r["relation"].strip().lower()
        if rel == "connect":
            a, b, row = r["edge_a"], r["edge_b"], {"relation": "meet", "a_end": r["endpoint_a"], "b_end": r["endpoint_b"]}
        elif rel in ("order", "near", "cross"):
            a, b, row = r["upper_edge_ref"], r["lower_edge_ref"], {"relation": "order" if rel == "order" else "stack", "a_end": "", "b_end": ""}
        else:
            raise SystemExit(f"unknown v2 relation {rel!r}")
        missing |= {x for x in (a, b) if x not in id_of}
        enabled = str(r.get("enabled", "")).strip().lower()
        rows.append({**row, "a": id_of.get(a, a), "b": id_of.get(b, b), "enabled": "false" if enabled in ("false", "0", "no") else "true"})
    if missing:
        raise SystemExit(f"edge_ref(s) not in the edges, nothing written: {sorted(missing)}")
    return pd.DataFrame(rows, columns=COLS)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("v2_overrides", type=Path)
    ap.add_argument("area_dir", type=Path)
    ap.add_argument("source", help="the edges the area was made from: a geo file, or a .duckdb with --query")
    ap.add_argument("--query")
    ap.add_argument("--id-col", default="edge_id")
    a = ap.parse_args(argv)
    edges = read_edges(a.source, a.query)
    id_of = {str(r): str(i) for r, i in zip(edges["edge_ref"], edges[a.id_col], strict=True)}
    new = convert(pd.read_csv(a.v2_overrides, dtype=str, keep_default_na=False), id_of)
    path = a.area_dir / "edits.csv"
    old = pd.read_csv(path, dtype=str, keep_default_na=False).reindex(columns=COLS, fill_value="") if path.exists() else pd.DataFrame(columns=COLS)
    seen = {tuple(r) for r in old[COLS].itertuples(index=False)}
    add = new[[tuple(r) not in seen for r in new[COLS].itertuples(index=False)]]
    pd.concat([old, add], ignore_index=True).to_csv(path, index=False)
    print(f"{len(add)} v2 override(s) added to {path} ({len(new) - len(add)} already there); solve with roadstyle-levels solve {a.area_dir}")


if __name__ == "__main__":
    main()
