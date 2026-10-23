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
    # the other keywords of the style and the page metadata
    "labels_off": {"labels": False},
    "arrows_off": {"arrows": False},
    "road_fill_off": {"road_fill": False},
    "road_popup": {"road_popup": ["name", "highway"]},
    "popup_off": {"road_popup": False},
    "popup_mode": {"popup_mode": "panel"},
    "road_tooltip": {"road_tooltip": ["name"]},
    "hover_delay": {"hover_delay_ms": 450},
    "data_maxzoom": {"data_maxzoom": 16},
    "data_tolerance": {"data_tolerance": 0.5},
    "camera": {"pitch": 30, "bearing": 20, "max_pitch": 70},
    "select_color": {"select_color": "#ff00ff"},
    "hover_color": {"hover_color": "#00ff00"},
    "view_3d_off": {"view_3d": False},
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

    py = rs.export_inline(part, engine="python", **{**keywords, **options(case, part)})
    ru = rs.export_inline(part, engine="rust", **{**keywords, **options(case, part)})
    assert [lyr["id"] for lyr in ru["layers"]] == [lyr["id"] for lyr in py["layers"]]
    assert diff(ru, py) == []


# render's level step: the keywords name no level columns, so both engines compute the positions (compute_levels, method="solve")
_LEVEL_COLS = ["casing_start", "casing_level", "casing_end", "fill_level", "head_start_m", "head_end_m", "cap_start", "cap_end"]
_LEVEL_ARGS = ["casing_start_col", "casing_level_col", "casing_end_col", "fill_level_col", "head_start_m_col", "head_end_m_col",
               "cap_start_col", "cap_end_col"]


def test_export_inline_levels_computed(part, keywords):
    from compare_engines import diff

    roads = part.drop(columns=[c for c in _LEVEL_COLS if c in part.columns])
    kw = {k: v for k, v in keywords.items() if k not in _LEVEL_ARGS}
    py = rs.export_inline(roads, engine="python", **kw)
    ru = rs.export_inline(roads, engine="rust", **kw)
    assert diff(ru, py) == []


# the column keywords: the same roads with other column names give the same style, with those names
_RENAME = {"highway": "fclass", "tunnel": "tun", "bridge": "brg", "layer": "lyr", "edge_id": "eid"}


@pytest.mark.parametrize("levels", ["given", "computed"])
def test_export_inline_column_names(part, keywords, levels):
    from compare_engines import diff

    roads, kw = part, dict(keywords)
    if levels == "computed":
        roads = part.drop(columns=[c for c in _LEVEL_COLS if c in part.columns])
        kw = {k: v for k, v in kw.items() if k not in _LEVEL_ARGS}
    roads = roads.rename(columns=_RENAME)
    kw.update(highway_col="fclass", tunnel_col="tun", bridge_col="brg", layer_col="lyr", edge_id_col="eid")
    py = rs.export_inline(roads, engine="python", **kw)
    ru = rs.export_inline(roads, engine="rust", **kw)
    assert diff(ru, py) == []


def test_export_inline_other_highway_column(part, keywords):
    """A column named highway that is not the class column (highway_col names another one) stays data, as in Python."""
    from compare_engines import diff

    roads = part.rename(columns={"highway": "fclass"})
    roads["highway"] = "other"
    kw = {**keywords, "highway_col": "fclass"}
    py = rs.export_inline(roads, engine="python", **kw)
    ru = rs.export_inline(roads, engine="rust", **kw)
    assert diff(ru, py) == []


def test_engine_names(monkeypatch):
    assert _engine.engine(None) == "python"
    monkeypatch.setenv("ROADSTYLE_ENGINE", "rust")
    assert _engine.engine(None) == "rust"
    with pytest.raises(ValueError, match="use one of"):
        _engine.engine("go")


