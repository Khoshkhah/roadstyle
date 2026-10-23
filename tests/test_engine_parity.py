"""The two engines give the same output (docs/design/rust_library.md, phase P5): export_inline with engine="python" and with
engine="rust", for the cases of the Rust golden tests (rust/roadstyle-rs/tests/make_goldens.py): a part of Monaco, with the options of
data-driven colour and width. Skipped when the Rust extension is not built (python rust/roadstyle-py/build.py)."""
import json
import sys
from pathlib import Path

import pytest

import roadstyle as rs
from roadstyle import _engine

pytestmark = pytest.mark.skipif(not _engine.available(), reason="the Rust extension roadstyle._rust is not built")

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "rust" / "roadstyle-rs" / "tests" / "data"
sys.path.insert(0, str(ROOT / "rust" / "roadstyle-py"))

CASES = {
    "plain": {},
    "numeric": {"color_by": "lanes", "cmap": "YlOrRd", "vmin": 1, "vmax": 4},
    "numeric_width": {"color_by": "lanes", "cmap": "viridis", "width_by": [1.0, 6.0]},
    "categorical": {"color_by": "access", "colors": {"private": "#d62728", "destination": "#ff7f0e", "no": "#7f7f7f"}},
    "color_options": {"color_options": {"class": {}, "lanes": {"color_by": "lanes", "cmap": "Blues", "vmin": 1, "vmax": 3},
                                        "access": {"color_by": "access", "colors": {"private": "#d62728"}, "missing": "self"}},
                      "color_active": "lanes"},
    "no_legend": {"color_by": "lanes", "cmap": "magma", "legend": False},
    "color_table": "every third road: one of three colours, by its edge_id",   # made from the roads (make_goldens.py: color_table)
}


def options(case, roads):
    """The keywords of a case; color_table is made from the roads, as in make_goldens.py."""
    if case == "color_table":
        cols = ["#e41a1c", "#377eb8", "#4daf4a"]
        return {"color_table": {str(e): cols[i % 3] for i, e in enumerate(roads["edge_id"]) if i % 3 == 0}}
    return CASES[case]


@pytest.fixture(scope="module")
def part():
    """The roads of make_goldens.py, read the same way (the integers stay integers)."""
    import geopandas as gpd
    import pyarrow.parquet as pq
    import shapely

    df = pq.read_table(DATA / "monaco_part" / "roads.parquet").to_pandas(integer_object_nulls=True)
    return gpd.GeoDataFrame(df.drop(columns="geometry"), geometry=shapely.from_wkb(df["geometry"]), crs="EPSG:4326")


@pytest.fixture(scope="module")
def keywords():
    look = json.loads((DATA / "look.json").read_text())
    return {"palette": look["palette"], "settings": look["settings"], **look["args"], "arrows": True, "labels": True}


@pytest.mark.parametrize("case", sorted(CASES))
def test_export_inline_same_style(part, keywords, case):
    from compare_engines import diff     # the first differences only: pytest's own diff of two styles of several MB is too slow

    py = rs.export_inline(part, engine="python", **keywords, **options(case, part))
    ru = rs.export_inline(part, engine="rust", **keywords, **options(case, part))
    assert [lyr["id"] for lyr in ru["layers"]] == [lyr["id"] for lyr in py["layers"]]
    assert diff(ru, py) == []


def test_engine_names(monkeypatch):
    assert _engine.engine(None) == "python"
    monkeypatch.setenv("ROADSTYLE_ENGINE", "rust")
    assert _engine.engine(None) == "rust"
    with pytest.raises(ValueError, match="use one of"):
        _engine.engine("go")


def test_rust_needs_the_levels(part, keywords):
    with pytest.raises(ValueError, match="no column casing_level"):
        rs.export_inline(part.drop(columns=["casing_level"]), engine="rust", **keywords)
