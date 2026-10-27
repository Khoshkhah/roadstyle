#!/usr/bin/env python3
"""The ratchet of the tile budget (docs/design/tile_contract.md, "The tile size standard").

Measure the tiles (the Rust test tile_budget) and update rust/roadstyle-rs/tests/data/tile_budget.json:

    scripts/tile_budget.py                          limits go down to the measured number plus the margin, never up
    scripts/tile_budget.py --raise --why "TEXT"     also raise or add limits; TEXT goes in the file, and the PR text must say it too

A limit is the measured number plus a margin of 2 % (at least 1). The file keeps each raise (`raises`) so that a review sees it.
`--measured FILE` reads numbers that the test wrote (ROADSTYLE_TILE_BUDGET_OUT) and does not run cargo.
"""
import argparse
import datetime
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUDGET = ROOT / "rust/roadstyle-rs/tests/data/tile_budget.json"
DOC = ("The tile size budget: the largest numbers that the tiles and the style can have (rust/roadstyle-rs/tests/tile_budget.rs; "
       "docs/design/tile_contract.md, 'The tile size standard'). Limits only go down: scripts/tile_budget.py. A raise needs --raise "
       "--why, is listed in `raises`, and the PR text must say why; Kaveh must agree.")


def limit(m):
    """The limit for a measured number: 2 % more, at least 1."""
    return m + max(1, math.ceil(m * 0.02))


def merge(measured, old, path, raising, log):
    """The new limits of `measured` (a tree of numbers) from the old ones. `log`: lowered, raised, missing, removed (lines)."""
    new = {}
    for k, m in measured.items():
        at = f"{path}.{k}"
        o = old.get(k) if isinstance(old, dict) else None
        if k == "center":
            new[k] = o if o is not None else m           # the view is fixed: it never moves
        elif isinstance(m, dict):
            new[k] = merge(m, o if isinstance(o, dict) else {}, at, raising, log)
        elif o is None:
            if raising:
                new[k] = limit(m)
                log["raised"].append(f"{at}: new, {limit(m)}")
            else:
                log["missing"].append(f"{at}: {m}")
        elif limit(m) < o:
            new[k] = limit(m)
            log["lowered"].append(f"{at}: {o} -> {limit(m)}")
        elif m <= o:
            new[k] = o                                    # within the limit: it stays (the margin does not creep up)
        elif raising:
            new[k] = limit(m)
            log["raised"].append(f"{at}: {o} -> {limit(m)}")
        else:
            new[k] = o
            log["missing"].append(f"{at}: {m} is over {o}")
    if isinstance(old, dict):
        log["removed"] += [f"{path}.{k}" for k in old if k not in measured]
    return new


def update(measured, budget, raising, why):
    log = {"lowered": [], "raised": [], "missing": [], "removed": []}
    areas = dict(budget.get("areas", {}))
    for area, m in measured.items():                     # an area that was not measured (no inputs here) stays as it is
        areas[area] = merge(m, areas.get(area, {}), area, raising, log)
    out = {"_doc": DOC, "areas": areas, "raises": list(budget.get("raises", []))}
    if log["raised"]:
        out["raises"].append({"date": datetime.date.today().isoformat(), "why": why, "changes": log["raised"]})
    return out, log


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raise", dest="raising", action="store_true", help="raise or add limits (needs --why)")
    ap.add_argument("--why", default="", help="the reason of a raise (the PR text says it too)")
    ap.add_argument("--measured", help="the numbers file that the test wrote; no cargo run")
    a = ap.parse_args(argv)
    if a.raising and not a.why.strip():
        ap.error("--raise needs --why 'the reason'")
    budget = json.loads(BUDGET.read_text()) if BUDGET.exists() else {}
    if a.measured:
        measured = json.loads(Path(a.measured).read_text())
    else:
        out = Path(tempfile.mkdtemp()) / "measured.json"
        # the test fails when a number is over its limit; the numbers are written first, so its exit code is not read
        subprocess.run(["cargo", "test", "--release", "-p", "roadstyle-rs", "--test", "tile_budget", "the_tiles_stay_within_their_budget"],
                       cwd=ROOT / "rust", env={**os.environ, "ROADSTYLE_TILE_BUDGET_OUT": str(out)}, check=False)
        if not out.exists():
            sys.exit("the test wrote no numbers: see its output")
        measured = json.loads(out.read_text())
    new, log = update(measured, budget, a.raising, a.why)
    BUDGET.write_text(json.dumps(new, indent=1) + "\n")
    for key in ("lowered", "raised", "removed"):
        for line in log[key]:
            print(f"{key}: {line}")
    if log["missing"]:
        print("\nthe test fails for these (no limit, or over it). To raise or add limits: --raise --why 'the reason', and say why in the PR:")
        print("\n".join("  " + m for m in log["missing"]))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
