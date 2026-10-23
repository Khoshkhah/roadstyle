"""Make the golden styles of tests/colors.rs: roadstyle's own style (export_inline, Python) for a part of Monaco with the options of
render_edges for data-driven colour and width (docs/design/rust_engine.md). Run it in the conda environment roadstyle (roadstyle from
this repository's src/):

    python rust/roadstyle-rs/tests/make_goldens.py

It writes tests/data/monaco_part/roads.parquet (the roads of tests/data/monaco/roads.parquet in a box around Monte Carlo) and, for each
case, <case>.json.gz: {"args": the options, "style": export_inline's style, "color_options": the page's COLOR_OPTIONS (the legend data)}.
A case's look is tests/data/look.json with the options added to look["args"]. It also writes src/cmaps.json, the colour ramps that
roadstyle's colors.py reads from branca and matplotlib: branca's schemes and colour names, and each matplotlib colormap at 9 stops."""
import gzip
import json
import re
from pathlib import Path

import geopandas as gpd
import pyarrow as pa
import pyarrow.parquet as pq
import shapely

import roadstyle as rs

DATA = Path(__file__).resolve().parent / "data"
BOX = (7.4205, 43.7360, 7.4265, 43.7410)        # lon / lat: Monte Carlo, about 480 m x 550 m

def color_table(roads):
    """Every third road: one of three colours, by its edge_id (the keys as text, as a JSON object has them)."""
    cols = ["#e41a1c", "#377eb8", "#4daf4a"]
    return {str(e): cols[i % 3] for i, e in enumerate(roads["edge_id"]) if i % 3 == 0}

CASES = {
    "plain": lambda r: {},
    "numeric": lambda r: {"color_by": "lanes", "cmap": "YlOrRd", "vmin": 1, "vmax": 4},
    "numeric_width": lambda r: {"color_by": "lanes", "cmap": "viridis", "width_by": [1.0, 6.0]},
    "categorical": lambda r: {"color_by": "access", "colors": {"private": "#d62728", "destination": "#ff7f0e", "no": "#7f7f7f"}},
    "color_table": lambda r: {"color_table": color_table(r)},
    "color_options": lambda r: {"color_options": {"class": {}, "lanes": {"color_by": "lanes", "cmap": "Blues", "vmin": 1, "vmax": 3},
                                                  "access": {"color_by": "access", "colors": {"private": "#d62728"}, "missing": "self"}},
                                "color_active": "lanes"},
    "no_legend": lambda r: {"color_by": "lanes", "cmap": "magma", "legend": False},
}

def write_cmaps():
    import os

    import branca
    import branca.colormap as bcm
    import matplotlib
    from matplotlib import colors as mcolors

    root = os.path.dirname(bcm.__file__)
    schemes = json.loads(Path(root, "_schemes.json").read_text())
    css = json.loads(Path(root, "_cnames.json").read_text())
    mpl = {n: [mcolors.to_hex(matplotlib.colormaps[n](i / 8.0)) for i in range(9)] for n in sorted(matplotlib.colormaps)}
    out = {"versions": {"branca": branca.__version__, "matplotlib": matplotlib.__version__}, "branca": schemes, "css": css, "matplotlib": mpl}
    Path(__file__).resolve().parent.parent.joinpath("src", "cmaps.json").write_text(json.dumps(out, separators=(",", ":")))

def main():
    write_cmaps()
    look = json.loads((DATA / "look.json").read_text())
    t = pq.read_table(DATA / "monaco" / "roads.parquet")     # plain Parquet, the geometry as WKB (as the worker's SQL writes it)
    b = shapely.bounds(shapely.from_wkb(t.column("geometry").to_pylist()))
    inside = (b[:, 0] >= BOX[0]) & (b[:, 2] <= BOX[2]) & (b[:, 1] >= BOX[1]) & (b[:, 3] <= BOX[3])
    out = DATA / "monaco_part"
    pq.write_table(t.filter(pa.array(inside)), out / "roads.parquet", compression="snappy")
    df = pq.read_table(out / "roads.parquet").to_pandas(integer_object_nulls=True)     # what the Rust test reads (integers stay integers)
    part = gpd.GeoDataFrame(df.drop(columns="geometry"), geometry=shapely.from_wkb(df["geometry"]), crs="EPSG:4326")
    kw = {**look["args"], "arrows": True, "labels": True}      # the engine always makes the names and arrows
    for name, opts in CASES.items():
        o = opts(part)
        style = rs.export_inline(part, palette=look["palette"], settings=look["settings"], **kw, **o)
        page = rs.render_edges(part, backend="web", palette=look["palette"], settings=look["settings"], **kw, **o)
        html = page if isinstance(page, str) else getattr(page, "html", None) or page.data
        meta = json.loads(re.search(r"const COLOR_OPTIONS = (.*?);\n", html).group(1))
        (out / f"{name}.json.gz").write_bytes(gzip.compress(json.dumps({"args": o, "style": style, "color_options": meta},
                                                                       separators=(",", ":")).encode(), 9, mtime=0))
        feats = style["sources"]["roads"]["data"]["features"]
        print(f"{name:14s} {len(feats)} roads, {len(style['layers'])} layers, color options {[m['name'] for m in meta]}, "
              f"{(out / f'{name}.json.gz').stat().st_size // 1000} KB")

if __name__ == "__main__":
    main()
