"""Fail when Python's design comes back into the Rust crates (docs/design/python_shape_left.md).

The rules, each counted in every file of rust/*/src (the binding crate roadstyle-py may name Python):
  py_fn      a function named py_*, or a truthy / py_truth function: Python's rounding, text and truth
  untyped    an option read by name from untyped JSON: args["..."] or a["..."]
  rs_literal a "__rs_ property name written as a string outside the one table (roadstyle-model/src/mark.rs)
  py_comment a comment that names Python, render_web or tiles.py (Python is not the reference)

The file scripts/python_shape_allow.json holds the counts that are still allowed (a ratchet: a count can go down, never up).
Run `python scripts/check_no_python_shape.py --write` after a commit that lowers a count. The goal: the file is empty.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOW = ROOT / "scripts" / "python_shape_allow.json"
TABLE = "rust/roadstyle-model/src/mark.rs"
RULES = {
    "py_fn": re.compile(r"\bfn (py_\w+|truthy|py_truth)\b"),
    "untyped": re.compile(r"\b(args|a)\[\"[a-z_0-9]+\"\]"),
    "rs_literal": re.compile(r"\"__rs_"),
    "py_comment": re.compile(r"//.*(\bPython\b|render_web|tiles\.py)"),
}


def count() -> dict:
    out = {}
    for f in sorted((ROOT / "rust").glob("*/src/**/*.rs")):
        rel = f.relative_to(ROOT).as_posix()
        if rel.startswith("rust/roadstyle-py/"):
            continue
        for line in f.read_text(errors="ignore").splitlines():
            for name, rx in RULES.items():
                if name == "rs_literal" and rel == TABLE:
                    continue
                if rx.search(line):
                    out.setdefault(rel, {}).setdefault(name, 0)
                    out[rel][name] += 1
    return out


def main() -> int:
    got = count()
    if "--write" in sys.argv:
        ALLOW.write_text(json.dumps(got, indent=1, sort_keys=True) + "\n")
        print(f"{sum(sum(v.values()) for v in got.values())} hits allowed in {len(got)} files")
        return 0
    allow = json.loads(ALLOW.read_text()) if ALLOW.exists() else {}
    bad = [f"{f}: {r} {n} > allowed {allow.get(f, {}).get(r, 0)}" for f, rs in got.items() for r, n in rs.items() if n > allow.get(f, {}).get(r, 0)]
    if bad:
        print("Python's design is back in the Rust crates:\n  " + "\n  ".join(bad))
        return 1
    print(f"ok: {sum(sum(v.values()) for v in got.values())} hits left (allowed {sum(sum(v.values()) for v in allow.values())})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
