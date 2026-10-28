"""Fail when Python's design comes back into the Rust crates (docs/design/python_shape_left.md).

The rules, each counted in every file of rust/*/src (the binding crate roadstyle-py may name Python):
  py_fn      a function named py_*, or a truthy / py_truth function: Python's rounding, text and truth
  untyped    an option read by name from untyped JSON: args["..."] or a["..."]
  rs_literal a `__rs_` property name in code (a string, a format! text, a concat) outside the one table (roadstyle-model/src/mark.rs), a test too; a comment may write them
  py_comment a comment that names Python, render_web or tiles.py (Python is not the reference; "the Python binding" is fine)

No hit is allowed: the rules are at zero.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = "rust/roadstyle-model/src/mark.rs"
RULES = {
    "py_fn": re.compile(r"\bfn (py_\w+|truthy|py_truth)\b"),
    "untyped": re.compile(r"\b(args|a)\[\"[a-z_0-9]+\"\]"),
    "rs_literal": re.compile(r"__rs_"),
    "py_comment": re.compile(r"//.*(\bPython\b(?! binding)|render_web|tiles\.py)"),
}


def count() -> dict:
    out = {}
    for f in sorted((ROOT / "rust").glob("*/src/**/*.rs")):
        rel = f.relative_to(ROOT).as_posix()
        if rel.startswith("rust/roadstyle-py/"):
            continue
        text = f.read_text(errors="ignore")
        code, _, tests = text.partition("\n#[cfg(test)]")        # the tests may name Python, but not a `__rs_` property
        for line in (code + "\n" + tests).splitlines():
            code_line = line.split("//")[0]       # all rules but py_comment read code, not comments
            in_tests = line in tests.splitlines() and line not in code.splitlines()
            for name, rx in RULES.items():
                if name == "rs_literal" and rel == TABLE or name != "rs_literal" and in_tests:
                    continue
                if rx.search(line if name == "py_comment" else code_line):
                    out.setdefault(rel, {}).setdefault(name, 0)
                    out[rel][name] += 1
    return out


def main() -> int:
    got = count()
    bad = [f"{f}: {r} {n}" for f, rs in got.items() for r, n in rs.items()]
    if bad:
        print("Python's design is back in the Rust crates:\n  " + "\n  ".join(bad))
        return 1
    print("ok: no Python design in the Rust crates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
