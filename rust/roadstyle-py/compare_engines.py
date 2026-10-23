"""Compare the two engines on the parity cases (tests/test_engine_parity.py) and print the first differences of each case. pytest's
diff of two styles of several MB is too slow to read, so use this script to find a difference:

    PYTHONPATH=src python rust/roadstyle-py/compare_engines.py [case ...]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))

import roadstyle as rs  # noqa: E402
from test_engine_parity import CASES, DATA, options  # noqa: E402


def roads():
    import geopandas as gpd
    import pyarrow.parquet as pq
    import shapely

    df = pq.read_table(DATA / "monaco_part" / "roads.parquet").to_pandas(integer_object_nulls=True)
    return gpd.GeoDataFrame(df.drop(columns="geometry"), geometry=shapely.from_wkb(df["geometry"]), crs="EPSG:4326")


def diff(a, b, path="$", out=None, most=8):
    """The first `most` places where a (Rust) and b (Python) are not equal."""
    out = [] if out is None else out
    if len(out) >= most:
        return out
    if type(a) is not type(b) and not (isinstance(a, (int, float)) and isinstance(b, (int, float)) and a == b):
        out.append(f"{path}: rust {type(a).__name__} {str(a)[:90]} | python {type(b).__name__} {str(b)[:90]}")
    elif isinstance(a, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                out.append(f"{path}.{k}: only in {'rust' if k in a else 'python'}")
            else:
                diff(a[k], b[k], f"{path}.{k}", out, most)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append(f"{path}: length rust {len(a)} | python {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            diff(x, y, f"{path}[{i}]", out, most)
    elif a != b:
        out.append(f"{path}: rust {str(a)[:100]} | python {str(b)[:100]}")
    return out


def main(cases):
    part = roads()
    look = json.loads((DATA / "look.json").read_text())
    kw = {"palette": look["palette"], "settings": look["settings"], **look["args"], "arrows": True, "labels": True}
    for case in cases or sorted(CASES):
        ru = rs.export_inline(part, engine="rust", **kw, **options(case, part))
        py = rs.export_inline(part, engine="python", **kw, **options(case, part))
        d = diff(ru, py)
        print(f"{case:14s} {'equal' if not d else 'DIFFERENT'}", flush=True)
        for x in d:
            print("   ", x)


if __name__ == "__main__":
    main(sys.argv[1:])
