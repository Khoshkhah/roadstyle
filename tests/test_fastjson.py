"""fc_dict must be indistinguishable from json.loads(gdf.to_json()) — the contract every
backend consumer (bake_props, _mark_lvl, build_pmtiles, the spec) was written against."""
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Point, Polygon

from roadstyle import fastjson
from roadstyle.fastjson import fc_dict

duckdb = pytest.importorskip("duckdb")


def _tricky_gdf():
    """Every dtype corner the real networks carry, plus hostile names."""
    g = gpd.GeoDataFrame({
        "edge_id": np.array([733914796050831227, -487532126140856100, 5], dtype="int64"),
        "name": ["Söderledstunneln", None, float("nan")],
        "length_m": np.array([94.2, 0.1, float("nan")], dtype="float32"),
        "oneway": [True, False, True],
        "lanes": pd.array([2, None, 3], dtype="Int64"),
        "refs": [[1, 2, 3], [4], []],
        "it's": ['quote"d', "x", "y"],
    }, geometry=[LineString([(18.0712345678901, 59.3141592653589), (18.08, 59.32)]),
                 LineString([(0, 0), (1, 1)]), LineString([(2, 2), (3, 3)])], crs=4326)
    g.index = [7, "x", 9]                       # non-range, mixed-type index → feature ids
    return g


def test_matches_geopandas_on_tricky_frame():
    g = _tricky_gdf()
    assert fc_dict(g) == json.loads(g.to_json())


def test_matches_on_full_precision_coordinates():
    rng = np.random.default_rng(11)
    pts = rng.uniform(-180, 180, (300, 4))      # full-precision doubles, no rounding anywhere
    g = gpd.GeoDataFrame({"v": rng.normal(size=300)},
                         geometry=[LineString([(a, b / 2), (c, d / 2)]) for a, b, c, d in pts],
                         crs=4326)
    assert fc_dict(g) == json.loads(g.to_json())


def test_matches_on_mixed_geometry_types():
    g = gpd.GeoDataFrame({"k": ["ln", "pt", "pg"]}, geometry=[
        LineString([(0, 0), (1, 1)]), Point(2.5, 3.5),
        Polygon([(0, 0), (1, 0), (1, 1), (0, 0)])], crs=4326)
    assert fc_dict(g) == json.loads(g.to_json())


def test_empty_and_missing_geometries_emit_null():
    """GeoPandas emits "geometry": null for EMPTY and missing geometries alike — duckmap
    building layers simplify some polygons to empty, which is how this was caught."""
    g = gpd.GeoDataFrame({"k": ["empty", "none", "ok"]},
                         geometry=[Polygon(), None, Point(1, 2)], crs=4326)
    new = fc_dict(g)
    assert new == json.loads(g.to_json())
    assert new["features"][0]["geometry"] is None
    assert new["features"][1]["geometry"] is None


def test_empty_frame():
    g = _tricky_gdf().iloc[0:0]
    assert fc_dict(g) == json.loads(g.to_json())


def test_feature_order_and_ids_preserved():
    g = _tricky_gdf()
    ids = [f["id"] for f in fc_dict(g)["features"]]
    assert ids == ["7", "x", "9"]


def test_fallback_on_fast_path_failure(monkeypatch):
    """A broken fast path must degrade to GeoPandas with a warning, never break a render."""
    def boom(gdf):
        raise RuntimeError("no")
    monkeypatch.setattr(fastjson, "_duckdb_fc", boom)
    g = _tricky_gdf()
    with pytest.warns(RuntimeWarning, match="fell back"):
        assert fc_dict(g) == json.loads(g.to_json())


def test_reserved_column_collision_falls_back():
    g = _tricky_gdf()
    g["__rs_fc_wkb"] = "boom"
    with pytest.warns(RuntimeWarning):
        assert fc_dict(g) == json.loads(g.to_json())
